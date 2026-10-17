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


def rows(p):
    return [r.get_child().get_text() for r in p.list.get_children()]


def test_the_shown_row_is_matched_without_case_like_missing_is():
    p, _ = picker("noto sans", system="")  # configured in lower case, installed as "Noto Sans"
    p.fill()
    assert p.visible_labels()[0] != "noto sans (not installed)"
    assert p.list.get_selected_row().get_child().get_text() == "Noto Sans"
    assert p.value == "noto sans"  # the configured spelling is kept until the user picks


def test_opening_again_rebuilds_the_rows_only_when_the_value_or_the_families_changed():
    p, _ = picker("Fira Mono")
    p.fill()
    first = p.list.get_children()
    p.search.set_text("sans")
    p.fill()  # the same value and families: the same row widgets, the search cleared
    assert p.list.get_children() == first and p.search.get_text() == ""
    assert p.list.get_selected_row().get_child().get_text() == "Fira Mono"
    p.set("Hack Nerd Font")
    p.fill()
    again = p.list.get_children()
    assert again != first and len(again) == len(p.entries)  # rebuilt, nothing left over
    assert p.list.get_selected_row().get_child().get_text() == "Hack Nerd Font"
    families = list(FAMILIES)
    q = fontpicker.FontPicker(lambda _v: None, lambda: families, lambda: "Noto Sans")
    q.set("Fira Mono")
    q.fill()
    old = q.list.get_children()
    families.append("Zeta")
    q.fill()
    assert q.list.get_children() != old and rows(q)[-1] == "Zeta"


def test_two_opens_never_hold_duplicate_rows():
    p, _ = picker("Fira Mono")
    p.fill()
    p.fill()
    p.set("Gone Font")
    p.fill()
    p.set("Fira Mono")
    p.fill()
    assert len(p.list.get_children()) == len(p.entries) == len(set(rows(p)))


def scrolling_picker(monkeypatch, value="Noto Sans", row_y=800, upper=2000, page=360):
    """A picker whose idle callbacks are collected, with a list of `upper` px in a view of
    `page` px and a selected row at `row_y` (30 px high)."""
    p, _ = picker(value)
    scheduled = []
    monkeypatch.setattr(
        fontpicker.GLib, "idle_add", lambda f, *a: scheduled.append(f) or len(scheduled)
    )
    monkeypatch.setattr(fontpicker.GLib, "source_remove", lambda _id: True)

    class Row:
        @staticmethod
        def get_allocation():
            return type("A", (), {"y": row_y, "height": 30})()

    p.scroller.get_vadjustment().configure(0, 0, upper, 10, 100, page)
    monkeypatch.setattr(p.list, "get_selected_row", lambda: Row())
    return p, scheduled


def allocate_list(p):
    p.list.emit("size-allocate", p.list.get_allocation())


def test_the_scroll_waits_for_the_lists_first_allocation_and_happens_once(monkeypatch):
    p, scheduled = scrolling_picker(monkeypatch)
    p.fill()
    assert scheduled == []  # the popover has no size yet (Wayland): nothing before it
    assert p.scroller.get_vadjustment().get_value() == 0
    allocate_list(p)
    assert len(scheduled) == 1
    scheduled[0]()
    assert p.scroller.get_vadjustment().get_value() == 800 + 15 - 180  # centred on the row
    allocate_list(p)  # later allocations (the search narrows the list) do not scroll again
    assert len(scheduled) == 1


def test_each_opening_scrolls_once_again(monkeypatch):
    p, scheduled = scrolling_picker(monkeypatch)
    p.fill()
    allocate_list(p)
    p.fill()  # opened again before the first allocation arrived: still one scroll pending
    allocate_list(p)
    allocate_list(p)
    assert len(scheduled) == 2


def test_an_open_list_scrolls_at_once(monkeypatch):
    p, scheduled = scrolling_picker(monkeypatch)
    monkeypatch.setattr(p.list, "get_mapped", lambda: True)  # already allocated
    p.fill()
    assert len(scheduled) == 1


def test_the_scroll_stays_inside_the_list(monkeypatch):
    p, scheduled = scrolling_picker(monkeypatch, row_y=10)  # near the top: no negative value
    p.fill()
    allocate_list(p)
    scheduled[0]()
    assert p.scroller.get_vadjustment().get_value() == 0
    q, scheduled = scrolling_picker(monkeypatch, row_y=1960)  # near the end: upper - page
    q.fill()
    allocate_list(q)
    scheduled[0]()
    assert q.scroller.get_vadjustment().get_value() == 2000 - 360


def test_nothing_runs_after_the_button_is_destroyed(monkeypatch):
    p, scheduled = scrolling_picker(monkeypatch)
    removed = []
    monkeypatch.setattr(fontpicker.GLib, "source_remove", lambda i: removed.append(i))
    p.fill()
    allocate_list(p)  # an idle is pending
    p.button.destroy()
    assert removed  # the pending idle is cancelled ...
    scheduled[0]()  # ... and if it ran anyway it does nothing (and does not raise)
    assert p.scroller.get_vadjustment().get_value() == 0
    q, scheduled = scrolling_picker(monkeypatch)
    q.fill()  # waiting for the allocation
    handler = q._scroll_handler
    assert handler and q.list.handler_is_connected(handler)
    q.button.destroy()
    assert not q.list.handler_is_connected(handler)


def test_a_pick_closes_the_list_and_opening_focuses_the_search():
    p, picks = picker("Fira Mono")
    closed, focused = [], []
    p.popover = type("Pop", (), {"popdown": lambda self: closed.append(1)})()
    p.search.grab_focus = lambda: focused.append(1)
    p.fill()
    assert focused == [1]
    p.list.emit("row-activated", p.list.get_row_at_index(len(p.entries) - 1))
    assert closed == [1] and len(picks) == 1


def test_the_button_label_is_cut_and_the_list_scrolls_at_its_height():
    from gi.repository import Pango

    p, _ = picker("Fira Mono")
    assert p.label.get_ellipsize() == Pango.EllipsizeMode.END
    assert p.label.get_max_width_chars() == p.label.get_width_chars() == fontpicker.FONT_CHARS
    assert p.scroller.get_max_content_height() == fontpicker.POPUP_HEIGHT
    assert p.scroller.get_propagate_natural_height()
    assert p.scroller.get_min_content_width() == fontpicker.POPUP_WIDTH


def test_a_missing_pangocairo_gives_no_installed_families(monkeypatch):
    import importlib.util

    real = gi.require_version

    def refuse(name, version):
        if name == "PangoCairo":
            raise ValueError("Namespace PangoCairo not available")
        return real(name, version)

    monkeypatch.setattr(gi, "require_version", refuse)
    spec = importlib.util.spec_from_file_location("fontpicker_nopc", fontpicker.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # a fresh copy; the real module is untouched
    assert module.PangoCairo is None and module.installed_families() == ()


def test_the_system_font_is_cleaned_like_the_installed_ones(monkeypatch):
    class Settings:
        def __init__(self, name):
            self.props = type("P", (), {"gtk_font_name": name})()

    def with_name(name):
        stub = type("G", (), {"Settings": type("S", (), {"get_default": lambda: Settings(name)})})
        monkeypatch.setattr(fontpicker, "Gtk", stub)
        return fontpicker.system_family()

    assert with_name("Sans 10") == "sans-serif"
    assert with_name("Noto Sans 11") == "Noto Sans"
    assert with_name('Bad"Font 10') == ""
    assert with_name("Cantarell, Noto Sans 11") == ""


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
