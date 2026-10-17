"""settings.form: the form description generated from the JSON schema (pure)."""

from typing import Annotated, Literal

import pytest
from pydantic import Field, create_model

from settings import form as form_module
from settings.form import (
    COLOR_KEYS,
    HINTS,
    LABELS,
    MODE_HINTS,
    WidgetChoice,
    add_choices,
    config_form,
    join_length,
    props_section,
    rgba_to_hex,
    section_for,
    split_length,
    uses_slider,
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
from shell.widget import WidgetProps

WIDGETS = (
    WidgetChoice("clock", "Clock"),
    WidgetChoice("dock", "Dock"),
    WidgetChoice("system_bar", "System bar"),
)


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
    keys = [f.key for f in p.fields]
    assert keys[:2] == ["name", "widget"] and "panel" not in keys  # one kind: no kind row
    assert not {"corner", "width", "height"} & set(keys)
    name = p.field("name")
    assert (name.kind, name.required, name.label) == ("text", True, "Name")
    widget = p.field("widget")
    assert widget.kind == "widget" and widget.required
    assert widget.choices == ("clock", "dock", "system_bar")
    assert widget.labels == ("Clock", "Dock", "System bar")
    assert not p.field("edge").required
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
    assert [f.key for f in p.fields] == [
        "name",
        "widget",
        "corner",
        "edge",
        "width",
        "height",
        "state",
    ]
    assert p.field("corner").choices == CORNERS
    width = p.field("width")
    assert (width.kind, width.minimum, width.maximum) == ("int", 60, 4000)
    assert width.hint == "px from the screen corner, frame included"
    assert [s.key for s in p.sections] == ["handle", "interaction"]


def test_the_panel_sections_split_the_panel_keys_by_kind(form):
    edge = {f.key for f in form.edge_panel.fields} | {s.key for s in form.edge_panel.sections}
    corner = {f.key for f in form.corner_panel.fields} | {s.key for s in form.corner_panel.sections}
    assert edge & corner == set(SHARED_KEYS)
    assert edge | corner == set(PanelConfig.model_fields) - {"widget_props"}
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


def test_widgets_are_listed_by_their_display_name():
    form = config_form(
        (
            WidgetChoice("system_bar", "System bar"),
            WidgetChoice("summary", "Summary", ("corner",)),
            WidgetChoice("dock", "Dock"),
            WidgetChoice("x"),  # no title: its id
            WidgetChoice("aaa", "Zulu"),  # its id sorts first, its title last
        )
    )
    widget = form.edge_panel.field("widget")
    assert widget.choices == ("dock", "summary", "system_bar", "x", "aaa")
    assert widget.labels == ("Dock", "Summary", "System bar", "x", "Zulu")
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
    assert form.monitor.field("shell").label == "Mode"

    def check(section):
        for spec in section.fields:
            assert "_" not in spec.label and spec.label[0].isupper(), spec.key
        for sub in section.sections:
            check(sub)

    for section in (form.theme, form.layout, form.monitor, form.edge_panel, form.corner_panel):
        check(section)


def test_the_order_hint(form):
    assert form.edge_panel.field("order").hint == (
        "within its align slot; equal orders keep the config order"
    )


def test_a_new_corner_key_does_not_break_the_form(monkeypatch):
    """A key that is neither in CORNER_ROWS nor edge-only follows the known rows."""
    monkeypatch.setattr(
        form_module, "EDGE_ONLY_KEYS", tuple(k for k in EDGE_ONLY_KEYS if k != "order")
    )
    rows = [f.key for f in config_form(WIDGETS).corner_panel.fields]
    assert rows == [
        "name",
        "widget",
        "panel",
        "corner",
        "edge",
        "width",
        "height",
        "state",
        "order",
    ]


def test_every_hint_and_label_names_a_schema_key():
    defs = Config.model_json_schema()["$defs"]
    for model, key in HINTS:
        assert key in defs[model]["properties"], (model, key)
    keys = {k for model in defs.values() for k in model["properties"]}
    for key in LABELS:
        assert key in keys, key


def test_every_int_field_has_both_bounds():
    # a deliberate choice, named here; length: the form bounds it itself (LENGTH_PX)
    unbounded = {("PanelConfig", "length")}
    defs = Config.model_json_schema()["$defs"]
    for name, model in defs.items():
        if name.endswith("Override"):  # create_model'd, bounds lost; the form never uses them
            continue
        for key, prop in model["properties"].items():
            options = [o for o in prop.get("anyOf", [prop]) if o.get("type") != "null"]
            if options[0].get("type") == "integer" and (name, key) not in unbounded:
                assert "minimum" in options[0] and "maximum" in options[0], (name, key)


def test_every_string_field_is_known_to_the_form():
    """A new string key in the models must be classified here (colour, font, enum, ...):
    otherwise section_for raises instead of guessing."""
    schema = Config.model_json_schema()
    for name, model in schema["$defs"].items():
        for key, prop in model["properties"].items():
            options = [o for o in prop.get("anyOf", [prop]) if o.get("type") != "null"]
            plain = [o for o in options if o.get("type") == "string" and "enum" not in o]
            if plain and key not in ("widget", "pos", "length", "name"):
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


# ---- panel type and widget properties (panel/widget spec 3.7) -------------------------


class TileProps(WidgetProps):
    text: str = Field("hi", description="what it says")
    size: Annotated[int, Field(ge=6, le=96)] | None = None
    mode: Literal["a", "b"] = "a"
    on: bool = False


TILE = WidgetChoice("tile", "Tile", ("edge", "corner"), TileProps)


def test_a_widget_with_properties_gets_a_widget_section():
    form = config_form((TILE, WidgetChoice("dock", "Dock", props=WidgetProps)))
    section = form.widget_props("tile")
    assert (section.key, section.label, section.sections) == ("", "Widget", ())
    assert [f.key for f in section.fields] == ["text", "size", "mode", "on"]
    text, size, mode, on = section.fields
    assert (text.kind, text.hint, text.label, text.required) == (
        "text",
        "what it says",
        "Text",
        False,
    )
    assert (size.kind, size.minimum, size.maximum) == ("int", 6, 96)
    assert (mode.kind, mode.choices) == ("enum", ("a", "b"))
    assert on.kind == "bool"
    assert form.widget_props("dock") is None  # no properties: no section
    assert form.widget_props("nope") is None


def test_the_panel_type_row_shows_only_for_a_widget_of_several_kinds(form):
    assert "panel" not in [f.key for f in form.panel_for("edge", kinds=("edge",)).fields]
    both = form.panel_for("corner", "top-left", kinds=("edge", "corner"))
    assert [f.key for f in both.fields][:3] == ["name", "widget", "panel"]
    kind = both.field("panel")
    assert kind.choices == ("edge", "corner", "float") and kind.required
    assert kind.labels == ("Edge", "Corner", "Float (coming soon)")
    assert kind.disabled == ("float",)  # float is listed, never chosen
    assert both.field("edge").choices == ("top", "left")
    corner_only = form.panel_for("corner", kinds=("corner", "edge"))
    assert corner_only.field("panel").disabled == ("float",)


def test_the_registry_widgets_for_the_form(corner_registry):
    from settings.form import registry_widgets

    got = {w.id: (w.label, w.kinds, w.props) for w in registry_widgets()}
    assert got["box"] == ("Box", ("corner",), WidgetProps)
    assert got["dock"] == ("Dock", ("edge",), WidgetProps)


class Inner(WidgetProps):
    size: int = 1


@pytest.mark.parametrize(
    "annotation",
    [
        str,
        int,
        bool,
        Literal["a", "b"],
        str | None,
        Annotated[int, Field(ge=1, le=9)] | None,
        float,
        float | None,
        list[str],
        dict[str, int],
        Literal[1, 2],
        Literal["z"],
        Annotated[int, Field(gt=0, lt=5)],
        int | str,
        Inner,
    ],
    ids=repr,
)
def test_the_registry_refuses_exactly_the_property_types_the_form_cannot_show(annotation):
    """shell.registry.form_type_ok (checked at registration) and props_section (the settings
    window) must agree, so a registered widget always gets its Widget rows."""
    from shell.registry import form_type_ok

    model = create_model("Props", __base__=WidgetProps, font=(annotation, None))
    try:
        props_section(model)
        shown = True
    except ValueError:
        shown = False
    assert form_type_ok(model.model_fields["font"].annotation) is shown


def test_a_one_value_literal_is_a_one_choice_row_and_exclusive_bounds_are_inclusive_ones():
    model = create_model(
        "Props",
        __base__=WidgetProps,
        mode=(Literal["z"], "z"),
        size=(Annotated[int, Field(gt=0, lt=5)], 1),
    )
    mode, size = props_section(model).fields
    assert (mode.kind, mode.choices) == ("enum", ("z",))
    assert (size.kind, size.minimum, size.maximum) == ("int", 1, 4)


def test_a_text_row_carries_the_schemas_max_length():
    class Props(WidgetProps):  # not ClockProps: widgets.clock imports gi, which CI does not have
        format: Annotated[str, Field(min_length=1, max_length=64)] = "HH:mm"

    fmt = props_section(Props).field("format")
    assert fmt.max_length == 64


def test_the_panel_types_are_sorted_by_display_name_without_case():
    choices = add_choices(
        (
            WidgetChoice("aa", "beta"),
            WidgetChoice("zz", "Alpha"),
            WidgetChoice("mm", "Gamma"),
        )
    )
    assert [c.id for c in choices] == ["edge:zz", "edge:aa", "edge:mm", "float"]
    assert [c.label for c in choices[:3]] == [
        "Alpha (edge panel)",
        "beta (edge panel)",
        "Gamma (edge panel)",
    ]


def test_widgets_with_one_title_get_distinct_panel_type_labels():
    choices = add_choices(
        (
            WidgetChoice("clock", "Clock", ("edge", "corner")),
            WidgetChoice("clock2", "Clock"),
            WidgetChoice("dock", "Dock"),
        )
    )
    assert [c.label for c in choices] == [
        "Clock (clock, edge panel)",
        "Clock (clock2, edge panel)",
        "Dock (edge panel)",
        "Clock (clock, corner panel)",
        "Float panel (coming soon)",
    ]
    assert len({c.label for c in choices}) == len(choices)


def test_a_bounded_whole_number_with_a_short_range_is_a_slider():
    form = config_form(WIDGETS)
    sliders = {
        (name, f.key)
        for name, section in (
            ("theme", form.theme),
            ("border", form.theme.section("border")),
            ("shadow", form.theme.section("shadow")),
            ("handle_style", form.theme.section("handle_style")),
            ("layout", form.layout),
            ("edge", form.edge_panel),
            ("edge.handle", form.edge_panel.section("handle")),
            ("corner", form.corner_panel),
        )
        for f in section.fields
        if uses_slider(f)
    }
    assert sliders == {
        ("theme", "thickness"),
        ("theme", "radius"),
        ("theme", "peek"),
        ("theme", "hover_zone"),
        ("border", "width"),
        ("shadow", "elevation"),
        ("handle_style", "size"),
        ("handle_style", "weight"),
        ("layout", "gap"),
        ("edge.handle", "size"),
        ("edge.handle", "weight"),
    }  # duration 0-5000, offsets, depth, order, lengths and corner sizes keep a spin button


def test_the_slider_rule_needs_both_bounds_and_a_short_range():
    from settings.form import SLIDER_MAX_SPAN, FieldSpec

    assert uses_slider(FieldSpec("a", "A", "int", minimum=0, maximum=SLIDER_MAX_SPAN))
    assert not uses_slider(FieldSpec("a", "A", "int", minimum=0, maximum=SLIDER_MAX_SPAN + 1))
    assert not uses_slider(FieldSpec("a", "A", "int", minimum=0))
    assert not uses_slider(FieldSpec("a", "A", "int", maximum=9))
    assert not uses_slider(FieldSpec("a", "A", "length", minimum=60, maximum=100))
