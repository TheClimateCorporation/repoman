#!/usr/bin/env python

from __future__ import print_function

# stdlib imports
import json
import logging
import os
import sys
import time

from logging import config
from pkg_resources import resource_stream
from six import iteritems
from six.moves import input

# pypi imports
from botocore.exceptions import ClientError
from colors import color
from pgpy.errors import PGPDecryptionError
from pydpkg import Dpkg
from pydpkg import Dsc
from pysectools.pinentry import Pinentry
from tabulate import tabulate

# internal imports
from apt_repoman.config import Config
from apt_repoman.connection import Connection
from apt_repoman.repo import KeyExistsError
from apt_repoman.repo import Repo
from apt_repoman.repodb import InvalidArchitectureError
from apt_repoman.repodb import ItemExistsError
from apt_repoman.repodb import Repodb


LOG = logging.getLogger(__name__)
HEADERS = ['name', 'distribution', 'component', 'architecture', 'version']


def repo_print_config(repodb, repo):
    LOG.info('Current repo configuration:')
    LOG.info('\tSimpledb domain: %s', repodb.domain_name)
    LOG.info('\tS3 bucket: s3://%s', repo.bucket_name)
    try:
        topic = repodb.topic_name or '---None configured---'
        LOG.info('\tSNS Notification topic: %s', topic)
        LOG.info('\tDistributions: %s', repodb.dists)
        LOG.info('\tComponents: %s', repodb.comps)
        LOG.info('\tArchitectures: %s', repodb.archs)
        LOG.info('\tOrigin: %s', repodb.origin)
        LOG.info('\tLabel: %s', repodb.label)
    except ClientError as ex:
        # if the domain doesn't exist, we can't query it
        # for its config...
        if ex.response.get('Error', {}).get('Code') == 'NoSuchDomain':
            LOG.error(
                'SDB domain does not exist yet, did you forget to run setup?')
        else:
            LOG.exception(ex)
        return 1
    return 0


def repo_add(thing, args, repodb, repo):
    abbrev = thing[0:4] + 's'
    argname = thing + '_names'
    candidates = getattr(args, argname)
    existing = getattr(repodb, abbrev)
    # the "all" architecture is special, you cannot remove it
    if abbrev == 'archs':
        while 'all' in args.architecture_names:
            LOG.error('You cannot add the "all" architecture, like the '
                      'Vorlons it has always been here.')
            args.architecture_names.remove('all')
        while 'source' in args.architecture_names:
            LOG.error('You cannot add the "source" architecture, like the '
                      'Vorlons it has always been here.')
            args.architecture_names.remove('source')
    for name in candidates:
        try:
            if name in existing:
                LOG.warning('%s %s already exists in repo %s',
                            thing, name, args.simpledb_domain)
                continue
        except KeyError:
            LOG.fatal('No repo configuration found, did you forget to '
                      'run "repoman setup"?')
            sys.exit(1)
    kwargs = {abbrev: candidates}
    LOG.warning(color(
        'Adding %s(s): %s', fg='red'), thing, ','.join(candidates))
    if confirm(args):
        res = repodb.add_meta(**kwargs)
    LOG.debug(res)
    return repo_print_config(repodb, repo)


