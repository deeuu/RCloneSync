#!/usr/bin/env python
#========================================================= 
#
#  Basic BiDirectional Sync using RClone 
#
#  Usage
#   Configure rclone, including authentication before using this tool.  rclone must be in the search path.
#
#  Chris Nelson, November 2017 - 2018
#  Revision and contributions:
#  Hildo G. Jr.
#
#  See README.md for revision history
#
# Known bugs:
#   
#
#==========================================================

import argparse # Deal with the input arguments.
import sys
import re # To deal with the `rclone` time stamp.
import os.path, subprocess
from datetime import datetime
import time
#import shlex # Not used anymore, so free the memory.
import logging # For terminal process messages.
import inspect # For getting the line number for error messages
import collections # Dictionary sorting 

__VERSION__ = '180405'

# Configurations.
LOCAL_WD = os.path.expanduser("~/.RCloneSyncWD/") # File lists for the local and remote trees as of last sync, etc.
if not os.path.exists(LOCAL_WD):
	os.makedirs(LOCAL_WD)

MAX_DELETE = 50 # Deleted allowed, else abort.  Use --Force to override.


logging.basicConfig(format='%(asctime)s/:  %(message)s') # /%(levelname)s/%(module)s/%(funcName)s

localListFile = remoteListFile = "" # On critical error, these files are deleted, requiring a --first-sync to recover.
RTN_ABORT = 1 # Tokens for return codes based on criticality.
RTN_CRITICAL = 2 # Aborts allow rerunning.  Criticals block further runs. See Readme.md.


