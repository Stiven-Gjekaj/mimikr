"""The look of the window: colors for light and dark, an accent, and a style sheet.

The module knows no Qt. It returns plain text and colors, so a test can check
them with no screen.
"""

import re
import zlib
from dataclasses import dataclass

THEMES = ("system", "light", "dark")

ACCENTS = {
    "violet": "#8b5cf6",
    "blue": "#3b82f6",
    "teal": "#14b8a6",
    "green": "#22c55e",
    "orange": "#f97316",
    "pink": "#ec4899",
}
DEFAULT_ACCENT = "violet"

FONT_SIZES = range(12, 19)

# The colors of the round pictures with the initials of an identity.
AVATAR_COLORS = ("#8b5cf6", "#3b82f6", "#14b8a6", "#22c55e", "#f59e0b", "#f97316", "#ec4899", "#06b6d4")


@dataclass(frozen=True)
class Palette:
    dark: bool
    window: str
    sidebar: str
    surface: str
    bubble: str
    border: str
    text: str
    muted: str
    hover: str
    selected: str
    danger: str
    accent: str
    accent_text: str


def _luminance(color: str) -> float:
    """Return the relative luminance of a color, as WCAG defines it."""
    channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first: str, second: str) -> float:
    light, dark = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def accent_color(accent: str) -> str:
    """Return the color of a named accent, or of a '#rrggbb' value. Use violet for any other value."""
    if accent in ACCENTS:
        return ACCENTS[accent]
    if re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
        return accent.lower()
    return ACCENTS[DEFAULT_ACCENT]


def text_on(color: str) -> str:
    """Return white or near black, whichever is easier to read on the color."""
    white, black = "#ffffff", "#0b0c0f"
    return white if contrast(color, white) >= contrast(color, black) else black


def is_dark(theme: str, system_dark: bool) -> bool:
    if theme == "dark":
        return True
    if theme == "light":
        return False
    return system_dark


def palette(dark: bool, accent: str) -> Palette:
    color = accent_color(accent)
    if dark:
        return Palette(
            dark=True, window="#111318", sidebar="#0c0e12", surface="#181b21", bubble="#23272f",
            border="#2a2f38", text="#e6e8ec", muted="#8b919c", hover="#1b1f26", selected="#232833",
            danger="#f87171", accent=color, accent_text=text_on(color),
        )
    return Palette(
        dark=False, window="#ffffff", sidebar="#f6f7f9", surface="#ffffff", bubble="#f0f2f5",
        border="#e3e6ea", text="#16181d", muted="#6b7280", hover="#eef0f3", selected="#e8ebf1",
        danger="#dc2626", accent=color, accent_text=text_on(color),
    )


def initials(name: str) -> str:
    """Return one or two letters for the round picture of a name."""
    words = [word for word in re.split(r"[\s._-]+", name) if word]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:1].upper()
    return (words[0][:1] + words[-1][:1]).upper()


def avatar_color(key: str) -> str:
    """Return the same color for the same identity, each time."""
    return AVATAR_COLORS[zlib.crc32(key.encode()) % len(AVATAR_COLORS)]


def font_size(size: int) -> int:
    return min(max(size, FONT_SIZES.start), FONT_SIZES.stop - 1)


