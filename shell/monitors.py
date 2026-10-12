"""Gdk monitor <-> connector name mapping, and the window set for one monitor (GTK)."""

from __future__ import annotations

import logging
import subprocess

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GLib, GtkLayerShell

from shell.config.diff import Change
from shell.config.models import Config
from shell.edge_panel import EdgePanel
from shell.frame import CORNERS, EDGES, FrameEdge, ScreenCorner
from shell.outputs import match_geometries, parse_kscreen, read_kscreen_json
from shell.panel_spec import PanelGeometry
from shell.registry import panels_for, widget_class
from shell.theme import scope_class

log = logging.getLogger(__name__)

# Empirical: re-mapping at 50 ms still left the strips on top (KWin restacks them when it
# first configures them); 500 ms is reliably after that (checked by screenshot).
RAISE_DELAY_MS = 500


def _geometry(monitor) -> tuple[int, int, int, int]:
    g = monitor.get_geometry()
    return (g.x, g.y, g.width, g.height)


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
    """Every Edge Shell window for one monitor: 4 frame strips, 4 corners, N panels."""

    def __init__(self, name: str, monitor: Gdk.Monitor, config: Config, register_window):
        self.name = name
        self.monitor = monitor
        self._register = register_window
        self._scope = scope_class(name)
        self.windows: list = []
        self.corners: list[ScreenCorner] = []
        self.panels: list[EdgePanel] = []
        theme = config.theme_for(name)
        for edge in EDGES:
            self._track(FrameEdge(edge, monitor, theme, self._scope))
        for corner in CORNERS:
            window = ScreenCorner(corner, monitor, theme, self._scope)
            self.corners.append(window)
            self._track(window)
        for index, geo in enumerate(panels_for(config, name)):
            self.panels.append(self._make_panel(index, geo, theme))
        if self.panels:
            self._raise_tries = 0
            GLib.timeout_add(RAISE_DELAY_MS, self._raise_panels)

    def _raise_panels(self) -> bool:
        """Once the frame strips are mapped, re-map panels so they stack above them."""
        if not self.panels:  # closed meanwhile
            return False
        self._raise_tries += 1
        strips = self.windows[: len(EDGES)]
        if not all(w.get_mapped() for w in strips) and self._raise_tries < 40:
            return True
        for panel in self.panels:
            panel.raise_to_top()
        return False

    def _make_panel(self, index: int, geo: PanelGeometry, theme) -> EdgePanel:
        panel = widget_class(geo.widget)(geo, theme, self.monitor, index, self._scope)
        self._track(panel)
        return panel

    def _track(self, window) -> None:
        self.windows.append(window)
        self._register(window)
        self._check_monitor(window)

    def _check_monitor(self, window) -> None:
        got = GtkLayerShell.get_monitor(window)
        want = _geometry(self.monitor)
        if got is None or _geometry(got) != want:
            log.error(
                "window %s is not on the requested monitor: layer-shell has %s, wanted %s",
                window.get_title(),
                _geometry(got) if got else None,
                want,
            )

    def _raise_one(self, panel: EdgePanel) -> bool:
        # The panel may have been rebuilt or removed during the delay: only raise live ones.
        if panel in self.panels:
            panel.raise_to_top()
        return False

    def _add_panel(self, index: int, geo: PanelGeometry, theme) -> EdgePanel:
        """Create a panel after startup and re-raise it above the strips, like the first ones."""
        panel = self._make_panel(index, geo, theme)
        GLib.timeout_add(RAISE_DELAY_MS, self._raise_one, panel)
        return panel

    def _destroy(self, window) -> None:
        if window in self.windows:
            self.windows.remove(window)
        try:
            window.destroy()
        except Exception:
            log.exception("failed to destroy window on %s", self.name)

    def apply(self, config: Config, changes: list[Change]) -> None:
        """Apply in-place changes for this monitor (the diff orders adds before removes)."""
        theme = config.theme_for(self.name)
        geos = panels_for(config, self.name)
        for change in changes:
            i = change.index
            if change.kind == "restyle":
                for corner in self.corners:
                    corner.set_theme(theme)
                for panel in self.panels:
                    panel.apply_theme(theme)
            elif change.kind == "panel-state":
                self.panels[i].set_state(geos[i].state)
            elif change.kind == "panel-rebuild":
                self._destroy(self.panels[i])
                self.panels[i] = self._add_panel(i, geos[i], theme)
            elif change.kind == "panel-add":
                self.panels.append(self._add_panel(i, geos[i], theme))
            elif change.kind == "panel-remove":
                self._destroy(self.panels.pop(i))

    def close(self) -> None:
        for window in self.windows:
            try:
                window.destroy()
            except Exception:  # the compositor may already have closed it (monitor unplugged)
                log.exception("failed to destroy window on %s", self.name)
        self.windows.clear()
        self.panels.clear()
