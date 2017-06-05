
# stdlib imports
import logging
import mimetypes
import os

# pypi imports
from botocore.exceptions import ClientError

# internal imports
from apt_repoman.connection import Connection

DEFAULT_ACL = 'bucket-owner-full-control'


LOG = logging.getLogger(__name__)


class RepoError(Exception):
    pass


class BucketNotFoundError(RepoError):
    pass


class KeyNotFoundError(RepoError):
    pass


class KeyExistsError(RepoError):
    pass


class FileNotFoundError(RepoError):
    pass


class Repo(object):
    """Object encapsulating actions on the S3 arm of a repoman repository."""
    def __init__(self, bucket_name, role_arn=None, connection=None):
        self.bucket_name = bucket_name
        self.role_arn = role_arn
        self._log = LOG or logging.getLogger(__name__)
        self._connection = connection or None
        self._s3 = None
        self._bucket = None

    @property
    def connection(self):
        if self._connection is None:
            self._connection = Connection(logger=self._log,
                                          role_arn=self.role_arn)
        return self._connection

    @property
    def s3(self):
        if not self._s3:
            self._s3 = self.connection.s3
        return self._s3

    @property
    def bucket(self):
        if not self._bucket:
            self._bucket = self.s3.Bucket(self.bucket_name)
            if not self._bucket_exists(self._bucket):
                raise BucketNotFoundError(
                    's3://%s/ does not exist or is not visible to me' %
                    self.bucket_name)
        return self._bucket

    def initialize(self, bucket_acl='private', region=None,
                   enable_website=False):
        try:
            self.bucket
            self._log.warning('bucket s3://%s already exists!',
                              self.bucket_name)
        except BucketNotFoundError:
            self._log.warning('Creating s3 bucket: %s', self.bucket_name)
            if enable_website:
                self._log.warning('Enabling the public-read ACL on s3://%s '
                                  'because you have enabled S3 website '
                                  'hosting.', self.bucket_name)
                bucket_acl = 'public-read'
            args = {'Bucket': self.bucket_name,
                    'ACL': bucket_acl}
            if region:
                args['CreateBucketConfiguration'] = {
                    'LocationConstraint': region}
            else:
                self._log.warning('no region specified; creating s3 bucket '
                                  'in US/Standard (us-east-1) region')
            try:
                bucket = self.s3.create_bucket(**args)
                if enable_website:
                    self._log.warning(
                        'Enabling a public website for your bucket')
                    website = bucket.Website()
                    website.put(
                        WebsiteConfiguration={
                            'ErrorDocument': {'Key': 'errors/404.html'},
                            'IndexDocument': {'Suffix': 'index.html'}})
                    policy = bucket.Policy()
                    policy.put(Policy='{"Version":"2012-10-17","Statement":['
                               '{"Effect":"Allow","Principal":"*",'
                               '"Action":["s3:GetObject"],'
                               '"Resource":["arn:aws:s3:::%s/*"]}]}' %
                               self.bucket_name)
                    self._log.info('Bucket website created: '
                                   'http://%s.s3-website-%s.amazonaws.com/',
                                   self.bucket_name, region or 'us-east-1')
                return bucket
            except ClientError as ex:
                if ex.response['Error']['Code'] == 'BucketAlreadyExists':
                    self._log.fatal(
                        'Bucket name "%s" appears to be in use by '
                        'another AWS account. We recommend using DNS '
                        'or classpath-style bucket names: '
                        '"apt.example.com" or "com.example.apt"',
                        self.bucket_name)
                else:
                    self._log.fatal(
                        'Failed to create S3 bucket %s: %s',
                        self.bucket_name, ex.response['Error']['Message'])
                raise
            except Exception as ex:
                self._log.fatal('Failed to create S3 bucket %s: %s',
                                self.bucket_name, ex)
                raise

    def _get_key(self, key_name, s3_obj=None):
        if s3_obj is None:
            return self.s3.Object(self.bucket_name, key_name)
        else:
            return s3_obj(self.bucket_name, key_name)

    def _bucket_exists(self, bucket_obj):
        try:
            bucket_obj.load()
            self._log.debug('s3//%s/ exists!', self.bucket_name)
        except ClientError as ex:
            self._log.error(
                's3//%s/ does not exist or is not visible to me: %s',
                self.bucket_name, ex)
            return False
        return True

    def _key_exists(self, key_obj):
        try:
            metadata = key_obj.metadata
            self._log.debug('key "s3://%s/%s" exists: %s',
                            key_obj.bucket_name, key_obj.key, metadata)
        except ClientError as ex:
            self._log.debug('key "s3://%s/%s" does not exist: %s',
                            key_obj.bucket_name, key_obj.key, ex)
            return False
        return True

    def _set_key_from_file(self, key_name, file_name, acl=DEFAULT_ACL,
                           overwrite=False):
        if not os.path.isfile(file_name):
            raise FileNotFoundError('"%s" is not a file', file_name)
        k = self._get_key(key_name)
        if self._key_exists(k) and not overwrite:
            raise KeyExistsError(
                's3://%s/%s" already exists' % (k.bucket_name, k.key))
        extra_args = {'ACL': acl}
        content_type, encoding = mimetypes.guess_type(file_name)
        if content_type:
            extra_args['ContentType'] = content_type
        if encoding:
            extra_args['ContentEncoding'] = encoding
        self._log.debug('uploading file "%s" with args %s to s3://%s/%s',
                        file_name, extra_args, k.bucket_name, k.key)
        result = k.upload_file(Filename=file_name, ExtraArgs=extra_args)
        self._log.debug('uploaded file "%s" to s3://%s/%s: %s',
                        file_name, k.bucket_name, k.key, result)
        k.reload()
        return k

    def copy_key(self, old_path, new_path, overwrite=False):
        old_key = self._get_key(old_path)
        new_key = self._get_key(new_path)
        if not self._key_exists(old_key):
            raise KeyNotFoundError(
                's3://%s/%s does not exist' % (
                    old_key.bucket_name, old_key.key))
        if not overwrite:
            if self._key_exists(new_key):
                raise KeyExistsError(
                    's3://%s/%s exists and overwrite=False' % (
                        new_key.bucket_name, new_key.key))
        self._log.debug(
            'copying s3://%s/%s to s3://%s/%s', old_key.bucket_name,
            old_key.key, new_key.bucket_name, new_key.key)
        new_key.copy(CopySource={'Bucket': old_key.bucket_name,
                                 'Key': old_key.key})
        new_key.reload()
        return new_key

    def _get_pkg_pathname(self, pkg, filename, dist):
        """Return the relative S3 path name for our package key.
        :param pkg string
        :param filename string
        :param dist string
        """
        return os.path.join('pool', dist, pkg[0], pkg, filename)

    def set_key_from_string(self, key_name, contents,
                            overwrite=True, acl=DEFAULT_ACL,
                            new_sess=True):
        key_url = 's3://{0}/{1}'.format(self.bucket_name, key_name)
        self._log.debug(
            'setting contents of S3 key %s to "%s"', key_url, contents)
        self._log.info('setting contents of %s', key_url)
        k = self._get_key(key_name)
        if not overwrite and self._key_exists(k):
            raise KeyExistsError('%s" already exists' % key_url)
        result = k.put(Body=contents)
        self._log.debug('set contents of %s: %s', key_url,
                        result['ResponseMetadata']['HTTPStatusCode'])
        k.reload()
        return k

    def add_package(self, pkg, dists=[], overwrite=False):
        pkg_name = pkg.get_header('package')
        pkg_file = os.path.basename(pkg.filename)
        for dist in dists:
            key_name = self._get_pkg_pathname(pkg_name, pkg_file, dist)
            try:
                self._log.info('Attempting to upload s3://%s/%s',
                               self.bucket_name, key_name)
                self._set_key_from_file(key_name, pkg.filename,
                                        overwrite=overwrite)
            except KeyExistsError:
                self._log.error(
                    'Key s3://%s/%s already exists, you probably meant '
                    'to copy it within the repo.',
                    self.bucket_name, key_name)
                raise

    def add_source(self, dsc, dists=[], overwrite=False):
        """Iterate over the files proprty of a pydpkg.Dsc object,
        derive the correct S3 pathname for each file and upload
        the file to S3.

        :param dsc: pydpkg.Dsc
        :param dists: list of strings
        :param overwrite: bool
        :returns None
        """
        # blow up immediately if the Dsc is not fully valid:
        dsc.validate()
        name = dsc.source
        for dist in dists:
            upload = dsc.source_files
            self._log.debug('files to upload: %s', upload)
            for src_file in upload:
                key_name = self._get_pkg_pathname(
                    name, os.path.basename(src_file), dist)
                try:
                    self._log.info('Attempting to upload s3://%s/%s',
                                   self.bucket_name, key_name)
                    self._set_key_from_file(key_name, src_file,
                                            overwrite=overwrite)
                except KeyExistsError:
                    self._log.error(
                        'Key s3://%s/%s already exists, you probably meant '
                        'to copy it within the repo.',
                        self.bucket_name, key_name)
                    raise
