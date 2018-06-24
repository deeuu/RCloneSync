import logging
import os
from .cli import cli
from . import core


RTN_ABORT = 1 # Tokens for return codes based on criticality.
RTN_CRITICAL = 2 # Aborts allow rerunning. Criticals block further runs. See Readme.md.

