# Querying the repository

The `repoman-cli query` command allows you to see the current state of the
repository.

By default and with no flags, `repoman-cli query` will list out every package in
every distribution, component and architecture that the repo currently is
configured to serve, but you can narrow down the query by means of the
following flags:

* `-p` or `--package` will only show packages with a name matching the one given
* `-w` or `--wildcard` will make the name given in the `-p` flag a wildcard match, ie. `-p test`
  will return packages named both "test" and "testamundo" and "testacular" if they exist.
* `-d` or `--distribution` will only show packages belonging to the specified distribution
* `-c` or `--component` will only show packages belonging to the specified component
* `-a` or `--architecture` will only show packages belonging to the specified architecture
* `-v` or `--version` will only show packages with a version matching the one given
* `-r` or `--recent` will return only the N newest packages (by debian version
  sorting order) by distribution/component/architecture
* `-l` or `--latest` will return only the most recent package; this is equivalent to `--recent 1`
* `-H` or `--query-hidden` will include packages belonging to distributions/components/architectures
  that have been deleted from the repo configuration; by default these are ignored.
* `-f` or `--format` lets you specify the output format of the query command;
  see the "Query output formats" section below

Query flags that take an argument can be specified multiple times and are ORed
internally when making the query: `repoman-cli query -d xenial -d trusty` will return
the entire list of packages for _both_ the trusty and xenial distributions for
example.

Adding multiple query flags of different types is an AND operation internally,
for example `repoman-cli query -c main -c universal -p testdeb -v 2:0.0.0-test`
will return only packages with the name "testdeb" _and_ the version "1:0.0.0"
in _either_ the "main" or "universal" components:

```
$ repoman-cli query -p testdeb -c main -c universal -v 2:0.0.0-test

name     distribution    component    architecture    version
-------  --------------  -----------  --------------  ------------
testdeb  xenial          main         all             2:0.0.0-test
testdeb  xenial          universal    all             2:0.0.0-test
```

## Query output formats

The Repoman cli uses the [Python
Tabulate](https://pypi.python.org/pypi/tabulate) module to format its output
and supports all of the output formats that Tabulate does:

* plain
* simple
* grid
* fancy\_grid
* pipe
* orgtbl
* jira
* psql
* rst
* mediawiki
* moinmoin
* html
* latex
* latex\_booktabs
* textile

By default, Repoman uses the "simple" format, and all examples in this guide
are presented using it.

In addition, repoman supports the following three formats:

* json
* jsonc
* packages

The "json" and "jsonc" formats are both dumps of the package data in JSON
format; the only difference between them is that "jsonc" does not put any line
breaks or whitespace into it output: the "c" is for "compact".

The json/jsonc formats dump package data as a nested JSON object, in the form
`{packagename: {distribution: {component: {architecture: package}}}}`, for
example:

```
$ repoman-cli query -p testdeb -c main -c universal -v 2:0.0.0-test -f json

{
  "testdeb": {
    "xenial": {
      "universal": {
        "all": [
          {
            "sha1": "2e3f6aca44459898fd1e05ab659ba1cd0aa9a613",
            "name": "testdeb",
            "component": "universal",
            "filename": "2:testdeb_0.0.0-test_all.deb",
            "version": "2:0.0.0-test",
            "controltxt0": "Package: testdeb\nVersion: 2:0.0.0-test\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: all\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n",
            "architecture": "all",
            "distribution": "xenial",
            "sha256": "7f29b9631765fb459c046fbda1586767e4d8a9ad330dff86bfae91c684aa3f30",
            "md5": "c8cd10216d5e99a18971c80531d10b01",
            "size": "1294"
          }
        ]
      },
      "main": {
        "all": [
          {
            "sha1": "2e3f6aca44459898fd1e05ab659ba1cd0aa9a613",
            "name": "testdeb",
            "component": "main",
            "filename": "2:testdeb_0.0.0-test_all.deb",
            "version": "2:0.0.0-test",
            "controltxt0": "Package: testdeb\nVersion: 2:0.0.0-test\nLicense: unknown\nVendor: n@C02SV1F1G8WL\nArchitecture: all\nMaintainer: <n@C02SV1F1G8WL>\nInstalled-Size: 0\nSection: default\nPriority: extra\nHomepage: http://example.com/no-uri-given\nDescription: no description given\n\n",
            "architecture": "all",
            "distribution": "xenial",
            "sha256": "7f29b9631765fb459c046fbda1586767e4d8a9ad330dff86bfae91c684aa3f30",
            "md5": "c8cd10216d5e99a18971c80531d10b01",
            "size": "1294"
          }
        ]
      }
    }
  }
}
```

The "packages" format dumps the package data an the same format as an apt
repository `Packages` file: a sequence of RFC822 messages.  For example:

```
$ repoman-cli query -p testdeb -c main -c universal -v 2:0.0.0-test -f packages

Filename: pool/xenial/t/testdeb/2:testdeb_0.0.0-test_all.deb
MD5sum: c8cd10216d5e99a18971c80531d10b01
SHA1: 2e3f6aca44459898fd1e05ab659ba1cd0aa9a613
SHA256: 7f29b9631765fb459c046fbda1586767e4d8a9ad330dff86bfae91c684aa3f30
Size: 1294
Package: testdeb
Version: 2:0.0.0-test
License: unknown
Vendor: n@C02SV1F1G8WL
Architecture: all
Maintainer: <n@C02SV1F1G8WL>
Installed-Size: 0
Section: default
Priority: extra
Homepage: http://example.com/no-uri-given
Description: no description given

Filename: pool/xenial/t/testdeb/2:testdeb_0.0.0-test_all.deb
MD5sum: c8cd10216d5e99a18971c80531d10b01
SHA1: 2e3f6aca44459898fd1e05ab659ba1cd0aa9a613
SHA256: 7f29b9631765fb459c046fbda1586767e4d8a9ad330dff86bfae91c684aa3f30
Size: 1294
Package: testdeb
Version: 2:0.0.0-test
License: unknown
Vendor: n@C02SV1F1G8WL
Architecture: all
Maintainer: <n@C02SV1F1G8WL>
Installed-Size: 0
Section: default
Priority: extra
Homepage: http://example.com/no-uri-given
Description: no description given
```

## Useful query examples

### Show the latest version of a package in all dists/comp/archs

```
$ repoman-cli query -p testdeb --latest

name     distribution    component    architecture    version
-------  --------------  -----------  --------------  ------------
testdeb  xenial          main         all             2:0.0.0-test
testdeb  xenial          universal    all             2:0.0.0-test
```

### Show the latest version of every package in a particular component+distribution

```
$ repoman-cli query -d xenial -c main --latest

name                   distribution    component    architecture    version
---------------------  --------------  -----------  --------------  ----------------------
AwsAgent               xenial          main         amd64           1.0.741.0-100741
docker-engine          xenial          main         amd64           1.12.6-0~ubuntu-xenial
consul-template        xenial          main         amd64           0.15-tcc01
consul-template        xenial          main         i386            0.15-tcc01
vault                  xenial          main         amd64           0.6.0-tcc01
jfrog-artifactory-pro  xenial          main         all             4.15.0
testdeb                xenial          main         all             2:0.0.0-test
```

Eagle-eyed readers will notice that 'consul-template' appears twice in that
listing: that's because there are two consul-template packages: one in the
amd64 architecture and one in the i386 architecture.

