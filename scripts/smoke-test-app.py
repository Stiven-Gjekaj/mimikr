#!/usr/bin/env python3
"""Test a built application: it reads identities, and its window starts.

On macOS, the test also finds the version of pyproject.toml in Info.plist.

    python scripts/smoke-test-app.py <the program>

The program is dist/mimikr.app/Contents/MacOS/mimikr on macOS,
dist/mimikr/mimikr.exe on Windows, and dist/mimikr/mimikr on Linux.
The test uses the invented identities in examples/identities, in a temporary
home, and the Qt offscreen platform, so it opens no window.
"""

import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

program = Path(sys.argv[1]).resolve()
plist = program.parent.parent / "Info.plist"
if plist.exists():
    version = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    info = plistlib.loads(plist.read_bytes())
    for key in ("CFBundleShortVersionString", "CFBundleVersion"):
        if info.get(key) != version:
            sys.exit(f"{key} in Info.plist is {info.get(key)!r}, and pyproject.toml says {version!r}")
    print(f"Info.plist says version {version}.")
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
