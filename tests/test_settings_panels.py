"""settings.panels: each panel's title and rows, and the add, move and remove edits with the
page shown after each (pure)."""

import pytest

pytest.importorskip("tomlkit")

from settings.document import UserDocument  # noqa: E402
from settings.form import WidgetChoice, config_form, registry_widgets  # noqa: E402
from settings.panels import add_step, panel_section, panel_step, panel_title  # noqa: E402
from shell.panel_spec import CornerDefaults, PanelDefaults  # noqa: E402
from shell.registry import requests_for  # noqa: E402
from shell.widget import Widget, WidgetProps  # noqa: E402

CORNER_FORM = config_form(
    (
        WidgetChoice("bar", "Bar"),
        WidgetChoice("box", "Box", ("corner",)),
        WidgetChoice("clock", "Clock"),
        WidgetChoice("dock", "Dock"),
    )
)
THREE = ("dock", "clock", "bar")


def widgets_after(edit):
    entry = '[[monitors.M.panels]]\npanel = "edge"\nname = "{0}"\nwidget = "{0}"\n'
    doc = UserDocument("".join(entry.format(w) for w in THREE))
    edit(doc)
    return [p["widget"] for p in doc.data["monitors"]["M"].get("panels", [])]


def test_corner_panels_get_their_own_rows_title_and_edges(make_config, corner_registry):
    """Spec 19: a corner widget's entry shows corner, edge (only its corner's two), width and
    height, never align or length; its title names the corner, the edge and the size."""
    entries = [
        {"panel": "edge", "name": "dock", "widget": "dock"},
        {"panel": "corner", "name": "box", "widget": "box"},
        {"panel": "corner", "name": "box 2", "widget": "box", "corner": "top-right"},
    ]
    requests = requests_for(make_config(monitors={"M": {"panels": entries}}), "M")
    assert [panel_title(i, r) for i, r in enumerate(requests)] == [
        "1. dock: bottom, center",
        "2. box: bottom-left, from bottom, 300x390",
        "3. box 2: top-right, from top, 300x390",  # the name, not the widget
    ]
    dock, box, moved = (panel_section(CORNER_FORM, r) for r in requests)
    assert "align" in {f.key for f in dock.fields} and "corner" not in {f.key for f in dock.fields}
    assert [f.key for f in box.fields] == [
        "name",
        "widget",
        "corner",
        "edge",
        "width",
        "height",
        "state",
    ]
    assert box.field("edge").choices == ("bottom", "left")
    assert moved.field("edge").choices == ("top", "right")


@pytest.mark.parametrize("i", [0, 1, 2])
def test_remove_takes_out_its_own_entry_and_shows_the_monitor(fake_registry, i):
    edit, page = panel_step("M", i, 3, "remove")
    assert widgets_after(edit) == [w for k, w in enumerate(THREE) if k != i]
    assert page == "monitor:M"


@pytest.mark.parametrize("i", [1, 2])
def test_move_up_moves_its_own_entry_and_shows_it(fake_registry, i):
    edit, page = panel_step("M", i, 3, "up")
    expected = list(THREE)
    expected[i - 1], expected[i] = expected[i], expected[i - 1]
    assert widgets_after(edit) == expected and page == f"panel:M:{i - 1}"


@pytest.mark.parametrize("i", [0, 1])
def test_move_down_moves_its_own_entry_and_shows_it(fake_registry, i):
    edit, page = panel_step("M", i, 3, "down")
    expected = list(THREE)
    expected[i], expected[i + 1] = expected[i + 1], expected[i]
    assert widgets_after(edit) == expected and page == f"panel:M:{i + 1}"


@pytest.mark.parametrize("index, action", [(0, "up"), (2, "down"), (3, "remove"), (-1, "remove")])
def test_nothing_to_do_is_none(index, action):
    assert panel_step("M", index, 3, action) is None


def test_an_unknown_action_is_an_error():
    with pytest.raises(ValueError, match="unknown panel action"):
        panel_step("M", 0, 3, "sideways")


def test_add_writes_the_widget_and_kind_with_a_free_name_and_shows_it(fake_registry):
    edit, page = add_step("M", 3, "clock")
    assert widgets_after(edit) == [*THREE, "clock"] and page == "panel:M:3"
    doc = UserDocument("")
    add_step("M", 0, "clock")[0](doc)
    add_step("M", 1, "clock")[0](doc)
    assert [p["name"] for p in doc.data["monitors"]["M"]["panels"]] == ["Clock", "Clock 2"]


def test_add_writes_a_corner_widgets_id_and_kind(corner_registry):
    doc = UserDocument("")
    add_step("M", 0, "box", "corner")[0](doc)
    assert doc.data == {
        "monitors": {"M": {"panels": [{"panel": "corner", "name": "Box", "widget": "box"}]}}
    }


class TileProps(WidgetProps):
    size: int = 10


@pytest.fixture
def tile(corner_registry):
    """A widget for both kinds, with one property."""
    corner_registry.register_widget(
        "tile",
        title="Tile",
        props=TileProps,
        edge=PanelDefaults(edge="top", length=200, depth=50, label="tile"),
        corner=CornerDefaults(corner="top-right", width=240, height=200, label="tile"),
    )(type("Tile", (Widget,), {}))
    return corner_registry


def test_titles_use_the_panel_name_and_a_two_kind_widget_gets_the_panel_type_row(make_config, tile):
    entries = [
        {"panel": "edge", "name": "Bottom dock", "widget": "dock"},
        {"panel": "corner", "name": "My tile", "widget": "tile", "corner": "top-left"},
    ]
    requests = requests_for(make_config(monitors={"M": {"panels": entries}}), "M")
    assert [panel_title(i, r) for i, r in enumerate(requests)] == [
        "1. Bottom dock: bottom, center",
        "2. My tile: top-left, from top, 240x200",
    ]
    form = config_form(registry_widgets())
    dock, tile_rows = (panel_section(form, r) for r in requests)
    assert "panel" not in [f.key for f in dock.fields]  # the dock has one kind
    kind = tile_rows.field("panel")  # the tile has two: the panel type row
    assert kind.choices == ("edge", "corner", "float") and kind.disabled == ("float",)
    assert form.widget_props("tile").label == "Widget" and form.widget_props("dock") is None
