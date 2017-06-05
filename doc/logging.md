# Logging and notifications

## Local log configuration

By default, the repoman cli logs info/warning/error messages to stderr.

The `--debug` flag can be passed in to get more visibility under the hood:

```
$ repoman-cli --debug query -p testdeb
2017-06-24 09:44:51,262 - apt_repoman.cli - DEBUG - doing package query
2017-06-24 09:44:51,262 - apt_repoman.connection - DEBUG - getting an AWS session with the default provider
2017-06-24 09:44:53,864 - apt_repoman.cli - DEBUG - querying simpledb
2017-06-24 09:44:53,864 - apt_repoman.repodb - DEBUG - query: select * from `com.example.apt` where `name` is not null and every(name) in ('testdeb') and every(distribution) in ('jessie','xenial') and every(component) in ('main','nightly') and every(architecture) in ('all','amd64','i386','source')

name     distribution    component    architecture    version
-------  --------------  -----------  --------------  -------------
testdeb  jessie          main         all             3:1.1.0-test2
```

You can also put `debug` into your [repoman config file](install.md) to
permanently enable debug logging.

For more fine-grained control over log output, including setting log levels for
underlying libraries (notably `boto3` and `botocore`) and enabling logging to
files, you can use the `--log-config` flag to point to a Python logging
configuration file in JSON format.  The default logging configuration file can
be seen in [doc/logconfig.json](../apt_repoman/resources/logconfig.json).

For more information on how to configure Python logging, see the
[logging.config.dictConfig dictionary schema
definition](https://docs.python.org/2/library/logging.config.html#configuration-dictionary-schema)
in the Python manual.

## SNS Notifications

Repoman may optionally be configured to log notifications of mutating actions
(ie: add/remove/copy packages, changes to the repo configuration) to an 
[Amazon Simple Notifications Service](https://aws.amazon.com/sns/)
topic.  The log messages are in JSON format, suitable for ingestion into log
aggregations services such as Elasticsearch/Logstash/Kibana or Loggly.  Users
may also subscribe directly to receive alerts as email or SNS messages.

For further information about how to use SNS topics and notifications, we
recommend perusing the [AWS SNS
Documentation](http://docs.aws.amazon.com/sns/latest/dg/welcome.html)

Configuring logging can be done at initial setup time:

```
# repoman-cli setup -a amd64 -d xenial -c main --sns-topic repoman-notifications
INFO:repoman.cli:Setting up repoman!
INFO:repoman.cli:Creating simpledb domain
INFO:repoman.cli:Initializing repository database
INFO:repoman.cli:Current repo configuration:
INFO:repoman.cli:    Simpledb domain: com.example.apt
INFO:repoman.cli:    S3 bucket: s3://repoman-demobucket
INFO:repoman.cli:    SNS Notification topic: repoman-notifications
INFO:repoman.cli:    Distributions: ['xenial']
INFO:repoman.cli:    Components: ['main']
INFO:repoman.cli:    Architectures: ['all', 'amd64', 'i386']
```

Logging can also be added after the fact with the `repoman-cli repo add-topic`
command:

```
$ repoman-cli repo add-topic repoman-notifications
WARNING:repoman.cli:Setting up SNS topic "repoman-notifications" for logging

Type "c" to confirm --> c
INFO:repoman.cli:Adding SNS topic for logging: repoman-notifications
INFO:repoman.cli:Current repo configuration:
INFO:repoman.cli:    Simpledb domain: com.example.apt
INFO:repoman.cli:    S3 bucket: s3://repoman-demobucket
INFO:repoman.cli:    SNS Notification topic: repoman-notifications
INFO:repoman.cli:    Distributions: ['xenial']
INFO:repoman.cli:    Components: ['main']
INFO:repoman.cli:    Architectures: ['all', 'amd64', 'i386']
```

Logging can be disabled with the `repoman-cli repo rm-topic` command:

```
$ repoman-cli repo rm-topic
WARNING:repoman.cli:Disabling SNS logging!

Type "c" to confirm --> c
INFO:repoman.cli:Deleting SNS topic for logging
INFO:repoman.cli:Current repo configuration:
INFO:repoman.cli:    Simpledb domain: com.example.apt
INFO:repoman.cli:    S3 bucket: s3://repoman-demobucket
INFO:repoman.cli:    SNS Notification topic: ---None configured---
INFO:repoman.cli:    Distributions: ['xenial']
INFO:repoman.cli:    Components: ['main']
INFO:repoman.cli:    Architectures: ['all', 'amd64', 'i386']
```

### Package add notification format

```
{"action": "add",
 "type": "package",
 "name": str,
 "version": str,
 "distribution": str,
 "component": str,
 "caller": str}
```

The `caller` key in the JSON will contain the IAM ARN of the user or role who
executed the action

### Package delete notification format

```
{"action": "delete",
 "type": "package",
 "name": str,
 "version": str,
 "distribution": str,
 "component": str,
 "caller": str}
```

The `caller` key in the JSON will contain the IAM ARN of the user or role who
executed the action

### Package copy notification format

```
{"action": "copy",
 "type": "package",
 "name": str,
 "version": str,
 "src_distribution": str,
 "src_component": str,
 "dst_distribution": str,
 "dst_component": str,
 "caller": str}
```

The `caller` key in the JSON will contain the IAM ARN of the user or role who
executed the action

### Repo configuration update format

```
 {"action": ('add' | 'delete'),
  "type": ('dists', 'comps', 'archs', 'sns_topic'),
  "name": str,
  "caller": str}
```

The `caller` key in the JSON will contain the IAM ARN of the user or role who
executed the action
