from .__version__ import __version__
import os
import sys
import re
import subprocess
import argparse # Deal with the input arguments.
import logging
from . import core
from .errors import *

MAX_DELETE = 10  # Deleted allowed, else abort. Use --force to override.

def cli():


    logging.basicConfig(format='%(asctime)s: %(message)s') # /%(levelname)s/%(module)s/%(funcName)s
    logging.warning("***** BiDirectional Sync for Cloud Services using RClone *****")

    try:
        clouds = subprocess.check_output(['rclone', 'listremotes'])
    except subprocess.CalledProcessError as e:
        logging.error("ERROR Can't get list of known remotes. Have you run rclone config?"); exit()
    except:
        logging.error("ERROR rclone not installed?\nError message: {}\n".format(sys.exc_info()[1])); exit()

    clouds = [c.decode('utf-8') for c in clouds.split()] # Py3 create a byte array instead a string list.

    parser = argparse.ArgumentParser(description="BiDirectional Sync for Cloud Services using RClone.")

    parser.add_argument('-v', '--version',
                        action='version',
                        version='RCloneSyn python2/3 script v.' + __version__)
    parser.add_argument('Cloud',
                        help="Name of remote cloud service ({}) plus optional path".format(clouds))
    parser.add_argument('LocalPath',
                        help="Path to local tree base",
                        default=None)
    parser.add_argument('-1', '--first-sync',
                        help="First run setup. WARNING: Local files may overwrite Remote versions. Also asserts --verbose.",
                        action='store_true')
    parser.add_argument('--check-access',
                        help="Ensure expected RCLONE_TEST files are found on both Local and Remote filesystems, else abort.",
                        action='store_true')
    parser.add_argument('-f', '--force',
                        help="Bypass MAX_DELETE ({}%%) safety check and run the sync. Also asserts --verbose.".format(MAX_DELETE),
                        action='store_true')
    parser.add_argument('-e', '--exclude-list-file',
                        help="File containing rclone file/path exclusions (Needed for Dropbox)",
                        default=None)
    parser.add_argument('-V', '--verbose',
                        help="Enable event logging with per-file details",
                        action='store_true')
    parser.add_argument('--rc-verbose',
                        help="Enable rclone's verbosity levels (May be specified more than once for more details. Also asserts --verbose.)",
                        action='count')
    parser.add_argument('--dry-run',
                        help="Go thru the motions - No files are copied/deleted. Also asserts --verbose.",
                        action='store_true')
    parser.add_argument('--cron',
                        help="Add the correspondent syncronization to the cron tab.",
                        type=int,
                        default=None)
    parser.add_argument('-n', '--no-local-delete',
                        help="Don't delete any local files.",
                        action='store_true')

    args = parser.parse_args()

    first_sync = args.first_sync
    checkAccess = args.check_access
    verbose = args.verbose
    no_local_delete = args.no_local_delete
    rcVerbose = (args.rc_verbose if args.rc_verbose else 0)
    exclusions = args.exclude_list_file
    dryRun = args.dry_run
    force = args.force

    remoteFormat = re.compile('([\w-]+):(.*)') # Handle variations in the Cloud argument -- Remote: or Remote:some/path or Remote:/some/path
    out = remoteFormat.match(args.Cloud)
    remoteName = remotePathPart = remotePathBase = ''
    if out:
        remoteName = out.group(1) + ':'
        if remoteName not in clouds:
            logging.error("ERROR Cloud argument <{}> not in list of configured remotes: {}".format(remoteName, clouds)); exit()
        remotePathPart = out.group(2)
        if remotePathPart != '':
            if remotePathPart[0] != '/':
                remotePathPart = '/' + remotePathPart # For consistency ensure the path part starts and ends with /'s
            if remotePathPart[-1] != '/':
                remotePathPart += '/'
        remotePathBase = remoteName + remotePathPart # 'Remote:' or 'Remote:/some/path/'
    else:
        logging.error("ERROR Cloud parameter <{}> cannot be parsed. ':' missing? Configured remotes: {}".format(args.Cloud, clouds)); exit()


    localPathBase = args.LocalPath
    if localPathBase[-1] != '/': # For consistency ensure the path ends with /
        localPathBase += '/'
    if not os.path.exists(localPathBase):
        logging.error("ERROR LocalPath parameter <{}> cannot be accessed. Path error? Aborting".format(localPathBase)); exit()


    if args.cron: # Add the correspondent execution to crontab.
        if sys.version_info<(3,0):
            cmd ="crontab -l */t * * * * python3 '{f}' 'remotePathBase' 'localPathBase'"
        else:
            cmd ="crontab -l */t * * * * python '{f}' 'remotePathBase' 'localPathBase'"
        cmd = cmd.format(t=args.cron,
                         f=os.path.realpath(__file__),
                         )
        os.system(cmd)

    if verbose or rcVerbose>0 or force or first_sync or dryRun:
        verbose = True
        logging.getLogger().setLevel(logging.INFO) # Log each file transaction
    else:
        logging.getLogger().setLevel(logging.WARNING) # Log only unusual events

    if core.requestLock(sys.argv) == 0:

        status = core.bidirSync(exclusions,
                                dryRun,
                                rcVerbose,
                                first_sync,
                                checkAccess,
                                force,
                                MAX_DELETE,
                                no_local_delete,
                                remotePathBase,
                                localPathBase,
                                )

        if status == RTN_CRITICAL:
            logging.error('***** Critical Error Abort - Must run --first-sync to recover. See README.md *****')
            if os.path.exists(localListFile): subprocess.call(['mv', localListFile, localListFile + '_ERROR'])
            if os.path.exists(remoteListFile): subprocess.call(['mv', remoteListFile, remoteListFile + '_ERROR'])
        if status == RTN_ABORT:
            logging.error('***** Error abort. Try running RCloneSync again. *****')
        core.releaseLock(sys.argv)
    else:
        logging.warning("Prior lock file in place. Aborting.")
    logging.warning(">>>>> All done.")

if __name__ == '__main__':
    
    cli()
