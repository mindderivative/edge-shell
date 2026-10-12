import pytest

from shell import registry
from shell.config.models import ConfigError, PanelConfig
from shell.panel_spec import PanelDefaults, PanelGeometry


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
