#!/usr/bin/env python

import json
import time
import unittest
import os

from collections import OrderedDict
from gzip import GzipFile
from io import BytesIO
from mock import patch, PropertyMock

import botocore.session
from botocore.stub import Stubber, ANY

from apt_repoman.repodb import Repodb
from apt_repoman.repodb import InvalidAttributesError
from apt_repoman.repodb import InvalidCopyActionError

HASH = 'ad30985578dcf4e5fe0d8f40270fcff7b4e39720307f95b4511be0eda8ddc0b9'

IPSUM = """Lorem ipsum dolor sit amet, consectetur adipiscing elit. Phasellus
mollis hendrerit quam, non consectetur elit vestibulum sed. Donec pharetra
egestas purus eu venenatis. Etiam dignissim pretium metus. Suspendisse nec dui
at nisi consectetur feugiat molestie eu metus. Donec eget urna id lorem ornare
aliquet eget et felis. Integer rutrum, eros ac vehicula aliquam, lorem quam
tincidunt mauris, eget laoreet diam nisi a libero. In elementum dui faucibus
odio efficitur, a dignissim ante pulvinar. Donec auctor mi nunc, commodo
hendrerit nulla consequat et. Nulla facilisi. Pellentesque tempor dui at
ultrices facilisis. In ullamcorper at lacus non luctus. Integer faucibus,
ligula in venenatis blandit, leo neque hendrerit velit, ac porttitor urna metus
a dolor."""


