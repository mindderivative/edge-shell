"""Monitor names in the config against the connected monitors (Phil, 2026-10-15: "if they
match everything is fine, if they do not then a warning should be output with the monitor
names that should be used"). Pure: the shell (shell/app.py) and the settings window
(settings/pages.py, the Detect monitors button) use the same comparison and text.

A configured name that is not connected is reported, with the connected names to use instead;
a connected monitor the config does not name is fine (it keeps the default, plasma) and is not
reported. Nothing changes in what the shell does: a monitor that is not connected has no
frame, as before."""

from __future__ import annotations

from collections.abc import Iterable

TITLE = "Monitor not connected"


def unknown_monitors(configured: Iterable[str], connected: Iterable[str]) -> list[str]:
    """The configured monitor names that are not connected, sorted."""
    known = set(connected)
    return sorted(name for name in set(configured) if name not in known)


def monitor_report(configured: Iterable[str], connected: Iterable[str]) -> str | None:
    """The text 'config monitors: HDMI-A-2; connected: DP-1, HDMI-A-1', or None when every
    configured name is connected (or the config names none). With nothing connected known
    (kscreen-doctor failed, or a hot-plug flap) there is nothing to compare against: None."""
    connected = sorted(set(connected))
    unknown = unknown_monitors(configured, connected)
    if not unknown or not connected:
        return None
    return f"config monitors: {', '.join(unknown)}; connected: {', '.join(connected)}"
