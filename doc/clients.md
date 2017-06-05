# Subscribing apt clients to the repository

Once you have published your repository to S3, you probably want to actually
use it!  This will require setting up apt clients to subscribe to your
repository.

For recent versions of Ubuntu Linux (Xenial Xerus/16.04 and later), you
can use the [apt-transport-s3](https://launchpad.net/ubuntu/+source/apt-transport-s3)
package.  The package is also available in the 'sid` distribution for Debian
GNU/Linux.

If your distribution does not natively package apt-transport-s3, you
can build it yourself from the [github source](https://github.com/BashtonLtd/apt-transport-s3)

```
$ apt-get install -y apt-transport-s3
Reading package lists... Done
Building dependency tree
Reading state information... Done
0 upgraded, 0 newly installed, 1 reinstalled, 0 to remove and 7 not upgraded.
Need to get 6482 B of archives.
After this operation, 0 B of additional disk space will be used.
Get:1 http://archive.ubuntu.com/ubuntu xenial/universe amd64 apt-transport-s3 all 1.2.1-1 [6482 B]
Fetched 6482 B in 0s (15.5 kB/s)
debconf: delaying package configuration, since apt-utils is not installed
(Reading database ... 17025 files and directories currently installed.)
Preparing to unpack .../apt-transport-s3_1.2.1-1_all.deb ...
Unpacking apt-transport-s3 (1.2.1-1) over (1.2.1-1) ...
Processing triggers for man-db (2.7.5-1) ...
Setting up apt-transport-s3 (1.2.1-1) ...
```

Once installed, you can configure a Repoman S3 repository like any other,
by adding it to `/etc/apt/sources.list` or to a file in `/etc/apt/sources.list.d`:

```
deb s3://repoman-demobucket.s3.amazonaws.com/ xenial main
```

Note that the format of the url is s3://_BUCKETNAME_.s3.amazonaws.com/

Note that you will also need to configure an `/etc/apt/s3auth.conf` file:

```
AccessKeyId = AKIAIABCDEFGU5YCSTQ
SecretAccessKey = m47irsasdjk+sfdhC/KWaAmFasdklw2EajhgC1wX9N
Token =
```

If you are operating in an environment where the access role is
provided for you automatically (e.g. from an [EC2 Instance Profile]()
or an [ECS Task Role]()) you can leave the values in `s3auth.conf`
blank, but the key names must still be in the file:

```
AccessKeyId =
SecretAccessKey =
Token =
```

Alternatively, if you configure your repository to be [publicly
accessible](public.md) you can skip the apt-transport-s3 package
entirely and use the standard https transport:

```
deb http://repoman-demobucket.s3-website-us-east-1.amazonaws.com/ xenial main
```
