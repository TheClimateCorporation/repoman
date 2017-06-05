#!/usr/bin/env python

import pytest
import os
from mock import MagicMock
import json

from apt_repoman import cli
from apt_repoman.repo import Repo
from apt_repoman.repodb import Repodb

import botocore.session
from botocore.stub import Stubber, ANY


@pytest.fixture
def setup():
    s3 = botocore.session.get_session().create_client('s3')
    sdb = botocore.session.get_session().create_client('sdb')
    sns = botocore.session.get_session().create_client('sns')
    repo = Repo('testbucket')
    repodb = Repodb('testdomain')
    repodb._s3 = s3
    repodb._sdb = sdb
    repodb._sns = sns
    repodb._archs = ['amd64', 'i386']
    repodb._dists = ['xenial', 'jessie']
    repodb._comps = ['main', 'nightly']
    repodb._topic_arn = ''
    args = MagicMock()
    _dir = os.path.dirname(__file__)
    return s3, sdb, sns, repo, repodb, args, _dir


def test_query(setup, capsys):
    s3, sdb, sns, repo, repodb, args, _dir = setup
    with open(os.path.join(_dir, 'query_output.json')) as fp:
        select_response = json.loads(fp.read())
    with open(os.path.join(_dir, 'get_attr_meta.json')) as fp:
        get_attr_meta_response = json.loads(fp.read())
    args.architecture = []
    args.distribution = []
    args.component = []
    args.package = []
    args.version = []
    args.query_hidden = False
    args.outputfmt = 'plain'
    args.latest_versions = 0
    with Stubber(sdb) as stub:
        select_params = {
            'ConsistentRead': True,
            'SelectExpression': "select * from `testdomain` where `name` is not null and every(distribution) in ('jessie','xenial') and every(component) in ('main','nightly') and every(architecture) in ('all','amd64','i386','source')"}
        get_attr_params = {'AttributeNames': [], 'ConsistentRead': True, 'DomainName': 'testdomain', 'ItemName': 'meta'}
        stub.add_response('get_attributes', get_attr_meta_response, get_attr_params)
        stub.add_response('select', select_response, select_params)
        expected = open(os.path.join(_dir, 'query_output.txt')).read()
        result = cli.query(args, repodb, repo)
        assert result == 0
        out, err = capsys.readouterr()
        assert out == expected
