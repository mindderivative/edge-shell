"""Gdk monitor <-> connector name mapping, and the window set for one monitor (GTK)."""

from __future__ import annotations

import logging
import os
import subprocess

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GLib, GtkLayerShell

from shell.canvas.canvas import ShapeCanvas
from shell.config.diff import Change
from shell.config.models import Config
from shell.edge_panel import EdgePanel
from shell.frame import EDGES, FrameEdge
from shell.outputs import match_geometries, parse_kscreen, read_kscreen_json
from shell.panel_spec import PanelGeometry
from shell.registry import panels_for, widget_class
from shell.theme import scope_class

log = logging.getLogger(__name__)

# Timing workaround, not an event-driven fix (core build): KWin restacks same-layer surfaces
# when it first configures them, which put the old frame strips above the panels. The strips
# now live on the bottom layer, but the canvas shares the panels' layer, so the re-map stays
# until Gates 1-2 show it is not needed. Empirical: 50 ms was too early, 500 ms reliable; the
# second raise is a safety net for a slow compositor; both are no-ops after close().
RAISE_DELAY_MS = 500
RAISE_FALLBACK_MS = 2000


def raise_delays(env=os.environ) -> tuple[int, ...]:
    """Re-raise delays. EDGE_SHELL_RAISE_MS=0 turns the re-raise off, so Gates 1-2 can test
    whether the canvas design still needs it (temporary switch, removed with the raise)."""
    if env.get("EDGE_SHELL_RAISE_MS", "").strip() == "0":
        return ()
    return (RAISE_DELAY_MS, RAISE_FALLBACK_MS)


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
    """Every Edge Shell window for one monitor: the shape canvas, 4 zone strips, N panels."""

    def __init__(
        self,
        name: str,
        monitor: Gdk.Monitor,
        config: Config,
        register_window,
        unregister_window=None,
    ):
        self.name = name
        self.monitor = monitor
        self._register = register_window
        self._unregister = unregister_window or (lambda _window: None)
        self._scope = scope_class(name)
        self._closed = False
        self.windows: list = []
        self.panels: list[EdgePanel] = []
        theme = config.theme_for(name)
        # The canvas first: it draws the frame and corners and must stay below every panel.
        self.canvas = ShapeCanvas(monitor, theme, self._scope)
        self._track(self.canvas)
        for edge in EDGES:
            self._track(FrameEdge(edge, monitor, theme, self._scope))
        for index, geo in enumerate(panels_for(config, name)):
            self.panels.append(self._make_panel(index, geo, theme))
        if self.panels:
            for delay in raise_delays():
                GLib.timeout_add(delay, self._raise_panels)

    def _raise_panels(self) -> bool:
        """Re-map the live panels so they stack above the canvas (see RAISE_DELAY_MS)."""
        if not self._closed:
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
        for delay in raise_delays()[:1]:
            GLib.timeout_add(delay, self._raise_one, panel)
        return panel

    def _release(self, window) -> None:
        """Drop the app's reference (Fabric keeps every added window) and destroy it."""
        try:
            self._unregister(window)
        except Exception:  # e.g. ValueError if the app never held it
            log.debug("could not unregister window on %s", self.name, exc_info=True)
        try:
            window.destroy()
        except Exception:  # the compositor may already have closed it (monitor unplugged)
            log.exception("failed to destroy window on %s", self.name)

    def _destroy(self, window) -> None:
        if window in self.windows:
            self.windows.remove(window)
        self._release(window)

    def apply(self, config: Config, changes: list[Change]) -> None:
        """Apply in-place changes for this monitor (the diff orders adds before removes)."""
        theme = config.theme_for(self.name)
        geos = panels_for(config, self.name)
        for change in changes:
            i = change.index
            if change.kind == "restyle":
                self.canvas.set_theme(theme)
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
        self._closed = True
        for window in self.windows:
            self._release(window)
        self.windows.clear()
        self.panels.clear()
