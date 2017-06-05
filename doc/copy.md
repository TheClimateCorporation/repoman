# Copying packages inside the repository

## Copying indivdual packages

Depending on your internal package lifecycle management approach, it may be
necessary to sometimes copy packages from one component to a different
component inside your repository, or possibly even from one distribution to
another.  For example, your repository might have an "experimental" component
that holds pre-release builds, or a "nightly" component that contains packages
built from the current HEAD state of your source ever day, and you might
sometimes need to promote packages from the nightly component to a
"release" component.

The `repoman-cli cp` command lets you copy packages between sections of your
repository, with the restriction that you must fully specify both the
distribution and component of both the source and destination of your copy
command.

The following flags to `cp` are _required:_

* `--src-distribution` -- Specify one distribution to copy from
* `--src-component` -- Specify one component to copy from

Note that flag names can be abbreviated to the minimum possible match:
`--src-distribution` and `--src-d` are equivalent.

You must use *at least* one of the following two flags:

* `--dst-distribution` -- Specify the distribution to copy to (if different than the source)
* `--dst-component` -- Specify the component to copy to (if different than the source)

The following flags are optional:

* `-p` or `--package` limits the candidates for copying to one or more packages by name
* `-w` or `--wildcard` makes the `-p` flag a left-hand match: `-p tr -w` will match
  packages named both "trader" and "trusty" for example.
