import pytest

from shell import registry
from shell.config.models import ConfigError, PanelConfig
from shell.panel_spec import PanelDefaults, PanelRequest


def test_duplicate_registration_rejected(fake_registry):
    with pytest.raises(ValueError):
        registry.register("dock", PanelDefaults("top", 100, 40, "x"))(type("X", (), {}))


def test_widget_names_sorted(fake_registry):
    assert registry.widget_names() == ["bar", "clock", "dock"]


def test_validate_widgets_reports_every_bad_path(fake_registry, make_config):
    cfg = make_config(
        monitors={
            "HDMI-A-1": {
                "panels": [
                    {"panel": "edge", "name": "dock", "widget": "dock"},
                    {"panel": "edge", "name": "ghost", "widget": "ghost"},
                ]
            },
            "DP-1": {"panels": [{"panel": "edge", "name": "phantom", "widget": "phantom"}]},
        }
    )
    with pytest.raises(ConfigError) as exc:
        registry.validate_widgets(cfg)
    text = str(exc.value)
    assert "monitors.HDMI-A-1.panels[1].widget" in text
    assert "monitors.DP-1.panels[0].widget" in text


def test_request_uses_widget_defaults(fake_registry):
    assert registry.request_for(
        PanelConfig(panel="edge", name="dock", widget="dock")
    ) == PanelRequest(
        widget="dock",
        edge="bottom",
        align="center",
        offset=0,
        pos=None,
        order=0,
        length=560,
        min_length=None,
        max_length=None,
        depth=64,
        state="extended",
        label="dock",
        fallback_length=560,
    )


def test_request_overrides_win(fake_registry):
    got = registry.request_for(
        PanelConfig(
            panel="edge",
            name="dock",
            widget="dock",
            depth=80,
            edge="top",
            state="collapsed",
            order=2,
        )
    )
    assert (got.depth, got.edge, got.state, got.length, got.order) == (
        80,
        "top",
        "collapsed",
        560,
        2,
    )


def test_length_modes_and_bounds_pass_through(fake_registry):
    got = registry.request_for(
        PanelConfig(
            panel="edge", name="dock", widget="dock", length="fill", min_length=100, max_length=900
        )
    )
    assert (got.length, got.min_length, got.max_length, got.fallback_length) == (
        "fill",
        100,
        900,
        560,
    )


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ({}, (600, "center", 0)),  # the bar's registered default: pos 600
        ({"pos": 100}, (100, "center", 0)),
        ({"pos": "center"}, (None, "center", 0)),
        ({"align": "end"}, (None, "end", 0)),  # the default pos is dropped
        ({"offset": 40}, (None, "center", 40)),
        ({"align": "start", "offset": 5}, (None, "start", 5)),
    ],
)
def test_placement_is_taken_as_a_whole(fake_registry, entry, expected):
    got = registry.request_for(PanelConfig(panel="edge", name="bar", widget="bar", **entry))
    assert (got.pos, got.align, got.offset) == expected


def test_unknown_widget_request_lists_known(fake_registry):
    with pytest.raises(ConfigError, match="nope"):
        registry.request_for(PanelConfig(panel="edge", name="nope", widget="nope"))


def test_requests_for_keeps_order_and_duplicates(fake_registry, make_config):
    cfg = make_config(
        monitors={
            "HDMI-A-1": {
                "panels": [
                    {"panel": "edge", "name": "dock", "widget": "dock"},
                    {"panel": "edge", "name": "clock", "widget": "clock"},
                    {"panel": "edge", "name": "dock 2", "widget": "dock", "order": 1},
                ]
            }
        }
    )
    got = registry.requests_for(cfg, "HDMI-A-1")
    assert [(r.widget, r.order) for r in got] == [("dock", 0), ("clock", 0), ("dock", 1)]


def test_deprecated_pos_paths_lists_every_entry_using_pos(make_config):
    cfg = make_config(
        monitors={
            "A": {
                "panels": [
                    {"panel": "edge", "name": "dock", "widget": "dock"},
                    {"panel": "edge", "name": "bar", "widget": "bar", "pos": 600},
                ]
            },
            "B": {
                "panels": [{"panel": "edge", "name": "clock", "widget": "clock", "pos": "center"}]
            },
        }
    )
    assert registry.deprecated_pos_paths(cfg) == [
        "monitors.A.panels.1.pos",
        "monitors.B.panels.0.pos",
    ]
    no_pos = make_config(
        monitors={
            "A": {"panels": [{"panel": "edge", "name": "dock", "widget": "dock", "align": "end"}]}
        }
    )
    assert registry.deprecated_pos_paths(no_pos) == []


def test_moved_default_paths_lists_system_bars_that_override_without_a_placement(make_config):
    cfg = make_config(
        monitors={
            "A": {
                "panels": [
                    {
                        "panel": "edge",
                        "name": "system_bar",
                        "widget": "system_bar",
                    },  # untouched default: not listed
                    {
                        "panel": "edge",
                        "name": "system_bar 2",
                        "widget": "system_bar",
                        "edge": "top",
                    },
                    {
                        "panel": "edge",
                        "name": "system_bar 3",
                        "widget": "system_bar",
                        "length": 524,
                        "pos": 600,
                    },  # has pos
                    {
                        "panel": "edge",
                        "name": "system_bar 4",
                        "widget": "system_bar",
                        "depth": 20,
                        "align": "end",
                    },  # has align
                    {
                        "panel": "edge",
                        "name": "system_bar 5",
                        "widget": "system_bar",
                        "state": "collapsed",
                    },  # no override
                    {
                        "panel": "edge",
                        "name": "dock",
                        "widget": "dock",
                        "edge": "top",
                    },  # not the system bar
                ]
            },
            "B": {
                "panels": [
                    {"panel": "edge", "name": "system_bar", "widget": "system_bar", "length": 524}
                ]
            },
        }
    )
    assert registry.moved_default_paths(cfg) == [
        "monitors.A.panels.1",
        "monitors.B.panels.0",
    ]