class RepodbTest(unittest.TestCase):

    def setUp(self):
        self.repodb = Repodb('testdomain')
        self._dir = os.path.dirname(__file__)

    def testMeta(self):
        self.repodb._meta = {'dists': ['d1', 'd2'],
                             'comps': ['c1', 'c2'],
                             'archs': ['a1', 'a2']}
        self.assertEqual(self.repodb.dists, ['d1', 'd2'])
        self.assertEqual(self.repodb.comps, ['c1', 'c2'])
        # tricky...
        self.assertEqual(self.repodb.archs, ['a1', 'a2', 'all', 'source'])

    def testRespoolAttributes(self):
        _in_good = {'foo': 'bar', 'xyzzy': ['bada', 'bing']}
        _in_bad_key = {1: 'bar'}
        _in_bad_val = {'a': 1}
        _in_bad_subval = {'a': ['bar', 1]}
        _out_true = [
            {'Name': 'foo', 'Value': 'bar', 'Replace': True},
            {'Name': 'xyzzy', 'Value': 'bada', 'Replace': True},
            {'Name': 'xyzzy', 'Value': 'bing', 'Replace': True}]
        _out_false = [
            {'Name': 'foo', 'Value': 'bar', 'Replace': False},
            {'Name': 'xyzzy', 'Value': 'bada', 'Replace': False},
            {'Name': 'xyzzy', 'Value': 'bing', 'Replace': False}]
        _out_none = [
            {'Name': 'foo', 'Value': 'bar'},
            {'Name': 'xyzzy', 'Value': 'bada'},
            {'Name': 'xyzzy', 'Value': 'bing'}]
        self.assertEqual(
            self.repodb._respool_attributes(_in_good, True),
            _out_true)
        self.assertEqual(
            self.repodb._respool_attributes(_in_good, False),
            _out_false)
        self.assertEqual(
            self.repodb._respool_attributes(_in_good, None),
            _out_none)
        self.assertRaises(
            InvalidAttributesError,
            self.repodb._respool_attributes, _in_bad_key)
        self.assertRaises(
            InvalidAttributesError,
            self.repodb._respool_attributes, _in_bad_val)
        self.assertRaises(
            InvalidAttributesError,
            self.repodb._respool_attributes, _in_bad_subval)

    def testUnspoolAttributes(self):
        _in = [{'Name': 'foo', 'Value': 'bar'},
               {'Name': 'xyzzy', 'Value': 'bada'},
               {'Name': 'xyzzy', 'Value': 'bing'}]
        _out = {'foo': 'bar', 'xyzzy': ['bada', 'bing']}
        self.assertEqual(
            self.repodb._unspool_attributes(_in),
            _out)

    def testAssembleSelectQuery(self):
        self.assertEqual(
            self.repodb._assemble_select_query(),
            "select * from `testdomain` where `name` is not null")
        self.assertEqual(
            self.repodb._assemble_select_query(names=['foo']),
            "select * from `testdomain` where `name` is not null and "
            "every(name) in ('foo')")
        self.assertEqual(
            self.repodb._assemble_select_query(names=['foo', 'bar']),
            "select * from `testdomain` where `name` is not null and "
            "every(name) in ('foo','bar')")
        self.assertEqual(
            self.repodb._assemble_select_query(
                names=['foo'], name_wildcard=True),
            "select * from `testdomain` where `name` is not null and  "
            "`name` LIKE 'foo%'")
        self.assertEqual(
            self.repodb._assemble_select_query(
                names=['foo', 'bar'], name_wildcard=True),
            "select * from `testdomain` where `name` is not null and  "
            "`name` LIKE 'foo%' or `name` LIKE 'bar%'")
        self.assertEqual(
            self.repodb._assemble_select_query(names=['foo'],
                                               dists=['bar', 'baz']),
            "select * from `testdomain` where `name` is not null and "
            "every(name) in ('foo') and every(distribution) in ('bar','baz')")
        self.assertEqual(
            self.repodb._assemble_select_query(names=['foo'],
                                               comps=['bar', 'baz']),
            "select * from `testdomain` where `name` is not null and "
            "every(name) in ('foo') and every(component) in ('bar','baz')")
        self.assertEqual(
            self.repodb._assemble_select_query(names=['foo'],
                                               archs=['bar', 'baz']),
            "select * from `testdomain` where `name` is not null and "
            "every(name) in ('foo') and every(architecture) in ('bar','baz')")
        self.assertEqual(
            self.repodb._assemble_select_query(names=['foo'],
                                               versions=['bar', 'baz']),
            "select * from `testdomain` where `name` is not null and "
            "every(name) in ('foo') and every(version) in ('bar','baz')")

    def testComputeKeyname(self):
        self.assertEqual(
            self.repodb._compute_keyname('foo', 'bar', 'baz', 'qux', 'xyzzy'),
            HASH)

    def testComputKeynameFromItem(self):
        _in = {'name': 'foo', 'version': 'bar',
               'distribution': 'baz', 'component': 'qux',
               'architecture': 'xyzzy'}
        self.assertEqual(
            self.repodb._compute_keyname_from_item(_in),
            HASH)

    def testSplitControlText(self):
        self.assertEqual(
            self.repodb._split_control_text(IPSUM, 64),
            OrderedDict([
                ('controltxt00', 'Lorem ipsum dolor sit amet, consectetur a'
                                 'dipiscing elit. Phasell'),
                ('controltxt01', 'us\nmollis hendrerit quam, non consectetu'
                                 'r elit vestibulum sed. D'),
                ('controltxt02', 'onec pharetra\negestas purus eu venenatis'
                                 '. Etiam dignissim pretiu'),
                ('controltxt03', 'm metus. Suspendisse nec dui\nat nisi con'
                                 'sectetur feugiat molesti'),
                ('controltxt04', 'e eu metus. Donec eget urna id lorem orna'
                                 're\naliquet eget et feli'),
                ('controltxt05', 's. Integer rutrum, eros ac vehicula aliqu'
                                 'am, lorem quam\ntincidun'),
                ('controltxt06', 't mauris, eget laoreet diam nisi a libero'
                                 '. In elementum dui fauc'),
                ('controltxt07', 'ibus\nodio efficitur, a dignissim ante pu'
                                 'lvinar. Donec auctor mi '),
                ('controltxt08', 'nunc, commodo\nhendrerit nulla consequat '
                                 'et. Nulla facilisi. Pell'),
                ('controltxt09', 'entesque tempor dui at\nultrices facilisi'
                                 's. In ullamcorper at lac'),
                ('controltxt10', 'us non luctus. Integer faucibus,\nligula '
                                 'in venenatis blandit, le'),
                ('controltxt11', 'o neque hendrerit velit, ac porttitor urn'
                                 'a metus\na dolor.')])
        )

    def testBuildDistRelease(self):
        date = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())
        self.assertEqual(
            self.repodb._build_dist_release(
                'foo', 'bar',
                comps=['baz', 'qux'],
                archs=['bada', 'bing'],
                date=date),
            '\n'.join(['Origin: bar',
                       'Label: bar',
                       'Codename: foo',
                       'Acquire-By-Hash: no',
                       'Date: %s' % date,
                       'Components: baz qux',
                       'Architectures: bada bing\n']))

    def testCreatePackageMessageFromItem(self):
        _in = {
            'name': 'foo',
            'filename': 'bar',
            'md5': 'DEADBEEF',
            'sha1': 'BEEFCAFE',
            'sha256': 'CAFEFACE',
            'size': '123',
            'controltxt01': 'us\nmollis hendrerit quam, non consectetur elit vestibulum sed. D',
            'controltxt00': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Phasell',
            'controltxt02': 'onec pharetra\negestas purus eu venenatis. Etiam dignissim pretiu'}
        self.assertEqual(
            self.repodb._create_pkg_msg_from_item(_in, 'xyzzy'),
            '\n'.join([
                'Filename: pool/xyzzy/f/foo/bar',
                'MD5sum: DEADBEEF',
                'SHA1: BEEFCAFE',
                'SHA256: CAFEFACE',
                'Size: 123',
                'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Phasellus',
                'mollis hendrerit quam, non consectetur elit vestibulum sed. Donec pharetra',
                'egestas purus eu venenatis. Etiam dignissim pretiu\n']))

    def testCreateSourceMessageFromItem(self):
        _in = {
            'name': 'foo',
            'controltxt01': 'us\nmollis hendrerit quam, non consectetur elit vestibulum sed. D',
            'controltxt00': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Phasell',
            'controltxt02': 'onec pharetra\negestas purus eu venenatis. Etiam dignissim pretiu'}
        expected = '\n'.join([
                'Directory: pool/xyzzy/f/foo',
                'Package: foo',
                'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Phasellus',
                'mollis hendrerit quam, non consectetur elit vestibulum sed. Donec pharetra',
                'egestas purus eu venenatis. Etiam dignissim pretiu\n'])
        self.assertEqual(
            expected,
            self.repodb._create_src_msg_from_item(_in, 'xyzzy'))

    def testGzipPackageFiles(self):
        # fun!
        _in = {'trusty': {'main': {'amd64': 'foobar'}},
               'xenial': {'main': {'all': 'xyzzy'}}}
        _out = self.repodb._gzip_nested_files(_in)
        tma = _out['trusty']['main']['amd64']
        xma = _out['xenial']['main']['all']
        with BytesIO(tma) as bz:
            with GzipFile(fileobj=bz) as gz:
                self.assertEqual(b'foobar', gz.read())
        with BytesIO(xma) as bz:
            with GzipFile(fileobj=bz) as gz:
                self.assertEqual(b'xyzzy', gz.read())

    @patch('apt_repoman.repodb.Repodb.archs', new_callable=PropertyMock)
    @patch('apt_repoman.repodb.Repodb.comps', new_callable=PropertyMock)
    def testNestedDict(self, comps, archs):
        comps.return_value = ['c1', 'c2']
        archs.return_value = ['a1', 'a2']
        _out = {'d1': {'c1': {'a1': None, 'a2': None},
                       'c2': {'a1': None, 'a2': None}},
                'd2': {'c1': {'a1': None, 'a2': None},
                       'c2': {'a1': None, 'a2': None}}}
        _in = self.repodb._nested_dict(['d1', 'd2'])
        self.assertEqual(_in, _out)

    @patch('apt_repoman.repodb.Repodb.archs', new_callable=PropertyMock)
    @patch('apt_repoman.repodb.Repodb.comps', new_callable=PropertyMock)
    @patch('apt_repoman.repodb.Repodb.dists', new_callable=PropertyMock)
    def testGenerateDistReleaseFiles(self, dists, comps, archs):
        dists.return_value = ['d1']
        comps.return_value = ['c1']
        archs.return_value = ['a1', 'all']
        faketime = time.gmtime(1497895073.870057)
        with patch('time.gmtime', return_value=faketime):
            package_files = {'d1': {'c1': {'a1': 'foo'}}}
            package_gz_files = {'d1': {'c1': {'a1': b'0xDEADBEEF'}}}
            source_files = {'d1': {'c1': {'source': 'bar'}}}
            source_gz_files = {'d1': {'c1': {'source': b'0xBEEFCAFE'}}}
            origin = 'test'
            label = 'test'
            self.maxDiff = None
            expected = {'d1': """Origin: test
Label: test
Codename: d1
Acquire-By-Hash: no
Date: Mon, 19 Jun 2017 17:57:53 +0000
Components: c1
Architectures: a1
MD5Sum:
 37b51d194a7513e45b56f6524f2d51f2 3 c1/source/Sources
 a4d4f03fbcc4a36782648488dd07319f 10 c1/source/Sources.gz
 acbd18db4cc2f85cedef654fccc4a4d8 3 c1/binary-a1/Packages
 545882e2eba6b126518d07c954698c83 10 c1/binary-a1/Packages.gz
SHA1:
 62cdb7020ff920e5aa642c3d4066950dd1f01f4d 3 c1/source/Sources
 cef0d0350de7697c4abe1e6b7db788d46dc748b1 10 c1/source/Sources.gz
 0beec7b5ea3f0fdbc95d0dd47f3c5bc275da8a33 3 c1/binary-a1/Packages
 fbc02cbc52f9aa96fefa06c567b180df6df832db 10 c1/binary-a1/Packages.gz
SHA256:
 fcde2b2edba56bf408601fb721fe9b5c338d10ee429ea04fae5511b68fbf8fb9 3 c1/source/Sources
 09a597d7489048ac580a36b0381b35d9140738f8e3b8dfc19a5edfd41f09cc2b 10 c1/source/Sources.gz
 2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae 3 c1/binary-a1/Packages
 5fce5f5878415a3bae17db60a69b08d51f0f962228bfdbb462993a3ac16171e4 10 c1/binary-a1/Packages.gz

"""}
            returned = self.repodb._generate_dist_release_files(
                ['d1'],
                package_files, package_gz_files,
                source_files, source_gz_files,
                origin, label)
            self.assertEqual(expected, returned)

    @patch('apt_repoman.repodb.Repodb.archs', new_callable=PropertyMock)
    @patch('apt_repoman.repodb.Repodb.comps', new_callable=PropertyMock)
    @patch('apt_repoman.repodb.Repodb.dists', new_callable=PropertyMock)
    def testGenerateLeafReleaseFiles(self, dists, comps, archs):
        dists.return_value = ['d1']
        comps.return_value = ['c1']
        archs.return_value = ['a1', 'all']
        origin = 'test'
        label = 'test'
        self.maxDiff = None
        self.assertEqual(
            self.repodb._generate_leaf_release_files(['d1'], origin, label),
            {'d1': {'c1': {'a1': 'Archive: d1\nComponent: c1\nOrigin: test\nLabel: test\nArchitecture: a1\n',
             'all': 'Archive: d1\nComponent: c1\nOrigin: test\nLabel: test\nArchitecture: all\n'}}}
        )

    @patch('apt_repoman.repodb.Repodb.archs', new_callable=PropertyMock)
    @patch('apt_repoman.repodb.Repodb.comps', new_callable=PropertyMock)
    @patch('apt_repoman.repodb.Repodb.dists', new_callable=PropertyMock)
    def testBuildPackageFiles(self, dists, comps, archs):
        dists.return_value = ['xenial', 'jessie']
        comps.return_value = ['main', 'nightly']
        archs.return_value = ['source', 'i386', 'amd64', 'all']
        self.repodb._sdb = botocore.session.get_session().create_client('sdb')
        self.maxDiff = None
        with open(os.path.join(self._dir, 'query_output.json')) as fp:
            select_response = json.loads(fp.read())
        with Stubber(self.repodb._sdb) as stub:
            stub.add_response('select', select_response, {
                'ConsistentRead': True,
                'SelectExpression': ANY})
            expected = {
                "jessie": {
                  "main": {
                    "i386": "Filename: pool/jessie/t/testdeb/3:testdeb_1.1.0-test2_all.deb\nMD5sum: 85813d0688494314fa37b4bca6939782\nSHA1: efa19aee680fbbb98f1915ee14c18ef902dfa025\nSHA256: 4d3ef2fe026ee7fae63584e2361ec3176f24fe448f48925189bb60fb2e72f2c6\nSize: 1298\nPackage: testdeb\nVersion: 3:1.1.0-test2\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: all\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\n",
                    "amd64": "Filename: pool/jessie/t/testdeb/3:testdeb_1.1.0-test2_amd64.deb\nMD5sum: 568728506dd4374cb34c12dbf9e9a148\nSHA1: dedbe9b395b22ff18d161bb9caaabaea09b2da5b\nSHA256: 4ab8523efef0a343f8cf301d67d4cb71b76b7761f1023523940928c223d02437\nSize: 1296\nPackage: testdeb\nVersion: 3:1.1.0-test2\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: amd64\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\nFilename: pool/jessie/t/testdeb/3:testdeb_1.1.0-test2_all.deb\nMD5sum: 85813d0688494314fa37b4bca6939782\nSHA1: efa19aee680fbbb98f1915ee14c18ef902dfa025\nSHA256: 4d3ef2fe026ee7fae63584e2361ec3176f24fe448f48925189bb60fb2e72f2c6\nSize: 1298\nPackage: testdeb\nVersion: 3:1.1.0-test2\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: all\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\n"
                  }
                },
                "xenial": {
                  "nightly": {
                    "i386": "Filename: pool/xenial/t/testdeb/testdeb_1:0.0.0-test_all.deb\nMD5sum: 149e61536a9fe36374732ec95cf7945d\nSHA1: a5d28ae2f23e726a797349d7dd5f21baf8aa02b4\nSHA256: 547500652257bac6f6bc83f0667d0d66c8abd1382c776c4de84b89d0f550ab7f\nSize: 910\nPackage: testdeb\nVersion: 1:0.0.0-test\nSection: base\nPriority: extra\nArchitecture: all\nInstalled-Size: 0\nMaintainer: Nathan Mehl <n@climate.com>\nDescription: testdeb\n a bogus debian package for testing dpkg builds\n\n\nFilename: pool/xenial/t/testdeb/1:testdeb_1.0.0-test_all.deb\nMD5sum: c9a1e0a35cc3706e8003edbc8bf60e7f\nSHA1: e3dc33ad3aa9c3ff81020bdfd629e171f6ac2c0e\nSHA256: 6bfe58c48ab34585b8c1bc671e8103c499e17af2a3a4e237a58bd57fc8d1501d\nSize: 1304\nPackage: testdeb\nVersion: 1:1.0.0-test\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: all\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\nFilename: pool/xenial/t/testdeb/1:testdeb_1.1.0-test_all.deb\nMD5sum: 9d72f9a5e0d739dcc5241f7e50e5addd\nSHA1: a923bd5489b8e5ec7d3e96fb1b700c29d81725df\nSHA256: a8e6bca9936270a057a670658bd4e43aaf1791495734d3d666be12815b4a56e2\nSize: 1300\nPackage: testdeb\nVersion: 1:1.1.0-test\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: all\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\nFilename: pool/xenial/t/testdeb/1:testdeb_1.1.0-test2_all.deb\nMD5sum: 36611a3c94464e954e54e5c385ff647e\nSHA1: f58ebb9e618d3ce1293c1a6e7dcb7e1d30ca242f\nSHA256: 7323ab214df42f89a5df4eedc4c0aeece14bff31425f2dd7bd90d2d21d56163a\nSize: 1292\nPackage: testdeb\nVersion: 1:1.1.0-test2\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: all\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\nFilename: pool/xenial/t/testdeb/2:testdeb_0.0.0-test_all.deb\nMD5sum: c8cd10216d5e99a18971c80531d10b01\nSHA1: 2e3f6aca44459898fd1e05ab659ba1cd0aa9a613\nSHA256: 7f29b9631765fb459c046fbda1586767e4d8a9ad330dff86bfae91c684aa3f30\nSize: 1294\nPackage: testdeb\nVersion: 2:0.0.0-test\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: all\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\nFilename: pool/xenial/t/testdeb/3:testdeb_1.1.0-test2_all.deb\nMD5sum: 85813d0688494314fa37b4bca6939782\nSHA1: efa19aee680fbbb98f1915ee14c18ef902dfa025\nSHA256: 4d3ef2fe026ee7fae63584e2361ec3176f24fe448f48925189bb60fb2e72f2c6\nSize: 1298\nPackage: testdeb\nVersion: 3:1.1.0-test2\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: all\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\n",
                    "amd64": "Filename: pool/xenial/t/testdeb/3:testdeb_1.1.0-test2_amd64.deb\nMD5sum: 568728506dd4374cb34c12dbf9e9a148\nSHA1: dedbe9b395b22ff18d161bb9caaabaea09b2da5b\nSHA256: 4ab8523efef0a343f8cf301d67d4cb71b76b7761f1023523940928c223d02437\nSize: 1296\nPackage: testdeb\nVersion: 3:1.1.0-test2\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: amd64\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\nFilename: pool/xenial/t/testdeb/testdeb_1:0.0.0-test_all.deb\nMD5sum: 149e61536a9fe36374732ec95cf7945d\nSHA1: a5d28ae2f23e726a797349d7dd5f21baf8aa02b4\nSHA256: 547500652257bac6f6bc83f0667d0d66c8abd1382c776c4de84b89d0f550ab7f\nSize: 910\nPackage: testdeb\nVersion: 1:0.0.0-test\nSection: base\nPriority: extra\nArchitecture: all\nInstalled-Size: 0\nMaintainer: Nathan Mehl <n@climate.com>\nDescription: testdeb\n a bogus debian package for testing dpkg builds\n\n\nFilename: pool/xenial/t/testdeb/1:testdeb_1.0.0-test_all.deb\nMD5sum: c9a1e0a35cc3706e8003edbc8bf60e7f\nSHA1: e3dc33ad3aa9c3ff81020bdfd629e171f6ac2c0e\nSHA256: 6bfe58c48ab34585b8c1bc671e8103c499e17af2a3a4e237a58bd57fc8d1501d\nSize: 1304\nPackage: testdeb\nVersion: 1:1.0.0-test\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: all\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\nFilename: pool/xenial/t/testdeb/1:testdeb_1.1.0-test_all.deb\nMD5sum: 9d72f9a5e0d739dcc5241f7e50e5addd\nSHA1: a923bd5489b8e5ec7d3e96fb1b700c29d81725df\nSHA256: a8e6bca9936270a057a670658bd4e43aaf1791495734d3d666be12815b4a56e2\nSize: 1300\nPackage: testdeb\nVersion: 1:1.1.0-test\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: all\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\nFilename: pool/xenial/t/testdeb/1:testdeb_1.1.0-test2_all.deb\nMD5sum: 36611a3c94464e954e54e5c385ff647e\nSHA1: f58ebb9e618d3ce1293c1a6e7dcb7e1d30ca242f\nSHA256: 7323ab214df42f89a5df4eedc4c0aeece14bff31425f2dd7bd90d2d21d56163a\nSize: 1292\nPackage: testdeb\nVersion: 1:1.1.0-test2\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: all\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\nFilename: pool/xenial/t/testdeb/2:testdeb_0.0.0-test_all.deb\nMD5sum: c8cd10216d5e99a18971c80531d10b01\nSHA1: 2e3f6aca44459898fd1e05ab659ba1cd0aa9a613\nSHA256: 7f29b9631765fb459c046fbda1586767e4d8a9ad330dff86bfae91c684aa3f30\nSize: 1294\nPackage: testdeb\nVersion: 2:0.0.0-test\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: all\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\nFilename: pool/xenial/t/testdeb/3:testdeb_1.1.0-test2_all.deb\nMD5sum: 85813d0688494314fa37b4bca6939782\nSHA1: efa19aee680fbbb98f1915ee14c18ef902dfa025\nSHA256: 4d3ef2fe026ee7fae63584e2361ec3176f24fe448f48925189bb60fb2e72f2c6\nSize: 1298\nPackage: testdeb\nVersion: 3:1.1.0-test2\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: all\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\n"
                  },
                  "main": {
                    "i386": "Filename: pool/xenial/h/hashicorp-consul-template/hashicorp-consul-template_0.15-tcc01_i386.deb\nMD5sum: 8fce38500395227d83095c2e1ef1f473\nSHA1: 88e9312553b083de908c875a2d581d6a407f00b0\nSHA256: baaa65ff64c1b3d1d90f48f87cedf49112a209d8b3af80b8b9422059c42caf00\nSize: 1342\nPackage: hashicorp-consul-template\nVersion: 0.15-tcc01\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: i386\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\nFilename: pool/xenial/t/testdeb/testdeb_1:0.0.0-test_all.deb\nMD5sum: 149e61536a9fe36374732ec95cf7945d\nSHA1: a5d28ae2f23e726a797349d7dd5f21baf8aa02b4\nSHA256: 547500652257bac6f6bc83f0667d0d66c8abd1382c776c4de84b89d0f550ab7f\nSize: 910\nPackage: testdeb\nVersion: 1:0.0.0-test\nSection: base\nPriority: extra\nArchitecture: all\nInstalled-Size: 0\nMaintainer: Nathan Mehl <n@climate.com>\nDescription: testdeb\n a bogus debian package for testing dpkg builds\n\n\nFilename: pool/xenial/t/testdeb/1:testdeb_1.0.0-test_all.deb\nMD5sum: c9a1e0a35cc3706e8003edbc8bf60e7f\nSHA1: e3dc33ad3aa9c3ff81020bdfd629e171f6ac2c0e\nSHA256: 6bfe58c48ab34585b8c1bc671e8103c499e17af2a3a4e237a58bd57fc8d1501d\nSize: 1304\nPackage: testdeb\nVersion: 1:1.0.0-test\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: all\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\nFilename: pool/xenial/t/testdeb/1:testdeb_1.1.0-test_all.deb\nMD5sum: 9d72f9a5e0d739dcc5241f7e50e5addd\nSHA1: a923bd5489b8e5ec7d3e96fb1b700c29d81725df\nSHA256: a8e6bca9936270a057a670658bd4e43aaf1791495734d3d666be12815b4a56e2\nSize: 1300\nPackage: testdeb\nVersion: 1:1.1.0-test\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: all\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\nFilename: pool/xenial/t/testdeb/1:testdeb_1.1.0-test2_all.deb\nMD5sum: 36611a3c94464e954e54e5c385ff647e\nSHA1: f58ebb9e618d3ce1293c1a6e7dcb7e1d30ca242f\nSHA256: 7323ab214df42f89a5df4eedc4c0aeece14bff31425f2dd7bd90d2d21d56163a\nSize: 1292\nPackage: testdeb\nVersion: 1:1.1.0-test2\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: all\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\nFilename: pool/xenial/t/testdeb/2:testdeb_0.0.0-test_all.deb\nMD5sum: c8cd10216d5e99a18971c80531d10b01\nSHA1: 2e3f6aca44459898fd1e05ab659ba1cd0aa9a613\nSHA256: 7f29b9631765fb459c046fbda1586767e4d8a9ad330dff86bfae91c684aa3f30\nSize: 1294\nPackage: testdeb\nVersion: 2:0.0.0-test\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: all\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\nFilename: pool/xenial/t/testdeb/3:testdeb_1.1.0-test2_all.deb\nMD5sum: 85813d0688494314fa37b4bca6939782\nSHA1: efa19aee680fbbb98f1915ee14c18ef902dfa025\nSHA256: 4d3ef2fe026ee7fae63584e2361ec3176f24fe448f48925189bb60fb2e72f2c6\nSize: 1298\nPackage: testdeb\nVersion: 3:1.1.0-test2\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: all\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\n",
                    "amd64": "Filename: pool/xenial/h/hashicorp-consul-template/hashicorp-consul-template_0.15-tcc01_amd64.deb\nMD5sum: 3fe3996aea835bb0fd9c9a7595ee969e\nSHA1: 85b006304079b32cd10283f55d009ba51a79b480\nSHA256: 77a3eaee90d8edabf0a73b3d3e7148d298e4e0461b3a1737b23dc78fce6da22e\nSize: 3521222\nPackage: hashicorp-consul-template\nVersion: 0.15-tcc01\nLicense: unknown\nVendor: none\nArchitecture: amd64\nMaintainer: <n@salacious.local>\nInstalled-Size: 12194\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\nFilename: pool/xenial/t/testdeb/3:testdeb_1.1.0-test2_amd64.deb\nMD5sum: 568728506dd4374cb34c12dbf9e9a148\nSHA1: dedbe9b395b22ff18d161bb9caaabaea09b2da5b\nSHA256: 4ab8523efef0a343f8cf301d67d4cb71b76b7761f1023523940928c223d02437\nSize: 1296\nPackage: testdeb\nVersion: 3:1.1.0-test2\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: amd64\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\nFilename: pool/xenial/t/testdeb/testdeb_1:0.0.0-test_all.deb\nMD5sum: 149e61536a9fe36374732ec95cf7945d\nSHA1: a5d28ae2f23e726a797349d7dd5f21baf8aa02b4\nSHA256: 547500652257bac6f6bc83f0667d0d66c8abd1382c776c4de84b89d0f550ab7f\nSize: 910\nPackage: testdeb\nVersion: 1:0.0.0-test\nSection: base\nPriority: extra\nArchitecture: all\nInstalled-Size: 0\nMaintainer: Nathan Mehl <n@climate.com>\nDescription: testdeb\n a bogus debian package for testing dpkg builds\n\n\nFilename: pool/xenial/t/testdeb/1:testdeb_1.0.0-test_all.deb\nMD5sum: c9a1e0a35cc3706e8003edbc8bf60e7f\nSHA1: e3dc33ad3aa9c3ff81020bdfd629e171f6ac2c0e\nSHA256: 6bfe58c48ab34585b8c1bc671e8103c499e17af2a3a4e237a58bd57fc8d1501d\nSize: 1304\nPackage: testdeb\nVersion: 1:1.0.0-test\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: all\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\nFilename: pool/xenial/t/testdeb/1:testdeb_1.1.0-test_all.deb\nMD5sum: 9d72f9a5e0d739dcc5241f7e50e5addd\nSHA1: a923bd5489b8e5ec7d3e96fb1b700c29d81725df\nSHA256: a8e6bca9936270a057a670658bd4e43aaf1791495734d3d666be12815b4a56e2\nSize: 1300\nPackage: testdeb\nVersion: 1:1.1.0-test\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: all\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\nFilename: pool/xenial/t/testdeb/1:testdeb_1.1.0-test2_all.deb\nMD5sum: 36611a3c94464e954e54e5c385ff647e\nSHA1: f58ebb9e618d3ce1293c1a6e7dcb7e1d30ca242f\nSHA256: 7323ab214df42f89a5df4eedc4c0aeece14bff31425f2dd7bd90d2d21d56163a\nSize: 1292\nPackage: testdeb\nVersion: 1:1.1.0-test2\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: all\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\nFilename: pool/xenial/t/testdeb/2:testdeb_0.0.0-test_all.deb\nMD5sum: c8cd10216d5e99a18971c80531d10b01\nSHA1: 2e3f6aca44459898fd1e05ab659ba1cd0aa9a613\nSHA256: 7f29b9631765fb459c046fbda1586767e4d8a9ad330dff86bfae91c684aa3f30\nSize: 1294\nPackage: testdeb\nVersion: 2:0.0.0-test\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: all\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\nFilename: pool/xenial/t/testdeb/3:testdeb_1.1.0-test2_all.deb\nMD5sum: 85813d0688494314fa37b4bca6939782\nSHA1: efa19aee680fbbb98f1915ee14c18ef902dfa025\nSHA256: 4d3ef2fe026ee7fae63584e2361ec3176f24fe448f48925189bb60fb2e72f2c6\nSize: 1298\nPackage: testdeb\nVersion: 3:1.1.0-test2\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: all\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n\n"
                  }
                }
              }
            returned = self.repodb._build_package_files(dists=['xenial', 'jessie'])
            self.assertEqual(expected, returned)

    @patch('apt_repoman.repodb.Repodb.archs', new_callable=PropertyMock)
    @patch('apt_repoman.repodb.Repodb.comps', new_callable=PropertyMock)
    @patch('apt_repoman.repodb.Repodb.dists', new_callable=PropertyMock)
    def testBuildSourceFiles(self, dists, comps, archs):
        dists.return_value = ['xenial', 'jessie']
        comps.return_value = ['main', 'nightly']
        archs.return_value = ['source', 'i386', 'amd64', 'all']
        self.repodb._sdb = botocore.session.get_session().create_client('sdb')
        self.maxDiff = None
        with open(os.path.join(self._dir, 'query_output.json')) as fp:
            select_response = json.loads(fp.read())
        with Stubber(self.repodb._sdb) as stub:
            stub.add_response('select', select_response, {
                'ConsistentRead': True,
                'SelectExpression': ANY})
            expected = {
                "jessie": {
                  "main": {
                    "source": "Directory: pool/jessie/a/apt-transport-s3\nPackage: apt-transport-s3\nFormat: 3.0 (quilt)\nSource: apt-transport-s3\nBinary: apt-transport-s3\nArchitecture: all\nVersion: 1.2.1-1\nMaintainer: Marcin Kulisz (kuLa) <debian@kulisz.net>\nUploaders: David Watson <dwatson@debian.org>\nHomepage: https://github.com/BashtonLtd/apt-transport-s3\nStandards-Version: 3.9.6\nVcs-Browser: https://github.com/BashtonLtd/apt-transport-s3/tree/debian/sid\nVcs-Git: https://github.com/BashtonLtd/apt-transport-s3.git\nBuild-Depends: python (>= 2.6.6-3), debhelper (>= 9)\nPackage-List: apt-transport-s3 deb admin optional arch=all\nChecksums-Sha1: fcaab2d352dda3c6e8894afef7ecf62f05367637 53764\n apt-transport-s3_1.2.1.orig.tar.gz\n 5833e6929583f1038c6aa2a26d264ed49f09106d 41920\n apt-transport-s3_1.2.1-1.debian.tar.xz\n 36c3bf0921f13de8176b3a86ecff1cac5532ff73 1986 apt-transport-s3_1.2.1-1.dsc\nChecksums-Sha256: 3935a698d3ca56ff02ffe133578c67d1e22b6599ab72643ac3b2564f7786dfcf 53764\n apt-transport-s3_1.2.1.orig.tar.gz\n 3b95f5222410637602f01d3120b0047a187afb8605e6fc444675aa599abc04c1 41920\n apt-transport-s3_1.2.1-1.debian.tar.xz\n fa801cc1da5a9acbbebdce30a1f32b260b50452125d84eedd45b917504206584 1986\n apt-transport-s3_1.2.1-1.dsc\nFiles: 8dfb207307b5fcfc917d5fbc6003ff95 53764\n apt-transport-s3_1.2.1.orig.tar.gz\n 76eb07b79e5cf34ba966a5cdd2817086 41920 apt-transport-s3_1.2.1-1.debian.tar.xz\n eca184b019fc93b069ae4bbe94ab9e3b 1986 apt-transport-s3_1.2.1-1.dsc\n\n\n"
                  }
                },
                "xenial": {
                  "main": {
                    "source": "Directory: pool/xenial/a/apt-transport-s3\nPackage: apt-transport-s3\nFormat: 3.0 (quilt)\nSource: apt-transport-s3\nBinary: apt-transport-s3\nArchitecture: all\nVersion: 1.2.1-1\nMaintainer: Marcin Kulisz (kuLa) <debian@kulisz.net>\nUploaders: David Watson <dwatson@debian.org>\nHomepage: https://github.com/BashtonLtd/apt-transport-s3\nStandards-Version: 3.9.6\nVcs-Browser: https://github.com/BashtonLtd/apt-transport-s3/tree/debian/sid\nVcs-Git: https://github.com/BashtonLtd/apt-transport-s3.git\nBuild-Depends: python (>= 2.6.6-3), debhelper (>= 9)\nPackage-List: apt-transport-s3 deb admin optional arch=all\nChecksums-Sha1: fcaab2d352dda3c6e8894afef7ecf62f05367637 53764\n apt-transport-s3_1.2.1.orig.tar.gz\n 5833e6929583f1038c6aa2a26d264ed49f09106d 41920\n apt-transport-s3_1.2.1-1.debian.tar.xz\n 36c3bf0921f13de8176b3a86ecff1cac5532ff73 1986 apt-transport-s3_1.2.1-1.dsc\nChecksums-Sha256: 3935a698d3ca56ff02ffe133578c67d1e22b6599ab72643ac3b2564f7786dfcf 53764\n apt-transport-s3_1.2.1.orig.tar.gz\n 3b95f5222410637602f01d3120b0047a187afb8605e6fc444675aa599abc04c1 41920\n apt-transport-s3_1.2.1-1.debian.tar.xz\n fa801cc1da5a9acbbebdce30a1f32b260b50452125d84eedd45b917504206584 1986\n apt-transport-s3_1.2.1-1.dsc\nFiles: 8dfb207307b5fcfc917d5fbc6003ff95 53764\n apt-transport-s3_1.2.1.orig.tar.gz\n 76eb07b79e5cf34ba966a5cdd2817086 41920 apt-transport-s3_1.2.1-1.debian.tar.xz\n eca184b019fc93b069ae4bbe94ab9e3b 1986 apt-transport-s3_1.2.1-1.dsc\n\n\n"
                  }
                }
            }
            returned = self.repodb._build_source_files(dists=['xenial', 'jessie'])
            self.assertEqual(expected, returned)

    @patch('apt_repoman.repodb.Repodb.archs', new_callable=PropertyMock)
    @patch('apt_repoman.repodb.Repodb.comps', new_callable=PropertyMock)
    def testAssemblePathData(self, comps, archs):
        comps.return_value = ['c1']
        archs.return_value = ['a1', 'all', 'source']
        dist_release_files = {'d1': 'foo'}
        dist_release_sigs = {'d1': {'c1': {'a1': '--PGP--', 'all': '--PGP--', 'source': '--PGP--'}}}
        package_files = {'d1': {'c1': {'a1': 'packages', 'all': 'morepackages'}}}
        package_gz_files = {'d1': {'c1': {'a1': b'0xDEADBEEF', 'all': b'0xBEEFCAFE'}}}
        source_files = {'d1': {'c1': {'source': 'sources'}}}
        source_gz_files = {'d1': {'c1': {'source': b'0xDEADBEEF'}}}
        leaf_release_files = {'d1': {'c1': {'a1': 'wash', 'all': 'wind', 'source': 'watch'}}}
        expected = [('dists/d1/Release', 'foo'),
                    ('dists/d1/Release.gpg', {'c1': {'a1': '--PGP--', 'all': '--PGP--', 'source': '--PGP--'}}),
                    ('dists/d1/c1/binary-a1/Packages', 'packages'),
                    ('dists/d1/c1/binary-a1/Packages.gz', b'0xDEADBEEF'),
                    ('dists/d1/c1/binary-a1/Release', 'wash'),
                    ('dists/d1/c1/source/Sources', 'sources'),
                    ('dists/d1/c1/source/Sources.gz', b'0xDEADBEEF'),
                    ('dists/d1/c1/source/Release', 'watch')]
        returned = self.repodb._assemble_path_data(
            dist_release_files, dist_release_sigs,
            package_files, package_gz_files,
            source_files, source_gz_files,
            leaf_release_files)
        self.maxDiff = None
        self.assertEquals(expected, returned)

    def testCreateSortedPackageDict(self):
        _in = [
            {'name': 'foo',
             'distribution': 'd1',
             'component': 'c1',
             'architecture': 'a1',
             'version': '1:0.0.0-test1'},
            {'name': 'foo',
             'distribution': 'd1',
             'component': 'c1',
             'architecture': 'a1',
             'version': '0.0.0-test1'},
            {'name': 'foo',
             'distribution': 'd1',
             'component': 'c1',
             'architecture': 'a1',
             'version': '0.0.0-~est1'},
        ]
        _out = {'foo': {'d1': {'c1': {'a1': [
            {'name': 'foo',
             'distribution': 'd1',
             'component': 'c1',
             'architecture': 'a1',
             'version': '0.0.0-~est1'},
            {'name': 'foo',
             'distribution': 'd1',
             'component': 'c1',
             'architecture': 'a1',
             'version': '0.0.0-test1'},
            {'name': 'foo',
             'distribution': 'd1',
             'component': 'c1',
             'architecture': 'a1',
             'version': '1:0.0.0-test1'}]}}}}
        _twolatest = {'foo': {'d1': {'c1': {'a1': [
            {'name': 'foo',
             'distribution': 'd1',
             'component': 'c1',
             'architecture': 'a1',
             'version': '0.0.0-test1'},
            {'name': 'foo',
             'distribution': 'd1',
             'component': 'c1',
             'architecture': 'a1',
             'version': '1:0.0.0-test1'}]}}}}
        _onelatest = {'foo': {'d1': {'c1': {'a1': [
            {'name': 'foo',
             'distribution': 'd1',
             'component': 'c1',
             'architecture': 'a1',
             'version': '1:0.0.0-test1'}]}}}}
        self.assertEqual(
            json.dumps(self.repodb._create_sorted_package_dict(_in)),
            json.dumps(_out))
        self.assertEqual(
            json.dumps(self.repodb._create_sorted_package_dict(_in, 1)),
            json.dumps(_onelatest))
        self.assertEqual(
            json.dumps(self.repodb._create_sorted_package_dict(_in, 2)),
            json.dumps(_twolatest))

    def testCheckSpec(self):
        _left = {'foo': {'d1': {'c1': {'a1': [
            {'name': 'foo',
             'distribution': 'd1',
             'component': 'c1',
             'architecture': 'a1',
             'version': '0.0.0-test1'},
            {'name': 'foo',
             'distribution': 'd1',
             'component': 'c1',
             'architecture': 'a1',
             'version': '1:0.0.0-test1'}]}}}}
        _right = {'foo': {'d1': {'c1': {'a1': [
            {'name': 'foo',
             'distribution': 'd1',
             'component': 'c1',
             'architecture': 'a1',
             'version': '0.0.0-test1'},
            {'name': 'foo',
             'distribution': 'd1',
             'component': 'c1',
             'architecture': 'a1',
             'version': '1:0.0.0-test1'}]}}}}
        _badlist = {'foo': {'d1': {'c1': {'a1': [
            {'name': 'foo',
             'distribution': 'd1',
             'component': 'c1',
             'architecture': 'a1',
             'version': '1:0.0.0-test1'}]}}}}
        _badkeys = {'bar': {'d1': {'c1': {'a1': [
            {'name': 'bar',
             'distribution': 'd1',
             'component': 'c1',
             'architecture': 'a1',
             'version': '0.0.0-test1'},
            {'name': 'foo',
             'distribution': 'd1',
             'component': 'c1',
             'architecture': 'a1',
             'version': '1:0.0.0-test1'}]}}}}
        self.maxDiff = None
        self.assertEqual(self.repodb._check_spec(_left, _right), True)
        self.assertRaises(InvalidCopyActionError,
                          self.repodb._check_spec, _left, _badkeys)
        self.assertRaises(InvalidCopyActionError,
                          self.repodb._check_spec, _left, _badlist)

    def testWalkNdcai(self):
        _in = {'foo': {'d1': {'c1': {'a1': ['foo-1', 'foo-2']}}}}
        _out = [('foo', 'd1', 'c1', 'a1', 'foo-1'),
                ('foo', 'd1', 'c1', 'a1', 'foo-2')]
        _out_idx = [('foo', 'd1', 'c1', 'a1', 0, 'foo-1'),
                    ('foo', 'd1', 'c1', 'a1', 1, 'foo-2')]
        self.assertEqual(
            list(self.repodb._walk_ndcai(_in)),
            _out)
        self.assertEqual(
            list(self.repodb._walk_ndcai(_in, True)),
            _out_idx)


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(RepodbTest)
    unittest.TextTestRunner(verbosity=2).run(suite)
