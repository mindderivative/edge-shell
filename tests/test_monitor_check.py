"""shell.monitor_check: configured monitor names against the connected ones (pure)."""

import pytest

from shell.monitor_check import monitor_report, unknown_monitors


def test_a_configured_name_that_is_not_connected_is_reported_with_the_names_to_use():
    report = monitor_report(["HDMI-A-2", "DP-1"], ["HDMI-A-1", "DP-1"])
    assert report == "config monitors: HDMI-A-2; connected: DP-1, HDMI-A-1"


@pytest.mark.parametrize(
    "configured, connected",
    [
        (["HDMI-A-1"], ["HDMI-A-1", "DP-1"]),  # every configured name is connected
        ([], ["HDMI-A-1"]),  # the config names no monitor
        (["HDMI-A-1"], []),  # nothing known to be connected: nothing to compare
    ],
)
def test_no_report(configured, connected):
    assert monitor_report(configured, connected) is None


def test_a_connected_monitor_missing_from_the_config_is_not_reported():
    assert unknown_monitors(["DP-1"], ["DP-1", "HDMI-A-1"]) == []


def test_unknown_names_are_sorted_and_counted_once():
    assert unknown_monitors(["b", "a", "b", "DP-1"], ["DP-1"]) == ["a", "b"]
    assert monitor_report({"b": 1, "a": 2}, {"DP-1": 0}) == "config monitors: a, b; connected: DP-1"
