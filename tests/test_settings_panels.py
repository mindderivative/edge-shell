"""settings.panels: the panel list editor of one monitor (widgets only; no window shown)."""

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
pytest.importorskip("tomlkit")

from gi.repository import Gtk  # noqa: E402

import settings.panels as panels  # noqa: E402

if not Gtk.init_check()[0]:
    pytest.skip("no display", allow_module_level=True)

from settings.document import UserDocument  # noqa: E402
from settings.form import config_form  # noqa: E402
from shell.registry import requests_for  # noqa: E402

FORM = config_form(("bar", "clock", "dock"))
USER = '[[monitors.M.panels]]\nwidget = "dock"\n[[monitors.M.panels]]\nwidget = "clock"\n'


@pytest.fixture
def editor(make_config, fake_registry):
    config = make_config(monitors={"M": {"panels": [{"widget": "dock"}, {"widget": "clock"}]}})
    made, edits = [], []

    def make_rows(section, prefix):
        made.append((section.label, prefix))
        return Gtk.Box()

    on_edit = lambda edit, open_index: edits.append((edit, open_index))  # noqa: E731
    ed = panels.PanelEditor(FORM, "M", requests_for(config, "M"), make_rows, on_edit, 1)
    return ed, made, edits


def apply(edits):
    doc = UserDocument(USER)
    for edit, _open in edits:
        edit(doc)
    return [p["widget"] for p in doc.data["monitors"]["M"].get("panels", [])]


def test_one_expander_per_entry_with_its_rows(editor):
    ed, made, _ = editor
    assert [e.get_label() for e in ed.expanders] == [
        "1. dock: bottom, center",
        "2. clock: top, center",
    ]
    assert made == [
        ("Panel", ("monitors", "M", "panels", 0)),
        ("Panel", ("monitors", "M", "panels", 1)),
    ]
    assert [e.get_expanded() for e in ed.expanders] == [False, True]


def test_add_remove_and_move_are_document_edits(editor):
    ed, _, edits = editor
    ed.add("bar")
    assert apply(edits) == ["dock", "clock", "bar"] and edits[0][1] == 2  # the new one opens
    edits.clear()
    ed.move(1, 0)
    assert apply(edits) == ["clock", "dock"] and edits[0][1] == 0  # the moved one opens
    edits.clear()
    ed.remove(0)
    assert apply(edits) == ["clock"] and edits[0][1] is None


def test_the_widget_list_comes_from_the_form(editor):
    ed, _, edits = editor
    model = ed.widget_choice.get_model()
    assert [row[0] for row in model] == ["bar", "clock", "dock"]
    ed.add(None)  # nothing chosen: no edit
    assert edits == []


def test_first_cannot_move_up_and_last_cannot_move_down(editor):
    ed, _, _ = editor

    def buttons(i):
        body = ed.expanders[i].get_child()
        return body.get_children()[0].get_children()

    up0, down0, _ = buttons(0)
    up1, down1, _ = buttons(1)
    assert (up0.get_sensitive(), down0.get_sensitive()) == (False, True)
    assert (up1.get_sensitive(), down1.get_sensitive()) == (True, False)


def test_corner_panels_get_their_own_rows_title_and_edges(make_config, corner_registry):
    """Spec 19: a corner widget's entry shows corner, edge (only its corner's two), width and
    height, never align or length; its title names the corner, the edge and the size."""
    form = config_form(("bar", "box", "clock", "dock"), corner_widgets=("box",))
    entries = [{"widget": "dock"}, {"widget": "box"}, {"widget": "box", "corner": "top-right"}]
    config = make_config(monitors={"M": {"panels": entries}})
    sections = []

    def make_rows(section, _prefix):
        sections.append(section)
        return Gtk.Box()

    ed = panels.PanelEditor(form, "M", requests_for(config, "M"), make_rows, lambda *_a: None)
    assert [e.get_label() for e in ed.expanders] == [
        "1. dock: bottom, center",
        "2. box: bottom-left, from bottom, 300x390",
        "3. box: top-right, from top, 300x390",
    ]
    dock, box, moved = sections
    assert "align" in {f.key for f in dock.fields} and "corner" not in {f.key for f in dock.fields}
    assert [f.key for f in box.fields] == ["widget", "corner", "edge", "width", "height", "state"]
    assert box.field("edge").choices == ("bottom", "left")
    assert moved.field("edge").choices == ("top", "right")
    assert [row[0] for row in ed.widget_choice.get_model()] == [
        "bar",
        "clock",
        "dock",
        "box (corner panel)",
    ]
    edits = []
    ed._on_edit = lambda edit, open_index: edits.append((edit, open_index))
    ed.add("box")
    doc = UserDocument("")
    edits[0][0](doc)
    assert doc.data == {"monitors": {"M": {"panels": [{"widget": "box"}]}}} and edits[0][1] == 3
