"""Small Gdk helpers (GTK)."""

from __future__ import annotations

import gi

gi.require_version("Gdk", "3.0")
from gi.repository import Gdk


def _geometry(monitor) -> tuple[int, int, int, int]:
    g = monitor.get_geometry()
    return (g.x, g.y, g.width, g.height)


def monitor_index(monitor, display=None) -> int:
    """Index of `monitor` in the display's monitor list (identity first, then geometry)."""
    display = display or Gdk.Display.get_default()
    candidates = [display.get_monitor(i) for i in range(display.get_n_monitors())]
    for i, m in enumerate(candidates):
        if m is monitor:
            return i
    wanted = _geometry(monitor)
    for i, m in enumerate(candidates):
        if _geometry(m) == wanted:
            return i
    raise ValueError(f"monitor {wanted} not found on the default display")
