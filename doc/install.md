# Installation, Configuration and Setup

## Installation

Repoman is written in python, and should work on either python 2.7, 3.3,
3.4 or 3.5.  It can be installed via the standard python `pip` command:

```
$ pip install apt-repoman
```

(The package name is `apt-repoman` in order to distinguish it from [this
project](https://pypi.python.org/pypi/repoman/))

## Initial configuration

All configuration variables in Repoman can be set as command line flags to the
`repoman-cli` cli tool.  But for convenience, many shared flags can also be set in
a configuration file.  By default, `repoman-cli` looks first in
`/etc/repoman/repoman.conf` and then in your local home directory for a
`~/.repoman` file.  Any values provided by the local configuration file override
those in the system-wide one, and any values provided by cli flags override
both configuration files.

At a minimum for convenience, we recommend putting the name of your SimpleDB
domain and S3 bucket into a configuration file, otherwise you will have to
use the `--simpledb-domain` and `--s3-bucket` flags with each command:

```
simpledb-domain=com.example.apt.sdb
s3-bucket=repoman-demobucket
```

An example repoman configuration file can be seen in
[the docs folder](repoman.conf.example).

Remember that S3 buckets are a flat, universal namespace: your bucket name must
be unique across all AWS customers! We recommend using DNS- or classpath-style
names but with dashes instead of dots, e.g. `apt-example-com` or
`com-example-apt`.  (Avoid using dots in S3 bucket names: Amazon's wildcard TLS
certificate for `*.s3.amazonaws.com` will not validate a connection to e.g.
https://apt.example.com.s3.amazonaws.com and some s3 clients will not successfully
connect to your bucket unless you specifically configure them to use [path
addressing](http://docs.aws.amazon.com/AmazonS3/latest/dev/VirtualHosting.html).)

### Region handling

Repoman will obey the `AWS_DEFAULT_REGION` environment variable, and will also
obey region configuration in the `~/.aws/config` file; see the [boto3
configuration documentation](http://boto3.readthedocs.io/en/latest/guide/configuration.html)
for more details.

Alternatively, you can specify an AWS region to connect to with the `--region`
flag, or you can put the `region` directive into your repoman config file:


```
# force connections to a specific AWS region; if unset
# this is inherited from the environment and/or your
# ~/.aws/config configuration file; see
# http://boto3.readthedocs.io/en/latest/guide/configuration.html
# for more details
#
#region = us-east-1
```

*Note: this is different from the `--s3-region` flag/directive, which specifies
the region for the S3 bucket.*

## Authorization

Since Repoman keeps everything of value in AWS services, it follows that you need
to be able to access AWS APIs in order to do anything useful with it.

Repoman attempts to follow the principle of least surprise; it uses the [standard
AWS credentials provider](http://boto3.readthedocs.io/en/latest/guide/configuration.html)
and will attempt to find valid credentials in, in order:

1. Environment variables (`AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`)
2. Shared credential file (`~/.aws/credentials`)
3. Instance metadata service on an Amazon EC2 instance or ECS task that has an
   IAM role configured.

If you have multiple profiles set up in your ~/.aws/credentials file, you can
pass repoman-cli the `--aws-profile=foo` flag to specify the profile name to use.
You can also set it permanently in your repoman config file:

```
aws-profile=foo
```

Optionally, you can use the `--aws-role` flag to tell Repoman to attempt to
assume an IAM role before accessing any AWS APIs.  This can also be set in
your configuration file:

```
aws-role=arn:aws:iam::99999999999:role/repoman-rw
```

The value of the `aws-role` flag/config must be the fully specified ARN
of the role to assume.

If you are using the `aws-role` feature, your local credentials (from,
if you use one, the profile name) are used to call sts.AssumeRole().

## First time setup

Once you have picked the names for your bucket and domain, repoman can
initialize the repository for you, but first you have to pick a minimum of:

* one or more apt _distributions_ that your repository will serve (e.g.
  `jessie` or `xenial`)
* one or more apt _components_ that your repository will serve (e.g.
  `main` or `universe`)
* one or more apt _architectures_ that your repository will serve (e.g.
  `amd64` or `i386`)

Optionally you may set an Origin and a Label string for your repository
with the `--origin` and `--label` flags respectively.  (If left unset,
both of these will default to "repoman".)

Once you've picked those, you're ready to go:

```
$ repoman-cli setup -d xenial -c main -a amd64 -a i386 --origin example.com --label hello
INFO:repoman.cli:Setting up repoman!
WARNING:apt_repoman.repodb:Creating simpledb domain
WARNING:apt_repoman.repodb:Initializing repository database
INFO:repoman.cli:Current repo configuration:
INFO:repoman.cli:    Simpledb domain: com.example.apt
INFO:repoman.cli:    S3 bucket: s3://com-example-apt
INFO:repoman.cli:    SNS Notification topic: ---None configured---
INFO:repoman.cli:    Architectures: ['amd64', 'i386', 'all', 'source']
INFO:repoman.cli:    Distributions: ['xenial']
INFO:repoman.cli:    Components: ['main']
INFO:repoman.cli:    Origin: example.com
INFO:repoman.cli:    Label: hello
```

(The eagle-eyed will note that repoman has automatically added support for the
`all` and `source` architectures: packages with no architecture dependency will
be automatically made available to all binary architectures repoman serves.
Source packages will be automatically added to the `source` architecture.)

Optionally, you may pass the `--sns-topic` flag to `repoman-cli setup` and pass the
topic name as an argument to it; this will configure repoman to log repository
actions to an [AWS SNS]( https://aws.amazon.com/sns/) topic; see the
[Logging](logging.md) section for more details.

## System health check

Before you go any further, we recommend running the `repoman-cli checkup` command,
which will attempt to verify that you have all of the minimum necessary
configuration and permissions necessary to use repoman:

```
$ repoman-cli checkup
INFO:repoman.cli:Doing repoman system health check: set skip-checkup to suppress
INFO:repoman.cli:Current repo configuration:
INFO:repoman.cli:    Simpledb domain: com.example.apt
INFO:repoman.cli:    S3 bucket: s3://com-example-apt
INFO:repoman.cli:    SNS Notification topic: ---None configured---
INFO:repoman.cli:    Distributions: ['xenial']
INFO:repoman.cli:    Components: ['main']
INFO:repoman.cli:    Architectures: ['all', 'amd64', 'i386']
INFO:repoman.cli:    Origin: example.com
INFO:repoman.cli:    Label: hello
INFO:repoman.cli:checking whether simpledb domain exists
INFO:repoman.cli:checking simpledb domain accessibility
INFO:repoman.cli:checking simpledb repo configuration
INFO:repoman.cli:checking S3 bucket writability: s3://repoman-demobucket
INFO:repoman.cli:Repomand system health check PASSES: all systems go!
```

If the checkup passes, you're probably in very good shape.

*WARNING*: by default, the `repoman-cli` utility runs the `checkup` ahead of
every other command.  This can obviously be slow and redundant; you can
suppress this behavior with the `--skip-checkup` command or by putting
`ship-checkup` into your configuration file.
