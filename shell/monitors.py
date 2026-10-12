"""Gdk monitor <-> connector name mapping, and the window set for one monitor (GTK)."""

from __future__ import annotations

import logging
import subprocess

import gi

gi.require_version("Gdk", "3.0")
from gi.repository import Gdk

from shell.config.models import Config
from shell.frame import CORNERS, EDGES, FrameEdge, ScreenCorner
from shell.outputs import match_geometries, parse_kscreen, read_kscreen_json
from shell.theme import scope_class

log = logging.getLogger(__name__)


def gdk_monitors() -> list[Gdk.Monitor]:
    display = Gdk.Display.get_default()
    return [display.get_monitor(i) for i in range(display.get_n_monitors())]


def _names_for(monitors: list[Gdk.Monitor]) -> list[str | None]:
    # Gdk's model string is the panel model, not the connector, so match by geometry.
    outputs = parse_kscreen(read_kscreen_json())
    geoms = []
    for m in monitors:
        g = m.get_geometry()
        geoms.append((g.x, g.y, g.width, g.height))
    return match_geometries(geoms, outputs)


def monitors_by_name() -> dict[str, Gdk.Monitor]:
    monitors = gdk_monitors()
    try:
        names = _names_for(monitors)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        log.error("cannot map monitors to connectors via kscreen-doctor: %s", exc)
        return {}
    return {name: mon for name, mon in zip(names, monitors, strict=True) if name}


def describe_monitors() -> list[str]:
    monitors = gdk_monitors()
    try:
        names = _names_for(monitors)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        names = [None] * len(monitors)
        log.error("kscreen-doctor failed: %s", exc)
    lines = []
    for i, (m, name) in enumerate(zip(monitors, names, strict=True)):
        g = m.get_geometry()
        lines.append(
            f"{i}  {name or '?':<10} {g.x},{g.y} {g.width}x{g.height}  scale {m.get_scale_factor()}"
        )
    return lines


class MonitorShell:
    """Every Edge Shell window for one monitor: 4 frame strips, 4 corners (panels: Task 15)."""

    def __init__(self, name: str, monitor: Gdk.Monitor, config: Config, register_window):
        self.name = name
        self.monitor = monitor
        self._register = register_window
        self.windows: list = []
        self.corners: list[ScreenCorner] = []
        theme = config.theme_for(name)
        scope = scope_class(name)
        for edge in EDGES:
            self._track(FrameEdge(edge, monitor, theme, scope))
        for corner in CORNERS:
            window = ScreenCorner(corner, monitor, theme, scope)
            self.corners.append(window)
            self._track(window)

    def _track(self, window) -> None:
        self.windows.append(window)
        self._register(window)

    def close(self) -> None:
        for window in self.windows:
            try:
                window.destroy()
            except Exception:  # the compositor may already have closed it (monitor unplugged)
                log.exception("failed to destroy window on %s", self.name)
        self.windows.clear()
