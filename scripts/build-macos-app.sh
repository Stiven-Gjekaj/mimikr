#!/bin/sh
# Build dist/mimikr.app and a zip of it, on macOS. Run it from the root of the repository.
#
#   scripts/build-macos-app.sh
#
# The script makes assets/icon.icns from assets/icon.svg when rsvg-convert is
# on the computer. Otherwise it uses the icon.icns in the repository.
set -eu

version=$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)
arch=$(uname -m)

if command -v rsvg-convert >/dev/null 2>&1; then
    iconset=$(mktemp -d)/mimikr.iconset
    mkdir -p "$iconset"
    for size in 16 32 128 256 512; do
        rsvg-convert -w $size -h $size assets/icon.svg -o "$iconset/icon_${size}x${size}.png"
        rsvg-convert -w $((size * 2)) -h $((size * 2)) assets/icon.svg -o "$iconset/icon_${size}x${size}@2x.png"
    done
    iconutil -c icns "$iconset" -o assets/icon.icns
fi

uv run --group build pyinstaller \
    --noconfirm --clean --windowed \
    --name mimikr \
    --icon assets/icon.icns \
    --osx-bundle-identifier com.stivengjekaj.mimikr \
    --collect-submodules mimikr \
    packaging/launch.py

# PyInstaller writes the version 0.0.0 into Info.plist. Write the version of
# the package. A change to Info.plist breaks the signature, so sign again.
plist=dist/mimikr.app/Contents/Info.plist
plutil -replace CFBundleShortVersionString -string "$version" "$plist"
plutil -replace CFBundleVersion -string "$version" "$plist"
codesign --force --deep --sign - dist/mimikr.app
codesign --verify --deep --strict dist/mimikr.app

zip="dist/mimikr-$version-macos-$arch.zip"
rm -f "$zip"
ditto -c -k --keepParent dist/mimikr.app "$zip"
shasum -a 256 "$zip"
