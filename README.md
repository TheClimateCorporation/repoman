# Repoman: a scalable apt server using Amazon SimpleDB and S3

## Introduction

Back in 2011, a scrappy young startup called "Weatherbill" found itself with a
conundrum: we were using Debian's `dpkg` and `apt` tools to package and serve
binary software within our own infrastructure, but we were also starting to use
Amazon's Elastic Mapreduce to create ephemeral Hadoop clusters for geospatial
and weather data processing, and it turned out that spinning up a 2,000-node
Hadoop cluster and downloading several dozen gigabytes of packages from our
standalone apt server onto each Hadoop compute node at once was an excellent
way to make the apt server vanish in a puff of smoke.

So with the optimism that comes from youth and too much caffiene, we wrote our
own apt server, based on Amazon's Simple Storage Service (S3) and SimpleDB
offerings.  We called it "Repoman", because the life of a repo man, much like
that of an engineer at a small startup, is always intense.  And since then,
Repoman has successfully served millions of packages to various servers and
services here at The Climate Corporation (which Weatherbill became) and we're
happy to finally get a chance to share it with you.

## Requirements

In order to operate an apt repository with Repoman, you will need at
a minimum:

- A working Python 2.7 or 3.5 installation
- An Amazon Web Services account
- User credentials in that AWS account, either in your shell environment,
  a `~/.aws/Credentials` file, or via an EC2 Instance Profile or ECS Task
  Role.  In general if the [AWS CLI](https://github.com/aws/aws-cli) runs
  successfully in your environment, Repoman should run.
- An [AWS SimpleDB Domain](http://docs.aws.amazon.com/AmazonSimpleDB/latest/DeveloperGuide/DataModel.html)
  which Repoman will use to store metadata about your packages.
- An [AWS S3 Bucket](http://docs.aws.amazon.com/AmazonS3/latest/dev/UsingBucket.html)
  which Repoman will use to store your actual `.deb` package files and
  also the generated metadata files that form an Apt repository.
- Your user credentials must have sufficient permissions (via [Amazon IAM](https://aws.amazon.com/documentation/iam/))
  to manipulate both the SimpleDB domain and the S3 bucket: you will need at a
  minimum to be able to create and delete keys in both.  A sample IAM security
  policy is provided in [the docs folder](doc/iam_policy.json)

Some basic familiarity with the concepts and nomenclature of running an apt
server is assumed: if you don't know what distributions, components and
architectures are, you may want to review [the apt
documentation](https://wiki.debian.org/DebianRepository)

### Optional

- Repoman can function with your own user credentials, or it can assume an IAM
  role before querying AWS APIs; see the [installation](doc/install.md) section
  for details on how to use roles.
- Repoman can [sign your apt repository's metadata files](https://wiki.debian.org/SecureApt)
  in order to provide strong assurances that the packages in the repo
  come from their claimed source. You will need a working GPG keyring,
  and key management is not provided by Repoman.

## Commands, flags and help

The `repoman-cli` cli tool offers the following commands:

* `setup` -- initial setup of the repository
* `checkup` -- check that SimpleDB and S3 are configured correctly
* `add` -- add packages to the repository
* `rm` -- delete packages from the repository
* `cp` -- copy packages from one distribution or component in the
  repository to another distribution or complnent
* `query` -- list packages in the repository based on filters
* `publish` -- publish the current SimpleDB repository to state to S3
* `backup` -- backup the current SimpleDB state to a JSON file
* `restore` -- restore SimpleDB state from a JSON file
* `repo` -- repository management sub-commands:
    * `repo add-distribution` -- add a distribution for the repo to serve
    * `repo rm-distribution` -- remove a distribution for the repo to serve
    * `repo add-component` -- add a component for the repo to serve
    * `repo rm-component` -- remove a component for the repo to serve
    * `repo add-architecture` -- add a architecture for the repo to serve
    * `repo rm-architecture` -- remove a architecture for the repo to serve
    * `repo add-topic` -- add an SNS topic to log notifications to
    * `repo rm-topic` -- remove any configured SNS topic
    * `repo show-config` -- show the current repository configuration
    * `repo add-origin` -- set an Origin string for the published repository
    * `repo add-label` -- set a Label string for the published repository

The `repoman-cli` utility itself and all of its commands and sub-commands will
take a `-h` or `--help` flag to show help text and all locally relevant flags.

Most commands that mutate the repository will prompt for confirmation;
this step can be bypassed by passing the `-y` or `--confirm` flag.

Some particularly dangerous commands (e.g. deleting an entire distribution's
worth of packages) will prompt for an _extra_ confirmation step; this too
can be bypassed by passing in the `--i-fear-no-evil` flag but this is a
_strictly_ at-your-own-risk proposition.

To automatically publish the repository to s3 after adding, copying or
removing packages, pass the `--publish` flag.

## Further Documentation

* Basic operations
    * [Theory of Operation](doc/theory.md)
    * [Installation, Configuration and Setup](doc/install.md)
    * [Adding binary and source packages to Repoman](doc/adding.md)
    * [Querying the repository](doc/query.md)
    * [Publishing and signing the repository](doc/publish.md)
    * [Copying and promoting packages within the repository](doc/copy.md)
    * [Removing and purging pacakges within the repository](doc/remove.md)
* Advanced topics
    * [Adding and removing sections (distributions, components, architectures) from the repository](doc/repomgt.md)
    * [Subscribing apt clients to the repository](doc/clients.md)
    * [Serving public repositories directly from S3](doc/public.md)
    * [Backups and restores](doc/backup.md)
    * [Logging and notifications](doc/logging.md)
    * [Recovering deleted packages](doc/recover.md)