def bidirSync():

	logging.warning("Synching Remote path  <{}>  with Local path  <{}>".format(remotePathBase, localPathBase))
	global localListFile, remoteListFile

	def printMsg(locale, msg, key=''):
		return "  {:9}{:35} - {}".format(locale, msg, key)

	excludes = []
	if exclusions:
		if not os.path.exists(exclusions):
			logging.error("Specified Exclusions file does not exist:  " + exclusions)
			return RTN_ABORT
		excludes.append("--exclude-from")
		excludes.append(exclusions)

	listFileBase  = LOCAL_WD + remotePathBase.replace(':','_').replace(r'/','_') # '/home/<user>/.RCloneSyncWD/Remote__some_path_' or '/home/<user>/.RCloneSyncWD/Remote_'

	localListFile  = listFileBase + '_llocalLSL' # '/home/<user>/.RCloneSyncWD/Remote__some_path_llocalLSL'  (extra 'l' to make the dir list pretty)
	remoteListFile = listFileBase + '_remoteLSL' # '/home/<user>/.RCloneSyncWD/Remote__some_path_remoteLSL'

	switches = []
	for x in range(rcVerbose):
		switches.append("-v")
	if dryRun:
		switches.append("--dry-run")
		if os.path.exists(localListFile): # If dryrun, origianl LSL files are preserved and lsl's are done to the _DRYRUN files
			subprocess.call(['cp', localListFile, localListFile + '_DRYRUN'])
			localListFile  += '_DRYRUN'
		if os.path.exists(remoteListFile):
			subprocess.call(['cp', remoteListFile, remoteListFile + '_DRYRUN'])
			remoteListFile += '_DRYRUN'

	# rclone call wrapper functions with retries
	maxTries=3
	def rcloneLSL(path, ofile, options=None, linenum=0):
		for x in range(maxTries):
			with open(ofile, "w") as of:
				processArgs = ["rclone", "lsl", path]
				if not options == None: processArgs.extend(options)
				if not subprocess.call(processArgs, stdout=of):  return 0
				logging.warning(printMsg("WARNING", "rclone lsl try {} failed.".format(x), path))
		logging.error(printMsg("ERROR", "rclone lsl failed.  Specified path invalid?  (Line {})".format(linenum), path))
		return 1
		

	def rcloneCmd(cmd, p1='', p2='', options=None, linenum=0):
		for x in range(maxTries):
			processArgs = ["rclone", cmd]
			if p1: processArgs.append(p1)
			if p2: processArgs.append(p2)
			if not options == None: processArgs.extend(options)
			if not subprocess.call(processArgs):  return 0
			logging.warning(printMsg("WARNING", "rclone {} try {} failed.".format(cmd, x), p1))
		logging.error(printMsg("ERROR", "rclone {} failed.  (Line {})".format(cmd, linenum), p1))
		return 1



	# ***** first-sync generate local and remote file lists, and copy any unique Remote files to Local ***** 
	if first_sync:
		logging.info(">>>>> Generating --first-sync Local and Remote lists")
		if rcloneLSL(localPathBase, localListFile, excludes, linenum=inspect.getframeinfo(inspect.currentframe()).lineno):  return RTN_CRITICAL

		if rcloneLSL(remotePathBase, remoteListFile, excludes, linenum=inspect.getframeinfo(inspect.currentframe()).lineno):  return RTN_CRITICAL

		status, localNow  = loadList(localListFile)
		if status:  logging.error(printMsg("ERROR", "Failed loading local list file <{}>".format(localListFile))); return RTN_CRITICAL

		status, remoteNow = loadList(remoteListFile)
		if status:  logging.error(printMsg("ERROR", "Failed loading remote list file <{}>".format(remoteListFile))); return RTN_CRITICAL

		for key in remoteNow:
			if key not in localNow:
				src  = remotePathBase + key
				dest = localPathBase + key
				logging.info(printMsg("REMOTE", "  Copying to local", dest))
				if rcloneCmd('copyto', src, dest, switches, linenum=inspect.getframeinfo(inspect.currentframe()).lineno): return RTN_CRITICAL

		if rcloneLSL(localPathBase, localListFile, excludes, linenum=inspect.getframeinfo(inspect.currentframe()).lineno):  return RTN_CRITICAL


	# ***** Check for existance of prior local and remote lsl files *****
	if not os.path.exists(localListFile) or not os.path.exists(remoteListFile):
		# On prior critical error abort, the prior LSL files are renamed to _ERRROR to lock out further runs
		logging.error("***** Cannot find prior local or remote lsl files."); return RTN_CRITICAL


	# ***** Check basic health of access to the local and remote filesystems *****
	if checkAccess:
		logging.info(">>>>> Checking rclone Local and Remote filesystems access health")
		localChkListFile  = listFileBase + '_localChkLSL'
		remoteChkListFile = listFileBase + '_remoteChkLSL'
		chkFile = 'RCLONE_TEST'

		if rcloneLSL(localPathBase, localChkListFile, ['--include', chkFile], linenum=inspect.getframeinfo(inspect.currentframe()).lineno):  return RTN_ABORT

		if rcloneLSL(remotePathBase, remoteChkListFile, ['--include', chkFile], linenum=inspect.getframeinfo(inspect.currentframe()).lineno):  return RTN_ABORT

		status, localCheck  = loadList(localChkListFile)
		if status:  logging.error(printMsg("ERROR", "Failed loading local check list file <{}>".format(localChkListFile))); return RTN_CRITICAL

		status, remoteCheck = loadList(remoteChkListFile)
		if status:  logging.error(printMsg("ERROR", "Failed loading remote check list file <{}>".format(remoteChkListFile))); return RTN_CRITICAL

		if len(localCheck) < 1 or len(localCheck) != len(remoteCheck):
			logging.error(printMsg("ERROR", "Failed access health test:  <{}> local count {}, remote count {}"
									 .format(chkFile, len(localCheck), len(remoteCheck)), "")); return RTN_CRITICAL
		else:
			for key in localCheck:
				logging.debug("Check key <{}>".format(key))
				if key not in remoteCheck:
					logging.error(printMsg("ERROR", "Failed access health test:  Local key <{}> not found in remote".format(key), "")); return RTN_CRITICAL

		os.remove(localChkListFile) # _*ChkLSL files will be left if the check fails.  Look at these files for clues.
		os.remove(remoteChkListFile)


	# ***** Get current listings of the local and remote trees *****
	logging.info(">>>>> Generating Local and Remote lists")

	localListFileNew = listFileBase + '_llocalLSL_new'
	if rcloneLSL(localPathBase, localListFileNew, excludes, linenum=inspect.getframeinfo(inspect.currentframe()).lineno):  return RTN_CRITICAL

	remoteListFileNew = listFileBase + '_remoteLSL_new'
	if rcloneLSL(remotePathBase, remoteListFileNew, excludes, linenum=inspect.getframeinfo(inspect.currentframe()).lineno):  return RTN_CRITICAL


	# ***** Load Current and Prior listings of both Local and Remote trees *****
	status, localPrior =   loadList(localListFile) # Successful load of the file return status = 0
	if status:				  logging.error(printMsg("ERROR", "Failed loading prior local list file <{}>".format(localListFile))); return RTN_CRITICAL
	if len(localPrior) == 0:	logging.error(printMsg("ERROR", "Zero length in prior local list file <{}>".format(localListFile))); return RTN_CRITICAL

	status, remotePrior =  loadList(remoteListFile)
	if status:				  logging.error(printMsg("ERROR", "Failed loading prior remote list file <{}>".format(remoteListFile))); return RTN_CRITICAL
	if len(remotePrior) == 0:   logging.error(printMsg("ERROR", "Zero length in prior remote list file <{}>".format(remoteListFile))); return RTN_CRITICAL

	status, localNow =	 loadList(localListFileNew)
	if status:				  logging.error(printMsg("ERROR", "Failed loading current local list file <{}>".format(localListFileNew))); return RTN_ABORT
	if len(localNow) == 0:	  logging.error(printMsg("ERROR", "Zero length in current local list file <{}>".format(localListFileNew))); return RTN_ABORT

	status, remoteNow =	loadList(remoteListFileNew)
	if status:				  logging.error(printMsg("ERROR", "Failed loading current remote list file <{}>".format(remoteListFileNew))); return RTN_ABORT
	if len(remoteNow) == 0:	 logging.error(printMsg("ERROR", "Zero length in current remote list file <{}>".format(remoteListFileNew))); return RTN_ABORT


	# ***** Check for LOCAL deltas relative to the prior sync
	logging.info(printMsg("LOCAL", "Checking for Diffs", localPathBase))
	localDeltas = {}
	localDeleted = 0
	for key in localPrior:
		_newer=False; _older=False; _size=False; _deleted=False
		if key not in localNow:
			logging.info(printMsg("LOCAL", "  File was deleted", key))
			localDeleted += 1
			_deleted=True			
		else:
			if localPrior[key]['datetime'] != localNow[key]['datetime']:
				if localPrior[key]['datetime'] < localNow[key]['datetime']:
					logging.info(printMsg("LOCAL", "  File is newer", key))
					_newer=True
				else: # Now local version is older than prior sync
					logging.info(printMsg("LOCAL", "  File is OLDER", key))
					_older=True
			if localPrior[key]['size'] != localNow[key]['size']:
				logging.info(printMsg("LOCAL", "  File size is different", key))
				_size=True

		if _newer or _older or _size or _deleted:
			localDeltas[key] = {'new':False, 'newer':_newer, 'older':_older, 'size':_size, 'deleted':_deleted}

	for key in localNow:
		if key not in localPrior:
			logging.info(printMsg("LOCAL", "  File is new", key))
			localDeltas[key] = {'new':True, 'newer':False, 'older':False, 'size':False, 'deleted':False}

	localDeltas = collections.OrderedDict(sorted(localDeltas.items())) # sort the deltas list
	if len(localDeltas) > 0:
		news = newers = olders = deletes = 0
		for key in localDeltas:
			if localDeltas[key]['new']:	  news += 1
			if localDeltas[key]['newer']:	newers += 1
			if localDeltas[key]['older']:	olders += 1
			if localDeltas[key]['deleted']:  deletes += 1
		logging.warning("  {:4} file change(s) on LOCAL:  {:4} new, {:4} newer, {:4} older, {:4} deleted".format(len(localDeltas), news, newers, olders, deletes))


	# ***** Check for REMOTE deltas relative to the prior sync
	logging.info(printMsg("REMOTE", "Checking for Diffs", remotePathBase))
	remoteDeltas = {}
	remoteDeleted = 0
	for key in remotePrior:
		_newer=False; _older=False; _size=False; _deleted=False
		if key not in remoteNow:
			logging.info(printMsg("REMOTE", "  File was deleted", key))
			remoteDeleted += 1
			_deleted=True			
		else:
			if remotePrior[key]['datetime'] != remoteNow[key]['datetime']:
				if remotePrior[key]['datetime'] < remoteNow[key]['datetime']:
					logging.info(printMsg("REMOTE", "  File is newer", key))
					_newer=True
				else: # Current remote version is older than prior sync 
					logging.info(printMsg("REMOTE", "  File is OLDER", key))
					_older=True
			if remotePrior[key]['size'] != remoteNow[key]['size']:
				logging.info(printMsg("REMOTE", "  File size is different", key))
				_size=True

		if _newer or _older or _size or _deleted:
			remoteDeltas[key] = {'new':False, 'newer':_newer, 'older':_older, 'size':_size, 'deleted':_deleted}

	for key in remoteNow:
		if key not in remotePrior:
			logging.info(printMsg("REMOTE", "  File is new", key))
			remoteDeltas[key] = {'new':True, 'newer':False, 'older':False, 'size':False, 'deleted':False}

	remoteDeltas = collections.OrderedDict(sorted(remoteDeltas.items())) # sort the deltas list
	if len(remoteDeltas) > 0:
		news = newers = olders = deletes = 0
		for key in remoteDeltas:
			if remoteDeltas[key]['new']:	  news += 1
			if remoteDeltas[key]['newer']:	newers += 1
			if remoteDeltas[key]['older']:	olders += 1
			if remoteDeltas[key]['deleted']:  deletes += 1
		logging.warning("  {:4} file change(s) on REMOTE: {:4} new, {:4} newer, {:4} older, {:4} deleted".format(len(remoteDeltas), news, newers, olders, deletes))


	# ***** Check for too many deleted files - possible error condition and don't want to start deleting on the other side !!!
	tooManyLocalDeletes = False
	if not force and float(localDeleted)/len(localPrior) > float(MAX_DELETE)/100:
		logging.error("Excessive number of deletes (>{}%, {} of {}) found on the Local system {} - Aborting.  Run with --Force if desired."
					   .format(MAX_DELETE, localDeleted, len(localPrior), localPathBase))
		tooManyLocalDeletes = True

	tooManyRemoteDeletes = False # Local error message placed here so that it is at the end of the listed changes for both
	if not force and float(remoteDeleted)/len(remotePrior) > float(MAX_DELETE)/100:
		logging.error("Excessive number of deletes (>{}%, {} of {}) found on the Remote system {} - Aborting.  Run with --Force if desired."
					   .format(MAX_DELETE, remoteDeleted, len(remotePrior), remotePathBase))
		tooManyRemoteDeletes = True

	if tooManyLocalDeletes or tooManyRemoteDeletes: return RTN_ABORT


	# ***** Update LOCAL with all the changes on REMOTE *****
	if len(remoteDeltas) == 0:
		logging.info(">>>>> No changes on Remote - Skipping ahead")
	else:
		logging.info(">>>>> Applying changes on Remote to Local")

	for key in remoteDeltas:

		if remoteDeltas[key]['new']:
			#logging.info(printMsg("REMOTE", "  New file", key))
			if key not in localNow:
				# File is new on remote, does not exist on local
				src  = remotePathBase + key
				dest = localPathBase + key
				logging.info(printMsg("REMOTE", "  Copying to local", dest))
				if rcloneCmd('copyto', src, dest, switches, linenum=inspect.getframeinfo(inspect.currentframe()).lineno): return RTN_CRITICAL

			else:
				# File is new on remote AND new on local
				src  = remotePathBase + key 
				dest = localPathBase + key + '_REMOTE' 
				logging.warning(printMsg("WARNING", "  Changed in both local and remote", key))
				logging.warning(printMsg("REMOTE", "  Copying to local", dest))
				if rcloneCmd('copyto', src, dest, switches, linenum=inspect.getframeinfo(inspect.currentframe()).lineno): return RTN_CRITICAL
				# Rename local
				src  = localPathBase + key 
				dest = localPathBase + key + '_LOCAL' 
				logging.warning(printMsg("LOCAL", "  Renaming local copy", dest))
				if rcloneCmd('moveto', src, dest, switches, linenum=inspect.getframeinfo(inspect.currentframe()).lineno): return RTN_CRITICAL


		if remoteDeltas[key]['newer']:
			if key not in localDeltas:
				# File is newer on remote, unchanged on local
				src  = remotePathBase + key 
				dest = localPathBase + key 
				logging.info(printMsg("REMOTE", "  Copying to local", dest))
				if rcloneCmd('copyto', src, dest, ["--ignore-times"] + switches, linenum=inspect.getframeinfo(inspect.currentframe()).lineno): return RTN_CRITICAL
			else:
				if key in localNow:
					# File is newer on remote AND also changed (newer/older/size) on local
					src  = remotePathBase + key 
					dest = localPathBase + key + '_REMOTE' 
					logging.warning(printMsg("WARNING", "  Changed in both local and remote", key))
					logging.warning(printMsg("REMOTE", "  Copying to local", dest))
					if rcloneCmd('copyto', src, dest, ["--ignore-times"] + switches, linenum=inspect.getframeinfo(inspect.currentframe()).lineno): return RTN_CRITICAL
					# Rename local
					src  = localPathBase + key 
					dest = localPathBase + key + '_LOCAL' 
					logging.warning(printMsg("LOCAL", "  Renaming local copy", dest))
					if rcloneCmd('moveto', src, dest, switches, linenum=inspect.getframeinfo(inspect.currentframe()).lineno): return RTN_CRITICAL
				else:
					# File is newer on remote AND also deleted locally
					src  = remotePathBase + key 
					dest = localPathBase + key 
					logging.info(printMsg("REMOTE", "  Copying to local", dest))
					if rcloneCmd('copyto', src, dest, ["--ignore-times"] + switches, linenum=inspect.getframeinfo(inspect.currentframe()).lineno): return RTN_CRITICAL
					

		if remoteDeltas[key]['deleted']:
			if key not in localDeltas:
				if key in localNow:
					# File is deleted on remote, unchanged locally
					src  = localPathBase + key 
					logging.info(printMsg("LOCAL", "  Deleting file", src))
					if rcloneCmd('delete', src, switches, linenum=inspect.getframeinfo(inspect.currentframe()).lineno): return RTN_CRITICAL

					# File is deleted on remote AND changed (newer/older/size) on local
					# Local version survives
