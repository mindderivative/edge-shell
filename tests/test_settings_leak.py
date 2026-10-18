"""A form rebuild must not keep the old rows alive. The settings window leaked every FieldRow
of a rebuild (about 28 on this config) with its editor: a slider's handler on its Gtk.Adjustment
and a font picker's handlers and filter function close over the editor, and GTK holds them in C,
where Python's collector cannot see them (FieldRow.discard now calls editor.release).

Widgets are only built, never shown: no window is created."""

import collections
import gc

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
pytest.importorskip("tomlkit")

from gi.repository import GLib, Gtk  # noqa: E402

if not Gtk.init_check()[0]:
    pytest.skip("no display", allow_module_level=True)

import widgets  # noqa: E402,F401  (registers the built-in widgets, as settings/app.py does)
from settings.session import SettingsSession  # noqa: E402
from settings.view import SettingsView  # noqa: E402
from shell import registry  # noqa: E402
from shell.outputs import Output  # noqa: E402

REAL_WIDGETS = dict(registry._WIDGETS)
USER = """\
[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]
panel = "edge"
name = "clock"
widget = "clock"

[[monitors.HDMI-A-1.panels]]
panel = "edge"
name = "dock"
widget = "dock"
"""
HDMI = Output("HDMI-A-1", 0, 0, 1920, 1080)
MODULES = ("settings.fields", "settings.fontpicker")  # FieldRow, every editor, FontPicker
PICKERS = ("FontPicker", "FontEditor", "FontListEditor")


def settle():
    """Run the idle destruction of the retired pages, then collect (twice, for cycles that
    only free up after the first sweep)."""
    ctx = GLib.MainContext.default()
    while ctx.iteration(False):
        pass
    gc.collect()
    gc.collect()


def live():
    """class name -> live objects of the settings rows' classes."""
    return collections.Counter(
        type(o).__name__ for o in gc.get_objects() if type(o).__module__ in MODULES
    )


@pytest.fixture
def view(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "_WIDGETS", dict(REAL_WIDGETS))
    path = tmp_path / "config.toml"
    path.write_text(USER)
    v = SettingsView(SettingsSession(path), [HDMI])
    yield v
    v.destroy()
    settle()


@pytest.mark.parametrize("page", ["theme", "monitor:HDMI-A-1", "panel:HDMI-A-1:0"])
def test_rebuilding_the_pages_does_not_grow_the_live_rows(view, page):
    view.show_page(page)
    counts = []
    for _ in range(5):
        view.rebuild()
        settle()
        counts.append(live())
    assert counts[0]["FieldRow"] > 50  # the pages really were built (theme, monitor, 2 panels)
    assert {"SliderEditor", "FontListEditor", "FontEditor"} <= set(counts[0])
    assert counts[1] == counts[4], {
        k: counts[4][k] - counts[1][k] for k in counts[4] if counts[4][k] != counts[1][k]
    }


def test_a_discarded_row_lets_go_of_its_pickers_and_sliders(view):
    """Rows discarded without a rebuild (the view retires) are freed too once dropped."""
    rows = [r for r in view.rows if type(r.editor).__name__ in ("SliderEditor", "FontEditor")]
    assert rows
    for row in view.rows:
        row.discard()
    # a released slider no longer reports its adjustment's changes
    sent = []
    for row in rows:
        row._on_change = lambda path, value, sent=sent: sent.append(path)
        row._on_queue = None
        row._discarding = False  # only the editor's own handlers are under test
        row._shown = None
    slider = next(r for r in rows if type(r.editor).__name__ == "SliderEditor")
    slider.editor.adjustment.set_value(slider.editor.adjustment.get_upper())
    assert sent == []
