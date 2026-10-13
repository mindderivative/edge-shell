import pytest

from shell import registry
from shell.config.models import ConfigError, PanelConfig
from shell.panel_spec import PanelDefaults, PanelGeometry, PanelRequest


def test_resolve_uses_widget_defaults(fake_registry):
    geo = registry.resolve_panel(PanelConfig(widget="dock"))
    assert geo == PanelGeometry("dock", "bottom", None, 560, 64, "extended", "dock")


def test_overrides_win(fake_registry):
    geo = registry.resolve_panel(
        PanelConfig(widget="dock", depth=80, edge="top", state="collapsed")
    )
    assert (geo.depth, geo.edge, geo.state, geo.length) == (80, "top", "collapsed", 560)


def test_pos_default_override_and_center(fake_registry):
    assert registry.resolve_panel(PanelConfig(widget="bar")).pos == 600
    assert registry.resolve_panel(PanelConfig(widget="bar", pos=100)).pos == 100
    assert registry.resolve_panel(PanelConfig(widget="bar", pos="center")).pos is None


def test_unknown_widget_lists_known(fake_registry):
    with pytest.raises(ConfigError) as exc:
        registry.resolve_panel(PanelConfig(widget="nope"))
    assert "nope" in str(exc.value) and "dock" in str(exc.value)


def test_duplicate_registration_rejected(fake_registry):
    with pytest.raises(ValueError):
        registry.register("dock", PanelDefaults("top", 100, 40, "x"))(type("X", (), {}))


def test_widget_names_sorted(fake_registry):
    assert registry.widget_names() == ["bar", "clock", "dock"]


def test_panels_for_keeps_order_and_duplicates(fake_registry, make_config):
    cfg = make_config(
        monitors={
            "HDMI-A-1": {
                "shell": "edge",
                "panels": [
                    {"widget": "dock"},
                    {"widget": "clock"},
                    {"widget": "dock", "depth": 70},
                ],
            }
        }
    )
    geos = registry.panels_for(cfg, "HDMI-A-1")
    assert [g.widget for g in geos] == ["dock", "clock", "dock"]
    assert geos[2].depth == 70


def test_validate_widgets_reports_every_bad_path(fake_registry, make_config):
    cfg = make_config(
        monitors={
            "HDMI-A-1": {"panels": [{"widget": "dock"}, {"widget": "ghost"}]},
            "DP-1": {"panels": [{"widget": "phantom"}]},
        }
    )
    with pytest.raises(ConfigError) as exc:
        registry.validate_widgets(cfg)
    text = str(exc.value)
    assert "monitors.HDMI-A-1.panels[1].widget" in text
    assert "monitors.DP-1.panels[0].widget" in text


def test_request_uses_widget_defaults(fake_registry):
    assert registry.request_for(PanelConfig(widget="dock")) == PanelRequest(
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
        PanelConfig(widget="dock", depth=80, edge="top", state="collapsed", order=2)
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
        PanelConfig(widget="dock", length="fill", min_length=100, max_length=900)
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
    got = registry.request_for(PanelConfig(widget="bar", **entry))
    assert (got.pos, got.align, got.offset) == expected


def test_unknown_widget_request_lists_known(fake_registry):
    with pytest.raises(ConfigError, match="nope"):
        registry.request_for(PanelConfig(widget="nope"))


def test_requests_for_keeps_order_and_duplicates(fake_registry, make_config):
    cfg = make_config(
        monitors={
            "HDMI-A-1": {
                "panels": [{"widget": "dock"}, {"widget": "clock"}, {"widget": "dock", "order": 1}]
            }
        }
    )
    got = registry.requests_for(cfg, "HDMI-A-1")
    assert [(r.widget, r.order) for r in got] == [("dock", 0), ("clock", 0), ("dock", 1)]


def test_deprecated_pos_paths_lists_every_entry_using_pos(make_config):
    cfg = make_config(
        monitors={
            "A": {"panels": [{"widget": "dock"}, {"widget": "bar", "pos": 600}]},
            "B": {"panels": [{"widget": "clock", "pos": "center"}]},
        }
    )
    assert registry.deprecated_pos_paths(cfg) == [
        "monitors.A.panels.1.pos",
        "monitors.B.panels.0.pos",
    ]
    no_pos = make_config(monitors={"A": {"panels": [{"widget": "dock", "align": "end"}]}})
    assert registry.deprecated_pos_paths(no_pos) == []
