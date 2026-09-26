#!/usr/bin/env python3
"""Build assets/icon.svg, the icon of the application. Run it from the root of the repository.

The icon is the pixel speech bubble of the wordmark, in white, on a tile with
the colors of the wordmark. scripts/build-macos-app.sh turns it into icon.icns.
"""

SIZE = 1024
# The bubble of the wordmark, one character for each cell. The cells are (row, col).
BUBBLE = (
    "0111110",
    "1000001",
    "1010101",
    "1000001",
    "0111110",
    "0110000",
    "0100000",
)
CELL = 88
width, height = len(BUBBLE[0]) * CELL, len(BUBBLE) * CELL
left, top = (SIZE - width) // 2, (SIZE - height) // 2 + 20

cells = "".join(
    f'<rect x="{left + col * CELL}" y="{top + row * CELL}" width="{CELL}" height="{CELL}"/>'
    for row, bits in enumerate(BUBBLE)
    for col, bit in enumerate(bits)
    if bit == "1"
)

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}" width="{SIZE}" height="{SIZE}">
  <defs>
    <linearGradient id="tile" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#a78bfa"/>
      <stop offset="0.55" stop-color="#60a5fa"/>
      <stop offset="1" stop-color="#34d399"/>
    </linearGradient>
  </defs>
  <!-- The macOS grid: a tile of 824 pixels with a radius of 185, in the middle of 1024. -->
  <rect x="100" y="100" width="824" height="824" rx="185" fill="url(#tile)"/>
  <g fill="#ffffff">{cells}</g>
</svg>
'''
open("assets/icon.svg", "w").write(svg)
print("written assets/icon.svg")
