# Recovering deleted packages

When a package is added to Repoman, two things happen:

1. Repoman parses the package file to get some essential information
   about the package: the name, the version, the description, the
   architecture and so on.  That metadata about the package is added
   to Repoman's SimpleDB database domain, associated with the
   distribution and component of your choice.

2. The actual package file is uploaded to the Repoman S3 bucket
   in the appropriate location for its distribution and architecture.

Importantly, when a package is _deleted_ from repoman using `repoman-cli rm`, the
only thing that is actually deleted is the metadata entry in the SimpleDB
database: the actual file in S3 is still there.  Once you publish the
repository using `repoman-cli publish`, clients will no longer see the package as
available, because it's no longer listed in the `Packages` files that Repoman
generates, but the actual package can still be downloaded directly from the S3
bucket with standard S3 tooling.

This means that if a package is deleted by accident, you can simply
download the package and re-add it using `repoman-cli add` -- the only hitch
is that you'll also have to use the `--overwrite` flag since the package
still exists in S3:

*IMPORTANT*: You only need to perform this procedure if you have deleted
a particular package version from _every_ component in your distribution.
If you've deleted it from (for example) the "release" component but the
package still exists in the "nightly" component, you can restore it back
to the release component by running [repoman-cli cp](copy.md).
So for example:

```
$ repoman-cli rm -p testdeb -v 3:1.1.0-test2

name     distribution    component    architecture    version
-------  --------------  -----------  --------------  -------------
testdeb  xenial          main         amd64           3:1.1.0-test2

WARNING:repoman.cli:Total packages to be deleted: 1

Type "c" to confirm --> c
WARNING:repoman.cli:Deleting pkg testdeb version 3:1.1.0-test2 in distribution xenial component main architecture amd64
```

Oops!  We just deleted the latest version of "testdeb!"  Let's find it in S3.
For this example we'll use the [AWS CLI](https://aws.amazon.com/cli/) tool, but
you could also use the Amazon web console:

```
$ aws s3 ls s3://repoman-demobucket/pool/xenial/t/testdeb/
2017-06-21 12:15:36       1304 1:testdeb_1.0.0-test_all.deb
2017-06-21 12:15:45       1292 1:testdeb_1.1.0-test2_all.deb
2017-06-21 12:15:50       1300 1:testdeb_1.1.0-test_all.deb
2017-06-21 12:15:56       1294 2:testdeb_0.0.0-test_all.deb
2017-06-21 12:16:07       1296 3:testdeb_1.1.0-test2_amd64.deb
```

Note that the path to the package files is BUCKET/pool/DISTRIBUTION/X/name,
where 'X' is the first letter of the package name.  And there's our
poor, prematurely deleted package.  Let's bring it back to life:

```
$ aws s3 cp s3://repoman-demobucket/pool/xenial/t/testdeb/3:testdeb_1.1.0-test2_amd64.deb .
download: s3://repoman-demobucket/pool/xenial/t/testdeb/3:testdeb_1.1.0-test2_amd64.deb to ./3:testdeb_1.1.0-test2_amd64.deb

$ repoman-cli add -d xenial -c main --overwrite 3:testdeb_1.1.0-test2_amd64.deb
INFO:repoman.cli:attempting to add file: /Users/n/3:testdeb_1.1.0-test2_amd64.deb
INFO:repoman.cli:attempting to add package to s3: 3:testdeb_1.1.0-test2_amd64.deb
INFO:repoman.cli:Attempting to upload s3://repoman-demobucket/pool/xenial/t/testdeb/3:testdeb_1.1.0-test2_amd64.deb
INFO:repoman.cli:attempting to add package to simpledb: 3:testdeb_1.1.0-test2_amd64.deb
INFO:repoman.cli:Successfully added /Users/n/3:testdeb_1.1.0-test2_amd64.deb to repoman!

$ repoman-cli query -p testdeb -v 3:1.1.0-test2

name     distribution    component    architecture    version
-------  --------------  -----------  --------------  -------------
testdeb  xenial          main         amd64           3:1.1.0-test2
```

And there, it's back!