* `-v` or `--version` limits the candidates for copying to one or more packages by version
* `-a` or `--architecture` restricts candidates for copying to a specific architecture
* `-r` or `--recent` restricts candidates for copying to only the N latest versions;
  see [below](#Copying only the latest package versions)
* `-l` or `--latest` specifies only the most recent version; this is equivalent
  to `--recent 1`
* `--promote` specifies promotion behavior; see [below](#The promote flag)
* `--overwrite` instructs repoman to not throw an error if the package file exists
  in the target location in S3.  This only applies in cross-distribution copies.
* `-y` or `--confirm` will skip the confirmation step for copying small numbers
  of packages
* `--i-fear-no-evil` will skip the extra confirmation step for copying large
  numbers of packages or entire components. _*At your own risk.*_
* `--publish` will publish the repository to S3 after a successful copy action.

For example, to copy every version of the 'testdeb' package out of the
'nightly' component and into the 'release' component:

```
$ repoman-cli cp -p testdeb --src-distribution xenial --src-component nightly --dst-comp release

WARNING:repoman.cli:We are about to do the following copy actions:

name     version        src dist    src comp    dst dist    dst comp
-------  -------------  ----------  ----------  ----------  ----------
testdeb  1:0.0.0-test   xenial      nightly        xenial      release
testdeb  1:1.0.0-test   xenial      nightly        xenial      release
testdeb  1:1.1.0-test   xenial      nightly        xenial      release
testdeb  1:1.1.0-test2  xenial      nightly        xenial      release
testdeb  2:0.0.0-test   xenial      nightly        xenial      release
testdeb  3:1.1.0-test2  xenial      nightly        xenial      release
testdeb  3:1.1.0-test2  xenial      nightly        xenial      release


Type "c" to confirm --> c
INFO:repoman.cli:creating package testdeb version 1:0.0.0-test distribution xenial component release architecture all
INFO:repoman.cli:creating package testdeb version 1:1.0.0-test distribution xenial component release architecture all
INFO:repoman.cli:creating package testdeb version 1:1.1.0-test distribution xenial component release architecture all
INFO:repoman.cli:creating package testdeb version 1:1.1.0-test2 distribution xenial component release architecture all
INFO:repoman.cli:creating package testdeb version 2:0.0.0-test distribution xenial component release architecture all
INFO:repoman.cli:creating package testdeb version 3:1.1.0-test2 distribution xenial component release architecture all
INFO:repoman.cli:creating package testdeb version 3:1.1.0-test2 distribution xenial component release architecture amd64
```

A few things to note about the above:

* if a destination section is the same as the source section, you can omit
  the relevant --dst-foo flag.  In this case, we are copying from the "nightly"
  component in the "xenial" distribution to the "release" component in the
  same distribution, so we did not have to specify `--dst-distribution xenial`
* Similarly, we could copy between distributions but preserving the same
  component with `repoman-cli cp --src-distribution xenial --src-component release
  --dst-distribution jessie`.

To copy only a particular package version or versions, use the `-v` or `--version`
flag:

```
$ repoman-cli cp --src-distribution xenial --src-component nightly --dst-comp release -p testdeb -v 3:1.1.0-test2
WARNING:repoman.cli:We are about to do the following copy actions:

name     version        architecture    src dist    src comp    dst dist    dst comp
-------  -------------  --------------  ----------  ----------  ----------  ----------
testdeb  3:1.1.0-test2  i386            xenial      nightly     xenial      release
testdeb  3:1.1.0-test2  amd64           xenial      nightly     xenial      release
```

To copy only packages in a particular architecture, use the `-a` or `--architecture`
flag:

```
$ repoman-cli cp --src-distribution xenial --src-component nightly --dst-comp release -p testdeb -v 3:1.1.0-test2 -a amd64
WARNING:repoman.cli:We are about to do the following copy actions:

name     version        architecture    src dist    src comp    dst dist    dst comp
-------  -------------  --------------  ----------  ----------  ----------  ----------
testdeb  3:1.1.0-test2  amd64           xenial      nightly     xenial      release
```

### Copying only the latest package versions

To copy only the _latest_ versions of a package available (by [Debian version
sorting order](https://www.debian.org/doc/debian-policy/ch-controlfields.html#s-f-Version))
you may optionally pass in the `-r` or `--recent` flag:

```
$ repoman-cli cp --src-distribution xenial --src-component nightly --dst-comp release -p testdeb --recent 2
WARNING:repoman.cli:We are about to do the following copy actions:

name     version        architecture    src dist    src comp    dst dist    dst comp
-------  -------------  --------------  ----------  ----------  ----------  ----------
testdeb  2:0.0.0-test   all             xenial      nightly     xenial      release
testdeb  3:1.1.0-test2  amd64           xenial      nightly     xenial      release
```

As a convenience, the `-l` or `--latest` flag is equivalent to `--recent 1`

### The promote flag

Optionally, you can pass in the `--promote` flag, which filters the list of
available packages to copy to _only_ those which are _newer_ than the _newest_
equivalent version on the destination side.

For example, if your 'nightly' component has versions 1 through 10 of the 'testdeb'
package, and your 'release' component has versions 1, 4 and 7, only versions 8, 9
and 10 will be seen as copyable from "nightly" to "release":

```
$ repoman-cli cp --src-distribution xenial --src-component nightly --dst-comp release -p testdeb --promote
WARNING:repoman.cli:We are about to do the following copy actions:

name     version        architecture    src dist    src comp    dst dist    dst comp
-------  -------------  --------------  ----------  ----------  ----------  ----------
testdeb  08             amd64           xenial      nightly     xenial      release
testdeb  09             amd64           xenial      nightly     xenial      release
testdeb  10             amd64           xenial      nightly     xenial      release
```

The `--recent` and `--latest` flags can be used in conjunction with the
`--promote` flag; in the previous example setting `--latest` would result in
only version 10 being copied.

## Mass copies

The `repoman-cli cp` command can be used _without_ the `--package` or `--version` flags
to copy up to an entire component's worth of packages to another component or
distribution.  This is a potentially difficult action to roll back, so an extra
layer of confirmation is requested:

```
$ repoman-cli cp --src-dist xenial --src-comp nightly --dst-comp release
WARNING:repoman.cli:We are about to do the following copy actions:

name     version        architecture    src dist    src comp    dst dist    dst comp
-------  -------------  --------------  ----------  ----------  ----------  ----------
testdeb  1:0.0.0-test   all             xenial      nightly     xenial      release
testdeb  1:1.0.0-test   all             xenial      nightly     xenial      release
testdeb  1:1.1.0-test   all             xenial      nightly     xenial      release
testdeb  1:1.1.0-test2  all             xenial      nightly     xenial      release
testdeb  2:0.0.0-test   all             xenial      nightly     xenial      release
testdeb  3:1.1.0-test2  all             xenial      nightly     xenial      release
testdeb  3:1.1.0-test2  amd64           xenial      nightly     xenial      release

WARNING:repoman.cli:Found something scary. Problem #1:

You are potentially copying up to an entire component's worth of packages!

Type exactly "I FEAR NO EVIL" to proceed --> I FEAR NO EVIL

Type "c" to confirm --> c
```
