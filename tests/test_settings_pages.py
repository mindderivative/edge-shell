"""settings.pages: page names and the tree's rows (pure)."""

import pytest

from settings.pages import (
    THEME,
    PageRef,
    TreeEntry,
    fallback_page,
    monitor_page,
    panel_page,
    parse_page,
    screen_of,
    tree_entries,
)
from shell.outputs import Output

HDMI = Output("HDMI-A-1", 0, 0, 1920, 1080)
DP = Output("DP-1", 0, 1080, 1920, 1080)


def test_page_names_round_trip():
    assert parse_page(THEME) == PageRef("theme")
    assert parse_page(monitor_page("HDMI-A-1")) == PageRef("monitor", "HDMI-A-1")
    assert parse_page(panel_page("HDMI-A-1", 3)) == PageRef("panel", "HDMI-A-1", 3)
    assert panel_page("HDMI-A-1", 3) == "panel:HDMI-A-1:3"


def test_a_monitor_name_with_a_colon_round_trips():
    assert parse_page(monitor_page("a:b")) == PageRef("monitor", "a:b")
    assert parse_page(panel_page("a:b", 10)) == PageRef("panel", "a:b", 10)


@pytest.mark.parametrize("name", ["", "monitor", "panel:M", "panel:M:x", "panel:M:²", "other:M"])
def test_anything_else_is_not_a_page(name):
    with pytest.raises(ValueError, match="not a settings page"):
        parse_page(name)


def test_the_screen_of_a_page():
    assert screen_of(None) is None and screen_of(THEME) is None
    assert screen_of(monitor_page("DP-1")) == "DP-1"
    assert screen_of(panel_page("HDMI-A-1", 0)) == "HDMI-A-1"


def test_a_gone_panel_falls_back_to_its_monitor_and_a_monitor_to_the_theme():
    assert fallback_page(panel_page("HDMI-A-1", 2)) == monitor_page("HDMI-A-1")
    assert fallback_page(monitor_page("DP-2")) == THEME


def test_the_tree_lists_theme_monitors_and_their_panels(make_config, fake_registry):
    config = make_config(
        monitors={
            "HDMI-A-1": {
                "shell": "edge",
                "panels": [
                    {"panel": "edge", "name": "Bottom dock", "widget": "dock"},
                    {"panel": "edge", "name": "Clock", "widget": "clock"},
                ],
            },
            "DP-2": {"shell": "plasma"},
        }
    )
    assert tree_entries(config, [HDMI, DP]) == (
        TreeEntry("theme", "Theme"),
        TreeEntry(
            "monitor:HDMI-A-1",
            "HDMI-A-1",
            (
                TreeEntry("panel:HDMI-A-1:0", "Bottom dock"),
                TreeEntry("panel:HDMI-A-1:1", "Clock"),
            ),
        ),
        TreeEntry("monitor:DP-1", "DP-1"),  # connected, not in the config
        TreeEntry("monitor:DP-2", "DP-2 (not connected)"),  # only in the config
    )


def test_with_nothing_detected_the_configured_monitors_are_listed(make_config):
    config = make_config(monitors={"HDMI-A-1": {"shell": "edge"}})
    assert [e.title for e in tree_entries(config, [])] == [
        "Theme",
        "HDMI-A-1 (not connected)",
    ]


def test_an_invalid_file_lists_only_the_theme():
    assert tree_entries(None, [HDMI]) == (TreeEntry("theme", "Theme"),)


def test_no_monitor_at_all_lists_only_the_theme(make_config):
    assert tree_entries(make_config(), []) == (TreeEntry("theme", "Theme"),)
