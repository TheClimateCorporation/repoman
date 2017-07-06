
# stdlib imports
import hashlib
import itertools
import json
import logging
import os
import time

from collections import Sequence, Set, OrderedDict, defaultdict
from copy import copy, deepcopy
from gzip import GzipFile
from io import BytesIO
from six import string_types, iteritems

# internal imports
from apt_repoman.connection import Connection
from apt_repoman.repo import KeyExistsError
from apt_repoman import utils

# pypi imports
from botocore.exceptions import ClientError
from pgpy import PGPKeyring
from pydpkg import Dpkg


LOG = logging.getLogger(__name__)


class RepodbError(Exception):
    pass


class InvalidAttributesError(RepodbError):
    pass


class InvalidArchitectureError(RepodbError):
    pass


class InvalidDistributionError(RepodbError):
    pass


class InvalidComponentError(RepodbError):
    pass


class InvalidCopyActionError(RepodbError):
    pass


class ItemExistsError(RepodbError):
    pass


class KeyringNotFoundError(RepodbError):
    pass


class Repodb(object):

    def __init__(self, domain_name, role_arn=None, connection=None):
        self.domain_name = domain_name
        self.role_arn = role_arn
        self._log = LOG or logging.getLogger(__name__)
        self._connection = connection or None
        self._sdb = None
        self._sns = None
        self._meta = {}
        self._domain_exists = None
        self._topic_exists = None
        self._topic_arn = None

    @property
    def connection(self):
        if self._connection is None:
            self._connection = Connection(role_arn=self.role_arn)
        return self._connection

    @property
    def sdb(self):
        if not self._sdb:
            self._sdb = self.connection.sdb
        return self._sdb

    @property
    def sns(self):
        if not self._sns:
            self._sns = self.connection.sns
        return self._sns

    @property
    def meta(self):
        if not self._meta:
            try:
                self._meta = self._get_attributes('meta', always_list=True)
            except KeyError:
                self._log.warning(
                    'No metadata found in simpledb domain %s, '
                    'did you forget to run "repoman setup"?', self.domain_name)
                self._meta = {}
        return self._meta

    @property
    def domain_exists(self):
        if isinstance(self._domain_exists, type(None)):
            domains = []
            paginator = self.sdb.get_paginator('list_domains')
            for page in paginator.paginate():
                domains.extend(page.get('DomainNames', []))
            self._domain_exists = self.domain_name in domains
        return self._domain_exists

    @property
    def topic_arn(self):
        # the SNS API is horrible: there is no way of verifying that a topic
        # exists without iterating through up to 100,000 (!) entries in the
        # output of sns.list_topics(). The recommended means of either
        # verifying an ARN or getting the ARN by the name is...this. :(
        if self._topic_arn is None:
            try:
                if not self.topic_name:
                    return self._topic_arn  # if unset, logging is off
                # be nice and accept either a name or a full ARN here
                elif self.topic_name.startswith('arn:aws:sns:'):
                    self._topic_arn = self.sns.create_topic(
                        Name=self.topic_name.split(':')[5])['TopicArn']
                else:
                    self._topic_arn = self.sns.create_topic(
                        Name=self.topic_name)['TopicArn']
            except KeyError:
                # someone put something unparseable into the topic config
                self._log.warning(
                    'Configured SNS topic "%s" is not parseable as either '
                    'a topic name or a topic ARN; logging is disabled.',
                    self.topic_name)
            except ClientError as ex:
                self._log.warning(
                    'Could not fetch/create SNS topic "%s"; '
                    'logging disabled: %s', self.topic_name, ex)
        return self._topic_arn

    @property
    def archs(self):
        archs = self.meta.get('archs', [])
        # the 'all' architecture is special
        if 'all' not in archs:
            archs.append('all')
        # ditto
        if 'source' not in archs:
            archs.append('source')
        return archs

    @property
    def dists(self):
        return self.meta.get('dists', [])

    @property
    def comps(self):
        return self.meta.get('comps', [])

    @property
    def topic_name(self):
        # this may be unset and that is legit
        try:
            return self.meta.get('topic_name')[0]
        except (IndexError, AttributeError, TypeError):
            return None

    @property
    def origin(self):
        # this may be unset and that is legit
        try:
            return self.meta.get('origin')[0]
        except (IndexError, AttributeError, TypeError):
            return 'repoman'

    @property
    def label(self):
        # this may be unset and that is legit
        try:
            return self.meta.get('label')[0]
        except (IndexError, AttributeError, TypeError):
            return 'repoman'

    def _create_domain(self):
        if self.domain_exists:
            self._log.warning('Simpledb domain "%s" already exists',
                              self.domain_name)
            return None
        try:
            self._log.warning('Creating simpledb domain %s', self.domain_name)
            return self.sdb.create_domain(DomainName=self.domain_name)
        except Exception as ex:
            self._log.fatal('Could not create simpledb domain "%s": %s',
                            self.domain_name, ex)
            raise

    def _create_meta(self, dists=[], comps=[], archs=[],
                     topic_name='', origin='', label='',
                     test_data=''):
        notifications = []
        while 'all' in archs:
            self._log.warning('You cannot add the "all" architecture; like '
                              'the Vorlons it has always been here.')
            archs.remove('all')
        while 'source' in archs:
            self._log.warning('You cannot add the "source" architecture; like '
                              'the Vorlons it has always been here.')
            archs.remove('source')
        for key in ('dists', 'comps', 'archs'):
            targets = locals()[key]
            if key not in self.meta:
                # if not present, add
                self._meta[key] = targets
            else:
                # if present, merge
                if isinstance(self._meta[key], string_types):
                    self._meta[key] = [self._meta[key]]
                existing = set(self._meta[key])
                new = set(targets)
                self._meta[key] = sorted(existing.union(new))
            for target in targets:
                notifications.append(
                    {'action': 'add', 'type': key, 'name': target,
                     'caller': self.connection.caller_id})
        if topic_name:
            self._log.debug('setting up sns notifications: %s', topic_name)
            self._meta['topic_name'] = [topic_name]
            notifications.append(
                {'action': 'add', 'type': 'sns_topic',
                 'name': topic_name, 'caller': self.connection.caller_id})
        if origin:
            self._log.debug('setting repo origin: %s', origin)
            self._meta['origin'] = [origin]
            notifications.append(
                {'action': 'add', 'type': 'origin',
                 'name': origin, 'caller': self.connection.caller_id})
        if label:
            self._log.debug('setting repo label: %s', label)
            self._meta['label'] = [label]
            notifications.append(
                {'action': 'add', 'type': 'label',
                 'name': label, 'caller': self.connection.caller_id})
        if topic_name:
            self._log.debug('setting up sns notifications: %s', topic_name)
            self._meta['topic_name'] = [topic_name]
            notifications.append(
                {'action': 'add', 'type': 'sns_topic',
                 'name': topic_name, 'caller': self.connection.caller_id})
        if test_data:
            self._meta['test_data'] = test_data
        self._log.debug('updated meta: %s', self._meta)
        response = self._put_attributes('meta', self.meta, replace=True)
        if response:
            self._send_notifications(notifications)
        return response

    def _delete_meta(self, dists=[], comps=[], archs=[],
                     topic_name=False, origin=False, label=False,
                     test_data=False):
        notifications = []
        for key in ('archs', 'dists', 'comps'):
            targets = locals()[key]
            for target in targets:
                current = getattr(self, key)
                if target not in current:
                    self._log.warning(
                        'Repo %s do not include %s; cannot delete',
                        key, target)
                    continue
                current.pop(current.index(target))
                self.meta[key] = current
                notifications.append(
                    {'action': 'delete', 'type': key,
                     'name': target, 'caller': self.connection.caller_id})
        if topic_name and 'topic_name' in self.meta:
            self._log.debug('Disabling sns notifications')
            self.meta['topic_name'] = ''
            notifications.append(
                {'action': 'delete', 'type': 'sns_topic',
                 'name': self.topic_name,
                 'caller': self.connection.caller_id})
        if origin and 'origin' in self.meta:
            self._log.debug('Disabling sns notifications')
            self.meta['origin'] = ''
            notifications.append(
                {'action': 'delete', 'type': 'origin',
                 'name': self.origin,
                 'caller': self.connection.caller_id})
        if label and 'label' in self.meta:
            self._log.debug('Disabling sns notifications')
            self.meta['label'] = ''
            notifications.append(
                {'action': 'delete', 'type': 'label',
                 'name': self.label,
                 'caller': self.connection.caller_id})
        if test_data and 'test_data' in self.meta:
            self.meta['test_data'] = ''
        response = self._put_attributes('meta', self.meta, replace=True)
        if response:
            self._send_notifications(notifications)
        return response

    def _send_notifications(self, notifications):
        if not self.topic_arn:
            return None
        for alert in notifications:
            self.sns.publish(
                TopicArn=self.topic_arn,
                Message=json.dumps(alert),
                Subject='Repoman notification')

    def _respool_attributes(self, attributes, replace=False):
        """ Transform a python dictionary in the form
        {str: str} or {str: [str, str]} into a list of
        dicts in the form [{'Name': str, 'Value': str}, ...]

        If the replace argument is not none, update each of the
        response dicts to include 'Replace'=replace.

        :param attributes: list
        :param replace: trinary True/False/None
        :returns list
        """
        response = []
        # simpledb doesn't care about order but our unit tests do :(
        for key in sorted(attributes.keys()):
            val = attributes[key]
            if not isinstance(key, string_types):
                raise InvalidAttributesError(
                    'simpledb attribute names must be strings: %s:%s' %
                    (type(key), key))
            if isinstance(val, string_types):
                entry = {'Name': key, 'Value': val}
                if replace is not None:
                    entry['Replace'] = replace
                response.append(entry)
            # anything that quacks like a list/tuple, we can handle
            elif isinstance(val, (Sequence, Set)):
                for item in val:
                    if isinstance(item, string_types):
                        entry = {'Name': key, 'Value': item}
                        if replace is not None:
                            entry['Replace'] = replace
                        response.append(entry)
                    else:
                        raise InvalidAttributesError(
                            'simpledb attribute values must be strings: %s:%s'
                            % (type(item), item))
            else:
                raise InvalidAttributesError(
                    'I can only convert string or list-like things '
                    'into simpledb attributes: %s:%s', (type(val), val))
        return response

    def _unspool_attributes(self, attributes, always_list=False):
        """ Transform output of boto3.sdb.get_attributes into
            a python dictionary in the form {name: [val, val...]}
        :param attributes: list of {'Name': str, 'Value': str} dicts
        :type attributes: list
        :return: dictionary of key=val[,val].. pairs
        :rtype: dict
        """
        response = {}
        for item in attributes:
            k = item['Name']
            v = item['Value']
            if k in response:
                if type(response[k]) is list:
                    response[k].append(v)
                else:
                    response[k] = [response[k]]
                    response[k].append(v)
            else:
                if always_list:
                    response[k] = [v]
                else:
                    response[k] = v
        return response

    def _get_attributes(self, key, attribute_names=[], consistent_read=True,
                        always_list=False):
        try:
            attributes = self.sdb.get_attributes(
                DomainName=self.domain_name,
                ItemName=key,
                AttributeNames=attribute_names,
                ConsistentRead=consistent_read)['Attributes']
        except Exception as ex:
            self._log.debug(
                'Could not read attributes for item %s: %s', key, ex)
            raise
        return self._unspool_attributes(attributes, always_list)

    def _item_exists(self, key, attribute_names=[]):
        try:
            return self._get_attributes(key, attribute_names)
        except KeyError:
            return None

    def _put_attributes(self, key, attrs, replace=True):
        attributes = self._respool_attributes(attrs, replace)
        try:
            response = self.sdb.put_attributes(
                DomainName=self.domain_name,
                ItemName=key,
                Attributes=attributes)
        except Exception as ex:
            self._log.fatal('Could not update key %s: %s', key, ex)
            raise
        return response

    def _put_item(self, item, replace=True):
        """A convenient wrapper around _put_attributes() and
        _compute_keyname_from_item()"""
        keyname = self._compute_keyname_from_item(item)
        return self._put_attributes(keyname, item, replace)

    def _delete_item(self, item):
        key = self._compute_keyname_from_item(item)
        attrs = self._respool_attributes(item, replace=None)
        try:
            response = self.sdb.delete_attributes(
                DomainName=self.domain_name,
                ItemName=key,
                Attributes=attrs)
        except Exception as ex:
            self._log.fatal('Could not delete item %s: %s', key, ex)
            raise
        return response

    def _select(self, query, consistent_read=True):
        pag = self.sdb.get_paginator('select')
        for page in pag.paginate(
                SelectExpression=query,
                ConsistentRead=consistent_read):
            for item in page.get('Items', []):
                yield self._unspool_attributes(item['Attributes'])

    def _assemble_select_query(self, names=[], dists=[], comps=[], archs=[],
                               versions=[], name_wildcard=False):
        """Query the simpledb database for package items: this function
        assembles a simpledb select query as a string suitable for feeding
        to repodb._select()

        Options are filters: setting e.g. dists to ['jessie', 'xenial'] will
        only return packages in that distribution.  With no options set, this
        will return the entire database.

        :param names: list of package names (strings)
        :param dists: list of repository distributions (strings)
        :param comps: list of repository components (strings)
        :param archs: list of package architectures (strings)
        :param versions: list of package versions (strings)
        :returns: a generator object for a simpledb select() query
        :rtype: Generator
        """
        query = 'select * from `{0}` where `name` is not null'.format(
            self.domain_name)
        selectors = []
        tmpl = "every({0}) in ({1})"
        wild_tmpl = "`{0}` LIKE '{1}%'"
        if names:
            if name_wildcard:
                # Warning: you will verrrry quickly hit the statement
                # predicate limit here; simpledb does not support
                # `every(foo) LIKE ('bar%', 'baz%')`
                statement = ' or '.join(
                    [wild_tmpl.format('name', name) for name in names])
                selectors.append(' {0}'.format(statement))
            else:
                selectors.append(tmpl.format(
                    'name', ','.join(["'%s'" % x for x in names])))
        if dists:
            selectors.append(tmpl.format(
                'distribution', ','.join(["'%s'" % x for x in dists])))
        if comps:
            selectors.append(tmpl.format(
                'component', ','.join(["'%s'" % x for x in comps])))
        if archs:
            selectors.append(tmpl.format(
                'architecture', ','.join(["'%s'" % x for x in archs])))
        if versions:
            selectors.append(tmpl.format(
                'version', ','.join(["'%s'" % x for x in versions])))
        if selectors:
            query += ' and '
            query += ' and '.join(selectors)
        self._log.debug('query: %s', query)
        return query

    def _check_for_hash(self, key):
        if self._get_attributes(key):
            return True
        else:
            return False

    def _compute_keyname(self, name, version, dist, comp, arch):
        """ return a sha256 hex hash of the name+version+dist+comp
        to be used as a unique item key in SDB
        """
        source_str = name + version + dist + comp + arch
        return hashlib.sha256(source_str.encode('ascii')).hexdigest()

    def _compute_keyname_from_item(self, item):
        return self._compute_keyname(
            name=item['name'],
            version=item['version'],
            dist=item['distribution'],
            comp=item['component'],
            arch=item['architecture'])

    def _split_control_text(self, txt, max_elems=256):
        """Simpledb attribute txtues are capped at 1024 bytes, and
        debian control messages can easily be longer than that.
        Even better, control messages can contain unicode strings.

        So: split into a list of substrings, each of which could
        be up to 4 bytes long...
        """
        splits = OrderedDict()
        frags = [txt[i:i+max_elems] for i in range(0, len(txt), max_elems)]
        # pad each key name to the minimum necessary length
        padding = len(str(len(frags)))  # think about it :)
        for count, frag in enumerate(frags):
            splits['controltxt%s' % str(count).zfill(padding)] = frag
        return splits

    def _build_dist_release(self, dist, origin, comps=[], archs=[], date=None):
        self._log.debug('assembling release file for %s', dist)
        if not archs:
            # if you're looking at this and going "wtf?" don't worry,
            # it's not you, it's me. I made a terrible decision in 2011
            # and we all get to pay for it forever
            archs = copy(self.archs)
            archs.remove('all')
        # okay that's done, we can move on now. pretend it never happened.
        if not comps:
            comps = self.comps
        if not date:
            date = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())
        return (
            'Origin: {origin}\n'
            'Label: {origin}\n'
            'Codename: {dist}\n'
            'Acquire-By-Hash: no\n'
            'Date: {date}\n'
            'Components: {comps}\n'
            'Architectures: {archs}\n'.format(
                origin=origin,
                dist=dist,
                date=date,
                comps=' '.join(comps),
                archs=' '.join(archs),
            ))

    def _create_pkg_msg_from_item(self, item, dist):
        message = 'Filename: pool/%s/%s/%s/%s\n' % (
            dist,
            item['name'][0],
            item['name'],
            item['filename'])
        message += 'MD5sum: %s\n' % item['md5']
        message += 'SHA1: %s\n' % item['sha1']
        message += 'SHA256: %s\n' % item['sha256']
        message += 'Size: %s\n' % item['size']
        # re-assemble control text from all fragments
        # this has to go last, as the control message
        # might have trailing newlines
        control_frags = []
        control_txt = ''
        for attr in item:
            if attr.startswith('controltxt'):
                control_frags.append(attr)
        for attr in sorted(control_frags):
            control_txt += item[attr]
        message += control_txt + '\n'
        return message

    def _build_package_files(self, dists):
        self._log.debug('assembling packages files for %s', dists)
        # the dict always has to return a string at the leaves in
        # order that gzip will have something to work on
        package_files = defaultdict(
            lambda: defaultdict(lambda: defaultdict(lambda: '')))
        # get all packages for the dists we are publishing
        archs = set(self.archs)
        archs.remove('source')
        query = self._create_sorted_package_dict(
            self._select(self._assemble_select_query(
                dists=dists, comps=self.comps, archs=archs)))
        # iterate over every package returned by simpledb;
        # sort them into a nested dictionary:
        # {dist: {comp: {arch: 'Packages.txt'}}}
        # (presort by package name so that output order remains more or less
        # consistent)
        for name in sorted(query.keys()):
            for dist in dists:  # iterate over every dist we are publishing
                for comp in self.comps:  # over every component we know
                    for arch in archs:  # and every architecture
                        if arch == 'all':
                            continue  # these do not get their own section
                        for pkg in query[name][dist][comp][arch]:
                            message = self._create_pkg_msg_from_item(
                                pkg, dist)
                            package_files[dist][comp][arch] += message
                        # packages with architecture=all show up in all
                        # binary distributions
                        for pkg in query[name][dist][comp]['all']:
                            message = self._create_pkg_msg_from_item(
                                pkg, dist)
                            package_files[dist][comp][arch] += message
        return package_files

    def _create_src_msg_from_item(self, item, dist):
        message = 'Directory: pool/%s/%s/%s\n' % (
            dist,
            item['name'][0],
            item['name'])
        message += 'Package: %s\n' % item['name']
        # re-assemble message text from all fragments. this has to go last, as
        # the message might have trailing newlines
        control_frags = []
        control_txt = ''
        for attr in item:
            if attr.startswith('controltxt'):
                control_frags.append(attr)
        for attr in sorted(control_frags):
            control_txt += item[attr]
        message += control_txt + '\n'
        return message

    def _build_source_files(self, dists):
        self._log.debug('assembling sources files for %s', dists)
        # the dict always has to return a string at the leaves in
        # order that gzip will have something to work on
        source_files = defaultdict(
            lambda: defaultdict(lambda: defaultdict(lambda: '')))
        # get all sources for the dists we are publishing
        query = self._create_sorted_package_dict(
            self._select(self._assemble_select_query(
                dists=dists, comps=self.comps, archs=['source'])))
        # iterate over every package returned by simpledb;
        # sort them into a nested dictionary:
        # {dist: {comp: {'source': 'Sources.txt'}}}
        for name in sorted(query.keys()):
            for dist in dists:  # iterate over every dist we are publishing
                for comp in self.comps:  # over every component we know
                    for src in query[name][dist][comp]['source']:
                        message = self._create_src_msg_from_item(src, dist)
                        source_files[dist][comp]['source'] += message
        return source_files

    def _gzip_nested_files(self, package_files):
        """Iterate over a nested dictionary of strings, return
        an equivalently nested dict of gzipped bytes."""
        ret = defaultdict(
            lambda: defaultdict(lambda: defaultdict(lambda: b'')))
        for dist, comps in iteritems(package_files):
            for comp, archs in iteritems(comps):
                for arch in archs:
                    text = package_files[dist][comp][arch]
                    with BytesIO() as buf:
                        with GzipFile(fileobj=buf, mode='wb') as gz:
                            gz.write(text.encode('utf-8'))
                        ret[dist][comp][arch] = buf.getvalue()
        return ret

    def _nested_dict(self, dists=[]):
        """ Many repoman functions return a nested dictionary
        in the form {dist: {comp: {arch: <something>}}}, this
        function provides such a container."""
        ret = {}
        for dist in dists:
            ret[dist] = {}
            for comp in self.comps:
                ret[dist][comp] = {}
                for arch in self.archs:
                    ret[dist][comp][arch] = None
        return ret

    def _generate_dist_release_files(self, dists,
                                     package_files,
                                     package_gz_files,
                                     source_files,
                                     source_gz_files,
                                     origin,
                                     label):
        dist_release_files = dict(itertools.product(dists, [None]))
        for dist in dists:
            dist_release_files[dist] = self._build_dist_release(
                dist, origin)
            for line in self._generate_release_hashes(
                    dist, package_files, package_gz_files,
                    source_files, source_gz_files):
                dist_release_files[dist] += line
        return dist_release_files

    def _generate_leaf_release_files(self, dists, origin, label):
        leaf_release_files = self._nested_dict(dists)
        for dist in dists:
            for comp in self.comps:
                for arch in self.archs:
                    leaf_release_files[dist][comp][arch] = (
                        'Archive: {dist}\n'
                        'Component: {comp}\n'
                        'Origin: {origin}\n'
                        'Label: {label}\n'
                        'Architecture: {arch}\n'.format(
                            dist=dist,
                            comp=comp,
                            origin=origin,
                            label=label,
                            arch=arch))
        return leaf_release_files

    def _get_gpg(self, gpg_home):
        ringfile = os.path.expanduser(
            os.path.join(gpg_home, 'secring.gpg'))
        if not os.path.isfile(ringfile):
            raise KeyringNotFoundError(
                'No gpg secret keyring found at "%s"' % ringfile)
        kr = PGPKeyring()
        kr.load(ringfile)
        return kr

    def _generate_release_sigs(self,
                               gpg_home,
                               gpg_signers,
                               dist_release_files,
                               gpg_passphrases=[]):
        self._log.debug('generating release signatures')
        ret = {}
        gpg = self._get_gpg(gpg_home)
        for dist, text in iteritems(dist_release_files):
            ret[dist] = ''
            for idx, signer in enumerate(gpg_signers):
                with gpg.key(signer) as sec:
                    self._log.debug('signing %s with key %s', dist, signer)
                    if sec.is_unlocked:
                        sig = sec.sign(text, detach=True)
                    else:
                        with sec.unlock(gpg_passphrases[idx]):
                            sig = sec.sign(text, detach=True)
                ret[dist] += str(sig)
        return ret

    def _generate_release_hashes(self, dist, pkgs, pkgs_gz, srcs, srcs_gz):
        for hashname in ('md5', 'sha1', 'sha256'):
            if hashname == 'md5':
                hn = 'MD5Sum'  # grrr
            else:
                hn = hashname.upper()
            yield '{0}:\n'.format(hn)
            hasher = getattr(hashlib, hashname)
            for comp in pkgs[dist]:
                src_text = srcs[dist][comp]['source'].encode('utf-8')  # py27--
                src_gzdata = srcs_gz[dist][comp]['source']
                yield ' {h} {l} {c}/source/Sources\n'.format(
                    h=hasher(src_text).hexdigest(),
                    l=len(src_text),
                    c=comp)
                yield ' {h} {l} {c}/source/Sources.gz\n'.format(
                    h=hasher(src_gzdata).hexdigest(),
                    l=len(src_gzdata),
                    c=comp)
                for arch in pkgs[dist][comp]:
                    pkg_text = pkgs[dist][comp][arch].encode('utf-8')  # py27--
                    pkg_gzdata = pkgs_gz[dist][comp][arch]
                    # add the leaf to the dist-level release file
                    # note the space at the start of this string
                    yield ' {h} {l} {c}/binary-{a}/Packages\n'.format(
                        h=hasher(pkg_text).hexdigest(),
                        l=len(pkg_text),
                        c=comp,
                        a=arch)
                    yield ' {h} {l} {c}/binary-{a}/Packages.gz\n'.format(
                        h=hasher(pkg_gzdata).hexdigest(),
                        l=len(pkg_gzdata),
                        c=comp,
                        a=arch)
        yield '\n'

    def _assemble_path_data(self, dist_release_files, dist_release_sigs,
                            package_files, package_gz_files,
                            source_files, source_gz_files,
                            leaf_release_files):
        path_data = []
        suffix = (self._connection.profile_name, self._connection.role_arn)
        # assemble lists of paths to write to s3
        for dist in dist_release_files.keys():
            # dist_release_files and dist_release_sigs are only
            # keyed by dist name
            path_data.append(
                ('dists/{0}/Release'.format(dist),
                 dist_release_files[dist]) + suffix)
            if dist_release_sigs:
                path_data.append(('dists/{0}/Release.gpg'.format(dist),
                                  dist_release_sigs[dist]) + suffix)
            # everything else is a walk down the comps/archs tree
            for comp in self.comps:
                for arch in self.archs:
                    if arch == 'all':
                        continue  # we don't generate a specific release here
                    elif arch == 'source':
                        path_data.append(
                            ('dists/{0}/{1}/source/Sources'.format(dist, comp),
                             source_files[dist][comp][arch]) + suffix)
                        path_data.append(
                            ('dists/{0}/{1}/source/Sources.gz'.format(
                                dist, comp),
                             source_gz_files[dist][comp][arch]) + suffix)
                        path_data.append(
                            ('dists/{0}/{1}/source/Release'.format(
                                dist, comp),
                             leaf_release_files[dist][comp][arch]) + suffix)
                    else:
                        path_data.append(
                            ('dists/{0}/{1}/binary-{2}/Packages'.format(
                                dist, comp, arch),
                             package_files[dist][comp][arch]) + suffix)
                        path_data.append(
                            ('dists/{0}/{1}/binary-{2}/Packages.gz'.format(
                                dist, comp, arch),
                             package_gz_files[dist][comp][arch]) + suffix)
                        path_data.append(
                            ('dists/{0}/{1}/binary-{2}/Release'.format(
                                dist, comp, arch),
                             leaf_release_files[dist][comp][arch]) + suffix)
        return path_data

    def _create_sorted_package_dict(self, sources, latest_versions=0):
        """ Given a list of package items returned from query(), sort
        them into a nested dict in the form:
            {name: {dist: {comp: {arch: [item, item...]}}}}
        ...then sort each list of items at the tree leaves from
        lowest to highest by debian package version sorting order."""
        self._log.debug('latest: %d', latest_versions)
        sorted_sources = defaultdict(lambda: defaultdict(
            lambda: defaultdict(lambda: defaultdict(list))))
        for pkg in sources:
            sorted_sources[pkg['name']][
                pkg['distribution']][
                    pkg['component']][pkg['architecture']].append(pkg)
        for name, dists in iteritems(sorted_sources):
            for dist, comps in iteritems(dists):
                for comp, archs in iteritems(comps):
                    for arch, pkgs in iteritems(archs):
                        ct = len(pkgs)
                        pkgs.sort(key=lambda x:
                                  Dpkg.compare_versions_key(x['version']))
                        self._log.debug('len pkgs: %d', ct)
                        if latest_versions > 0:
                            # prune to only the N most "recent" packages
                            sorted_sources[name][dist][comp][arch] = (
                                pkgs[-latest_versions:])
                        elif (latest_versions < 0 and -latest_versions-1 < ct):
                            # prune to ALL BUT the N most "recent" packages
                            sorted_sources[name][dist][comp][arch] = (
                                pkgs[:latest_versions])
        return sorted_sources

    def _check_spec(self, sources, targets):
        """
        Ensure that two nested dicts of package items have the same keys and
        the same number of items in each list.
        """
        success = True
        for name, dists in iteritems(sources):
            if name not in targets:
                self._log.fatal('Source package name %s not found in '
                                'destination spec: %s', name, targets)
                success = False
                break
            for dist, comps in iteritems(dists):
                for comp, archs in iteritems(comps):
                    for arch, items in iteritems(archs):
                        if len(items) != len(targets[name][dist][comp][arch]):
                            self._log.fatal(
                                'Source and destination specs for '
                                'package %s have non-matching lengths. '
                                '\n\tSrc: %s\n\tDst: %s ',
                                name, items, targets[name][dist][comp][arch])
                            success = False
                            break
        if not success:
            raise InvalidCopyActionError(
                'Something has gone horrifically wrong; the '
                'source and destination side of a copy action '
                'should have the same number of items. This is '
                'probably a bug: please open an issue on github '
                'with as much detail as you can provide')
        return True

    def _walk_ndcai(self, ndcai, enumerate_items=False):
        """Multiple functions in this object have to unspool
        a nested dictionary in the form of:
            {name: {dist: {comp: {arch: [item, item]}}}}
        This leads to some ridiculously deep nesting of functions,
        so turn this process into a generator."""
        for name, dists in iteritems(ndcai):
            for dist, comps in iteritems(dists):
                for comp, archs in iteritems(comps):
                    for arch, items in iteritems(archs):
                        if enumerate_items:
                            for idx, item in enumerate(items):
                                yield (name, dist, comp, arch, idx, item)
                        else:
                            for item in items:
                                yield (name, dist, comp, arch, item)

    def initialize(self, dists=[], comps=[], archs=[], topic_name=None,
                   origin=None, label=None):
        self._log.info('Creating simpledb domain')
        self._create_domain()
        self._log.info('Initializing repository database')
        self._create_meta(dists=dists, comps=comps, archs=archs,
                          topic_name=topic_name,
                          origin=origin,
                          label=label)
        return 0

    def add_meta(self, archs=[], dists=[], comps=[],
                 topic_name='', origin='', label='',
                 test_data=''):
        if archs:
            self._log.info('Adding architectures: %s', archs)
        if dists:
            self._log.info('Adding distributions: %s', dists)
        if comps:
            self._log.info('Adding components: %s', comps)
        if topic_name:
            self._log.info('Adding SNS topic for logging: %s', topic_name)
        if origin:
            self._log.info('Setting repository origin: %s', origin)
        if label:
            self._log.info('Setting repository label: %s', label)
        if test_data:
            self._log.info('Writing test data to repo: %s', test_data)
        return self._create_meta(dists, comps, archs,
                                 topic_name, origin, label, test_data)

    def rm_meta(self, archs=[], dists=[], comps=[],
                topic_name=False, test_data=False):
        if archs:
            self._log.info('Deleting architectures: %s', archs)
        if dists:
            self._log.info('Deleting distributions: %s', dists)
        if comps:
            self._log.info('Deleting components: %s', comps)
        if topic_name:
            self._log.info('Deleting SNS topic for logging')
        if test_data:
            self._log.info('Deleting test data from repo')
        return self._delete_meta(dists, comps, archs, topic_name, test_data)

    def find_invalid_metadata(self, candidates, metadata_type):
        """Check that each member of a list of possible repository
           metadata configuration values (architectures, distributions,
           components) are known to the repository."""
        if not getattr(self, metadata_type):
            raise KeyError(
                '%s is not a known type of metadata' % metadata_type)
        failed = []
        for candidate in candidates:
            if candidate not in getattr(self, metadata_type):
                self._log.debug(
                    '%s is not a known type of %s', candidate, metadata_type)
                failed.append(candidate)
        return failed

    def check_valid_archs(self, archs=[]):
        """Assert that each member of the list `archs` is a architecture
        this repo is currently configured to serve; otherwise raise
        InvalidArchitectureError.

        :param archs: list
        :returns: true
        :raises: InvalidArchitectureError
        """
        unrecognized = self.find_invalid_metadata(archs, 'archs')
        if unrecognized:
            raise InvalidArchitectureError(
                'architectures %s are not currently served by this repo' %
                unrecognized)
        return True

    def check_valid_dists(self, dists=[]):
        """Assert that each member of the list `dists` is a distribution
        this repo is currently configured to serve; otherwise raise
        InvalidDistributionError.

        :param dists: list
        :returns: true
        :raises: InvalidDistributionError
        """
        unrecognized = self.find_invalid_metadata(dists, 'dists')
        if unrecognized:
            raise InvalidDistributionError(
                'distributions %s are not currently served by this repo' %
                unrecognized)
        return True

    def check_valid_comps(self, comps=[]):
        """Assert that each member of the list `comps` is a component
        this repo is currently configured to serve; otherwise raise
        InvalidComponentError.

        :param comps: list
        :returns: true
        :raises: InvalidComponentError
        """
        unrecognized = self.find_invalid_metadata(comps, 'comps')
        if unrecognized:
            raise InvalidComponentError(
                'components %s are not currently served by this repo' %
                unrecognized)
        return True

    def add_package(self, pkg, dists=[], comps=[],
                    overwrite=False, auto_purge=0):
        """Import the metadata from a pydpkg.Dpkg object as a
        simpledb item for each of the specified distributions
        and components.

        :param pkg: a pydpkg.Dpkg object
        :param dists: list of strings
        :param comps: list of strings
        :param overwrite: bool
        :param auto_purge: int
        """
        pkg_name = pkg.get_header('package')
        pkg_file = os.path.basename(pkg.filename)
        control_str = str(pkg.message.as_string())
        pkg_arch = pkg.get_header('architecture')
        self.check_valid_archs([pkg_arch])
        self.check_valid_dists(dists)
        self.check_valid_comps(comps)
        for dist in dists:
            for comp in comps:
                attrs = {'name': pkg_name,
                         'filename': pkg_file,
                         'distribution': dist,
                         'component': comp,
                         'version': pkg.version,
                         'architecture': pkg_arch,
                         'md5': pkg.md5,
                         'sha1': pkg.sha1,
                         'sha256': pkg.sha256,
                         'size': str(pkg.filesize)}
                attrs.update(self._split_control_text(control_str))
                self._log.debug('attrs: %s', attrs)
                key_name = self._compute_keyname_from_item(attrs)
                self._log.debug('key name: %s', key_name)
                if self._item_exists(key_name) and not overwrite:
                    raise ItemExistsError(
                        'Package %s version %s in distribution % and '
                        'component %s already exists in simpledb',
                        pkg_name, pkg.version, dist, comp)
                self._put_attributes(key_name, attrs)
                self._send_notifications([
                    {'action': 'add', 'type': 'package',
                     'name': attrs['name'],
                     'version': attrs['version'],
                     'distribution': attrs['distribution'],
                     'component': attrs['component'],
                     'caller': self.connection.caller_id}])
                if auto_purge > 0:
                    self._log.warning(
                        'Automatically purging %d oldest versions of %s '
                        'in the %s distribution, %s component and %s '
                        'architecture.', auto_purge, pkg_name, dist,
                        comp, pkg_arch)
                    targets = self.get_candidates(
                        dist, comp, names=[pkg_name], archs=[pkg_arch],
                        latest_versions=-auto_purge)
                    self.do_rm(targets)

    def add_source(self, dsc, dists=[], comps=[], overwrite=False,
                   auto_purge=0):
        """Import the metadata from a pydpkg.Dsc object as a
        simpledb item for each of the specified distributions
        and components.

        Annoyingly, debian dsc messages are juuuuust different
        enough from binary ones that this has to be a special case.

        :param dsc: a pydpkg.Dsc object
        :param dists: list of strings
        :param comps: list of strings
        :param overwrite: bool
        :param auto_purge: int
        """
        # blow up immediately if the source bundle is incomplete
        # or corrupt
        dsc.validate()
        dsc_arch = 'source'
        dsc_name = dsc.source
        source_files = [os.path.basename(x) for x in dsc.source_files]
        message_str = dsc.message_str
        self.check_valid_dists(dists)
        self.check_valid_comps(comps)
        for dist in dists:
            for comp in comps:
                attrs = {'name': dsc_name,
                         'files': source_files,  # nb: this will be a list
                         'distribution': dist,
                         'component': comp,
                         'version': dsc.version,
                         'architecture': dsc_arch}
                attrs.update(self._split_control_text(message_str))
                self._log.debug('attrs: %s', attrs)
                key_name = self._compute_keyname_from_item(attrs)
                self._log.debug('key name: %s', key_name)
                if self._item_exists(key_name) and not overwrite:
                    raise ItemExistsError(
                        'Source package %s version %s in distribution % and '
                        'component %s already exists in simpledb',
                        dsc_name, dsc.version, dist, comp)
                self._put_attributes(key_name, attrs)
                self._send_notifications([
                    {'action': 'add', 'type': 'source',
                     'name': dsc_name,
                     'version': attrs['version'],
                     'distribution': dist,
                     'component': comp,
                     'caller': self.connection.caller_id}])
                if auto_purge > 0:
                    self._log.warning(
                        'Automatically purging %d oldest versions of %s '
                        'in the %s distribution, %s component and %s '
                        'architecture.', auto_purge, dsc_name, dist,
                        comp, dsc_arch)
                    targets = self.get_candidates(
                        dist, comp, names=[dsc_name], archs=[dsc_arch],
                        latest_versions=-auto_purge)
                    self.do_rm(targets)

    def publish(self, repo, dists=[],
                gpg_home='~/.gnupg', gpg_signers=[], gpg_passphrases=[]):
        """Assemble the metadata files of the repository and write them
        to the repo s3 bucket."""
        retval = 0
        origin = self.origin or 'repoman'
        label = self.label or 'repoman'
        if dists is None or len(dists) == 0:
            dists = self.dists
        package_files = self._build_package_files(dists)
        source_files = self._build_source_files(dists)
        # pre-compress the package file strings
        package_gz_files = self._gzip_nested_files(package_files)
        source_gz_files = self._gzip_nested_files(source_files)
        dist_release_files = self._generate_dist_release_files(
            dists, package_files, package_gz_files,
            source_files, source_gz_files,
            origin, label)
        leaf_release_files = self._generate_leaf_release_files(
            dists, origin, label)
        if gpg_signers:
            dist_release_sigs = self._generate_release_sigs(
                gpg_home, gpg_signers, dist_release_files, gpg_passphrases)
        else:
            dist_release_sigs = None

        path_data = self._assemble_path_data(
            dist_release_files, dist_release_sigs,
            package_files, package_gz_files,
            source_files, source_gz_files,
            leaf_release_files)

        results = utils.write_paths(
            repo.bucket_name, path_data, threads=0)

        for path, code in results:
            if not code or code.get(
                    'ResponseMetadata', {}).get('HTTPStatusCode') != 200:
                self._log.error(
                    'Did not successfully write "s3://%s/%s: %s',
                    repo.bucket_name, path, code)
                retval = 1

        self._log.info('Successfully published repository for dists %s '
                       'to bucket s3://%s', dists, repo.bucket_name)

        return retval

    def query(self, names=[], dists=[], comps=[], archs=[], versions=[],
              latest_versions=0, name_wildcard=False):
        """
        A friendly wrapper around repodb._assemble_select_query() and
        _create_sorted_package_dict() that returns a nested dictionary of
        package items, keyed by package name, and with the list of packages
        sorted in strict debian package ordering, oldest to newest:
            {name:{dist:{comp:[pkg, pkg]}}}
        Optionally if latest_versions is positive, each of the lists is pruned
        to only the N newest packages (again by debian sorting rules).

        :param names: list of strings
        :param dists: list of strings
        :param comps: list of strings
        :param archs: list of strings
        :param versions: list of strings
        :param latest_versions: int
        :param name_wildcard: bool
        :rtype: dict
        """
        if dists:
            self.check_valid_dists(dists)
            if isinstance(dists, str):
                dists = [dists]
        if comps:
            self.check_valid_comps(comps)
            if isinstance(comps, str):
                comps = [comps]
        if archs:
            self.check_valid_archs(archs)
            if isinstance(archs, str):
                archs = [archs]
        query_str = self._assemble_select_query(
            names=names,
            dists=dists,
            comps=comps,
            archs=archs,
            versions=versions,
            name_wildcard=name_wildcard)
        return self._create_sorted_package_dict(
            self._select(query_str),
            latest_versions)

    def get_candidates(self, src_dist, src_comp,
                       names=[], versions=[], archs=[],
                       latest_versions=0, name_wildcard=False):
        """
        A small wrapper around repodb.query() that ensures we are only
        passing in a single distribution and/or component, since
        multiples would not make sense in a copying context.

        :param src_dict: string
        :param src_comp: string
        :param packages: list of strings
        :param versions: list of strings
        :param archs: list of strings
        :param latest_versions: int
        :param name_wildcard: bool
        :rtype: dict
        :raises: InvalidDistributionError, InvalidComponentError
        """
        if not isinstance(src_dist, string_types):
            raise InvalidDistributionError(
                'src_dist must be the name of a single distribution: %s',
                src_dist)
        if not isinstance(src_comp, string_types):
            raise InvalidComponentError(
                'src_comp must be the name of a single component: %s',
                src_comp)
        sources = self.query(
            names=names,
            dists=[src_dist] if src_dist else [],
            comps=[src_comp] if src_comp else [],
            archs=archs,
            versions=versions,
            latest_versions=latest_versions,
            name_wildcard=name_wildcard)
        return sources

    def get_copy_spec(self, candidates, src_dist, src_comp,
                      dst_dist=None, dst_comp=None,
                      prune_for_promote=False):
        """Given a nested dict of source packages for copying,
        compute an equivalent nested dict of new package items to
        create, and prune no-ops from both the source and the
        destination side.

        If prune_for_promote is true, prune from the source side
        any packages that are older, version-wise, than the newest
        package on the destination side.
        """
        # if no destination distribution or component is specified, then
        # the move is within the source dist/comp
        dst_dist = dst_dist or src_dist
        dst_comp = dst_comp or src_comp
        self.check_valid_dists([dst_dist])
        self.check_valid_comps([dst_comp])
        existing = self.get_candidates(
            dst_dist, dst_comp, names=candidates.keys())
        targets = defaultdict(
            lambda: defaultdict(
                lambda: defaultdict(lambda: defaultdict(list))))
        # what's an o(n^4) between friends?
        for name, dist, comp, arch, idx, old in self._walk_ndcai(
                candidates, enumerate_items=True):
            new = deepcopy(old)
            new['distribution'] = dst_dist or new['distribution']
            new['component'] = dst_comp or new['component']
            if new == old:
                self._log.debug('Same as source: %s', new)
                candidates[name][dist][comp][arch][idx] = None
                continue
            if new in existing[name][dist][comp][arch]:
                self._log.debug('Already at target: %s', new)
                candidates[name][dist][comp][arch][idx] = None
                continue
            if prune_for_promote:
                # if the old version < the newest available
                # version on the destination side (if there are
                # any), we are not a candidate for promotion
                if existing[name][dst_dist][dst_comp][arch]:
                    latest = existing[name][dst_dist][dst_comp][arch][-1]
                    res = Dpkg.compare_versions(
                        latest['version'], new['version'])
                    if res >= 0:
                        self._log.warning('skipping')
                        candidates[name][dist][comp][arch][idx] = None
                        continue
            targets[name][dist][comp][arch].append(new)
            # prune no-ops from source side
            if None in candidates[name][dist][comp][arch]:
                candidates[name][dist][comp][arch].remove(None)
        if self._check_spec(candidates, targets):
            return candidates, targets

    def do_copy(self, candidates, targets, repo,
                overwrite=False, auto_purge=0):
        for name, dist, comp, arch, idx, pkg in self._walk_ndcai(
                targets, enumerate_items=True):
            src_dist = candidates[name][dist][comp][arch][idx]['distribution']
            src_comp = candidates[name][dist][comp][arch][idx]['component']
            dst_dist = pkg['distribution']
            if src_dist != dst_dist:
                self._log.warning(
                    'copy of package %s from distribution %s to '
                    '%s requires an s3 copy',
                    name, src_dist, dst_dist)
                # handle both source and binary files
                filenames = filter(
                    None,
                    itertools.chain([pkg.get('filename')],
                                    pkg.get('files', [])))
                for fn in filenames:
                    old_path = os.path.join(
                        'pool', src_dist, pkg['name'][0],
                        pkg['name'], fn)
                    new_path = os.path.join(
                        'pool', dst_dist, pkg['name'][0],
                        pkg['name'], fn)
                    try:
                        repo.copy_key(old_path, new_path, overwrite)
                    except KeyExistsError:
                        self._log.warning(
                            'package already exists at s3://%s ',
                            new_path)
            self._log.info(
                'creating package %s version %s '
                'distribution %s component %s '
                'architecture %s', pkg['name'],
                pkg['version'], pkg['distribution'],
                pkg['component'], pkg['architecture'])
            key = self._compute_keyname_from_item(pkg)
            self._put_attributes(key, pkg)
            self._send_notifications([
                {'action': 'copy', 'type': 'package',
                 'name': pkg['name'],
                 'version': pkg['version'],
                 'dst_distribution': pkg['distribution'],
                 'dst_component': pkg['component'],
                 'src_distribution': src_dist,
                 'src_component': src_comp,
                 'caller': self.connection.caller_id}])
        if auto_purge > 0:
            for name, dists in iteritems(targets):
                for dist, comps in iteritems(dists):
                    for comp, archs in iteritems(comps):
                        for arch, items in iteritems(archs):
                            # horrible cheat here
                            dst_dist = items[0]['distribution']
                            dst_comp = items[0]['component']
                            self._log.warning(
                                'Automatically purging %d oldest versions of '
                                '%s in the %s distribution, %s component and '
                                '%s architecture.', auto_purge, name, dist,
                                comp, arch)
                            purge_targets = self.get_candidates(
                                dst_dist, dst_comp, names=[name], archs=[arch],
                                latest_versions=-auto_purge)
                            self.do_rm(purge_targets)

    def do_rm(self, targets):
        for name, dist, comp, arch, item in self._walk_ndcai(targets):
            self._log.warning(
                'Deleting pkg %s version %s in distribution '
                '%s component %s architecture %s',
                item['name'], item['version'],
                item['distribution'], item['component'],
                item['architecture'])
            self._delete_item(item)
            self._send_notifications([
                {'action': 'delete', 'type': 'package',
                 'name': item['name'],
                 'version': item['version'],
                 'distribution': item['distribution'],
                 'component': item['component'],
                 'caller': self.connection.caller_id}])