def repo_rm(thing, args, repodb, repo):
    abbrev = thing[0:4] + 's'
    argname = thing + '_names'
    candidates = getattr(args, argname)
    existing = getattr(repodb, abbrev)
    elected = []
    evil = []
    if abbrev == 'archs':
        while 'all' in args.architecture_names:
            LOG.error('You cannot remove the "all" architecture, like the '
                      'Talamasca it watches and is always there.')
            args.architecture_names.remove('all')
        while 'source' in args.architecture_names:
            LOG.error('You cannot remove the "source" architecture, like the '
                      'Talamasca it watches and is always there.')
            args.architecture_names.remove('source')
    for name in candidates:
        try:
            if name not in existing:
                LOG.warning('%s %s does not exist in repo %s',
                            thing, name, args.simpledb_domain)
                continue
            elected.append(name)
        except KeyError:
            LOG.fatal('No repo configuration found, did you forget to '
                      'run "repoman setup"?')
            sys.exit(1)
    if not elected:
        LOG.error('No valid %ss to delete', thing)
        return 1
    LOG.warning(color(
        'Deleting %s(s): %s', fg='red'), thing, ','.join(elected))
    # ugh I am so sorry
    evil_msg = 'You are about to delete EVERY %s this repo serves' % thing
    if abbrev == 'archs':
        if len(elected) == len(repodb.archs) - 1:
            evil.append(evil_msg)
    elif len(elected) == len(existing):
        evil.append(evil_msg)
    if confirm(args, evil):
        res = repodb.rm_meta(**{abbrev: elected})
    LOG.debug(res)
    LOG.warning('Deleting a {0} from a repository does not actually '
                'delete the package files from S3 or the items from '
                'simpledb, it just stops including those {0}s in '
                'query results, cp/rm commands and '
                'the publishing process: you will need to clean up '
                'the orphaned resources manually if you care.'.format(
                    thing))
    return repo_print_config(repodb, repo)


def repo_topic(action, args, repodb, repo):
    if action == 'add':
        topic_name = args.topic_name[0]
        LOG.warning(color('Setting up SNS topic "%s" for logging' %
                          topic_name, fg='red'))
        if confirm(args):
            repodb.add_meta(topic_name=topic_name)
    elif action == 'rm':
        LOG.warning(color('Disabling SNS logging!', fg='red'))
        if confirm(args):
            repodb.rm_meta(topic_name=True)
    return repo_print_config(repodb, repo)


def repo_origin(action, args, repodb, repo):
    if action == 'add':
        origin = args.origin[0]
        LOG.warning(
            color('Setting repository origin: "%s"' % origin, fg='red'))
        if confirm(args):
            repodb.add_meta(origin=origin)
    else:
        LOG.fatal('You cannot remove an origin, you can only change it.')
        sys.exit(1)
    return repo_print_config(repodb, repo)


def repo_label(action, args, repodb, repo):
    if action == 'add':
        label = args.label[0]
        LOG.warning(
            color('Setting repository label: "%s"' % label, fg='red'))
        if confirm(args):
            repodb.add_meta(label=label)
    else:
        LOG.fatal('You cannot remove an label, you can only change it.')
        sys.exit(1)
    return repo_print_config(repodb, repo)


def repo(args, repodb, repo):
    command = args.repo_command
    if command == 'show-config':
        return repo_print_config(repodb, repo)
    if command.startswith('add-') or command.startswith('rm-'):
        verb, noun = command.split('-')
        if noun in ('topic', 'origin', 'label'):
            # sns topic handling is a little different
            return globals()['repo_' + noun](verb, args, repodb, repo)
        else:
            return globals()['repo_' + verb](noun, args, repodb, repo)


