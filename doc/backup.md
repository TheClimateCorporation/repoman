# Backups and restores

## S3

By design, Repoman itself does not ever delete package files from S3: once
uploaded they are there for good.  However it is possible that repoman can
_overwrite_ package files in S3 if someone uploads a duplicate package
using `repoman-cli add --overwrite`.

If your use case requires that you be able to recover the original package
file in that case, our recommendation is that you enable [versioning](
http://docs.aws.amazon.com/AmazonS3/latest/dev/Versioning.html) on the
S3 bucket being used as your Repoman repository.  Note that the Repoman
`publish` command will in this case always create new versions of most
or all files under the `dists/` prefix and these can pile up quickly;
you will want to set a [S3 lifecycle policy](
http://docs.aws.amazon.com/AmazonS3/latest/UG/lifecycle-configuration-bucket-with-versioning.html)
to archive or delete old versions.

## SimpleDB

A full restorable dump of the current state of the SimpleDB domain can be done
with the `repoman-cli query` command using the `--format jsonc` flag:

```
$ repoman-cli backup > backup.json
```

Any of the usual flags to `repoman-cli query` can be used to filter the backup to
a subsection of the repository.

A utility is provided to restore such a backup file to SimpleDB:

```
$ repoman-cli restore backup.json
```

*WARNING:* doing a restore of a full backup of the repository can have
unpredictable results!

* If you delete and recreate the simpledb domain in order to do a "clean"
  restore, any mutating actions done in between the last backup and the
  time of deletion will be lost.

* If you restore the backup _on top of_ the current state of simpledb,
  no attempt to merge the two states is made: each item and attribute
  in the backup is restored to the domain.  This will silently revert
  _deletions_ but not add or copies of packages.  Similarly any
  deletions of repo configuration (distributions, components, etc)
  will be restored but any newly created ones since the backup
  will remain.

In both cases we recommend careful examination of your SNS logs (which
you hopefully turned on) in order to determine any changes which may need
to be made by hand post-restoration.
