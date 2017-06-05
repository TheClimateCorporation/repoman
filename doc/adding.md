# Adding content to Repoman

## Adding binary packages

The `repoman-cli add` command will upload any `.deb` package files to the
distribution and component of the repository that you specify:

```
$ repoman-cli add -d xenial -c main ~/testdeb*deb
INFO:repoman.cli:attempting to add file: /home/jane/testdeb_1:0.0.0-test_all.deb
INFO:repoman.cli:attempting to add package to s3: testdeb_1:0.0.0-test_all.deb
INFO:apt_repoman.repo:Attempting to upload s3://repoman-demobucket/pool/xenial/t/testdeb/testdeb_1:0.0.0-test_all.deb
INFO:repoman.cli:attempting to add package to simpledb: testdeb_1:0.0.0-test_all.deb
INFO:repoman.cli:Successfully added /home/jane/testdeb_1:0.0.0-test_all.deb to repoman!
```

Optionally, you may pass the `--publish` flag to `repoman-cli add`; this will
cause the repository to be published to S3 once all packages are added.

By default, repoman-cli will not let you upload a package file if a file of
the same name has been uploaded to S3 already.  The `--overwrite` flag
will allow you to replace a file that has already been placed in S3.

## Adding source packages

The `repoman-cli add` command will also handle [Debian Source
Control](https://wiki.debian.org/dsc) files and will add them to the
repository under the `source` architecture.  Like any other package,
they must be associated with a distribution and a component, and can
be [copied](copy.md) between distributions and components:

```
$ repoman-cli add -d xenial -c main ~/src/testdeb_1.2.1-1.dsc
INFO:repoman.cli:attempting to add file: /home/jane/src/testdeb_1.2.1-1.dsc
INFO:repoman.cli:attempting to add source to s3: testdeb_1.2.1-1.dsc
INFO:repoman.cli:Attempting to upload s3://repoman-demobucket/pool/xenial/a/testdeb/testdeb_1.2.1.orig.tar.gz
INFO:repoman.cli:Attempting to upload s3://repoman-demobucket/pool/xenial/a/testdeb/testdeb_1.2.1-1.debian.tar.xz
INFO:repoman.cli:Attempting to upload s3://repoman-demobucket/pool/xenial/a/testdeb/testdeb_1.2.1-1.dsc
INFO:repoman.cli:attempting to add source to simpledb: testdeb_1.2.1-1.dsc
INFO:repoman.cli:Successfully added /home/jane/src/testdeb_1.2.1-1.dsc to repoman!

$ repoman-cli query -p testdeb

name     distribution    component    architecture    version
-------  --------------  -----------  --------------  ---------
testdeb  xenial          main         source          1.2.1-1
testdeb  xenial          main         amd64           1.2.1-1
```

*WARNING*: any package source files listed in the dsc file
('testdeb\_1.2.1.orig.tar.gz' and 'testdeb\_1.2.1-1.debian.tar.xz' in our
example above) _must_ be in the same directory as the dsc file for Repoman to
be able to discover and add them, and they must pass all of the checksums
included in the dsc file; an error will be raised otherwise.

While Repoman will parse OpenPGP-signed dsc files, it does not currently
attempt to validate the signature.
