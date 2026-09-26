from mimikr.theme import (
    ACCENTS,
    accent_color,
    avatar_color,
    contrast,
    initials,
    is_dark,
    palette,
    stylesheet,
    text_on,
)


def test_the_system_theme_follows_the_system_and_the_others_do_not():
    assert is_dark("system", system_dark=True) and not is_dark("system", system_dark=False)
    assert is_dark("dark", system_dark=False)
    assert not is_dark("light", system_dark=True)


def test_an_accent_is_a_name_or_a_hex_color_and_anything_else_is_violet():
    assert accent_color("teal") == ACCENTS["teal"]
    assert accent_color("#ABCDEF") == "#abcdef"
    assert accent_color("rainbow") == ACCENTS["violet"]
    assert accent_color("#abc") == ACCENTS["violet"]


def test_the_text_on_an_accent_is_the_easier_color_to_read():
    for color in [*ACCENTS.values(), "#ffff00", "#000080"]:
        chosen = text_on(color)
        other = "#0b0c0f" if chosen == "#ffffff" else "#ffffff"
        assert contrast(color, chosen) >= contrast(color, other)


def test_the_text_of_each_palette_is_easy_to_read():
    for dark in (True, False):
        p = palette(dark, "violet")
        # WCAG AA asks for 4.5 for normal text.
        assert contrast(p.text, p.window) >= 4.5
        assert contrast(p.text, p.bubble) >= 4.5
        assert contrast(p.muted, p.window) >= 4.5


def test_the_stylesheet_uses_the_accent_and_the_font_size():
    sheet = stylesheet(palette(True, "#123456"), size=16)
    assert "background: #123456" in sheet
    assert "font-size: 16px" in sheet and "font-size: 20px" in sheet


def test_the_font_size_has_limits():
    assert "* { font-size: 18px;" in stylesheet(palette(False, "blue"), size=40)
    assert "* { font-size: 12px;" in stylesheet(palette(False, "blue"), size=2)


def test_initials_take_the_first_and_the_last_word():
    assert initials("sam") == "S"
    assert initials("June Park") == "JP"
    assert initials("mary-jane watson") == "MW"
    assert initials("  ") == "?"


def test_an_identity_keeps_its_avatar_color():
    assert avatar_color("sam") == avatar_color("sam")
    assert len({avatar_color(name) for name in ("sam", "june", "ana", "bo", "cy", "di")}) > 1