##			else:
##				if key in localNow:
##					src  = localRoot + '/' + key 
##					dest = localRoot + '/' + key + '_LOCAL' 
##					logging.warning(printMsg("*****", "  Also changed locally", key))
##					logging.warning(printMsg("LOCAL", "  Renaming local", dest))
##					if subprocess.call(shlex.split("rclone moveto " + src + dest + switches)):
##						logging.error(printMsg("*****", "Failed rclone moveto.  (Line {})".format(inspect.getframeinfo(inspect.currentframe()).lineno-1), src)); return RTN_CRITICAL

	for key in localDeltas:
		if localDeltas[key]['deleted']:
			if (key in remoteDeltas) and (key in remoteNow):
				# File is deleted on local AND changed (newer/older/size) on remote
				src  = remotePathBase + key 
				dest = localPathBase + key 
				logging.warning(printMsg("WARNING", "  Deleted locally and also changed remotely", key))
				logging.warning(printMsg("REMOTE", "  Copying to local", dest))
				if rcloneCmd('copyto', src, dest, switches, linenum=inspect.getframeinfo(inspect.currentframe()).lineno): return RTN_CRITICAL


	# ***** Sync LOCAL changes to REMOTE ***** 
	if len(remoteDeltas) == 0 and len(localDeltas) == 0 and not first_sync:
		logging.info(">>>>> No changes on Local  - Skipping sync from Local to Remote")
	else:
		logging.info(">>>>> Synching Local to Remote")
		# switches = '' #'--ignore-size '
		if rcloneCmd('sync', localPathBase, remotePathBase, excludes + switches, linenum=inspect.getframeinfo(inspect.currentframe()).lineno): return RTN_CRITICAL

		logging.info(">>>>> rmdirs Remote")
		if rcloneCmd('rmdirs', remotePathBase, None, switches, linenum=inspect.getframeinfo(inspect.currentframe()).lineno): return RTN_CRITICAL

		logging.info(">>>>> rmdirs Local")
		if rcloneCmd('rmdirs', localPathBase, None, switches, linenum=inspect.getframeinfo(inspect.currentframe()).lineno): return RTN_CRITICAL


	# ***** Clean up *****
	logging.info(">>>>> Refreshing Local and Remote lsl files")
	os.remove(remoteListFileNew)
	os.remove(localListFileNew)

	if rcloneLSL(localPathBase, localListFile, excludes, linenum=inspect.getframeinfo(inspect.currentframe()).lineno):  return RTN_CRITICAL

	if rcloneLSL(remotePathBase, remoteListFile, excludes, linenum=inspect.getframeinfo(inspect.currentframe()).lineno):  return RTN_CRITICAL



