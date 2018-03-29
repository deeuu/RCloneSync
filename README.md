# RCloneSync


Python 2.7 cloud sync utility using rclone

[Rclone](https://rclone.org/) provides a programmatic building block interface for transferring files between a cloud service 
provider and your local filesystem (actually a lot of functionality), but rclone does not provide a turnkey bidirectional 
sync capability.  RCloneSync.py provides a bidirectional sync solution using rclone.

I use RCloneSync on a Centos 7 box to sync both Dropbox and Google Drive to a local disk which is Samba shared on my LAN. 
I run RCloneSync as a Cron job every 30 minutes, or on-demand from the command line.  
RCloneSync was developed and debugged for Google Drive and Dropbox (not tested on other services).  

### High level behaviors / operations
-  Keeps `rclone lsl` file lists of the Local and Remote systems, and on each run checks for deltas on Local and Remote
-  Applies Remote deltas to the Local filesystem, then `rclone syncs` the Local to the Remote filesystem
-  Handles change conflicts nondestructively by creating _LOCAL and _REMOTE file versions
-  Reasonably fail safe:
	- Lock file prevents multiple simultaneous runs when taking a while
	- File access health check using `RCLONE_TEST` files (see --CheckAccess switch)
	- Excessive deletes abort - Protects against a failing `rclone lsl` being interpreted as all the files were deleted.  See `maxDelta` within the code and --Force switch
	- If something evil happens, RCloneSync goes into a safe state to block damage by later run.  (See **Runtime Error Handling**, below)


```
xxx@xxx RCloneSyncWD]$ ./RCloneSync.py -h
2017-11-19 20:13:58,282/:  ***** BiDirectional Sync for Cloud Services using RClone *****
usage: RCloneSync.py [-h] [--FirstSync] [--CheckAccess] [--Force]
                     [--ExcludeListFile EXCLUDELISTFILE] [--Verbose]
                     [--rcVerbose] [--DryRun]
                     Cloud LocalPath

***** BiDirectional Sync for Cloud Services using RClone *****

positional arguments:
  Cloud                 Name of remote cloud service (['Dropbox:', 'GDrive:'])
                        plus optional path
  LocalPath             Path to local tree base

optional arguments:
  -h, --help            show this help message and exit
  --FirstSync           First run setup. WARNING: Local files may overwrite
                        Remote versions. Also asserts --Verbose.
  --CheckAccess         Ensure expected RCLONE_TEST files are found on both
                        Local and Remote filesystems, else abort.
  --Force               Bypass maxDelta (50%) safety check and run the sync.
                        Also asserts --Verbose.
  --ExcludeListFile EXCLUDELISTFILE
                        File containing rclone file/path exclusions (Needed
                        for Dropbox)
  --Verbose             Enable event logging with per-file details
  --rcVerbose           Enable rclone's verbosity levels (May be specified
                        more than once for more details. Also asserts
                        --Verbose.)
  --DryRun              Go thru the motions - No files are copied/deleted.
                        Also asserts --Verbose.
```	

Typical run log:
```
[xxx@xxx]$ ./RCloneSync.py  GDrive:   /mnt/raid1/share/public/DBox/GoogleDrive --CheckAccess --Verbose
2017-11-19 20:25:06,367/:  ***** BiDirectional Sync for Cloud Services using RClone *****
2017-11-19 20:25:06,374/:  Synching Remote path  <GDrive:>  with Local path  </mnt/raid1/share/public/DBox/GoogleDrive/>
2017-11-19 20:25:06,375/:  >>>>> Checking rclone Local and Remote filesystems access health
2017-11-19 20:25:07,500/:  >>>>> Generating Local and Remote lists
2017-11-19 20:25:08,339/:    LOCAL    Checking for Diffs                  - /mnt/raid1/share/public/DBox/GoogleDrive/
2017-11-19 20:25:08,339/:    LOCAL      File is newer                     - Exchange/config.txt10
2017-11-19 20:25:08,339/:    LOCAL      File size is different            - Exchange/config.txt10
2017-11-19 20:25:08,339/:       1 file change(s) on LOCAL:     0 new,    1 newer,    0 older,    0 deleted
2017-11-19 20:25:08,339/:    REMOTE   Checking for Diffs                  - GDrive:
2017-11-19 20:25:08,339/:    REMOTE     File was deleted                  - Exchange/config.txt7
2017-11-19 20:25:08,339/:    REMOTE     File is new                       - Exchange/config.txt8
2017-11-19 20:25:08,339/:       2 file change(s) on REMOTE:    1 new,    0 newer,    0 older,    1 deleted
2017-11-19 20:25:08,340/:  >>>>> Applying changes on Remote to Local
2017-11-19 20:25:08,340/:    LOCAL      Deleting file                     - "/mnt/raid1/share/public/DBox/GoogleDrive/Exchange/config.txt7" 
2017-11-19 20:25:08,346/:    REMOTE     Copying to local                  - "/mnt/raid1/share/public/DBox/GoogleDrive/Exchange/config.txt8" 
2017-11-19 20:25:09,966/:  >>>>> Synching Local to Remote
2017-11-19 20:25:11,329/:  >>>>> rmdirs Remote
2017-11-19 20:25:20,810/:  >>>>> rmdirs Local
2017-11-19 20:25:20,816/:  >>>>> Refreshing Local and Remote lsl files
2017-11-19 20:25:21,655/:  >>>>> All done.

```

## RCloneSync Operations

RCloneSync keeps copies of the prior sync file lists of both local and remote, and on a new run checks for any changes 
locally and then remotely.  Note that on some (all?) cloud storage systems it is not possible to have file timestamps 
that match between the local and cloud copies of a file.  RCloneSync works around this problem by tracking local-to-local 
and remote-to-remote deltas, and then applying the changes on the other side. 

### Notable features / functions / behaviors

- The **Cloud** argument may be just the configured remote name (i.e., `GDrive:`), or it may include a path to a sub-directory within the 
tree of the remote (i.e., `GDrive:/Exchange`).  Leading and trailing '/'s are not required but will be added by RCloneSync.  The 
path reference is identical with or without the '/'s.  The LSL files in the RCloneSync's local working directory (`~/.RCloneSync`) are named based 
on the Cloud argument, thus separate syncs to individual directories within the tree may be set up. 
Test with `--DryRun` first to make sure the remote 
and local path bases are as expected.  As usual, double quote `"Exchange/Paths with spaces"`.

- For the **LocalPath** argument, absolute paths or paths relative to the current working directory may be used.  `RCloneSync GDrive:Exchange
 /mnt/raid1/share/public/DBox/GoogleDrive` is equivalent to `RCloneSync GDrive:Exchange Exchange` if the cwd is /mnt/raid1/share/public/DBox/GoogleDrive.
As usual, double quote `"Exchange/Paths with spaces"`.

- RCloneSync applies any changes to the Local file system first, then uses `rclone sync` to make the Remote filesystem match the Local.
In the tables below, understand that the last operation is to do an `rclone sync` if RCloneSync makes changes on the local filesystem.

- Any empty directories after the RCloneSync are deleted on both the Local and Remote filesystems.

- **--FirstSync** - This will effectively make both Local and Remote contain a matching superset of all files.  Remote 
files that do not exist locally will be copied locally, and the process will then sync the Local tree to the Remote.  

- **--CheckAccess** - Access check files is an additional safety measure against data loss.  RCloneSync will ensure it can 
find matching RCLONE_TEST files in the same places in the local and remote file systems.  Time stamps and file contents 
are not important, just the names and locations.  Place one or more RCLONE_TEST files in the local or remote filesystem and then 
do either a run without --CheckAccess or a --FirstSync to set matching files on both filesystems.

- **Verbosity controls** - `--Verbose` enables RCloneSync's logging of each check and action (as shown in the typical run log, above). 
rclone's verbosity levels also be enabled using the `--rcVerbose` switch.  rclone supports additional verbosity levels which may be 
enabled by providing the `--rcVerbose` switch more than once.  Turning on rclone's verbosity using `--rcVerbose` will also turn on
RCloneSync's `--Verbose` switch.

- **Runtime Error Handling** - Certain RCloneSync critical errors, such as `rclone copyto` failing, 
will result in an RCloneSync lockout of successive runs.  The lockout is asserted because the sync status of the local and remote filesystems
can't be trusted, so it is safer to block any further changes until someone with a brain (you) check things out.
The recovery is to do a --FirstSync again.  It is recommended to use --FirstSync 
--DryRun initially and carefully review what changes will be made before running the --FirstSync without --DryRun. 
Most of these events come up due to rclone returning a non-zero status from a command.  On such a critical error 
the *_localLSL and *_remoteLSL files are renamed adding _ERROR, which blocks any future RCloneSync runs (since the 
original files are not found).  These files may possibly be valid and may be renamed back to the non-_ERROR versions 
to unblock further RCloneSync runs.  Some errors are considered temporary, and re-running the RCloneSync is not blocked. 
Within the code, see usages of `return RTN_CRITICAL` and `return RTN_ABORT`.  `return RTN_CRITICAL` blocks further RCloneSync runs.

- **--DryRun oddity** - The --DryRun messages may indicate that it would try to delete files on the remote server in the last 
RCloneSync step of rclone syncing the local to the remote.  If the file did not exist locally then it would normally be copied to 
the local filesystem, but with --DryRun enabled those copies didn't happen, and thus on the final rclone sync step they don't exist locally, 
which leads to the attempted delete on the remote, blocked again by --DryRun `... Not deleting as --dry-run`.  This whole situation is an 
artifact of the --DryRun switch.  Scrutinize the proposed deletes carefully, and if they would have been copied to local then they may be disregarded.

- **Lock file** - When RCloneSync is running, a lock file is created (/tmp/RCloneSync_LOCK).  If RCloneSync should crash or 
hang the lock file will remain in place and block any further runs of RCloneSync.  Delete the lock file as part of 
debugging the situation.  The lock file effectively blocks follow on CRON scheduled runs when the prior invocation 
is taking a long time.  The lock file contains the job command line and time, which may help in debug.

### Usual sync checks

 Type | Description | Result| Implementation ** 
--------|-----------------|---------|------------------------
Remote new| File is new on remote, does not exist on local | Remote version survives | `rclone copyto` remote to local
Remote newer| File is newer on remote, unchanged on local | Remote version survives | `rclone copyto` remote to local
Remote deleted | File is deleted on remote, unchanged locally | File is deleted | `rclone delete` local
Local new | File is new on local, does not exist on remote | Local version survives | `rclone sync` local to remote
Local newer| File is newer on local, unchanged on remote | Local version survives | `rclone sync` local to remote
Local older| File is older on local, unchanged on remote | Local version survives | `rclone sync` local to remote
Local deleted| File no longer exists on local| File is deleted | `rclone sync` local to remote


### *UNusual* sync checks

 Type | Description | Result| Implementation **
--------|-----------------|---------|------------------------
Remote new AND Local new | File is new on remote AND new on local | Files renamed to _LOCAL and _REMOTE | `rclone copyto` remote to local as _REMOTE, `rclone moveto` local as _LOCAL
Remote newer AND Local changed | File is newer on remote AND also changed (newer/older/size) on local | Files renamed to _LOCAL and _REMOTE | `rclone copyto` remote to local as _REMOTE, `rclone moveto` local as _LOCAL
Remote newer AND Local deleted | File is newer on remote AND also deleted locally | Remote version survives  | `rclone copyto` remote to local
Remote deleted AND Local changed | File is deleted on remote AND changed (newer/older/size) on local | Local version survives |`rclone sync` local to remote
Local deleted AND Remote changed | File is deleted on local AND changed (newer/older/size) on remote | Remote version survives  | `rclone copyto` remote to local

** If any changes are made on the Local filesystem then the final operation is an `rclone sync` to update the Remote filesystem to match.

### Unhandled

 Type | Description | Comment 
--------|-----------------|---------
Remote older|  File is older on remote, unchanged on local | `rclone sync` will push the newer local version to the remote.
Local size | File size is different (same timestamp) | Not sure if `rclone sync` will pick up on just a size difference and push the local to the remote.


## Revision history

- ??????  Added Python 3 support.

- 180314  Incorporated rework by croadfeldt, changing handling of subprocess commands and many src/dest, etc. from strings 
		to lists.  No functional or interface changes.  Added --DryRun oddity note to the README.

- 171119  Added 3x retry on rclone commands to improve robustness.  Beautified the `--Verbose` mode output.  Broke out control of 
		rclone's verbosity with the`--rcVerbose` switch.
		
- 171115  Remote supports path entry.  Reworked LSL file naming to support for remote paths.
       --Verbose switch applies to all rclone copyto, moveto, delete, and sync calls (was only on sync)

- 171112  Revamped error handling to be effective.  See Readme.md.
       Added --CheckAccess switch to make filesystems access test optional.  Default is False (no check).

- 171015  Moved tooManyLocalDeletes error message down below the remote check to provide both local and remote change lists to the stdout

- 170917  Added --Force switch - required when the % changes on local or remote system are grater than maxDelta.  Safeguard for
       local or remote not online.
       Added --ignore-times to the copy of changed file on remote to local.  Was not copying files with matching sizes.

- 170805  Added --Verbose command line switch 

- 170730  Horrible bug - remote lsl failing results in deleting all local files, and then iteratively replicating _LOCAL and _REMOTE files.
       Added connection test/checking files to abort if the basic connection is down.  RCLONE_TEST files on the local system
       must match the remote system (and be unchanged), else abort.
       Added lockfile so that a second run aborts if a first run is still in process, or failed and left the lockfile in place.
       Added python logging, sorted processing

- 170716  New

