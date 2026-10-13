# tests/test_config_diff.py
import pytest

from shell.config.diff import Change, diff_configs


def mon(shell="edge", panels=(), theme=None):
    return {"shell": shell, "panels": list(panels), "theme": theme or {}}


def test_identical_is_empty(fake_registry, make_config):
    cfg = make_config(monitors={"HDMI-A-1": mon(panels=[{"widget": "dock"}])})
    assert diff_configs(cfg, cfg) == []


def test_color_change_restyles_edge_monitors_only(fake_registry, make_config):
    old = make_config(monitors={"HDMI-A-1": mon(), "DP-1": mon("plasma")})
    new = make_config(
        theme={"accent": "#112233"}, monitors={"HDMI-A-1": mon(), "DP-1": mon("plasma")}
    )
    assert diff_configs(old, new) == [Change("restyle", "HDMI-A-1")]


def test_structural_theme_change_rebuilds_monitor(fake_registry, make_config):
    old = make_config(monitors={"HDMI-A-1": mon()})
    new = make_config(theme={"thickness": 12}, monitors={"HDMI-A-1": mon()})
    assert diff_configs(old, new) == [Change("rebuild-monitor", "HDMI-A-1")]


def test_mode_changes(fake_registry, make_config):
    def cfg(shell):
        return make_config(monitors={"HDMI-A-1": mon(shell)})

    assert diff_configs(cfg("plasma"), cfg("edge")) == [Change("rebuild-monitor", "HDMI-A-1")]
    assert diff_configs(cfg("edge"), cfg("none")) == [Change("rebuild-monitor", "HDMI-A-1")]
    assert diff_configs(cfg("edge"), cfg("both")) == []  # windows unchanged
    assert diff_configs(cfg("plasma"), cfg("none")) == []


def test_panel_state_only(fake_registry, make_config):
    old = make_config(monitors={"HDMI-A-1": mon(panels=[{"widget": "dock", "state": "extended"}])})
    new = make_config(monitors={"HDMI-A-1": mon(panels=[{"widget": "dock", "state": "collapsed"}])})
    assert diff_configs(old, new) == [Change("panel-state", "HDMI-A-1", 0)]


def test_panel_geometry_change_rebuilds_that_panel(fake_registry, make_config):
    old = make_config(monitors={"HDMI-A-1": mon(panels=[{"widget": "dock"}, {"widget": "clock"}])})
    new = make_config(
        monitors={"HDMI-A-1": mon(panels=[{"widget": "dock"}, {"widget": "clock", "depth": 50}])}
    )
    assert diff_configs(old, new) == [Change("panel-rebuild", "HDMI-A-1", 1)]


def test_widget_swap_at_same_index_rebuilds(fake_registry, make_config):
    old = make_config(monitors={"HDMI-A-1": mon(panels=[{"widget": "dock"}])})
    new = make_config(monitors={"HDMI-A-1": mon(panels=[{"widget": "clock"}])})
    assert diff_configs(old, new) == [Change("panel-rebuild", "HDMI-A-1", 0)]


def test_add_and_remove_panels(fake_registry, make_config):
    one = make_config(monitors={"HDMI-A-1": mon(panels=[{"widget": "dock"}])})
    three = make_config(
        monitors={
            "HDMI-A-1": mon(panels=[{"widget": "dock"}, {"widget": "clock"}, {"widget": "bar"}])
        }
    )
    assert diff_configs(one, three) == [
        Change("panel-add", "HDMI-A-1", 1),
        Change("panel-add", "HDMI-A-1", 2),
    ]
    assert diff_configs(three, one) == [  # highest index first so indexes stay valid
        Change("panel-remove", "HDMI-A-1", 2),
        Change("panel-remove", "HDMI-A-1", 1),
    ]


def test_non_edge_monitor_panel_changes_ignored(fake_registry, make_config):
    old = make_config(monitors={"DP-1": mon("plasma", panels=[{"widget": "dock"}])})
    new = make_config(monitors={"DP-1": mon("plasma", panels=[{"widget": "clock"}])})
    assert diff_configs(old, new) == []


def test_gap_change_relayouts_without_touching_panels(fake_registry, make_config):
    def cfg(gap):
        return make_config(
            monitors={"HDMI-A-1": {**mon(panels=[{"widget": "dock"}]), "layout": {"gap": gap}}}
        )

    assert diff_configs(cfg(8), cfg(20)) == [Change("relayout", "HDMI-A-1")]


def test_global_gap_change_relayouts_every_edge_monitor(fake_registry, make_config):
    monitors = {"HDMI-A-1": mon(), "DP-1": mon("plasma")}
    old = make_config(monitors=monitors)
    new = make_config(monitors=monitors)
    new = new.model_copy(update={"layout": new.layout.model_copy(update={"gap": 30})})
    assert diff_configs(old, new) == [Change("relayout", "HDMI-A-1")]


@pytest.mark.parametrize(
    "entry",
    [
        {"align": "end"},
        {"offset": 30},
        {"order": 2},
        {"length": "fill"},
        {"min_length": 100},
        {"max_length": 900},
    ],
)
def test_placement_and_length_changes_rebuild_that_panel(fake_registry, make_config, entry):
    old = make_config(monitors={"HDMI-A-1": mon(panels=[{"widget": "dock"}])})
    new = make_config(monitors={"HDMI-A-1": mon(panels=[{"widget": "dock", **entry}])})
    assert diff_configs(old, new) == [Change("panel-rebuild", "HDMI-A-1", 0)]