LINE_FORMAT = re.compile('\s*([0-9]+) ([\d\-]+) ([\d:]+).([\d]+) (.*)')

def loadList(infile):
	# Format ex:
	#  3009805 2013-09-16 04:13:50.000000000 12 - Wait.mp3
	#   541087 2017-06-19 21:23:28.610000000 DSC02478.JPG
	#	size  <----- datetime (epoch) ----> key

	d = {}
	try:
		with open(infile, 'r') as f:
			for line in f:
				out = LINE_FORMAT.match(line)
				if out:
					size = out.group(1)
					date = out.group(2)
					_time = out.group(3)
					microsec = out.group(4)
					date_time = time.mktime(datetime.strptime(date + ' ' + _time, '%Y-%m-%d %H:%M:%S').timetuple()) + float('.'+ microsec)
					filename = out.group(5)
					d[filename] = {'size': size, 'datetime': date_time}
				else:
					logging.warning("Something wrong with this line (ignored) in {}:\n   <{}>".format(infile, line))

		return 0, collections.OrderedDict(sorted(d.items())) # return Success and a sorted list
	except:
		logging.error("Exception in loadList loading <{}>:  <{}>".format(infile, sys.exc_info()))
		return 1, "" # return False


LOCK_FILE = "/tmp/RCloneSync_LOCK"
def requestLock(caller):
	for xx in range(5):
		if os.path.exists(LOCK_FILE):
			with open(LOCK_FILE) as fd:
				lockedBy = fd.read()
				logging.debug("{}.  Waiting a sec.".format(lockedBy[:-1])) # remove the \n
			time.sleep(1)
		else:  
			with open(LOCK_FILE, 'w') as fd:
				fd.write("Locked by {} at {}\n".format(caller, time.asctime(time.localtime())))
				logging.debug("LOCKed by {} at {}.".format(caller, time.asctime(time.localtime())))
			return 0
	logging.warning("Timed out waiting for LOCK file to be cleared.  {}".format(lockedBy))
	return -1

