"""Corner panel keys in the config models (spec 19): corner, edge, width, height."""

import pytest

from shell.config.loader import parse_config
from shell.config.models import (
    CORNER_ONLY_KEYS,
    CORNERS,
    EDGE_ONLY_KEYS,
    SHARED_KEYS,
    Config,
    ConfigError,
    PanelConfig,
)


def entry(**keys):
    return PanelConfig.model_validate({"widget": "widget_panel", **keys})


def load(make_config, **keys):
    return parse_config(
        {
            "theme": make_config().theme.model_dump(),
            "monitors": {"HDMI-A-1": {"shell": "edge", "panels": [{"widget": "w", **keys}]}},
        }
    )


def test_corner_keys_default_to_none():
    p = entry()
    assert (p.corner, p.width, p.height) == (None, None, None)


def test_corner_keys_are_read():
    p = entry(corner="bottom-left", edge="left", width=300, height=390)
    assert (p.corner, p.edge, p.width, p.height) == ("bottom-left", "left", 300, 390)


def test_the_four_corners_are_exported_in_order():
    assert CORNERS == ("top-left", "top-right", "bottom-left", "bottom-right")


def test_the_key_sets_partition_the_panel_keys():
    """The settings window shows SHARED_KEYS plus the keys of the widget's kind."""
    assert SHARED_KEYS == ("widget", "edge", "state", "handle", "interaction")
    assert CORNER_ONLY_KEYS == ("corner", "width", "height")
    keys = SHARED_KEYS + EDGE_ONLY_KEYS + CORNER_ONLY_KEYS
    assert len(set(keys)) == len(keys) and set(keys) == set(PanelConfig.model_fields)


@pytest.mark.parametrize(
    ("keys", "path", "words"),
    [
        ({"corner": "middle"}, "corner", "'top-left', 'top-right', 'bottom-left' or"),
        ({"width": 59}, "width", "greater than or equal to 60"),
        ({"height": 4001}, "height", "less than or equal to 4000"),
        ({"width": 300.5}, "width", "valid integer"),
        ({"corner": "bottom-left", "edge": "top"}, "", "not an edge of the bottom-left corner"),
        ({"corner": "top-right", "align": "end"}, "", "align cannot be combined with corner"),
        ({"width": 300, "depth": 80, "length": 200}, "", "length, depth cannot be combined"),
        ({"height": 300, "pos": 40}, "", "pos cannot be combined with height"),
    ],
)
def test_bad_corner_values_name_the_key_path(make_config, keys, path, words):
    with pytest.raises(ConfigError) as exc:
        load(make_config, **keys)
    where = "monitors.HDMI-A-1.panels.0" + (f".{path}" if path else "")
    assert where in str(exc.value) and words in str(exc.value), str(exc.value)


def test_the_edge_may_be_either_edge_of_the_corner():
    assert entry(corner="top-right", edge="right").edge == "right"
    assert entry(corner="top-right", edge="top").edge == "top"


def test_an_edge_without_a_corner_is_left_to_the_registry():
    # the widget's default corner is only known to the registry (validate_widgets)
    assert entry(edge="top", width=200).edge == "top"


def test_the_schema_offers_the_corner_keys():
    panel = Config.model_json_schema()["$defs"]["PanelConfig"]["properties"]
    assert {"corner", "width", "height"} <= set(panel)
    corner = panel["corner"]["anyOf"][0]
    assert corner["enum"] == list(CORNERS)
    width = panel["width"]["anyOf"][0]
    assert (width["minimum"], width["maximum"]) == (60, 4000)


def test_defaults_change_nothing(make_config):
    cfg = make_config(monitors={"HDMI-A-1": {"shell": "edge", "panels": [{"widget": "dock"}]}})
    p = cfg.monitor("HDMI-A-1").panels[0]
    assert (p.corner, p.width, p.height) == (None, None, None)
