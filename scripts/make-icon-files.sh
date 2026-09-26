#!/bin/sh
# Make assets/icon.icns (macOS) and assets/icon.ico (Windows) from assets/icon.svg.
# Run it on macOS from the root of the repository, after scripts/make-icon.py.
# It needs rsvg-convert, and it gets Pillow through uv.
set -eu
work=$(mktemp -d)
iconset="$work/mimikr.iconset"
mkdir -p "$iconset"
for size in 16 32 128 256 512; do
    rsvg-convert -w $size -h $size assets/icon.svg -o "$iconset/icon_${size}x${size}.png"
    rsvg-convert -w $((size * 2)) -h $((size * 2)) assets/icon.svg -o "$iconset/icon_${size}x${size}@2x.png"
done
iconutil -c icns "$iconset" -o assets/icon.icns
rsvg-convert -w 256 -h 256 assets/icon.svg -o "$work/icon256.png"
uv run --with pillow python -c "
from PIL import Image
Image.open('$work/icon256.png').save('assets/icon.ico', sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
"
echo "written assets/icon.icns and assets/icon.ico"
