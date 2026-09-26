"""The start of the packaged application. PyInstaller builds the app from this file."""

import sys

from mimikr.cli import main

sys.exit(main())
