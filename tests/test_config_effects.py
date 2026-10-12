"""[theme.border] / [theme.shadow]: validation, defaults, per-monitor deep merge, diff."""

import pytest
from pydantic import ValidationError

from shell.config.diff import Change, diff_configs
from shell.config.loader import load_config
from shell.config.models import Border, Shadow, deep_merge


def test_defaults_are_opt_in_and_calibrated(make_config):
    theme = make_config().theme
    assert theme.border == Border(enabled=False, width=2, color="#8fd3b6ff")
    assert theme.shadow == Shadow(enabled=False, elevation=50, color="#00000080")


def test_partial_table_keeps_the_other_defaults(make_config):
    shadow = make_config(theme={"shadow": {"enabled": True}}).theme.shadow
    assert shadow == Shadow(enabled=True, elevation=50, color="#00000080")


@pytest.mark.parametrize("elevation", [0, 100])
def test_elevation_bounds_inclusive(make_config, elevation):
    assert make_config(theme={"shadow": {"elevation": elevation}}).theme.shadow.elevation == (
        elevation
    )


@pytest.mark.parametrize(
    ("table", "loc"),
    [
        ({"shadow": {"elevation": -1}}, ("theme", "shadow", "elevation")),
        ({"shadow": {"elevation": 101}}, ("theme", "shadow", "elevation")),
        ({"shadow": {"color": "black"}}, ("theme", "shadow", "color")),
        ({"shadow": {"offset": 3}}, ("theme", "shadow", "offset")),
        ({"border": {"width": 0}}, ("theme", "border", "width")),
        ({"border": {"color": "#8fd3b6f"}}, ("theme", "border", "color")),
    ],
)
def test_bad_effect_values_report_the_key_path(make_config, table, loc):
    with pytest.raises(ValidationError) as exc:
        make_config(theme=table)
    assert exc.value.errors()[0]["loc"] == loc


def test_monitor_override_merges_nested_tables_key_by_key(make_config):
    cfg = make_config(
        theme={"shadow": {"enabled": True, "color": "#11223380"}},
        monitors={"HDMI-A-1": {"shell": "edge", "theme": {"shadow": {"elevation": 80}}}},
    )
    assert cfg.theme_for("HDMI-A-1").shadow == Shadow(enabled=True, elevation=80, color="#11223380")
    assert cfg.theme_for("DP-1").shadow == Shadow(enabled=True, elevation=50, color="#11223380")


def test_monitor_override_can_switch_an_effect_off(make_config):
    cfg = make_config(
        theme={"border": {"enabled": True}},
        monitors={"HDMI-A-1": {"theme": {"border": {"enabled": False}}}},
    )
    assert cfg.theme_for("HDMI-A-1").border.enabled is False
    assert cfg.theme_for("DP-1").border.enabled is True


def test_out_of_range_override_fails_at_load_with_its_path(make_config):
    with pytest.raises(ValidationError) as exc:
        make_config(monitors={"HDMI-A-1": {"theme": {"shadow": {"elevation": 150}}}})
    assert "monitors.HDMI-A-1.theme" in str(exc.value)
    assert "shadow.elevation" in str(exc.value)


def test_deep_merge_merges_tables_replaces_lists_and_copies():
    base = {"a": {"x": 1, "y": 2}, "l": [1, 2], "s": 1}
    out = deep_merge(base, {"a": {"y": 3}, "l": [9]})
    assert out == {"a": {"x": 1, "y": 3}, "l": [9], "s": 1}
    assert base == {"a": {"x": 1, "y": 2}, "l": [1, 2], "s": 1}  # not mutated


# ---- loader -----------------------------------------------------------------------


def test_default_file_defines_the_effect_tables():
    theme = load_config(None).theme
    assert theme.border == Border() and theme.shadow == Shadow()


def test_user_file_enables_shadow_and_keeps_defaults(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text("[theme.shadow]\nenabled = true\n")
    assert load_config(path).theme.shadow == Shadow(enabled=True)


def test_user_file_monitor_border_override(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text(
        '[monitors.HDMI-A-1]\nshell = "edge"\n[monitors.HDMI-A-1.theme.border]\nwidth = 4\n'
    )
    border = load_config(path).theme_for("HDMI-A-1").border
    assert border == Border(width=4)


# ---- diff -------------------------------------------------------------------------


def _mon(theme=None):
    return {"shell": "edge", "panels": [], "theme": theme or {}}


@pytest.mark.parametrize(
    "theme",
    [
        {"shadow": {"enabled": True}},
        {"shadow": {"elevation": 90}},
        {"shadow": {"color": "#ff000080"}},
        {"border": {"enabled": True}},
        {"border": {"width": 5, "color": "#ffffff40"}},
    ],
)
def test_effect_changes_are_a_restyle_not_a_rebuild(fake_registry, make_config, theme):
    old = make_config(monitors={"HDMI-A-1": _mon()})
    new = make_config(theme=theme, monitors={"HDMI-A-1": _mon()})
    assert diff_configs(old, new) == [Change("restyle", "HDMI-A-1")]


def test_per_monitor_effect_override_restyles_only_that_monitor(fake_registry, make_config):
    old = make_config(monitors={"HDMI-A-1": _mon(), "DP-2": _mon()})
    new = make_config(monitors={"HDMI-A-1": _mon({"border": {"enabled": True}}), "DP-2": _mon()})
    assert diff_configs(old, new) == [Change("restyle", "HDMI-A-1")]