def add(args, repodb, repo):
    """Add packages"""
    # we check this here before we risk uploading to s3
    if not validate_meta(args, repodb):
        return 1
    success = 0
    for fn in args.files:
        LOG.info('attempting to add file: %s', fn)
        if fn.endswith('.deb'):
            pkg = Dpkg(fn)
        elif fn.endswith('.dsc'):
            pkg = Dsc(fn)
        else:
            LOG.error('File "%s" is neither a deb nor a dsc files', fn)
            success += 1
            continue
        try:
            if isinstance(pkg, Dsc):
                LOG.info('attempting to add source to s3: %s',
                         os.path.basename(fn))
                repo.add_source(pkg,
                                dists=args.distribution,
                                overwrite=args.overwrite)
                LOG.info('attempting to add source to simpledb: %s',
                         os.path.basename(fn))
                repodb.add_source(pkg,
                                  dists=args.distribution,
                                  comps=args.component,
                                  overwrite=args.overwrite,
                                  auto_purge=args.auto_purge)
            else:
                arch = pkg.architecture
                repodb.check_valid_archs([arch])
                LOG.info('attempting to add package to s3: %s',
                         os.path.basename(pkg.filename))
                repo.add_package(pkg,
                                 dists=args.distribution,
                                 overwrite=args.overwrite)
                LOG.info('attempting to add package to simpledb: %s',
                         os.path.basename(pkg.filename))
                repodb.add_package(pkg,
                                   dists=args.distribution,
                                   comps=args.component,
                                   overwrite=args.overwrite,
                                   auto_purge=args.auto_purge)
            LOG.info('Successfully added %s to repoman!', fn)
        except InvalidArchitectureError:
            LOG.error('Package %s is built for the "%s" architecture, '
                      'which this repo is not currently configured to '
                      'serve; I will not add it.  You may which to run '
                      '"repoman repo add_architecture %s"', fn, arch, arch)
            success += 1
            continue
        except KeyExistsError:
            LOG.error('Package %s already exists in S3, you either want the '
                      '--overwrite flag or you want to move/copy the package '
                      'within the repo.  Skipping.', fn)
            success += 1
            continue
        except ItemExistsError:
            LOG.error('Package %s already exists in simpledb, you either want '
                      'the --overwrite flag or you want to move/copy the '
                      'package within the repo.  Skipping.', fn)
            success += 1
            continue
    if success > 0:
        LOG.error('Not all packages uploadeded successfully; inspect '
                  'the log output for errors.')
    return success


def pin_entry(args, signer):
    pinentry = Pinentry(
        pinentry_path=args.gpg_pinentry_path,
        fallback_to_getpass=True)
    passphrase = pinentry.ask(
        prompt='Enter your gpg passphrase --> ',
        description='Repoman requires a passphrase to unlock key "%s"' %
        signer)
    pinentry.close()
    return passphrase


def get_passphrases(args, repodb):
    passphrases = []
    gpg = repodb._get_gpg(args.gpg_home)
    for idx, signer in enumerate(args.gpg_signer):
        count = 0
        while True:
            try:
                with gpg.key(signer) as sec:
                    if sec.is_unlocked:
                        LOG.warning('gpg key for %s is not locked!', signer)
                        passphrases.append(None)
                        break
                    if args.gpg_passphrase:
                        try:
                            passphrase = args.gpg_passphrase[idx]
                            LOG.warning(
                                'Using passphrase from config for key %s',
                                signer)
                        except IndexError:
                            passphrase = pin_entry(args, signer)
                    else:
                        passphrase = pin_entry(args, signer)
                    with sec.unlock(passphrase):
                        sec.sign('test')
                        passphrases.append(passphrase)
                        break
            except KeyError as ex:
                LOG.fatal('gpg key id "%s" not found in keyring at %s',
                          signer, args.gpg_home)
                sys.exit(1)
            except PGPDecryptionError as ex:
                LOG.error('Could not decrypt gpg key for %s: %s', signer, ex)
                # if they're using pinentry-curses, this error might flash
                # by too quickly to see...
                time.sleep(2)
                if count >= 2:
                    raise
                else:
                    count += 1
            except Exception as ex:
                # something went terribly wrong
                LOG.exception(ex)
                LOG.fatal('something went terribly wrong?!')
                sys.exit(1)
    return passphrases


def publish(args, repodb, repo):
    LOG.info('publishing repository to S3')
    gpg_passphrases = []
    if 'gpg_signer' in args and args.gpg_signer:
        gpg_passphrases = get_passphrases(args, repodb)
    else:
        LOG.warning(
            'no gpg signers present; this will be an insecure apt release')

    return repodb.publish(
        repo,
        dists=args.distribution,
        gpg_home=args.gpg_home,
        gpg_signers=args.gpg_signer,
        gpg_passphrases=gpg_passphrases
    )


