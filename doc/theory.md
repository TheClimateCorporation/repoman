# Theory of operation

## Separation of duties

Unlike traditional apt repository managers (e.g.
[dpkg-scanpackages](http://manpages.ubuntu.com/manpages/xenial/man1/dpkg-scanpackages.1.html)),
repoman separates _package metadata_ (ie: information about which packages
you have and which distributions/components/architectures they are
associated with) into a queryable database seperate from the _repository_,
which holds the package files themselves and the repository summary files
that tell apt clients which packages are available in the repo.

In simpler terms: just adding a package to Repoman won't automatically
make it visible to your users.  You have to _publish_ the repository, which
generates new apt configuration files, optionally signs them with your
GPG key, and uploads them to S3.

It is very common when using repoman to do a large number of actions
such as adding/removing packages or copying them between components, and
then only to publish the updated repository to S3 as the last step.

## Multiple versions

Unlike the traditional
[reprepro](https://mirrorer.alioth.debian.org/reprepro.1.html) repository
manager, Repoman allows for there to be multiple versions of the same package
(relative to the distribution, component and architecture) present at the same
time.  This allows potentially for fast rollbacks or for locally pinning older
versions on clients, but means that the Repoman operator must make some
decisions about when and where to purge older versions from the database.  See
the documentation for [repoman-cli rm](remove.md) and the `--autopurge` flag for
more details.

## SimpleDB, really?

Sigh, yes, really.

Part of it is simple temporal logistics: DynamoDB didn't exist in 2011, and for
that matter neither did Amazon RDS.  So our options for a hosted data store on
AWS were limited: it was SimpleDB or try to write a properly denormalized
schema for an apt repository and self-host a postgres server for it.

But for all that, SimpleDB turned out to be a reasonably good fit for the
project: the combination of a schemaless data model combined with a SQL-esque
query language worked surprisingly well for tracking what is basically a small
amount (by modern "big data" standards) of RFC822-esque message documents.
It's not the fastest thing in the world, but it's not in the critical path for
apt clients, just administrators of the repository itself.

There's something to be said for a no-smarter-than-necessary data store that
just ticks along quitely over the years without complaint. One day we'd like to
find the one remaining engineer at Amazon still tasked with keeping SimpleDB up
and running, and buy her or him a drink.
