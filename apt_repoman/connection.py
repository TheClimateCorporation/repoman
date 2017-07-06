
# stdlib imports
import logging
import time

# pypi imports
from boto3 import Session


LOG = logging.getLogger(__name__)


class Connection(object):

    def __init__(self, role_arn='', profile_name='', region=None):
        self._log = LOG or logging.getLogger(__name__)
        self.role_arn = role_arn
        self.profile_name = profile_name
        self.region = region
        self._s3 = None
        self._sdb = None
        self._sts = None
        self._iam = None
        self._sns = None
        self._session = None
        self._caller_id = None

    @property
    def session(self):
        '''Set our object's self._session attribute to a boto3
        session object.  If profile_name is set, use it to pull a
        specific credentials profile from ~/.aws/credentials,
        otherwise use the default credentials path.
        If role_arn is set, use the first session object to
        assume the role, and then overwrite self._session with
        a new session object created using the role credentials.'''
        if self._session is None:
            self._session = self.get_session()
        return self._session

    @property
    def s3(self):
        if self._s3 is None:
            self._s3 = self.get_resource('s3')
        return self._s3

    @property
    def sdb(self):
        if self._sdb is None:
            self._sdb = self.get_client('sdb')
        return self._sdb

    @property
    def sts(self):
        if self._sts is None:
            self._sts = self.get_client('sts')
        return self._sts

    @property
    def iam(self):
        if self._iam is None:
            self._iam = self.get_client('iam')
        return self._iam

    @property
    def sns(self):
        if self._sns is None:
            self._sns = self.get_client('sns')
        return self._sns

    @property
    def caller_id(self):
        if self._caller_id is None:
            self._caller_id = self.sts.get_caller_identity()['Arn']
        return self._caller_id

    def get_session(self):
        if self.profile_name:
            self._log.info(
                'using AWS credential profile %s', self.profile_name)
            try:
                kwargs = {'profile_name': self.profile_name}
                if self.region:
                    kwargs['region_name'] = self.region
                session = Session(**kwargs)
            except Exception as ex:
                self._log.fatal(
                    'Could not connect to AWS using profile %s: %s',
                    self.profile_name, ex)
                raise
        else:
            self._log.debug(
                'getting an AWS session with the default provider')
            kwargs = {}
            if self.region:
                kwargs['region_name'] = self.region
            session = Session(**kwargs)
        if self.role_arn:
            self._log.info(
                'attempting to assume STS self.role %s', self.role_arn)
            try:
                self.role_creds = session.client('sts').assume_role(
                    RoleArn=self.role_arn,
                    RoleSessionName='repoman-%s' % time.time(),
                    DurationSeconds=3600)['Credentials']
            except Exception as ex:
                self._log.fatal(
                    'Could not assume self.role %s: %s',
                    self.role_arn, ex)
                raise
            kwargs = {
                'aws_access_key_id': self.role_creds['AccessKeyId'],
                'aws_secret_access_key': self.role_creds['SecretAccessKey'],
                'aws_session_token': self.role_creds['SessionToken']}
            if self.region:
                kwargs['region_name'] = self.region
            session = Session(**kwargs)
        return session

    def get_client(self, service_name):
        return self.session.client(service_name)

    def get_resource(self, service_name):
        return self.session.resource(service_name)
