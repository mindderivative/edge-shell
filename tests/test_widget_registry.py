"""register_widget, per-kind defaults and widget properties (panel/widget spec 3.4-3.5)."""

from typing import Annotated, Literal

import pytest
from pydantic import AliasChoices, ConfigDict, Field, create_model

from shell.config.diff import Change, diff_configs
from shell.config.models import ConfigError, PanelConfig
from shell.panel_spec import CornerDefaults, CornerRequest, PanelDefaults, PanelRequest
from shell.widget import NO_PROPS, Widget, WidgetProps

EDGE = PanelDefaults(edge="top", length=200, depth=50, label="tile")
CORNER = CornerDefaults(corner="top-right", width=240, height=200, label="tile")


class TileProps(WidgetProps):
    text: str = "hi"
    size: Annotated[int, Field(ge=6, le=96)] | None = None


@pytest.fixture
def tile(fake_registry):
    """A widget for both kinds, with two properties."""
    fake_registry.register_widget("tile", title="Tile", props=TileProps, edge=EDGE, corner=CORNER)(
        type("Tile", (Widget,), {})
    )
    return fake_registry


def mon(*panels):
    return {"HDMI-A-1": {"shell": "edge", "panels": list(panels)}}


def entry(**keys):
    return {"panel": "edge", "name": "Tile", "widget": "tile", **keys}


def test_a_widget_for_both_kinds_takes_the_defaults_of_the_entrys_kind(tile):
    assert tile.supported_kinds("tile") == ("edge", "corner")
    edge = tile.request_for(PanelConfig(**entry()))
    corner = tile.request_for(PanelConfig(**entry(panel="corner")))
    assert isinstance(edge, PanelRequest) and (edge.edge, edge.length, edge.depth) == (
        "top",
        200,
        50,
    )
    assert isinstance(corner, CornerRequest)
    assert (corner.corner, corner.edge, corner.width, corner.height) == (
        "top-right",
        "top",
        240,
        200,
    )
    assert tile.defaults("tile", "edge") is EDGE and tile.defaults("tile", "corner") is CORNER


def test_a_corner_request_carries_the_name_and_the_properties(tile):
    req = tile.request_for(PanelConfig(**entry(panel="corner", text="ho")))
    assert req.name == "Tile"
    assert req.props == TileProps(text="ho")


def test_defaults_refuse_a_name_that_is_not_a_kind(tile):
    for kind in ("title", "cls", "props"):
        with pytest.raises(KeyError):
            tile.defaults("tile", kind)


def test_title_and_property_model_are_public(tile):
    assert tile.widget_title("tile") == "Tile"
    assert tile.widget_props_model("tile") is TileProps
    assert tile.widget_props_model("dock") is WidgetProps  # no properties


def test_requests_carry_the_name_and_the_validated_properties(tile):
    req = tile.request_for(PanelConfig(**entry(size=12)))
    assert req.name == "Tile"
    assert req.props == TileProps(text="hi", size=12)
    plain = tile.request_for(PanelConfig(panel="edge", name="D", widget="dock"))
    assert plain.props == NO_PROPS


def test_a_kind_the_widget_does_not_support_is_refused_by_request_for(fake_registry):
    with pytest.raises(ConfigError, match="dock cannot be shown in a corner panel"):
        fake_registry.request_for(PanelConfig(panel="corner", name="D", widget="dock"))


@pytest.mark.parametrize(
    ("keys", "message"),
    [
        ({"colour": "red"}, "monitors.HDMI-A-1.panels[0].colour: unknown key for widget 'tile'"),
        ({"size": 5}, "monitors.HDMI-A-1.panels[0].size: Input should be greater than or equal"),
        ({"text": 3}, "monitors.HDMI-A-1.panels[0].text: Input should be a valid string"),
    ],
)
def test_widget_keys_are_checked_against_the_widgets_model(tile, make_config, keys, message):
    with pytest.raises(ConfigError) as exc:
        tile.validate_widgets(make_config(monitors=mon(entry(**keys))))
    assert message in str(exc.value)


def test_good_widget_keys_pass(tile, make_config):
    tile.validate_widgets(make_config(monitors=mon(entry(text="ho", size=20))))


def test_the_supported_kinds_are_listed_when_a_kind_is_wrong(corner_registry, make_config):
    with pytest.raises(ConfigError) as exc:
        corner_registry.validate_widgets(
            make_config(monitors=mon({"panel": "edge", "name": "B", "widget": "box"}))
        )
    assert "box cannot be shown in an edge panel (it supports: corner)" in str(exc.value)


@pytest.mark.parametrize(
    ("change", "kind"),
    [
        ({"name": "Tile 2"}, "panel-rebuild"),
        ({"size": 30}, "panel-rebuild"),
        ({"text": "ho"}, "panel-rebuild"),
        ({"panel": "corner"}, "panel-rebuild"),
        ({"state": "collapsed"}, "panel-state"),
    ],
)
def test_a_name_or_property_change_rebuilds_the_panel(tile, make_config, change, kind):
    old = make_config(monitors=mon(entry()))
    new = make_config(monitors=mon(entry(**change)))
    assert diff_configs(old, new) == [Change(kind, "HDMI-A-1", 0)]


class Clash(WidgetProps):
    edge: str = "x"


class Sneaky(WidgetProps):
    widget_props: int = 0


class NoDefault(WidgetProps):
    text: str


class LooseFrozen(WidgetProps):
    model_config = ConfigDict(frozen=False)


class LooseExtra(WidgetProps):
    model_config = ConfigDict(extra="allow")


class IgnoreExtra(WidgetProps):
    model_config = ConfigDict(extra="ignore")


class Aliased(WidgetProps):
    label: str = Field("x", alias="edge")


