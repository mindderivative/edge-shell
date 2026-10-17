"""settings.style: the window's one stylesheet. The CSS text is tested without GTK; the tests
that measure a widget need a display (no window is shown)."""

import re

import pytest

from settings import style


@pytest.fixture
def gtk():
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gtk

    if not Gtk.init_check()[0]:
        pytest.skip("no display")
    return Gtk


def selectors(css: str) -> list[str]:
    """Every selector of `css` (the text before each `{`, split at commas)."""
    heads = re.findall(r"([^{}]+)\{", css)
    return [s.strip() for head in heads for s in head.split(",")]


def rule(css: str, selector: str) -> dict[str, str]:
    """The declarations of the rule whose selector is exactly `selector`."""
    for head, body in re.findall(r"([^{}]+)\{([^}]*)\}", css):
        if head.strip() == selector:
            pairs = (d.split(":", 1) for d in body.split(";") if d.strip())
            return {k.strip(): v.strip() for k, v in pairs}
    raise KeyError(selector)


def test_every_rule_is_scoped_by_one_of_our_classes():
    """Never a bare `switch` or `label`: the stylesheet is on the whole screen."""
    found = selectors(style.STYLESHEET)
    assert len(found) >= 6
    for selector in found:
        first = selector.split()[0]
        assert f".{style.INFO_NOTE_CLASS}" in first or f".{style.SWITCH_CLASS}" in first, selector


def test_the_info_note_css_has_the_class_colours_and_a_backdrop_rule():
    css = style.INFO_NOTE_CSS
    assert f".{style.INFO_NOTE_CLASS}" in css
    assert "#2b5c8a" in css  # the background
    assert "#ffffff" in css  # the text
    assert ":backdrop" in css  # an unfocused window keeps both


def test_the_switch_content_is_twice_as_wide_as_high_and_the_knob_is_round():
    """GTK gives the knob half the content width and the whole content height: a circle when
    the content is 2:1 (settings.style)."""
    track = rule(style.SWITCH_CSS, f"switch.{style.SWITCH_CLASS}")
    knob = rule(style.SWITCH_CSS, f"switch.{style.SWITCH_CLASS} slider")
    assert track["min-width"] == f"{2 * style.KNOB_PX}px"
    assert track["min-height"] == f"{style.KNOB_PX}px"
    assert track["margin"] == "0" and track["border-width"] == f"{style.BORDER_PX}px"
    inner = style.KNOB_PX - 2 * style.BORDER_PX  # the knob's border makes it KNOB_PX across
    assert knob["min-width"] == knob["min-height"] == f"{inner}px"
    assert knob["border-width"] == f"{style.BORDER_PX}px"
    assert knob["margin"] == knob["padding"] == "0"
    assert knob["border-radius"] == "50%"


def test_the_stylesheet_is_valid_and_installed_once(gtk):
    provider = gtk.CssProvider()
    provider.load_from_data(style.STYLESHEET.encode())  # raises on a parse error
    first = style.install_css()
    assert style.install_css() is first  # a second call reuses it


def test_a_styled_switch_is_thinner_with_a_2_to_1_content_box(gtk):
    style.install_css()
    plain, styled = gtk.Switch(), gtk.Switch()
    styled.get_style_context().add_class(style.SWITCH_CLASS)
    for switch in (plain, styled):
        switch.show()  # a widget flag only: no window exists
    edge = 2 * (style.TRACK_PADDING_PX + style.BORDER_PX)  # padding and border, both sides
    height = styled.get_preferred_height().minimum_height
    assert styled.get_preferred_width().minimum_width == 2 * style.KNOB_PX + edge  # 38
    assert height == style.KNOB_PX + edge  # 22: the content is 2:1
    assert height < plain.get_preferred_height().minimum_height  # Breeze 24, Adwaita 26


def test_the_exact_selectors_of_the_stylesheet():
    sw = style.SWITCH_CLASS
    assert selectors(style.STYLESHEET) == [
        "infobar.info-note",
        "infobar.info-note > revealer > box",
        "infobar.info-note:backdrop",
        "infobar.info-note:backdrop > revealer > box",
        "infobar.info-note label",
        "infobar.info-note:backdrop label",
        f"switch.{sw}",
        f"switch.{sw} slider",
    ]


def test_the_stylesheet_is_added_at_user_priority(gtk, monkeypatch):
    calls = []
    monkeypatch.setattr(
        gtk.StyleContext,
        "add_provider_for_screen",
        staticmethod(lambda screen, provider, priority: calls.append(priority)),
    )
    monkeypatch.setattr(style, "_provider", None)
    style.install_css()
    assert calls == [gtk.STYLE_PROVIDER_PRIORITY_USER]