def stylesheet(p: Palette, size: int = 14) -> str:
    """Return the Qt style sheet of the whole window."""
    base = font_size(size)
    small, large = base - 2, base + 4
    return f"""
* {{ font-size: {base}px; color: {p.text}; }}
QMainWindow, QWidget#main, QWidget#page, QStackedWidget, QScrollArea, QWidget#messages {{ background: {p.window}; }}
QDialog {{ background: {p.window}; }}
QWidget#sidebar {{ background: {p.sidebar}; border-right: 1px solid {p.border}; }}
QLabel#brand {{ font-size: {base + 6}px; font-weight: 700; }}
QLabel#brandDot {{ color: {p.accent}; font-size: {base + 6}px; font-weight: 700; }}

QPushButton {{
    background: {p.surface}; border: 1px solid {p.border}; border-radius: 9px;
    padding: 7px 14px; font-weight: 500;
}}
QPushButton:hover {{ background: {p.hover}; }}
QPushButton:disabled {{ color: {p.muted}; }}
QPushButton#primary {{ background: {p.accent}; color: {p.accent_text}; border: none; font-weight: 600; }}
QPushButton#primary:hover {{ background: {p.accent}; }}
QPushButton#primary:disabled {{ background: {p.border}; color: {p.muted}; }}
QPushButton#ghost {{ background: transparent; border: none; color: {p.muted}; text-align: left; }}
QPushButton#ghost:hover {{ background: {p.hover}; color: {p.text}; }}
QPushButton#ghost:checked {{ background: {p.selected}; color: {p.text}; }}
QPushButton#danger {{ background: transparent; border: 1px solid {p.border}; color: {p.danger}; }}
QPushButton#danger:hover {{ background: {p.hover}; }}
QPushButton#swatch {{ border-radius: 13px; padding: 0; min-width: 26px; max-width: 26px;
    min-height: 26px; max-height: 26px; }}

QListWidget#rooms {{ background: transparent; border: none; outline: none; }}
QListWidget#rooms::item {{ border-radius: 10px; margin: 1px 0; }}
QListWidget#rooms::item:hover {{ background: {p.hover}; }}
QListWidget#rooms::item:selected {{ background: {p.selected}; }}
QLabel#roomTitle {{ font-weight: 600; background: transparent; }}
QLabel#roomMembers {{ color: {p.muted}; font-size: {small}px; background: transparent; }}
QLabel#sectionLabel {{ color: {p.muted}; font-size: {small}px; font-weight: 600; letter-spacing: 0.5px; }}

QWidget#header {{ background: {p.window}; border-bottom: 1px solid {p.border}; }}
QLabel#title {{ font-size: {large}px; font-weight: 700; }}
QLabel#subtitle, QLabel#status, QLabel#hint {{ color: {p.muted}; font-size: {small}px; }}
QLabel#error {{ color: {p.danger}; font-size: {small}px; }}
QLabel#emptyTitle {{ font-size: {base + 10}px; font-weight: 700; }}
QLabel#emptyText {{ color: {p.muted}; }}

QLabel#name {{ color: {p.muted}; font-size: {small}px; font-weight: 600; }}
QLabel#bubble {{ background: {p.bubble}; border-radius: 16px; padding: 9px 13px; }}
QLabel#draft {{ background: {p.bubble}; color: {p.muted}; border-radius: 16px; padding: 9px 13px; }}
QLabel#mine {{ background: {p.accent}; color: {p.accent_text}; border-radius: 16px; padding: 9px 13px; }}
QLabel#avatar {{ color: #ffffff; font-size: {small}px; font-weight: 700; border-radius: 14px; }}

QWidget#composerBox {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 16px; }}
QPlainTextEdit#composer {{ background: transparent; border: none; padding: 4px 2px; }}
QWidget#toolbar {{ background: transparent; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {p.surface}; border: 1px solid {p.border}; border-radius: 8px; padding: 6px 9px;
    selection-background-color: {p.accent}; selection-color: {p.accent_text};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {p.accent}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QMenuBar {{ background: {p.sidebar}; border-bottom: 1px solid {p.border}; }}
QMenuBar::item:selected, QMenu::item:selected {{ background: {p.selected}; }}
QMenu {{ background: {p.surface}; border: 1px solid {p.border}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QComboBox QAbstractItemView {{ background: {p.surface}; border: 1px solid {p.border};
    selection-background-color: {p.selected}; selection-color: {p.text}; }}
QListWidget#members {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 8px; padding: 4px; }}

QWidget#card {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 14px; }}
QLabel#cardTitle {{ font-size: {base + 2}px; font-weight: 700; background: transparent; }}
QWidget#card QLabel {{ background: transparent; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {p.muted}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QToolTip {{ background: {p.surface}; color: {p.text}; border: 1px solid {p.border}; padding: 5px 8px; }}
QSplitter::handle {{ background: {p.border}; }}
"""