def setup(args, repodb, repo):
    """Initialize basic configuration"""
    LOG.info('Setting up repoman!')
    try:
        repodb.initialize(
            dists=args.distribution,
            comps=args.component,
            archs=args.architecture,
            topic_name=args.sns_topic,
            origin=args.origin,
            label=args.label
        )
    except Exception as ex:
        LOG.exception(ex)
        LOG.fatal('Could not initialize simpledb domain: %s', ex)
        LOG.fatal('Failed repoman setup!')
        sys.exit(1)
    try:
        repo.initialize(args.s3_acl, args.s3_region, args.enable_website)
    except Exception as ex:
        LOG.exception(ex)
        LOG.fatal('Could not create S3 bucket: %s', ex)
        LOG.fatal('Failed repoman setup!')
        sys.exit(1)
    repo_print_config(repodb, repo)
    return 0


def checkup(args, repodb, repo):
    retval = 0
    LOG.info('Doing repoman system health check: set skip-checkup to suppress')
    repo_print_config(repodb, repo)
    LOG.info('checking whether simpledb domain exists')
    if not repodb.domain_exists:
        LOG.fatal('Repository simpledb domain does not appear to exist; did '
                  'you forget to run setup?')
        retval = 1
    try:
        LOG.info('checking simpledb domain accessibility')
        result = repodb.add_meta(test_data='foo')
        if not result or result['ResponseMetadata']['HTTPStatusCode'] != 200:
            raise Exception('Got error writing to simpledb: %s' % result)
        result = repodb.rm_meta(test_data=True)
        if not result or result['ResponseMetadata']['HTTPStatusCode'] != 200:
            raise Exception('Got error deleting from simpledb: %s' % result)
        LOG.info('checking simpledb repo configuration')
        for name, values in iteritems(repodb.meta):
            if name not in ('topic_name', 'test_data'):
                if len(values) < 1:
                    LOG.error('Repository DB has no %ss configured, '
                              'did you forget to run setup?', name)
                    retval = 1
        if repodb.topic_name:
            LOG.info('Checking SNS topic "%s" exists', repodb.topic_name)
            topic_arn = repodb.topic_arn
            if not topic_arn:
                LOG.fatal('SNS topic name "%s" does not exist and I do not '
                          'have permissions to create it!', repodb.topic_name)
                retval = 1
    except ClientError as ex:
        # if the domain doesn't exist, we can't query it
        # for its config...
        if ex.response.get('Error', {}).get('Code') == 'NoSuchDomain':
            LOG.fatal(
                'SDB domain does not exist yet, did you forget to run setup?')
        else:
            LOG.exception(ex)
        retval = 1
    except Exception as ex:
        LOG.fatal('Could not successfully perform a test update against '
                  'simpledb domain %s, check your IAM permissions: %s',
                  repodb.domain_name, ex)
        retval = 1
    LOG.info('checking S3 bucket writability: s3://%s', repo.bucket_name)
    try:
        repo.set_key_from_string('test_key', 'test')
    except Exception as ex:
        LOG.fatal('Could not successfully write to s3://%s/test_key, '
                  'check your IAM permissions: %s', repo.bucket_name, ex)
        retval = 1
    if retval > 0:
        LOG.fatal('Repoman system health check FAILED; see above.')
    else:
        LOG.info('Repomand system health check PASSES: all systems go!')
    return retval


def create_table_data(results, headers):
    table = []
    for name in sorted(results):
        for dist in sorted(results[name]):
            for comp in sorted(results[name][dist]):
                for arch in sorted(results[name][dist][comp]):
                    pkgs = results[name][dist][comp][arch]
                    pkgs.sort(
                        key=lambda x: Dpkg.compare_versions_key(x['version']))
                    for pkg in pkgs:
                        table.append([pkg[x] for x in headers])
    return table


