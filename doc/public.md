# Serving public repositories directly from S3

Serving packages from S3 normally requires that any apt clients be
properly configured to [use S3 as an apt source](clients.md), but this
is generally not possible or convenient when serving packages to clients
you do not directly manage.  (_"L’enfer, c’est les autres"_ as a wise man
once said.)

Luckily, Amazon S3 has the ability to configure individual buckets to
act as [web servers for the objects in them](http://docs.aws.amazon.com/AmazonS3/latest/dev/WebsiteHosting.html),
which means that you can, subject to some limitations, serve your
repository to the entire world.

Repoman can set up S3 website hosting for your respository when
you set up the repository:

```
$ repoman-cli setup -a amd64 -c main -d xenial --enable-website
INFO:repoman.cli:Setting up repoman!
INFO:repoman.cli:Creating simpledb domain
INFO:repoman.cli:Initializing repository database
WARNING:repoman.cli:Creating s3 bucket: repoman-demobucket
WARNING:repoman.cli:Enabling the public-read ACL on s3://repoman-demobucket because you have enabled S3 website hosting.
INFO:repoman.cli:Bucket website created: http://repoman-demobucket.s3-website-us-east-1.amazonaws.com/
```

A few things to note:

* Repoman will set up a standard IndexDocument of `index.html`;
  this is not generally needed or used by apt repositories.
* Repoman will set up a default ErrorDocument of `/errors/404.html`
  for your bucket's website, but does not actually put any such
  file into your bucket: if you want a fancy error page you will
  need to add it yourself.  See the Amazon documentation for details.

If you want to enable S3 website hosting for your repository after
you have done the initial setup, you can simply enable it on the S3
bucket by following the procedure from [Amazon's
documentation](http://docs.aws.amazon.com/AmazonS3/latest/dev/WebsiteHosting.html)

Once website hosting is set up, your clients can add your repository to
their `/etc/apt/sources.list` file as a standard http repo:

```
deb http://repoman-demobucket.s3-website-us-east-1.amazonaws.com/ xenial main
```

*WARNING*: at present time, using https/ssl to access amazon S3
websites is not supported by S3.  If you need SSL validation for your
repo, you will need to configure an [Amazon Cloudfront CDN
distribution](http://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/DownloadDistS3AndCustomOrigins.html)
to use your bucket as an origin, and attach an SSL certificate to the
Cloudfront distribution.
