"""settings.form: the form description generated from the JSON schema (pure)."""

import pytest

from settings.form import (
    COLOR_KEYS,
    MODE_HINTS,
    config_form,
    format_fonts,
    join_length,
    parse_fonts,
    rgba_to_hex,
    section_for,
    split_length,
)
from shell.config.models import (
    COLOR_FIELDS,
    CORNER_ONLY_KEYS,
    CORNERS,
    EDGE_ONLY_KEYS,
    HANDLE_SHAPES,
    SHARED_KEYS,
    Config,
    PanelConfig,
)

WIDGETS = ("clock", "dock", "system_bar")


@pytest.fixture
def form():
    return config_form(WIDGETS)


def test_theme_colours_are_colour_fields(form):
    for key in COLOR_FIELDS:
        assert form.theme.field(key).kind == "color"


def test_theme_numbers_take_their_bounds_from_the_schema(form):
    thickness = form.theme.field("thickness")
    assert (thickness.kind, thickness.minimum, thickness.maximum) == ("int", 2, 64)
    assert form.theme.field("duration_ms").maximum == 5000
    assert form.theme.field("thickness").hint == "px"


def test_theme_font_is_a_font_list(form):
    assert form.theme.field("font").kind == "fonts"


def test_nested_theme_tables_are_sub_sections(form):
    assert [s.key for s in form.theme.sections] == ["border", "shadow", "handle_style"]
    border = form.theme.section("border")
    assert border.field("enabled").kind == "bool"
    assert (border.field("width").minimum, border.field("width").maximum) == (1, 16)
    assert border.field("color").kind == "color"
    assert form.theme.section("shadow").field("elevation").maximum == 100


def test_handle_shapes_come_from_the_model(form):
    shape = form.theme.section("handle_style").field("shape")
    assert shape.kind == "enum" and shape.choices == HANDLE_SHAPES
    for kind in ("edge", "corner"):
        assert form.panel_for(kind).section("handle").field("shape").choices == HANDLE_SHAPES


def test_layout_gap(form):
    gap = form.layout.field("gap")
    assert (gap.kind, gap.minimum, gap.maximum) == ("int", 0, 400)


def test_monitor_section_is_the_shell_mode_only(form):
    assert [f.key for f in form.monitor.fields] == ["shell"]
    assert form.monitor.field("shell").choices == ("edge", "plasma", "both", "none")
    assert form.monitor.sections == ()
    assert set(MODE_HINTS) == set(form.monitor.field("shell").choices)


def test_panel_fields(form):
    p = form.panel_for("edge")
    assert p is form.edge_panel and not {"corner", "width", "height"} & {f.key for f in p.fields}
    assert p.field("widget").kind == "widget" and p.field("widget").choices == WIDGETS
    assert p.field("edge").choices == ("top", "bottom", "left", "right")
    assert p.field("align").choices == ("start", "center", "end")
    assert (p.field("offset").minimum, p.field("offset").maximum) == (-20000, 20000)
    assert p.field("length").kind == "length"
    assert (p.field("depth").minimum, p.field("depth").maximum) == (16, 2000)
    assert p.field("state").choices == ("collapsed", "extended")
    assert p.field("pos").kind == "deprecated"
    assert [s.key for s in p.sections] == ["handle", "interaction"]
    assert p.section("interaction").field("hover").kind == "bool"
    handle = p.section("handle")
    assert (handle.field("size").minimum, handle.field("size").maximum) == (4, 40)
    assert handle.field("hover_color").kind == "color"
    assert handle.field("offset").hint == "px from the middle of the panel"
    assert p.field("offset").hint == "px from the aligned end"


def test_corner_panel_fields(form):
    """A corner widget's entry (spec 19): SHARED_KEYS plus CORNER_ONLY_KEYS."""
    p = form.panel_for("corner")
    assert [f.key for f in p.fields] == ["widget", "corner", "edge", "width", "height", "state"]
    assert p.field("corner").choices == CORNERS
    width = p.field("width")
    assert (width.kind, width.minimum, width.maximum) == ("int", 60, 4000)
    assert width.hint == "px from the screen corner, frame included"
    assert [s.key for s in p.sections] == ["handle", "interaction"]


