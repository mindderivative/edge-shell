"""settings.form: the tabs of the Theme, monitor and panel pages, and the toolbar's panel type
list (pure)."""

from dataclasses import replace

from settings.form import (
    FLOAT_CHOICE,
    PANEL_TABS,
    THEME_TABS,
    FieldSpec,
    SectionSpec,
    WidgetChoice,
    add_choices,
    config_form,
    panel_tabs,
    props_section,
    theme_tabs,
)
from settings.values import new_panel_entry
from shell.widget import WidgetProps

WIDGETS = (
    WidgetChoice("clock", "Clock"),
    WidgetChoice("dock", "Dock"),
    WidgetChoice("summary", "Summary", ("corner",)),
    WidgetChoice("system_bar", "System bar"),
)
FORM = config_form(WIDGETS)


def keys(tab):
    """(key path, row key) of every row on a tab, in order."""
    return [(*key, f.key) for key, section in tab.parts for f in section.fields] + [
        (*key, sub.key, f.key)
        for key, section in tab.parts
        for sub in section.sections
        for f in sub.fields
    ]


def by_title(tabs):
    return {t.title: t for t in tabs}


def test_the_theme_page_has_five_tabs_in_order():
    assert tuple(t.title for t in theme_tabs(FORM)) == THEME_TABS
    assert THEME_TABS == ("General", "Borders", "Shadows", "Handle", "Layout")


def test_each_theme_key_is_on_its_tab():
    tabs = by_title(theme_tabs(FORM))
    general = keys(tabs["General"])
    assert ("theme", "accent") in general and ("theme", "thickness") in general
    assert ("theme", "font") in general and ("theme", "handle") not in general
    assert ("theme", "fade_ms") in general  # no tab of its own: General
    assert keys(tabs["Borders"]) == [
        ("theme", "border", "enabled"),
        ("theme", "border", "width"),
        ("theme", "border", "color"),
    ]
    assert keys(tabs["Shadows"])[0] == ("theme", "shadow", "enabled")
    assert keys(tabs["Handle"]) == [
        ("theme", "handle"),
        ("theme", "handle_hover"),
        ("theme", "handle_style", "shape"),
        ("theme", "handle_style", "size"),
        ("theme", "handle_style", "weight"),
    ]
    assert keys(tabs["Layout"]) == [("layout", "gap")]


def test_every_theme_and_layout_key_is_on_exactly_one_tab():
    shown = [k for t in theme_tabs(FORM) for k in keys(t)]
    every = [("theme", f.key) for f in FORM.theme.fields]
    every += [("theme", s.key, f.key) for s in FORM.theme.sections for f in s.fields]
    every += [("layout", f.key) for f in FORM.layout.fields]
    assert sorted(shown) == sorted(every) and len(shown) == len(set(shown))


def test_a_new_theme_key_or_table_lands_on_general():
    new_row = FieldSpec("glow", "Glow", "int")
    new_table = SectionSpec("halo", "Halo", (FieldSpec("size", "Size", "int"),))
    theme = replace(
        FORM.theme, fields=(*FORM.theme.fields, new_row), sections=(*FORM.theme.sections, new_table)
    )
    general = by_title(theme_tabs(replace(FORM, theme=theme)))["General"]
    assert ("theme", "glow") in keys(general)
    assert general.parts[-1][0] == ("theme", "halo")  # a table of its own, shown flat


def test_a_sub_table_part_is_shown_at_its_own_key_path():
    borders = by_title(theme_tabs(FORM))["Borders"]
    ((key, section),) = borders.parts
    assert key == ("theme", "border") and section.key == "border"


