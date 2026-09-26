#!/usr/bin/env python3
"""Build the application for Windows or Linux, and pack it. Run it from the root of the repository:

    uv run --group build python scripts/build-app.py

On Windows it writes dist/mimikr-<version>-windows-x64.zip, and on Linux
dist/mimikr-<version>-linux-x64.tar.gz. Each holds the folder dist/mimikr with
the program mimikr (mimikr.exe on Windows). macOS uses build-macos-app.sh.
"""

import platform
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

version = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
system = {"win32": "windows", "linux": "linux"}.get(sys.platform)
if system is None:
    sys.exit("This script builds for Windows and Linux. On macOS, run scripts/build-macos-app.sh.")
machine = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(platform.machine().lower(),
                                                                                  platform.machine().lower())

command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", "mimikr",
           "--collect-submodules", "mimikr"]
if system == "windows":
    command += ["--icon", "assets/icon.ico"]
subprocess.run([*command, "packaging/launch.py"], check=True)

base = Path("dist") / f"mimikr-{version}-{system}-{machine}"
archive = shutil.make_archive(str(base), "zip" if system == "windows" else "gztar", root_dir="dist", base_dir="mimikr")
print(f"written {archive}")
