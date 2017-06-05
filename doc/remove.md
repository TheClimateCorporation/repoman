# Removing packages from the repository

The `repoman-cli rm` command allows you remove packages from the repository,
either singly or in groups.

By default and with no flags, `repoman-cli rm` *will remove out every package in
every distribution, component and architecture that the repo currently is
configured to serve*, but multiple layers of confirmation will prevent you from
doing that, and you can narrow down the list of packages to be deleted
 by means of the following flags:

* `-p` or `--package` will only remove packages with a name matching the one given
* `-w` or `--wildcard` will make the name given in the `-p` flag a wildcard match, ie. `-p test`
  will return packages named both "test" and "testamundo" and "testacular" if they exist
* `-d` or `--distribution` will only remove packages belonging to the specified distribution
* `-c` or `--component` will only remove packages belonging to the specified component
* `-a` or `--architecture` will only remove packages belonging to the specified architecture
* `-v` or `--version` will only remove packages with a version matching the one given
* `-r` or `--exclude-recent` will exclude the N newest packages (by debian version
  sorting order) by distribution/component/architecture from the list of packages
  to be deleted
* `-l` or `--exclude-latest` will exclude the most recent package; this is equivalent to `--recent 1`
* `-H` or `--rm-hidden` will include packages belonging to distributions/components/architectures
  that have been deleted from the repo configuration; by default these are ignored
* `--publish` will publish the repository to S3 after a successful rm action

Flags that take an argument can be specified multiple times and are ORed
internally when making the query: `repoman-cli query -d xenial -d trusty` will
remove the entire list of packages for _both_ the trusty and xenial
distributions for example.

Adding multiple flags of different types is an AND operation internally,
for example `repoman-cli rm -c main -c universal -p testdeb -v 2:0.0.0-test`
will remove only packages with the name "testdeb" _and_ the version "1:0.0.0"
in _either_ the "main" or "universal" components:

```
$ repoman-cli rm -p testdeb -c main -c nightly -v 2:0.0.0-test

name     distribution    component    architecture    version
-------  --------------  -----------  --------------  ------------
testdeb  xenial          main         all             2:0.0.0-test
testdeb  xenial          nightly      all             2:0.0.0-test

WARNING:repoman.cli:Total packages to be deleted: 2
```

Adding the `-y` or `--confirm` flag will skip the confirmation step;
obviously only do this if you are extremely confident in what you
are doing!

Adding the `--publish` flag will cause the respository to be published
to S3 automatically after all packages specified are successfully removed.

# Automatic purging of old package versions

Because Repoman allow for multiple versions of a package to be published
at the same time (relative to distribution/component/architecture), it is
common especially in situations where automated CI/CD systems build new
packages on the fly for dozens or even hundreds of versions of any given
package to be "live" in the repo all at once.  And unfortunatly, this can
slow many common operations down: notably publishing the repo and running
`apt-get update` on a client machine are both operations that take linear
amount of time relative to the total size of the repository.

There are two ways to deal with this issue:

1. Use the `repoman-cli rm` command on a regular schedule to purge out old
   package versions.

Repoman's `rm` command takes two flags that can automate the common
cases here:

- `-r` or `--exclude-recent` lets you set the N most recent versions to
  *exclude* from the list of packages to be deleted.
- `-l` or `--exclude-latest` will cause `repoman-cli rm` to exclude the most recent
  package versions (by debian package sorting order) from the list of
  packages to be deleted: this is equivalent to `--exclude-recent 1`

For example, to purge all but the 2 most recent versions of every package
in the "main" component of the "xenial" distribution, you would run:

```
$ repoman-cli rm -d xenial -c main --exclude-recent 2
```

To purge all but the two most recent versions of *every* package (relative
to distribution/component/architecture) you would simply run:

```
$ repoman-cli rm --exclude-recent 2
```

2. Use the `--auto-purge` flag or config file variable.

Alternatively, Repoman offers the ability to _automatically_ purge old
versions of packages when adding new packages to the repo or when copying
them within the repository, using the `--auto-purge` flag.  (Again this
is always relative to the dist/comp/arch of the packages in question!)

For example, if you had 5 versions of the "testdeb" package in the "main"
component of the "trusty" distribution and you had just built version 6,
and wished to dispense with versions 1 through 4, you could run:

```
repoman-cli --auto-purge=2 add -d trusty -c main testdeb_6_all.deb
```

And when you copied that package into the "xenial" distribution, you could
purge out the old versions there:

```
repoman-cli --auto-purge=2 copy --src-dist trusty \
    --src-comp main \
    --dst-dist xenial \
    --latest \
    -p testdeb
```

The result would be:

```
$ repoman-cli query -p testdeb

name     distribution    component    architecture    version
-------  --------------  -----------  --------------  -------------
testdeb  trusty          main         all             5
testdeb  trusty          main         all             6
testdeb  xenial          main         all             5
testdeb  xenial          main         all             6
```

*NOTE:* the `--auto-purge` flag is a top-level flag so that it can also
be put into your repoman configuration file.  This means that it comes
_before_ the command: `repoman-cli --auto-purge=N copy` not `repoman-cli copy
--auto-purge N`

