
# stdlib imports
import logging
import sys

# pypi imports
from configargparse import ArgParser

DEFAULT_CONFIG_FILES = ('/etc/repoman/repoman.conf', '~/.repoman')

# note that we do not offer public-read-write as an option; if
# you want to do that, you can do it to yourself
S3_BUCKET_ACLS = ('private', 'public-read', 'authenticated-read')
LOG = logging.getLogger(__name__)


class Config(object):

    def __init__(self, argv=None, config_files=DEFAULT_CONFIG_FILES):
        self._log = LOG or logging.getLogger(__name__)
        self.argv = argv or sys.argv
        self._args = None
        self.config_files = config_files

    @property
    def args(self):
        if not self._args:
            self._args = self._process_args()
        return self._args

    def _process_args(self):
        flags = ArgParser(prog='repoman',
                          add_config_file_help=True,
                          ignore_unknown_config_file_keys=True,
                          default_config_files=self.config_files)
        flags.add('--config-file', required=False, is_config_file=True,
                  env_var='REPOMAN_CONFIG_FILE',
                  help='override config file path')

        # global flags
        flags.add('--simpledb-domain', action='store', required=True,
                  env_var='REPOMAN_SIMPLEDB_DOMAIN')
        flags.add('--s3-bucket', action='store', required=True,
                  env_var='REPOMAN_S3_BUCKET')
        flags.add('--aws-profile', action='store', required=False, default='',
                  env_var='REPOMAN_AWS_CREDENTIAL_PROFILE',
                  help='Use the specified profile in ~/.aws/credentials')
        flags.add('--region', action='store', required=False,
                  default=None, help='AWS region to connect to')
        flags.add('--aws-role', action='store', required=False, default='',
                  env_var='REPOMAN_AWS_ROLE',
                  help='Full ARN of IAM role to assume before calling any '
                  'other AWS APIs')
        flags.add('--log-config', action='store', required=False, default='',
                  env_var='REPOMAN_LOG_CONFIG',
                  help='path to a JSON file with a python log configuration ')
        flags.add('--skip-checkup', action='store_true',
                  required=False, default=False,
                  help='do not run system health checkup on every action')
        flags.add('--debug', action='store_true', required=False,
                  default=False, help='debug logging')
        flags.add('--gpg-home',
                  required=False, env_var='REPOMAN_GPG_HOME',
                  default='~/.gnupg',
                  help='set path to gpg keyring')
        flags.add('--gpg-signer', action='append',
                  required=False, help='gpg identity to sign as')
        flags.add('--gpg-pinentry-path', action='store',
                  default='/usr/bin/pinentry',
                  required=False, help='path to gpg pinentry program')
        flags.add('--gpg-passphrase', action='append',
                  required=False,
                  help='passphrase for gpg secret key for signing '
                  '(if multiple, must be in same order as --gpg-signer)')
        flags.add('--auto-purge', action='store', default=0,
                  type=int, required=False,
                  help='automatically purge packages older than the '
                  'last N revisions when adding or copying')

        # subparsers for commands
        commands = flags.add_subparsers(dest='command')

        # singelton commands
        commands.add_parser('checkup', help='check that all systems are go')
        commands.add_parser('backup',
                            help='dump the simpledb state to a JSON file')

        # restore command
        restore_flags = commands.add_parser(
            'restore', help='restore simpledb state from a JSON file')
        restore_flags.add(
            'filename', nargs=1, help='path to backup file')

        # commands that take flags
        setup_flags = commands.add_parser(
            'setup',
            help='do initial system configuration: create simpledb domain '
                 'and s3 bucket, specify at least one each architecture, '
                 'distribution and component to publish.'
        )
        repo_flags = commands.add_parser(
            'repo', help='repo management commands')
        add_flags = commands.add_parser(
            'add', help='add package files to repo')
        cp_flags = commands.add_parser(
            'cp', help='move packages between components and distributions')
        rm_flags = commands.add_parser(
            'rm', help='remove specific packages from repo')
        publish_flags = commands.add_parser(
            'publish', help='publish the repository to s3')
        query_flags = commands.add_parser(
            'query', help='query the repository')

        # command flags

        # query
        query_flags.add('-a', '--architecture',
                        action='append', required=False,
                        help='narrow query by architecture(s)')
        query_flags.add('-d', '--distribution',
                        action='append', required=False,
                        help='narrow query by distribution(s)')
        query_flags.add('-c', '--component',
                        action='append', required=False,
                        help='narrow query by component(s)')
        query_flags.add('-p', '--package',
                        action='append', required=False,
                        help='narrow query by package name(s)')
        query_flags.add('-w', '--wildcard', action='store_true', default=False,
                        help='match package names to left of --package flag')
        query_flags.add('-H', '--query-hidden', action='store_true',
                        default=False,
                        help='include packages "hidden" by the removal of '
                        'their distribution/component/architecture')
        query_flags.add('-f', '--format', action='store',
                        dest='outputfmt', default='simple',
                        choices=('json', 'jsonc', 'packages', 'simple',
                                 'plain', 'grid', 'fancy_grid', 'pipe',
                                 'orgtbl', 'jira', 'psql', 'rst', 'mediawiki',
                                 'moinmoin', 'html', 'latex', 'latex_booktabs',
                                 'textile'),
                        help='select output format for querys & rm/cp prompts')
        query_latest = query_flags.add_mutually_exclusive_group()
        query_latest.add('-v', '--version', action='append',
                         help='only return packages matching these versions')
        query_latest.add('-l', '--latest', action='store_const',
                         dest='latest_versions', const=1,
                         help='only return the most recent package version '
                         '(equivalent to `--recent 1`)')
        query_latest.add('-r', '--recent', action='store', default=0,
                         type=int, dest='latest_versions',
                         help='only return the N most recent package versions')

        # setup
        setup_flags.add('-a', '--architecture',
                        action='append', required=True,
                        help='specify at least one architecture')
        setup_flags.add('-d', '--distribution',
                        action='append', required=True,
                        help='specify at least one distribution')
        setup_flags.add('-c', '--component',
                        action='append', required=True,
                        help='specify at least one component')
        setup_flags.add('--s3-acl', action='store',
                        default='private', required=False,
                        choices=S3_BUCKET_ACLS,
                        help='set a canned ACL for the S3 bucket '
                        '(default is private)')
        setup_flags.add('--s3-region', action='store', required=False,
                        help='set region for s3 bucket '
                        '(default is us-east-1 AKA US/Standard)')
        setup_flags.add('--sns-topic', action='store', required=False,
                        help='AWS SNS topic name for logging')
        setup_flags.add('--origin', action='store', required=False,
                        help='origin string for repository')
        setup_flags.add('--label', action='store', required=False,
                        help='label string for repository')
        setup_flags.add('--enable-website', action='store_true',
                        required=False, default=False,
                        help='configure public website hosting for '
                        'the S3 bucket. Implies --s3-acl=public-read')

        # repo management operations
        repo_commands = repo_flags.add_subparsers(dest='repo_command')
        repo_add_architecture_flags = repo_commands.add_parser(
            'add-architecture', help='add a architecture to repo')
        repo_add_architecture_flags.add(
            'architecture_names', nargs='+', help='architecture to add')
        repo_add_architecture_flags.add(
            '--i-fear-no-evil', action='store_true',
            default=False, required=False,
            help='skip confirmation step for scary actions')
        raa_confirm = \
            repo_add_architecture_flags.add_mutually_exclusive_group()
        raa_confirm.add('--confirm', action='store_true', dest='confirm',
                        required=False, default=True,
                        help='confirm any mutating actions')
        raa_confirm.add('-y', '--no-confirm', action='store_false',
                        dest='confirm', required=False, default=False,
                        help='do not prompt for confirmation')

        repo_rm_architecture_flags = repo_commands.add_parser(
            'rm-architecture', help='remove a architecture from repo')
        repo_rm_architecture_flags.add(
            'architecture_names', nargs='+', help='architecture to remove')
        repo_rm_architecture_flags.add(
            '--i-fear-no-evil', action='store_true',
            default=False, required=False,
            help='skip confirmation step for scary actions')
        rra_confirm = repo_rm_architecture_flags.add_mutually_exclusive_group()
        rra_confirm.add('--confirm', action='store_true', dest='confirm',
                        required=False, default=True,
                        help='confirm any mutating actions')
        rra_confirm.add('-y', '--no-confirm', action='store_false',
                        dest='confirm', required=False, default=False,
                        help='do not prompt for confirmation')

        repo_add_distribution_flags = repo_commands.add_parser(
            'add-distribution', help='add a distribution to repo')
        repo_add_distribution_flags.add(
            'distribution_names', nargs='+', help='distribution to add')
        repo_add_distribution_flags.add(
            '--i-fear-no-evil', action='store_true',
            default=False, required=False,
            help='skip confirmation step for scary actions')
        rad_confirm = \
            repo_add_distribution_flags.add_mutually_exclusive_group()
        rad_confirm.add('--confirm', action='store_true', dest='confirm',
                        required=False, default=True,
                        help='confirm any mutating actions')
        rad_confirm.add('-y', '--no-confirm', action='store_false',
                        dest='confirm', required=False, default=False,
                        help='do not prompt for confirmation')

        repo_rm_distribution_flags = repo_commands.add_parser(
            'rm-distribution', help='remove a distribution from repo')
        repo_rm_distribution_flags.add(
            'distribution_names', nargs='+', help='distribution to remove')
        repo_rm_distribution_flags.add(
            '--i-fear-no-evil', action='store_true',
            default=False, required=False,
            help='skip confirmation step for scary actions')
        rrd_confirm = repo_rm_distribution_flags.add_mutually_exclusive_group()
        rrd_confirm.add('--confirm', action='store_true', dest='confirm',
                        required=False, default=True,
                        help='confirm any mutating actions')
        rrd_confirm.add('-y', '--no-confirm', action='store_false',
                        dest='confirm', required=False, default=False,
                        help='do not prompt for confirmation')

        repo_add_component_flags = repo_commands.add_parser(
            'add-component', help='add a component to repo')
        repo_add_component_flags.add(
            'component_names', nargs='+', help='component to add')
        repo_add_component_flags.add(
            '--i-fear-no-evil', action='store_true',
            default=False, required=False,
            help='skip confirmation step for scary actions')
        rac_confirm = repo_add_component_flags.add_mutually_exclusive_group()
        rac_confirm.add('--confirm', action='store_true', dest='confirm',
                        required=False, default=True,
                        help='confirm any mutating actions')
        rac_confirm.add('-y', '--no-confirm', action='store_false',
                        dest='confirm', required=False, default=False,
                        help='do not prompt for confirmation')

        repo_rm_component_flags = repo_commands.add_parser(
            'rm-component', help='remove a component from repo')
        repo_rm_component_flags.add(
            'component_names', nargs='+', help='component to remove')
        repo_rm_component_flags.add(
            '--i-fear-no-evil', action='store_true',
            default=False, required=False,
            help='skip confirmation step for scary actions')
        rrc_confirm = repo_rm_component_flags.add_mutually_exclusive_group()
        rrc_confirm.add('--confirm', action='store_true', dest='confirm',
                        required=False, default=True,
                        help='confirm any mutating actions')
        rrc_confirm.add('-y', '--no-confirm', action='store_false',
                        dest='confirm', required=False, default=False,
                        help='do not prompt for confirmation')

        repo_add_topic_flags = repo_commands.add_parser(
            'add-topic', help='send notifications to an SNS topic')
        repo_add_topic_flags.add('topic_name', nargs=1, action='store',
                                 help='SNS topic to configure for logging')
        rat_confirm = repo_add_topic_flags.add_mutually_exclusive_group()
        rat_confirm.add('--confirm', action='store_true', dest='confirm',
                        required=False, default=True,
                        help='confirm any mutating actions')
        rat_confirm.add('-y', '--no-confirm', action='store_false',
                        dest='confirm', required=False, default=False,
                        help='do not prompt for confirmation')

        repo_rm_topic_flags = repo_commands.add_parser(
            'rm-topic', help='remove SNS topic logging')
        rrt_confirm = repo_rm_topic_flags.add_mutually_exclusive_group()
        rrt_confirm.add('--confirm', action='store_true', dest='confirm',
                        required=False, default=True,
                        help='confirm any mutating actions')
        rrt_confirm.add('-y', '--no-confirm', action='store_false',
                        dest='confirm', required=False, default=False,
                        help='do not prompt for confirmation')

        repo_commands.add_parser('show-config',
                                 help='show current repo configuration')

        repo_add_origin_flags = repo_commands.add_parser(
            'add-origin', help='set the repository origin string')
        repo_add_origin_flags.add('origin', nargs=1, action='store',
                                  help='origin string')
        rao_confirm = repo_add_origin_flags.add_mutually_exclusive_group()
        rao_confirm.add('--confirm', action='store_true', dest='confirm',
                        required=False, default=True,
                        help='confirm any mutating actions')
        rao_confirm.add('-y', '--no-confirm', action='store_false',
                        dest='confirm', required=False, default=False,
                        help='do not prompt for confirmation')

        repo_add_label_flags = repo_commands.add_parser(
            'add-label', help='set the repository label string')
        repo_add_label_flags.add('label', nargs=1, action='store',
                                 help='label string')
        ral_confirm = repo_add_label_flags.add_mutually_exclusive_group()
        ral_confirm.add('--confirm', action='store_true', dest='confirm',
                        required=False, default=True,
                        help='confirm any mutating actions')
        ral_confirm.add('-y', '--no-confirm', action='store_false',
                        dest='confirm', required=False, default=False,
                        help='do not prompt for confirmation')

        repo_commands.add_parser('show-config',
                                 help='show current repo configuration')
        # add packages
        add_flags.add('-d', '--distribution', action='append', required=True,
                      help='add to specified distribution')
        add_flags.add('-c', '--component', action='append', required=True,
                      help='add to specified component')
        add_flags.add('--overwrite',
                      action='store_true', required=False, default=False,
                      help='re-upload packages even if they already exist '
                      'in the repository')
        add_flags.add('--publish',
                      action='store_true', required=False, default=False,
                      help='publish the repo to s3 after adding packages')
        add_flags.add('files', nargs='+', help='debian package files to add')

        # copy
        cp_flags.add('--src-distribution', action='store', required=True,
                     help='specify one or more distributions to copy from')
        cp_flags.add('--dst-distribution', action='store',
                     help='specify one or more distributions to copy to')
        cp_flags.add('--src-component', action='store', required=True,
                     help='specify one or more components to copy from')
        cp_flags.add('--dst-component', action='store',
                     help='specify one or more components to copy to')
        cp_flags.add('-a', '--architecture', action='append', required=False,
                     help='limit to specified architectures')
        cp_flags.add('-p', '--package', action='append',
                     help='specify one or more package names to act on')
        cp_flags.add('--overwrite',
                     action='store_true', required=False, default=False,
                     help='re-upload packages even if they already exist '
                     'in the repository -- this only applies to cross-'
                     'distribution copies')
        cp_flags.add('--promote',
                     action='store_true', required=False, default=False,
                     help='only copy files where the latest source version '
                     'is more recent than the latest destination version ')
        cp_flags.add('-w', '--wildcard', action='store_true', default=False,
                     help='match package names to left of --package flag')
        cp_latest = cp_flags.add_mutually_exclusive_group()
        cp_latest.add('-v', '--version', action='append',
                      help='only copy packages matching these versions')
        cp_latest.add('-l', '--latest', action='store_const',
                      dest='latest_versions', const=1,
                      help='only copy the most recent package version '
                      '(equivalent to `--recent 1`)')
        cp_latest.add('-r', '--recent', action='store', default=0,
                      type=int, dest='latest_versions',
                      help='only copy the N most recent package versions')
        cp_flags.add('--i-fear-no-evil', action='store_true',
                     default=False, required=False,
                     help='skip confirmation step for scary actions')
        cp_confirm = cp_flags.add_mutually_exclusive_group()
        cp_confirm.add('--confirm', action='store_true', dest='confirm',
                       required=False, default=True,
                       help='confirm any mutating actions')
        cp_confirm.add('-y', '--no-confirm', action='store_false',
                       dest='confirm', required=False, default=False,
                       help='do not prompt for confirmation')

        # remove
        rm_flags.add('-a', '--architecture', action='append', required=False,
                     help='limit to specified architectures')
        rm_flags.add('-d', '--distribution', action='append', required=False,
                     help='limit to specified distributions')
        rm_flags.add('-c', '--component', action='append', required=False,
                     help='limit to specified distributions')
        rm_flags.add('-p', '--package', action='append', required=False,
                     help='limit to specified package names')
        rm_flags.add('--remove-from-s3', action='store_true',
                     default=False, required=False,
                     help='remove package files from s3')
        rm_flags.add('--publish', action='store_true', required=False,
                     default=False, help='publish the repo to s3')
        rm_flags.add('-w', '--wildcard', action='store_true', default=False,
                     help='match package names to left of --package flag')
        rm_flags.add('-H', '--rm-hidden', action='store_true',
                     default=False,
                     help='include packages "hidden" by the removal of '
                     'their distribution/component/architecture')
        rm_flags.add('--i-fear-no-evil', action='store_true',
                     default=False, required=False,
                     help='skip confirmation step for scary actions')
        rm_flags.add('-f', '--format', action='store',
                     dest='outputfmt', default='simple',
                     choices=('json', 'jsonc', 'simple', 'plain', 'grid',
                              'fancy_grid', 'pipe', 'orgtbl', 'jira',
                              'psql', 'rst', 'mediawiki', 'moinmoin',
                              'html', 'latex', 'latex_booktabs', 'textile'),
                     help='select output format for querys & rm/cp prompts')
        rm_latest = rm_flags.add_mutually_exclusive_group()

        rm_latest.add('-v', '--version', action='append',
                      help='only delete packages matching these versions')
        rm_latest.add('-l', '--exclude-latest', action='store_const',
                      dest='latest_versions', const=1,
                      help='only delete the most recent package version '
                      '(equivalent to `--recent 1`)')
        rm_latest.add('-r', '--exclude-recent', action='store', default=0,
                      type=int, dest='latest_versions',
                      help='only delete the N most recent package versions')

        rm_confirm = rm_flags.add_mutually_exclusive_group()
        rm_confirm.add('--confirm', action='store_true', dest='confirm',
                       required=False, default=True,
                       help='confirm any mutating actions')
        rm_confirm.add('-y', '--no-confirm', action='store_false',
                       dest='confirm', required=False, default=False,
                       help='do not prompt for confirmation')

        # publish to s3
        publish_flags.add('-d', '--distribution', action='append',
                          required=False,
                          help='limit to specified distributions '
                               '(default is all)')

        config = flags.parse_args(self.argv)
        return config
