# Publishing and signing the repository

## Publishing

The bare `repoman-cli publish` command will publish the repository metadata
for every distribution the repo has been configured to serve to S3 so
that apt clients will see those packages as available for installation.

```
$ repoman-cli publish
INFO:repoman.cli:publishing repository to S3
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/xenial/main/binary-amd64/Packages.gz
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/xenial/main/binary-amd64/Packages
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/xenial/Release.gpg
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/xenial/Release
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/xenial/main/binary-amd64/Release
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/xenial/main/binary-i386/Packages.gz
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/xenial/main/binary-i386/Packages
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/xenial/main/binary-i386/Release
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/jessie/main/binary-amd64/Packages.gz
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/jessie/main/binary-amd64/Packages
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/jessie/Release.gpg
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/jessie/Release
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/jessie/main/binary-amd64/Release
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/jessie/main/binary-i386/Packages.gz
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/jessie/main/binary-i386/Packages
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/jessie/main/binary-i386/Release
INFO:apt_repoman.utils:done writing to s3
INFO:repoman.cli:Successfully published repository for dists ['xenial', 'jessie'] to bucket s3://repoman-demobucket
```

Optionally, the `-d` or `--distribution` flag can be passed to limit
which distributions are being published.

```
$ repoman-cli publish -d xenial
INFO:repoman.cli:publishing repository to S3
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/xenial/main/binary-amd64/Packages.gz
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/xenial/Release
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/xenial/main/binary-amd64/Release
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/xenial/main/binary-amd64/Packages
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/xenial/Release.gpg
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/xenial/main/binary-i386/Packages
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/xenial/main/binary-i386/Packages.gz
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/xenial/main/binary-i386/Release
INFO:apt_repoman.utils:done writing to s3
INFO:repoman.cli:Successfully published repository for dists ['xenial'] to bucket s3://repoman-demobucket
```

## GPG Signing

Optionally, Repoman can use [Gnu Privacy Guard](https://www.gnupg.org/) to sign
the Release files that `repoman-cli publish` generates in your repository.

If you are not familiar with this process, we recommend reading the [Secure
apt](https://wiki.debian.org/SecureApt) documentation.  Repoman itself
does not handle distributing your public keys to any keyservers or to any
apt clients.

To sign a release, you need to pass two flags to the repoman cli when running
the 'publish' command:

* `--gpg-home` takes as an argument the path to the directory with
  your GPG secret key ring.  By default this is `~/.gnupg`.
* `--gpg-signer` takes as an argument the key ID associated
  with the secret key that will sign your release. (This can be an email
  address if there is only one matching key in your keyring.) You can
  add multiple --gpg-signer keys to sign with multiple keys at once.

Note that these are top-level flags, so they go immediately after the repoman-cli
command, e.g. `repoman-cli --gpg-home=/etc/gpg --gpg-signer=apt@example.com
publish`.

```
# repoman-cli --gpg-signer=repo@example.com publish -d xenial
INFO:repoman.cli:publishing repository to S3
Repoman requires a passphrase to unlock key "repo@example.com"
Enter your gpg passphrase --> ***************************
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/xenial/main/binary-amd64/Packages.gz
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/xenial/main/binary-amd64/Release
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/xenial/Release.gpg
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/xenial/main/binary-amd64/Packages
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/xenial/Release
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/xenial/main/binary-i386/Packages
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/xenial/main/binary-i386/Packages.gz
INFO:apt_repoman.utils:writing s3://repoman-demobucket/dists/xenial/main/binary-i386/Release
INFO:apt_repoman.utils:done writing to s3
INFO:repoman.cli:Successfully published repository for dists ['xenial'] to bucket s3://repoman-demobucket
```

Optionally, you may set the `--gpg-pinentry-path` flag to point to the location
of a [GPG Pinentry](https://www.gnupg.org/software/pinentry/index.html) program
on your system.  If this is unset or points to a nonexistent program, Repoman
will fall back to using python's
[getpass](https://docs.python.org/2/library/getpass.html) function.

Optionally you may set the `--gpg-passphrase` flag to directly pass in
the passphrase for the private key -- but see below!

For convenience, it is usually simpler to put this information into your
repoman configuration file:

```
# if you are signing your apt releases, you must set
# gpg-home to point to a directory with the keyring
# of the signing key
#
gpg-home=~/.gnupg

# you may optionally generate multiple signatures
# by setting gpg-signer to a list: [foo,bar]
#
#gpg-signer=signer@example.com
#gpg-signer=B02EDBDB
gpg-signer=[repo@example.com,B02EDBDB]

# you may optionally pick a pinentry program
#
#gpg-pinentry-path=/usr/local/MacGPG2/libexec/pinentry-mac.app/Contents/MacOS/pinentry-mac
gpg-pinentry-path=/usr/local/bin/pinentry

# you may optionally set the gpg passphrase here, but
# this is potentially very dangerous behavior!
#
#gpg-passphrase=I do not really value my security!
#
# if you have multiple signing keys, you may specify
# passphrases for them in the same order:
#
#gpg-passphrase=[I do not really value my security!,I really dont!]
#
# if one key in the list is not locked, put an empty item
# in the corresponding place in the passphrase list:
#
#gpg-passphrase=[locked,,locked]

```

Repoman uses the [PGPy](https://github.com/SecurityInnovation/PGPy) library to
parse and manipulate GPG key rings.  It is unlikely that PGPy will operate in
the absence of a working libssl.  Unfortunately, PGPy does not currently
interoperate with GPGkeychain.

*WARNING*: Encoding your passphrase into Repoman's configuration -- whether via
command line flags or configuration files -- is potentially risky behavior!  On
its own, Repoman makes no attempt to secure either its configuration files, its
argument vector or its memory contents against malicious actors, and indeed on
a shared system it is mostly not possible to do that.  GPG key management is a
fraught topic; we recommend reading up:

* [OpenPGP Best Practices](https://riseup.net/en/security/message-security/openpgp/best-practices)
* [Key Management from the GnuPG Manual](https://www.gnupg.org/gph/en/manual/c235.html)
* [Using Subkeys from the Debian Manual](https://wiki.debian.org/Subkeys?action=show&redirect=subkeys)