def validate_meta(args, repodb):
    """Preflight check: make sure any distributions, components or
    architectures specified in command line flags are ones that we
    are set up to serve."""
    ret = True
    if 'distribution' in args and args.distribution:
        bad_dists = repodb.find_invalid_metadata(args.distribution, 'dists')
        if bad_dists:
            LOG.error(' "%s" is/are not distributions that this repo '
                      'currently publishes', ','.join(bad_dists))
            ret = False
    if 'component' in args and args.component:
        bad_comps = repodb.find_invalid_metadata(args.component, 'comps')
        if bad_comps:
            LOG.error(' "%s" is/are not components that this repo '
                      'currently publishes', ','.join(bad_comps))
            ret = False
    if 'architecture' in args and args.architecture:
        bad_archs = repodb.find_invalid_metadata(args.architecture, 'archs')
        if bad_archs:
            LOG.error(' "%s" is/are not architectures that this repo '
                      'currently publishes', ','.join(bad_archs))
            ret = False
    return ret


def dump_packages(packages, repodb):
    for name, dists in iteritems(packages):
        for dist, comps in iteritems(dists):
            for comp, archs in iteritems(comps):
                for arch, items in iteritems(archs):
                    for item in items:
                        if 'files' in item:
                            msg = repodb._create_src_msg_from_item(item, dist)
                        else:
                            msg = repodb._create_pkg_msg_from_item(item, dist)
                        print(msg)


def query(args, repodb, repo):
    LOG.debug('doing package query')
    if args.query_hidden:
        # only if --query-hidden should we allow people
        # to pass in empty values here
        LOG.warning('--query-hidden: potentially returning packages that '
                    'are part of deleted distributions, components or '
                    'architectures')
        dists = args.distribution
        comps = args.component
        archs = args.architecture
    else:
        if not validate_meta(args, repodb):
            return 1
        dists = args.distribution or repodb.dists
        comps = args.component or repodb.comps
        archs = args.architecture or repodb.archs

    LOG.debug('querying simpledb')
    results = repodb.query(
        name_wildcard=args.wildcard,
        dists=dists,
        comps=comps,
        archs=archs,
        names=args.package,
        versions=args.version,
        latest_versions=args.latest_versions or 0)

    if not results.keys():
        LOG.fatal('No packages found')
        return False

    if args.outputfmt == 'json':
        print(json.dumps(results, indent=2))
    elif args.outputfmt == 'jsonc':
        print(json.dumps(results))
    elif args.outputfmt == 'packages':
        dump_packages(results, repodb)
    else:
        table = create_table_data(results, HEADERS)
        print('\n' + tabulate(table, headers=HEADERS, tablefmt=args.outputfmt))
    return 0


def confirm(args, evil=[]):
    if not evil and not args.confirm:
        LOG.warning(color(
            'You used the --confirm flag so we are proceeding '
            'without a review/confimation step. Good luck. ', fg='yellow'))
        return True
    if evil:
        for idx, message in enumerate(evil, start=1):
            LOG.warn(color(
                'Found something scary. Problem #%d:\n',
                fg='red', style='bold'), idx)
            sys.stderr.write(
                color(message, fg='black', bg='yellow', style='bold') + '\n\n')
        if args.i_fear_no_evil:
            LOG.warning(color(
                'You used the --i-fear-no-evil flag, so we are '
                'proceeding without review/confirmation even though '
                'you\'re trying to do something scary.  I hope your '
                'insurance is fully paid up...', fg='red'))
        else:
            x = 'I FEAR NO EVIL'
            while input(color(
                    '\nType exactly "%s" to proceed --> ' % x, fg='red')) != x:
                pass
    # yes, we do this even if we pass through the evil check;
    # that's intentional
    if args.confirm:
        while input(color('\nType "c" to confirm --> ', fg='cyan')) != 'c':
            pass
    return True