def releaseLock(caller):
	if os.path.exists(LOCK_FILE):
		with open(LOCK_FILE) as fd:
			lockedBy = fd.read()
			logging.debug("Removed lock file:  {}.".format(lockedBy))
		os.remove(LOCK_FILE)
		return 0
	else:
		logging.warning("<{}> attempted to remove /tmp/LOCK but the file does not exist.".format(caller))
		return -1



########### Call point.
if __name__ == '__main__':

	logging.warning("***** BiDirectional Sync for Cloud Services using RClone *****")

	try:
		clouds = subprocess.check_output(['rclone', 'listremotes'])
	except subprocess.CalledProcessError as e:
		logging.error("ERROR  Can't get list of known remotes.  Have you run rclone config?"); exit()
	except:
		logging.error("ERROR  rclone not installed?\nError message: {}\n".format(sys.exc_info()[1])); exit()
	clouds = [c.decode('utf-8') for c in clouds.split()] # Py3 create a byte array instead a string list.

	parser = argparse.ArgumentParser(description="BiDirectional Sync for Cloud Services using RClone.")
	parser.add_argument('-v', '--version',
		action='version',
		version='RCloneSyn python2/3 script v.' + __VERSION__)
	parser.add_argument('Cloud',
		help="Name of remote cloud service ({}) plus optional path".format(clouds))
	parser.add_argument('LocalPath',
		help="Path to local tree base",
		default=None)
	parser.add_argument('-1', '--first-sync',
		help="First run setup.  WARNING: Local files may overwrite Remote versions. Also asserts --verbose.",
		action='store_true')
	parser.add_argument('--check-access',
		help="Ensure expected RCLONE_TEST files are found on both Local and Remote filesystems, else abort.",
		action='store_true')
	parser.add_argument('-f', '--force',
		help="Bypass MAX_DELETE ({}%%) safety check and run the sync.  Also asserts --verbose.".format(MAX_DELETE),
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
		default=5)
	args = parser.parse_args()

	first_sync	= args.first_sync
	checkAccess  = args.check_access
	verbose	  = args.verbose
	rcVerbose	= (args.rc_verbose if args.rc_verbose else 0)
	exclusions   = args.exclude_list_file
	dryRun	   = args.dry_run
	force		= args.force

	remoteFormat = re.compile('([\w-]+):(.*)') # Handle variations in the Cloud argument -- Remote: or Remote:some/path or Remote:/some/path
	out = remoteFormat.match(args.Cloud)
	remoteName = remotePathPart = remotePathBase = ''
	if out:
		remoteName = out.group(1) + ':'
		if remoteName not in clouds:
			logging.error("ERROR  Cloud argument <{}> not in list of configured remotes: {}".format(remoteName, clouds)); exit()
		remotePathPart = out.group(2)
		if remotePathPart != '':
			if remotePathPart[0] != '/':
				remotePathPart = '/' + remotePathPart # For consistency ensure the path part starts and ends with /'s
			if remotePathPart[-1] != '/':
				remotePathPart += '/'
		remotePathBase = remoteName + remotePathPart # 'Remote:' or 'Remote:/some/path/'
	else:
		logging.error("ERROR  Cloud parameter <{}> cannot be parsed. ':' missing?  Configured remotes: {}".format(args.Cloud, clouds)); exit()


	localPathBase = args.LocalPath
	if localPathBase[-1] != '/': # For consistency ensure the path ends with /
		localPathBase += '/'								
	if not os.path.exists(localPathBase):
		logging.error("ERROR  LocalPath parameter <{}> cannot be accessed.  Path error?  Aborting".format(localPathBase)); exit()


	if verbose or rcVerbose>0 or force or first_sync or dryRun:
		verbose = True
		logging.getLogger().setLevel(logging.INFO) # Log each file transaction
	else:
		logging.getLogger().setLevel(logging.WARNING) # Log only unusual events


	if requestLock(sys.argv) == 0:
		status = bidirSync()
		if status == RTN_CRITICAL:
			logging.error('***** Critical Error Abort - Must run --first-sync to recover.  See README.md *****')
			if os.path.exists(localListFile):   subprocess.call(['mv', localListFile, localListFile + '_ERROR'])
			if os.path.exists(remoteListFile):  subprocess.call(['mv', remoteListFile, remoteListFile + '_ERROR'])
		if status == RTN_ABORT:			
			logging.error('***** Error abort.  Try running RCloneSync again. *****')
		releaseLock(sys.argv)
	else:  logging.warning("Prior lock file in place.  Aborting.")
	logging.warning(">>>>> All done.\n\n")