class AliasedIn(WidgetProps):
    label: str = Field("x", validation_alias="name")


class AliasedChoice(WidgetProps):
    label: str = Field("x", validation_alias=AliasChoices("fine", "depth"))


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({}, "give edge or corner defaults"),
        ({"edge": EDGE, "props": Clash}, "property 'edge' has the name of a panel key"),
        ({"edge": EDGE, "props": Sneaky}, "property 'widget_props' has the name of a panel key"),
        ({"edge": EDGE, "props": NoDefault}, "every property needs a default"),
        ({"edge": EDGE, "props": dict}, "props must be a WidgetProps model"),
        ({"edge": CORNER}, "edge defaults must be PanelDefaults"),
        ({"corner": EDGE}, "corner defaults must be CornerDefaults"),
        ({"edge": EDGE, "title": ""}, "title must be 1-40 characters"),
        ({"edge": EDGE, "title": "T" * 41}, "title must be 1-40 characters"),
        ({"edge": EDGE, "title": "a\nb"}, "widget 'bad': title must not contain control"),
        ({"edge": EDGE, "title": " a"}, "widget 'bad': title must not start or end with white"),
        ({"edge": EDGE, "title": 5}, "title must be a string"),
        ({"edge": EDGE, "props": LooseFrozen}, "widget 'bad': props must stay frozen"),
        ({"edge": EDGE, "props": LooseExtra}, "widget 'bad': props must forbid extra"),
        ({"edge": EDGE, "props": IgnoreExtra}, "widget 'bad': props must forbid extra"),
        ({"edge": EDGE, "props": Aliased}, "property 'label' has the alias 'edge'"),
        ({"edge": EDGE, "props": AliasedIn}, "property 'label' has the alias 'name'"),
        ({"edge": EDGE, "props": AliasedChoice}, "property 'label' has the alias 'depth'"),
    ],
)
def test_a_bad_registration_fails_at_import(fake_registry, kwargs, message):
    kwargs = {"title": "Bad", **kwargs}
    with pytest.raises(ValueError, match=message):
        fake_registry.register_widget("bad", **kwargs)
    assert "bad" not in fake_registry.widget_names()


def test_the_widget_base_class_must_be_overridden():
    with pytest.raises(NotImplementedError):
        Widget().build(NO_PROPS)
    assert Widget().destroy() is None


def test_widget_props_are_frozen_and_strict():
    with pytest.raises(Exception, match="frozen"):
        TileProps().text = "x"
    with pytest.raises(Exception, match="Extra inputs"):
        TileProps(colour="red")


class Nested(WidgetProps):
    size: int = 1


@pytest.mark.parametrize(
    ("annotation", "default", "words"),
    [
        (float, 1.0, "type float"),
        (float | None, None, "type float | None"),
        (int | str, 1, "type int | str"),
        (int | float, 1, "type int | float"),
        (list[str], [], "type list"),
        (dict[str, int], {}, "type dict"),
        (Literal[1, 2], 1, "Literal[1, 2]"),
        (Nested, Nested(), "type Nested"),
    ],
)
def test_a_property_the_settings_window_cannot_show_is_refused(
    fake_registry, annotation, default, words
):
    model = create_model("Odd", __base__=WidgetProps, odd=(annotation, default))
    with pytest.raises(ValueError) as exc:
        fake_registry.register_widget("odd", title="Odd", props=model, edge=EDGE)
    text = str(exc.value)
    assert "widget 'odd': property 'odd'" in text and words in text
    assert "str, int, bool, a Literal of strings" in text
    assert "odd" not in fake_registry.widget_names()


@pytest.mark.parametrize(
    ("annotation", "default"),
    [
        (str, "x"),
        (int, 1),
        (bool, False),
        (Literal["a", "b"], "a"),
        (Annotated[int, Field(ge=1, le=9)] | None, None),
        (str | None, None),
    ],
)
def test_the_property_types_the_settings_window_shows_are_accepted(
    fake_registry, annotation, default
):
    model = create_model("Fine", __base__=WidgetProps, fine=(annotation, default))
    fake_registry.register_widget("fine", title="Fine", props=model, edge=EDGE)(
        type("FineWidget", (Widget,), {})
    )
    assert fake_registry.widget_props_model("fine") is model


def test_bad_properties_name_the_widget_and_list_key_message_lines(tile):
    cfg = PanelConfig(**entry(size=5, text=3))
    for call in (tile.request_for, tile.widget_props):
        with pytest.raises(ConfigError) as exc:
            call(cfg)
        text = str(exc.value)
        assert text.startswith("tile properties:")
        assert "size: Input should be greater than or equal to 6" in text
        assert "text: Input should be a valid string" in text
        assert "pydantic.dev" not in text and "validation error" not in text


def test_a_property_is_not_coerced_from_another_type(tile, fake_registry):
    class Flags(WidgetProps):
        on: bool = False
        n: int = 1

    fake_registry.register_widget("flags", title="Flags", props=Flags, edge=EDGE)(
        type("Flags", (Widget,), {})
    )
    for keys in ({"size": "4"}, {"size": True}):
        with pytest.raises(ConfigError, match="size"):
            tile.widget_props(PanelConfig(**entry(**keys)))
    for keys in ({"on": 1}, {"on": "true"}, {"n": True}, {"n": "2"}):
        with pytest.raises(ConfigError):
            fake_registry.widget_props(PanelConfig(**entry(widget="flags", **keys)))
    assert fake_registry.widget_props(PanelConfig(**entry(widget="flags", on=True, n=3))) == Flags(
        on=True, n=3
    )
    assert tile.widget_props(PanelConfig(**entry(size=12))) == TileProps(size=12)
