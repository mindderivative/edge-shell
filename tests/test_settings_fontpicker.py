"""settings.fontpicker: the searchable font dropdown. The fonts are a fixed list (never the
machine's); the popover is opened as a widget flag only (no window exists, nothing is
mapped)."""

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")

from gi.repository import Gtk  # noqa: E402

if not Gtk.init_check()[0]:
    pytest.skip("no display", allow_module_level=True)

from settings import fontpicker  # noqa: E402

FAMILIES = ("DejaVu Sans", "Fira Mono", "Hack Nerd Font", "Noto Sans")


def picker(value="Fira Mono", inherit=None, system="Noto Sans"):
    picks = []
    p = fontpicker.FontPicker(picks.append, lambda: FAMILIES, lambda: system, inherit)
    p.set(value)
    return p, picks


def test_the_button_shows_the_value_and_set_never_calls_back():
    p, picks = picker("Fira Mono")
    assert p.label.get_text() == "Fira Mono" and p.button.get_tooltip_text() == "Fira Mono"
    p.set(None)
    assert p.label.get_text() == ""  # no inherited row: nothing to name
    q, _ = picker(None, inherit="Theme font")
    assert q.label.get_text() == "Theme font"
    assert picks == []


def test_opening_the_list_fills_it_with_the_system_font_first_and_the_shown_row_selected():
    p, _ = picker("Fira Mono")
    assert len(p.list.get_children()) == 0  # nothing is built before the list opens
    p.button.set_active(True)  # the popover is visible as a flag only: no window exists
    labels = [row.get_child().get_text() for row in p.list.get_children()]
    assert labels[0] == "Noto Sans (system font)"
    assert labels == p.visible_labels()
    assert p.list.get_selected_row().get_child().get_text() == "Fira Mono"
    p.button.set_active(False)


def test_typing_filters_the_rows_and_enter_picks_the_first():
    p, picks = picker("Fira Mono")
    p.fill()
    p.search.set_text("SANS")
    assert p.visible_labels() == ["Noto Sans (system font)", "sans-serif", "DejaVu Sans"]
    rows = p.list.get_children()
    shown = [row.get_child().get_text() for row in rows if row.get_child_visible()]
    assert shown == p.visible_labels()  # what the list box shows after its own filter
    p.search.emit("activate")  # Enter
    assert picks == ["Noto Sans"] and p.label.get_text() == "Noto Sans"
    p.fill()  # opened again: the search starts empty and every row is listed
    assert p.search.get_text() == "" and len(p.visible_labels()) == len(p.entries)


def test_a_click_picks_a_row_and_the_shown_row_sends_nothing():
    p, picks = picker("Fira Mono")
    p.fill()
    rows = p.list.get_children()
    fira = next(r for r in rows if r.get_child().get_text() == "Fira Mono")
    p.list.emit("row-activated", fira)  # the value shown: nothing to send
    assert picks == []
    dejavu = next(r for r in rows if r.get_child().get_text() == "DejaVu Sans")
    p.list.emit("row-activated", dejavu)
    assert picks == ["DejaVu Sans"]


def test_the_inherited_row_picks_none():
    p, picks = picker("Fira Mono", inherit="Theme font")
    p.fill()
    p.list.emit("row-activated", p.list.get_row_at_index(0))
    assert picks == [None] and p.label.get_text() == "Theme font"


def test_a_font_that_is_not_installed_is_listed_and_kept():
    p, picks = picker("Gone Font")
    p.fill()
    assert p.visible_labels()[0] == "Gone Font (not installed)"
    assert p.list.get_selected_row().get_index() == 0
    assert p.label.get_text() == "Gone Font" and picks == []


def test_the_desktop_font_and_the_installed_families(monkeypatch):
    assert fontpicker.family_of("Hack Nerd Font  10") == "Hack Nerd Font"
    assert fontpicker.family_of("Noto Sans Bold Italic 11") == "Noto Sans"
    assert isinstance(fontpicker.system_family(), str)  # the desktop's: any string holds

    class Family:
        def __init__(self, name):
            self.get_name = lambda: name

    reads = []

    class FontMap:
        @staticmethod
        def get_default():
            reads.append(1)
            names = ["Sans", "zeta", "Alpha", "Monospace", "alpha", 'Bad"Font']
            return type("Map", (), {"list_families": lambda self: [Family(n) for n in names]})()

    monkeypatch.setattr(fontpicker, "PangoCairo", type("PC", (), {"FontMap": FontMap}))
    fontpicker.installed_families.cache_clear()
    try:
        families = fontpicker.installed_families()  # a fixed font map, never the machine's
        assert families == ("Alpha", "zeta")
        assert fontpicker.installed_families() is families and len(reads) == 1  # read once
    finally:
        fontpicker.installed_families.cache_clear()
