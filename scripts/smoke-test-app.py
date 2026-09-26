#!/usr/bin/env python3
"""Test a built application: it reads identities, and its window starts.

    python scripts/smoke-test-app.py <the program>

The program is dist/mimikr.app/Contents/MacOS/mimikr on macOS,
dist/mimikr/mimikr.exe on Windows, and dist/mimikr/mimikr on Linux.
The test uses the invented identities in examples/identities, in a temporary
home, and the Qt offscreen platform, so it opens no window.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

program = Path(sys.argv[1]).resolve()
home = Path(tempfile.mkdtemp())
shutil.copytree("examples/identities", home / "identities")
environment = {**os.environ, "MIMIKR_HOME": str(home), "QT_QPA_PLATFORM": "offscreen"}

check = subprocess.run([str(program), "check"], env=environment, capture_output=True, text=True, timeout=120)
print(check.stdout)
if check.returncode != 0 or "sam (Sam)" not in check.stdout:
    print(check.stderr)
    sys.exit(f"check failed with exit code {check.returncode}")

window = subprocess.Popen([str(program)], env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
time.sleep(10)
if window.poll() is not None:
    print(window.stdout.read())
    sys.exit(f"the window stopped with exit code {window.returncode}")
window.kill()
window.wait()
print("The window ran for 10 seconds.")
