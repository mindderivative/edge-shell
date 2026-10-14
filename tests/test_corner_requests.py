"""Corner widgets in the registry, their requests, key checks and reload diff (spec 19)."""

import pytest

from shell.config.diff import diff_configs
from shell.config.models import ConfigError
from shell.panel_spec import (
    CornerDefaults,
    CornerGeometry,
    CornerRequest,
    HandleSpec,
    Interaction,
    PanelRequest,
    corner_has_edge,
    default_edge,
)


def mon(*panels):
    return {"HDMI-A-1": {"shell": "edge", "panels": list(panels)}}


def requests(registry, make_config, *panels):
    return registry.requests_for(make_config(monitors=mon(*panels)), "HDMI-A-1")


def test_default_edge_is_the_top_or_bottom_edge_of_the_corner():
    assert [default_edge(c) for c in ("top-left", "top-right", "bottom-left", "bottom-right")] == [
        "top",
        "top",
        "bottom",
        "bottom",
    ]
    assert corner_has_edge("bottom-left", "left") and not corner_has_edge("bottom-left", "top")


def test_corner_geometry_carries_the_handle_length():
    geo = CornerGeometry("box", "bottom-left", "bottom", 300, 290, 380, "extended", "box")
    assert (geo.along, geo.length, geo.depth) == (300, 290, 380)


def test_a_corner_widget_gives_a_corner_request(corner_registry, make_config):
    (req,) = requests(
        corner_registry, make_config, {"panel": "corner", "name": "box", "widget": "box"}
    )
    assert req == CornerRequest(
        "box", "bottom-left", "bottom", 300, 390, "extended", "box", HandleSpec(), Interaction()
    )
    assert corner_registry.widget_kind("box") == "corner"
    assert corner_registry.widget_kind("dock") == "edge"


def test_a_widgets_defaults_are_public(corner_registry):
    """The settings window reads defaults(name), never _DEFAULTS."""
    assert corner_registry.defaults("box") == CornerDefaults(
        corner="bottom-left", width=300, height=390, label="box"
    )
    assert corner_registry.defaults("dock").edge == "bottom"
    with pytest.raises(KeyError):
        corner_registry.defaults("nope")


def test_entry_keys_override_the_corner_defaults(corner_registry, make_config):
    (req,) = requests(
        corner_registry,
        make_config,
        {
            "panel": "corner",
            "name": "box",
            "widget": "box",
            "corner": "top-right",
            "edge": "right",
            "width": 200,
            "height": 150,
            "state": "collapsed",
            "handle": {"shape": "bar"},
            "interaction": {"hover": False},
        },
    )
    assert (req.corner, req.edge, req.width, req.height, req.state) == (
        "top-right",
        "right",
        200,
        150,
        "collapsed",
    )
    assert req.handle.shape == "bar" and req.interaction == Interaction(hover=False)


def test_a_new_corner_without_an_edge_opens_from_its_top_or_bottom(corner_registry, make_config):
    (req,) = requests(
        corner_registry,
        make_config,
        {"panel": "corner", "name": "box", "widget": "box", "corner": "top-right"},
    )
    assert req.edge == "top"


def test_a_widget_edge_that_fits_the_new_corner_is_kept(corner_registry, make_config):
    corner_registry.register(
        "side", CornerDefaults(corner="bottom-left", width=200, height=300, label="s", edge="left")
    )(type("Side", (), {}))
    a, b = requests(
        corner_registry,
        make_config,
        {"panel": "corner", "name": "side", "widget": "side", "corner": "top-left"},
        {"panel": "corner", "name": "side 2", "widget": "side", "corner": "top-right"},
    )
    assert a.edge == "left" and b.edge == "top"


