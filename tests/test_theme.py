import re

import pytest

from shell.theme import css_color, hex_to_rgba, scope_class, to_css


def test_hex_to_rgba():
    assert hex_to_rgba("#0b0c0d") == (11 / 255, 12 / 255, 13 / 255, 1.0)
    assert hex_to_rgba("#ffffff", 0.5) == (1.0, 1.0, 1.0, 0.5)


@pytest.mark.parametrize(
    ("name", "scope"),
    [("HDMI-A-1", "mon-hdmi-a-1"), ("DP-1", "mon-dp-1"), ("eDP_1", "mon-edp-1")],
)
def test_scope_class(name, scope):
    assert scope_class(name) == scope


def test_css_font_stack_quotes_names_but_not_generics(make_config):
    css = to_css(make_config().theme, "mon-x")
    assert 'font-family: "Hack Nerd Font Mono", "JetBrains Mono", monospace;' in css


def test_css_is_scoped_and_uses_theme_colors(make_config):
    css = to_css(make_config(theme={"accent": "#112233"}).theme, "mon-x")
    assert ".mon-x .active { color: #112233; }" in css
    assert "frame-strip" not in css  # the strips are invisible; the canvas draws the frame
    assert "window.mon-x" in css
    for line in css.splitlines():
        if "{" in line and not line.startswith("}"):
            assert "mon-x" in line, line  # nothing unscoped


def test_two_monitors_do_not_share_rules(make_config):
    cfg = make_config(monitors={"HDMI-A-1": {"theme": {"accent": "#111111"}}})
    a = to_css(cfg.theme_for("HDMI-A-1"), scope_class("HDMI-A-1"))
    b = to_css(cfg.theme_for("DP-1"), scope_class("DP-1"))
    assert "#111111" in a and "#111111" not in b


# ---- alpha colours (#rrggbbaa) ----------------------------------------------------


def test_hex_to_rgba_reads_the_alpha_digits():
    expected = (0x8F / 255, 0xD3 / 255, 0xB6 / 255, 0x80 / 255)
    assert hex_to_rgba("#8fd3b680") == pytest.approx(expected)
    assert hex_to_rgba("#000000ff") == (0.0, 0.0, 0.0, 1.0)
    assert hex_to_rgba("#ffffff80", 0.5) == pytest.approx((1.0, 1.0, 1.0, 0x80 / 255 * 0.5))


@pytest.mark.parametrize("bad", ["", "#fff", "#8fd3b", "#8fd3b6800"])
def test_hex_to_rgba_rejects_other_lengths(bad):
    with pytest.raises(ValueError):
        hex_to_rgba(bad)


def test_css_color_keeps_six_digits_and_converts_eight():
    assert css_color("#8fd3b6") == "#8fd3b6"
    assert css_color("#8fd3b680") == "rgba(143, 211, 182, 0.502)"
    assert css_color("#000000ff") == "rgba(0, 0, 0, 1.000)"


def test_css_never_contains_eight_digit_hex(make_config):
    css = to_css(make_config(theme={"accent": "#8fd3b680", "text": "#e6e8eaff"}).theme, "mon-x")
    assert ".mon-x .active { color: rgba(143, 211, 182, 0.502); }" in css
    assert re.search(r"#[0-9a-fA-F]{8}\b", css) is None


def test_every_css_colour_parses_in_gtk3(make_config):
    gi = pytest.importorskip("gi")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk

    theme = make_config(theme={"accent": "#8fd3b680", "text": "#e6e8eaff"}).theme
    values = re.findall(r"(?:color|background-color): ([^;]+);", to_css(theme, "mon-x"))
    assert len(values) >= 5  # the handle colours are drawn with cairo, not CSS
    for value in (v for v in values if v != "transparent"):
        assert Gdk.RGBA().parse(value), value


def test_css_no_longer_styles_handle_dots(make_config):
    css = to_css(make_config().theme, "mon-x")
    assert "handle-dot" not in css
    assert ".mon-x #handle { min-width: 0; min-height: 0; padding: 0; }" in css
