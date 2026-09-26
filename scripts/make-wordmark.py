#!/usr/bin/env python3
"""Build assets/wordmark.svg. Run it from the root of the repository.

The banner is a chat window: a speech bubble and the name in a 5x7 pixel face
on a 15px grid. The margin above the name is equal to the margin below it, so
the content is at the vertical center.

The script draws the letters itself. Thus the file needs no font on the
computer of the reader, and it carries no font licence.
"""

CELL = 15          # one pixel of the face
COLS, ROWS = 5, 7  # each glyph has this size
ADVANCE = (COLS + 1) * CELL

FACE = {
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
}

# A speech bubble with a tail at the bottom left. It has the height of a glyph.
BUBBLE = (
    "0111110",
    "1000001",
    "1000001",
    "1000001",
    "0111110",
    "0110000",
    "0100000",
)


def blocks(cells):
    """Join the cells of each row into one rectangle for each run."""
    out, cells = [], sorted(cells)
    i = 0
    while i < len(cells):
        row, col = cells[i]
        run = 1
        while i + run < len(cells) and cells[i + run] == (row, col + run):
            run += 1
        out.append(f"M{col*CELL} {row*CELL}h{run*CELL}v{CELL}h-{run*CELL}z")
        i += run
    return "".join(out)


def grid(rows):
    return [(r, c) for r, bits in enumerate(rows) for c, bit in enumerate(bits) if bit == "1"]


def word(text):
    cells = []
    for n, ch in enumerate(text):
        cells += [(r, c + n * (COLS + 1)) for r, c in grid(FACE[ch])]
    return blocks(cells)


WORD = "MIMIKR"
PAD = 48                            # the margin on each side
text_x = PAD + (len(BUBBLE[0]) + 2) * CELL
text_w = len(WORD) * ADVANCE - CELL
W = text_x + text_w + PAD
H = 2 * PAD + ROWS * CELL

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="mimikr">
  <title>mimikr</title>

  <defs>
    <!-- The colors of a chameleon, from violet to green. The gradient moves
         along the word, so the letters change color the way a mimic does. -->
    <linearGradient id="ink" x1="0" y1="0" x2="1" y2="0.3" spreadMethod="reflect">
      <stop offset="0" stop-color="#a78bfa"/>
      <stop offset="0.35" stop-color="#60a5fa"/>
      <stop offset="0.7" stop-color="#34d399"/>
      <stop offset="1" stop-color="#a3e635"/>
      <animateTransform attributeName="gradientTransform" type="translate"
                        values="0 0;1 0;0 0" dur="12s" repeatCount="indefinite"/>
    </linearGradient>

    <filter id="glow" x="-20%" y="-40%" width="140%" height="180%">
      <feGaussianBlur stdDeviation="6" result="blur"/>
      <feMerge>
        <feMergeNode in="blur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>

    <!-- One scanline, tiled. -->
    <pattern id="scanlines" width="4" height="4" patternUnits="userSpaceOnUse">
      <rect width="4" height="2" fill="#000" opacity="0.28"/>
    </pattern>
  </defs>

  <rect width="{W}" height="{H}" rx="16" fill="#07090f"/>
  <rect x="6" y="6" width="{W-12}" height="{H-12}" rx="11"
        fill="none" stroke="#60a5fa" stroke-opacity="0.28" stroke-width="2"/>

  <g filter="url(#glow)">
    <path d="{blocks(grid(BUBBLE))}" fill="#a78bfa" opacity="0.6"
          transform="translate({PAD} {PAD})"/>
    <path d="{word(WORD)}" fill="url(#ink)" transform="translate({text_x} {PAD})"/>
  </g>

  <rect width="{W}" height="{H}" rx="16" fill="url(#scanlines)"
        opacity="0.5" pointer-events="none"/>
</svg>
'''
open("assets/wordmark.svg", "w").write(svg)
print(f"written {W}x{H}")