def test_an_edge_panel_has_four_tabs_without_widget_properties():
    tabs = panel_tabs(FORM.panel_for("edge"))
    assert [t.title for t in tabs] == ["Panel", "Position", "Handle", "Interaction"]
    t = by_title(tabs)
    assert keys(t["Panel"]) == [("name",), ("widget",)]  # one kind: no Panel type row
    assert keys(t["Position"]) == [
        ("edge",),
        ("pos",),
        ("align",),
        ("offset",),
        ("order",),
        ("length",),
        ("min_length",),
        ("max_length",),
        ("depth",),
    ]
    assert keys(t["Handle"])[0] == ("handle", "shape") and len(keys(t["Handle"])) == 6
    assert keys(t["Interaction"]) == [
        ("state",),
        ("interaction", "click"),
        ("interaction", "hover"),
        ("interaction", "drag"),
    ]


def test_a_corner_panel_has_its_own_position_rows():
    t = by_title(panel_tabs(FORM.panel_for("corner", "top-right")))
    assert keys(t["Position"]) == [("corner",), ("edge",), ("width",), ("height",)]
    assert t["Position"].parts[0][1].field("edge").choices == ("top", "right")


def test_a_two_kind_widget_shows_the_panel_type_on_the_panel_tab():
    t = by_title(panel_tabs(FORM.panel_for("edge", kinds=("edge", "corner"))))
    assert keys(t["Panel"]) == [("name",), ("widget",), ("panel",)]


class Props(WidgetProps):
    format: str = "HH:mm"


def test_the_widget_tab_is_last_and_only_with_properties():
    tabs = panel_tabs(FORM.panel_for("edge"), props_section(Props))
    assert tuple(t.title for t in tabs) == PANEL_TABS
    assert keys(tabs[-1]) == [("format",)]  # a key of the entry itself


def test_every_panel_key_is_on_exactly_one_tab():
    for section in (FORM.panel_for("edge"), FORM.panel_for("corner")):
        shown = [k for t in panel_tabs(section) for k in keys(t)]
        every = [(f.key,) for f in section.fields]
        every += [(s.key, f.key) for s in section.sections for f in s.fields]
        assert sorted(shown) == sorted(every) and len(shown) == len(set(shown))


def test_the_panel_type_list_names_widget_and_kind():
    choices = add_choices(WIDGETS)
    assert [c.label for c in choices] == [
        "Clock (edge panel)",
        "Dock (edge panel)",
        "System bar (edge panel)",
        "Summary (corner panel)",
        "Float panel (coming soon)",
    ]
    assert [c.id for c in choices][:4] == [
        "edge:clock",
        "edge:dock",
        "edge:system_bar",
        "corner:summary",
    ]
    assert (choices[3].kind, choices[3].widget, choices[3].enabled) == ("corner", "summary", True)
    float_ = choices[-1]
    assert (float_.id, float_.kind, float_.widget, float_.enabled) == (
        FLOAT_CHOICE,
        "float",
        None,
        False,
    )


def test_a_widget_of_two_kinds_is_listed_once_per_kind():
    both = WidgetChoice("tile", "Tile", ("edge", "corner"))
    ids = [c.id for c in add_choices((both,))]
    assert ids == ["edge:tile", "corner:tile", FLOAT_CHOICE]


def test_a_new_panel_entry_takes_the_chosen_kind(corner_registry):
    from shell.panel_spec import CornerDefaults, PanelDefaults
    from shell.widget import Widget

    corner_registry.register_widget(
        "tile",
        title="Tile",
        edge=PanelDefaults(edge="top", length=100, depth=40, label="tile"),
        corner=CornerDefaults(corner="top-left", width=200, height=100, label="tile"),
    )(type("Tile", (Widget,), {}))
    assert new_panel_entry({}, "M", "tile")["panel"] == "edge"  # the first kind
    assert new_panel_entry({}, "M", "tile", "corner") == {
        "panel": "corner",
        "name": "Tile",
        "widget": "tile",
    }
    # a kind the widget lacks is written as asked: the session's check refuses it
    assert new_panel_entry({}, "M", "dock", "corner")["panel"] == "corner"