def cp_prompt(args, candidates, targets, evil=''):
    table = []
    headers = ['name', 'version', 'architecture', 'src dist', 'src comp',
               'dst dist', 'dst comp']
    for name, dists in iteritems(candidates):
        for dist, comps in iteritems(dists):
            for comp, archs in iteritems(comps):
                for arch, pkgs in iteritems(archs):
                    if not pkgs:
                        LOG.warning('no copy actions possible for %s=>%s=>%s',
                                    name, dist, comp)
                        continue
                    for count, pkg in enumerate(pkgs):
                        dst_dist = targets[
                            name][dist][comp][arch][count]['distribution']
                        dst_comp = targets[
                            name][dist][comp][arch][count]['component']
                        table.append(
                            [name, pkg['version'], pkg['architecture'],
                             pkg['distribution'], pkg['component'],
                             dst_dist, dst_comp])
    if not table:
        LOG.fatal('No copy actions were possible with that set of flags.')
        return False
    if not evil and len(table) > 10:
        evil.append(
            'You are about to copy a large number of packages, are '
            'you sure that\'s what you intend?')
    LOG.warning('We are about to do the following copy actions:')
    print('\n' + tabulate(table, headers=headers) + '\n')
    return confirm(args, evil)


def validate_copy_args(args, repodb):
    """Proper argument positioning for a copy operation is
    slightly fussy; make sure cli users do not shoot themselves
    in the foot."""
    evil = []
    if not validate_meta(args, repodb):
        return 1
    if args.src_distribution == args.dst_distribution and \
            args.src_component == args.dst_component:
        LOG.fatal(color(
            'The source and destination distribution and '
            'component flags cannot both match; you\'d have nothing '
            'to copy.', fg='red'))
        return 1
    if not any((args.dst_distribution, args.dst_component)):
        LOG.fatal(color(
            'You must specify at least one of a destination '
            'component or distribution when copying packages, '
            'otherwise what would be the point?', fg='red'))
        return 1
    if not any((args.package, args.version)):
        evil.append(
            'You are potentially copying up to an entire component\'s '
            'worth of packages!')
    return evil


def cp(args, repodb, repo):
    evil = validate_copy_args(args, repodb)
    if evil == 1:
        # we hit a fatal error already
        return 1
    candidates = repodb.get_candidates(
        names=args.package,
        src_dist=args.src_distribution,
        src_comp=args.src_component,
        archs=args.architecture,
        versions=args.version,
        name_wildcard=args.wildcard,
        latest_versions=args.latest_versions or 0)
    candidates, targets = repodb.get_copy_spec(
        candidates=candidates,
        src_dist=args.src_distribution,
        src_comp=args.src_component,
        dst_dist=args.dst_distribution,
        dst_comp=args.dst_component,
        prune_for_promote=args.promote)
    if cp_prompt(args, candidates, targets, evil):
        repodb.do_copy(candidates, targets, repo,
                       overwrite=args.overwrite,
                       auto_purge=args.auto_purge)
    return 0