def test_the_panel_sections_split_the_panel_keys_by_kind(form):
    edge = {f.key for f in form.edge_panel.fields} | {s.key for s in form.edge_panel.sections}
    corner = {f.key for f in form.corner_panel.fields} | {s.key for s in form.corner_panel.sections}
    assert edge & corner == set(SHARED_KEYS)
    assert edge | corner == set(PanelConfig.model_fields)
    assert edge - corner == set(EDGE_ONLY_KEYS) and corner - edge == set(CORNER_ONLY_KEYS)


@pytest.mark.parametrize(
    "corner, edges",
    [("bottom-left", ("bottom", "left")), ("top-right", ("top", "right"))],
)
def test_the_edge_of_a_corner_panel_offers_only_its_corners_edges(form, corner, edges):
    assert form.panel_for("corner", corner).field("edge").choices == edges
    assert form.panel_for("corner").field("edge").choices == ("top", "bottom", "left", "right")
    with pytest.raises(ValueError):
        form.panel_for("middle")


def test_corner_widgets_are_listed_after_edge_widgets_and_labelled():
    form = config_form(("bar", "box", "clock"), corner_widgets=("box",))
    widget = form.edge_panel.field("widget")
    assert widget.choices == ("bar", "clock", "box")
    assert widget.labels == ("bar", "clock", "box (corner panel)")
    assert form.corner_panel.field("widget").choices == widget.choices


def test_hints_belong_to_their_table(form):
    """'width' is the border's px in [theme.border] and a corner panel's size in a panel."""
    assert form.theme.section("border").field("width").hint == "px"
    assert form.panel_for("corner").field("width").hint.startswith("px from the screen corner")


def test_labels_are_readable(form):
    assert form.theme.field("duration_ms").label == "Duration"
    assert form.theme.field("text_secondary").label == "Secondary text"
    assert form.theme.field("hover_zone").label == "Hover zone"
    assert form.edge_panel.field("min_length").label == "Minimum length"
    for section in (form.theme, form.layout, form.edge_panel, form.corner_panel):
        for spec in section.fields:
            assert "_" not in spec.label and spec.label[0].isupper(), spec.key


def test_every_string_field_is_known_to_the_form():
    """A new string key in the models must be classified here (colour, font, enum, ...):
    otherwise section_for raises instead of guessing."""
    schema = Config.model_json_schema()
    for name, model in schema["$defs"].items():
        for key, prop in model["properties"].items():
            options = [o for o in prop.get("anyOf", [prop]) if o.get("type") != "null"]
            plain = [o for o in options if o.get("type") == "string" and "enum" not in o]
            if plain and key not in ("widget", "pos", "length"):
                assert key in COLOR_KEYS, f"{name}.{key}"


def test_an_unknown_field_kind_is_an_error():
    schema = {"$defs": {"M": {"properties": {"blob": {"type": "object"}}}}}
    with pytest.raises(ValueError, match="blob"):
        section_for(schema, "M")


@pytest.mark.parametrize(
    "rgba, expected",
    [
        ((0.0, 0.0, 0.0, 1.0), "#000000"),
        ((1.0, 1.0, 1.0, 1.0), "#ffffff"),
        ((143 / 255, 211 / 255, 182 / 255, 1.0), "#8fd3b6"),
        ((0.0, 0.0, 0.0, 128 / 255), "#00000080"),
        ((0.0, 0.0, 0.0, 0.0), "#00000000"),
        ((1.2, -0.1, 0.5, 1.0), "#ff0080"),
    ],
)
def test_rgba_to_hex(rgba, expected):
    assert rgba_to_hex(*rgba) == expected


@pytest.mark.parametrize(
    "value, split",
    [
        (300, ("px", 300.0)),
        ("fill", ("fill", None)),
        ("content", ("content", None)),
        ("50%", ("percent", 50.0)),
        ("12.5%", ("percent", 12.5)),
    ],
)
def test_lengths_round_trip(value, split):
    assert split_length(value) == split
    assert join_length(*split) == value


def test_join_length_rounds_px_and_ignores_the_number_for_fill():
    assert join_length("px", 299.6) == 300
    assert join_length("fill", 42.0) == "fill"
    with pytest.raises(ValueError):
        join_length("inches", 3.0)
    with pytest.raises(ValueError):
        split_length("wide")


def test_fonts_round_trip():
    assert parse_fonts(" Hack Nerd Font Mono , JetBrains Mono,, monospace ") == [
        "Hack Nerd Font Mono",
        "JetBrains Mono",
        "monospace",
    ]
    assert format_fonts(["A", "b c"]) == "A, b c"
    assert parse_fonts("  ") == []