def test_edge_widgets_still_give_panel_requests(corner_registry, make_config):
    (req,) = requests(
        corner_registry, make_config, {"panel": "edge", "name": "dock", "widget": "dock"}
    )
    assert isinstance(req, PanelRequest) and req.edge == "bottom"


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        (
            {"panel": "corner", "name": "box", "widget": "box", "align": "end"},
            "monitors.HDMI-A-1.panels[0].align: a corner panel takes corner, edge, width and "
            "height, not align",
        ),
        (
            {"panel": "corner", "name": "box", "widget": "box", "edge": "top"},
            "monitors.HDMI-A-1.panels[0].edge: 'top' is not an edge of the bottom-left corner "
            "(use bottom or left)",
        ),
        (
            {"panel": "edge", "name": "dock", "widget": "dock", "width": 300},
            "monitors.HDMI-A-1.panels[0].width: an edge panel takes no width; corner, width and "
            "height only apply to corner panels",
        ),
        (
            {"panel": "edge", "name": "clock", "widget": "clock", "corner": "top-left"},
            "monitors.HDMI-A-1.panels[0].corner: an edge panel takes no corner",
        ),
    ],
)
def test_keys_of_the_other_kind_are_rejected_with_the_key_path(
    corner_registry, make_config, entry, message
):
    with pytest.raises(ConfigError) as exc:
        corner_registry.validate_widgets(make_config(monitors=mon(entry)))
    assert message in str(exc.value)


def test_a_valid_corner_entry_passes(corner_registry, make_config):
    corner_registry.validate_widgets(
        make_config(
            monitors=mon(
                {
                    "panel": "corner",
                    "name": "box",
                    "widget": "box",
                    "corner": "top-right",
                    "edge": "right",
                }
            )
        )
    )


@pytest.mark.parametrize(
    ("defaults", "message"),
    [
        (
            CornerDefaults(corner="bottom-left", width=300, height=390, label="x", edge="top"),
            "not an edge of",
        ),
        (CornerDefaults(corner="bottom-left", width=30, height=390, label="x"), "60-4000"),
        (CornerDefaults(corner="bottom-left", width=4001, height=390, label="x"), "60-4000"),
        (CornerDefaults(corner="bottom-left", width=300, height=59, label="x"), "60-4000"),
        (
            CornerDefaults(corner="middle", width=300, height=390, label="x"),
            "corner 'middle' must be one of",
        ),
        (
            CornerDefaults(corner="bottom-left", width=300, height=390, label="x", state="open"),
            "state 'open' must be",
        ),
        (
            CornerDefaults(
                corner="bottom-left", width=300, height=390, label="x", handle=HandleSpec(size=99)
            ),
            "invalid handle",
        ),
    ],
)
def test_bad_corner_defaults_fail_at_registration(corner_registry, defaults, message):
    with pytest.raises(ValueError, match=message):
        corner_registry.register("bad", defaults)
    assert "bad" not in corner_registry.widget_names()


def test_all_off_corner_panels_are_listed(corner_registry, make_config):
    cfg = make_config(
        monitors=mon(
            {
                "panel": "corner",
                "name": "box",
                "widget": "box",
                "interaction": {"click": False, "hover": False, "drag": False},
            }
        )
    )
    assert corner_registry.all_off_paths(cfg) == ["monitors.HDMI-A-1.panels.0"]


def _diff(make_config, before, after):
    return [c.kind for c in diff_configs(make_config(monitors=before), make_config(monitors=after))]


@pytest.mark.parametrize(
    ("change", "kind"),
    [
        ({"state": "collapsed"}, "panel-state"),
        ({"handle": {"shape": "chevron"}}, "panel-handle"),
        ({"interaction": {"drag": False}}, "panel-handle"),
        ({"width": 320}, "panel-rebuild"),
        ({"height": 200}, "panel-rebuild"),
        ({"corner": "top-left"}, "panel-rebuild"),
        ({"edge": "left"}, "panel-rebuild"),
    ],
)
def test_reload_kinds_for_corner_panels(corner_registry, make_config, change, kind):
    assert _diff(
        make_config,
        mon({"panel": "corner", "name": "box", "widget": "box"}),
        mon({"panel": "corner", "name": "box", "widget": "box", **change}),
    ) == [kind]


def test_swapping_an_edge_widget_for_a_corner_widget_rebuilds(corner_registry, make_config):
    assert _diff(
        make_config,
        mon({"panel": "edge", "name": "dock", "widget": "dock"}),
        mon({"panel": "corner", "name": "box", "widget": "box"}),
    ) == ["panel-rebuild"]
