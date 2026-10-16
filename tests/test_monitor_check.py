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


def test_the_unknown_names_are_capped_so_the_names_to_use_always_show():
    configured = [f"BAD-{n:02d}" for n in range(40)]
    report = monitor_report(configured, ["HDMI-A-1", "DP-1"])
    assert report.endswith("connected: DP-1, HDMI-A-1")
    assert "BAD-09" in report
    assert "BAD-10" not in report
    assert "... and 30 more" in report
    assert len(report) < 200


def test_case_differences_are_not_matched():
    assert unknown_monitors(["hdmi-a-1"], ["HDMI-A-1"]) == ["hdmi-a-1"]
    assert monitor_report(["hdmi-a-1"], ["HDMI-A-1"]) == (
        "config monitors: hdmi-a-1; connected: HDMI-A-1"
    )


def test_whitespace_is_not_stripped_and_shows_in_the_report():
    assert unknown_monitors([" HDMI-A-1"], ["HDMI-A-1"]) == [" HDMI-A-1"]
    report = monitor_report([" HDMI-A-1"], ["HDMI-A-1"])
    assert report == "config monitors: ' HDMI-A-1'; connected: HDMI-A-1"


def test_control_characters_show_escaped():
    report = monitor_report(["HDMI\x00X"], ["HDMI-A-1"])
    assert "\x00" not in report
    assert "'HDMI\\x00X'" in report