def rm(args, repodb, repo):
    if not validate_meta(args, repodb):
        return 1
    evil = []
    if not any((args.package, args.version)) and not args.latest_versions:
        evil.append(
            'You are potentially deleting a full component '
            'or distribution!')
    if not any((args.package, args.component,
                args.distribution, args.version,
                args.latest_versions)):
        evil.append('\n\t'.join((
            '\n\t***      YOU      ***',
            '***      ARE      ***',
            '***  POTENTIALLY  ***',
            '***    DELETING   ***',
            '***     EVERY     ***',
            '***    PACKAGE    ***',
            '***      IN       ***',
            '***     THIS      ***',
            '***    ENTIRE     ***',
            '*** REPOSITORY!!! ***')))

    # stupid argparse doesn't seem to want to let us set a default
    # on a flag that stores an int inside a mutually exclusive group
    # so we have to resort to this nonsense
    if isinstance(args.latest_versions, int):
        if args.latest_versions > 0:
            # the meaning of "latest" is reversed from the sense of how
            # it's used when querying or copying:
            # `repoman rm -p foo --exclude-latest` means  delete all BUT
            # the most recent version
            args.latest_versions = -args.latest_versions
        elif args.latest_versions < 0:
            evil.append(
                'You have specified a NEGATIVE value for --exclude-versions. '
                'This means that you are going to DELETE the %s MOST RECENT '
                'packages matching your filter. Review carefully the list of '
                'packages to be deleted and consider your next move carefully.'
                % -args.latest_versions)
        elif args.latest_versions == 0:
            LOG.warning(color(
                '--exclude-recent=0 technically means the same as '
                'not using the flag at all, but the fact that you '
                'did it this way suggests that you might be a little '
                'confused about what you\'re trying to do so I\'m '
                'going to exclude the most recent versions on your '
                'behalf.', fg='red'))
            args.latest_versions = -1

    targets = repodb.query(
        names=args.package,
        dists=args.distribution,
        comps=args.component,
        versions=args.version,
        name_wildcard=args.wildcard,
        latest_versions=args.latest_versions or 0)

    if not targets.keys():
        LOG.warning('No packages to delete; try adjusting your filters.')
        return 0

    table = create_table_data(targets, HEADERS)
    if len(table) > 9:
        evil.append(
            '*** You are about to delete %d packages, which '
            'seems like a lot. Are you sure?' % len(table))
    if not table:
        LOG.info('Found no packages to delete')
        return 0

    print('\n' + tabulate(
        table, headers=HEADERS, tablefmt=args.outputfmt) + '\n')

    LOG.warning('Total packages to be deleted: %s',
                color(str(len(table)), fg='red', style='bold'))
    if confirm(args, evil):
        repodb.do_rm(targets)
    return 0


def backup(args, repodb, repo):
    # this is just like a query with no options, only we
    # also include the _meta key
    backup = {}
    backup['metadata'] = repodb._get_attributes('meta', always_list=True)
    backup['packages'] = repodb.query()
    print(json.dumps(backup, indent=2))
    return 0


def restore(args, repodb, repo):
    with open(args.filename[0]) as fp:
        js = json.loads(fp.read())
        if sorted(js.keys()) != ['metadata', 'packages']:
            LOG.fatal('Backup file corrupt: must have both '
                      'metadata and packages keys.')
            return 1
        meta = js['metadata']
        packages = js['packages']
        for name, dists in iteritems(packages):
            for dist, comps in iteritems(dists):
                for comp, archs in iteritems(comps):
                    for arch, items in iteritems(archs):
                        for item in items:
                            LOG.info('Restoring item: %s', item)
                            repodb._put_item(item)
        LOG.info('Restoring repo configuration: %s', meta)
        repodb._put_attributes('meta', meta)
    return 0


def main():
    retval = 0
    repoman_config = Config(sys.argv[1:])
    args = repoman_config.args

    if args.log_config:
        fp = open(args.log_config, encoding='utf-8')
    else:
        fp = resource_stream('apt_repoman.resources', 'logconfig.json')
    logging.config.dictConfig(json.loads(fp.read().decode()))
    fp.close()

    command = args.command
    if args.debug:
        logging.getLogger('apt_repoman').setLevel(logging.DEBUG)

    if args.region:
        LOG.warning('overriding default AWS region to: %s', args.region)

    connection = Connection(role_arn=args.aws_role, region=args.region)
    repodb = Repodb(args.simpledb_domain, connection=connection)
    repo = Repo(args.s3_bucket, connection=connection)

    funcs = globals()

    if command == 'checkup' or not args.skip_checkup:
        # don't do checkup before setup, that's silly
        if command != 'setup':
            retval += funcs['checkup'](args, repodb, repo)

    if command in ('setup', 'repo', 'add', 'cp', 'rm', 'query',
                   'backup', 'restore'):
        retval += funcs[command](args, repodb, repo)

    # never auto-publish if something above threw an error
    if retval == 0:
        if command == 'publish' or (
                'publish' in args and args.publish is True):
            retval += funcs['publish'](args, repodb, repo)

    return retval

if __name__ == '__main__':
    sys.exit(main())
