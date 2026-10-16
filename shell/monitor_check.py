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
MAX_LISTED = 10  # unknown names in the text; the rest is counted


def unknown_monitors(configured: Iterable[str], connected: Iterable[str]) -> list[str]:
    """The configured monitor names that are not connected, sorted."""
    known = set(connected)
    return sorted(name for name in set(configured) if name not in known)


def _shown(name: str) -> str:
    """A name as typed, or its repr when it has whitespace or a control character (a stray
    leading space must be visible, and a NUL must not reach notify-send)."""
    return name if name.isprintable() and name == name.strip() else repr(name)


def monitor_report(configured: Iterable[str], connected: Iterable[str]) -> str | None:
    """The text 'config monitors: HDMI-A-2; connected: DP-1, HDMI-A-1', or None when every
    configured name is connected (or the config names none). With nothing connected known
    (kscreen-doctor failed, or a hot-plug flap) there is nothing to compare against: None.
    The names are compared exactly (case and spaces count). At most 10 unknown names are
    listed, so the connected names to use, which come last, are not cut off."""
    connected = sorted(set(connected))
    unknown = unknown_monitors(configured, connected)
    if not unknown or not connected:
        return None
    listed = ", ".join(_shown(name) for name in unknown[:MAX_LISTED])
    if len(unknown) > MAX_LISTED:
        listed += f", ... and {len(unknown) - MAX_LISTED} more"
    return f"config monitors: {listed}; connected: {', '.join(_shown(n) for n in connected)}"
