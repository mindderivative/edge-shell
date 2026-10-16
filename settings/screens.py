"""The per-screen toolbar's logic (panel/widget spec 7). Pure: no GTK.

- `mode_flags` / `mode_of`: the toolbar's two checkboxes (Edge Shell on this screen, the
  native desktop on this screen) and the monitor's four-valued `shell` key. Edge on + native
  off = "edge", edge off + native on = "plasma", both on = "both", both off = "none". The shell
  does not hide or show Plasma's panel yet (spec 7, deferred), so "edge" and "both" behave the
  same at runtime today: SHELL_NOTE says so under the checkboxes.
- `desktop_label`: the native checkbox's label, from XDG_CURRENT_DESKTOP.
- `detect_outputs`: the connected monitors (kscreen-doctor), raising DetectError on failure
  (settings.app.connected_outputs, used at start, returns [] instead).
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Mapping

from shell.outputs import Output, parse_kscreen, read_kscreen_json

_FLAGS: dict[str, tuple[bool, bool]] = {
    "edge": (True, False),
    "plasma": (False, True),
    "both": (True, True),
    "none": (False, False),
}
SHELL_NOTE = (
    "Plasma's panel is not hidden or shown by Edge Shell yet; with both on, keep the bottom "
    "edge free of Edge Shell panels"
)
# XDG_CURRENT_DESKTOP's first known component (matched without case) -> the checkbox's label
DESKTOP_NAMES = {
    "KDE": "KDE Plasma",
    "Hyprland": "Hyprland",
    "GNOME": "GNOME",
    "sway": "Sway",
    "niri": "niri",
    "XFCE": "Xfce",
    "LXQt": "LXQt",
    "X-Cinnamon": "Cinnamon",
    "MATE": "MATE",
    "Budgie": "Budgie",
    "COSMIC": "COSMIC",
}
NATIVE_FALLBACK = "Native desktop"


def mode_flags(mode: str) -> tuple[bool, bool]:
    """(Edge Shell on, native desktop on) for a `shell` value; KeyError for anything else."""
    return _FLAGS[mode]


def mode_of(edge: bool, native: bool) -> str:
    """The `shell` value the two checkboxes write."""
    return next(mode for mode, flags in _FLAGS.items() if flags == (bool(edge), bool(native)))


def desktop_label(env: Mapping[str, str] | None = None) -> str:
    """The native desktop's name: the first known component of XDG_CURRENT_DESKTOP ("KDE" in
    "KDE:plasma", "GNOME" in "ubuntu:GNOME") through DESKTOP_NAMES; NATIVE_FALLBACK when it
    is unset, empty or has no known component."""
    env = os.environ if env is None else env
    names = {key.casefold(): label for key, label in DESKTOP_NAMES.items()}
    for part in env.get("XDG_CURRENT_DESKTOP", "").split(":"):
        if part.strip().casefold() in names:
            return names[part.strip().casefold()]
    return NATIVE_FALLBACK


class DetectError(Exception):
    """The monitors could not be detected (the message says why)."""


def detect_outputs(read: Callable[[], str] | None = None) -> list[Output]:
    """The connected monitors now, from `read` (default: `kscreen-doctor -j`); DetectError when
    it fails or prints something unexpected. Tests always pass `read`."""
    try:
        return parse_kscreen((read or read_kscreen_json)())
    except (OSError, subprocess.SubprocessError, ValueError, RecursionError) as exc:
        raise DetectError(f"kscreen-doctor failed: {exc}") from None
