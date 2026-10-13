"""Gdk monitor <-> connector name mapping, and the window set for one monitor (GTK)."""

from __future__ import annotations

import itertools
import logging
import os
import subprocess
from dataclasses import replace

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GLib, GtkLayerShell

from shell.canvas.canvas import ShapeCanvas
from shell.canvas.scene import PanelShape
from shell.config.diff import Change
from shell.config.models import Config
from shell.edge_panel import EdgePanel
from shell.frame import EDGES, FrameEdge
from shell.outputs import match_geometries, parse_kscreen, read_kscreen_json
from shell.panel_layout import Layout, resolve_layout
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
        self.strips: list = []  # the 4 zone strips (also in `windows`)
        # Config order; None = not shown (rejected by shell.panel_layout, see layout_warnings).
        self.panels: list[EdgePanel | None] = []
        self._resolved: list[PanelGeometry | None] = []
        self.layout_warnings: list[str] = []
        self._keys = itertools.count()  # scene keys for the canvas
        theme = config.theme_for(name)
        # The canvas first: it draws the frame and corners and must stay below every panel.
        self.canvas = ShapeCanvas(monitor, theme, self._scope)
        self._track(self.canvas)
        self.strips = [FrameEdge(edge, monitor, theme, self._scope) for edge in EDGES]
        for strip in self.strips:
            self._track(strip)
        self._sync_panels(config, theme, startup=True)
        if self.live_panels():
            for delay in raise_delays():
                GLib.timeout_add(delay, self._raise_panels)

    def live_panels(self) -> list[EdgePanel]:
        return [p for p in self.panels if p is not None]

    # ---- panels ---------------------------------------------------------------------------
    def _layout(self, config: Config, theme) -> Layout:
        g = self.monitor.get_geometry()
        return resolve_layout(
            panels_for(config, self.name),
            g.width,
            g.height,
            theme.thickness,
            theme.radius,
            where=f"monitors.{self.name}",
        )

    def _sync_panels(self, config: Config, theme, startup: bool) -> None:
        """Make the panels match the resolved layout: rebuild a panel whose resolved geometry
        changed (also when a neighbour's change moved or hid it), retarget a state change."""
        layout = self._layout(config, theme)
        self.layout_warnings = list(layout.warnings)
        for message in layout.warnings:
            log.warning("%s", message)
        wanted = layout.panels
        while len(self.panels) > len(wanted):  # removed at the end of the list
            if self.panels[-1] is not None:
                self._destroy_panel(len(self.panels) - 1)
            self.panels.pop()
            self._resolved.pop()
        for i, geo in enumerate(wanted):
            if i == len(self.panels):
                self.panels.append(None)
                self._resolved.append(None)
            old, panel = self._resolved[i], self.panels[i]
            if geo is None:
                if panel is not None:
                    self._destroy_panel(i)
            elif panel is None or old is None or replace(old, state=geo.state) != geo:
                if panel is not None:
                    self._destroy_panel(i)
                self.panels[i] = self._new_panel(i, geo, theme, raise_later=not startup)
            elif old.state != geo.state:
                panel.set_state(geo.state)
            self._resolved[i] = geo

    def _new_panel(self, index: int, geo: PanelGeometry, theme, raise_later: bool) -> EdgePanel:
        key = next(self._keys)
        self.canvas.add_panel(key, PanelShape(geo.edge, geo.pos, geo.length, geo.depth))
        try:
            panel = widget_class(geo.widget)(
                geo,
                theme,
                self.monitor,
                index,
                self._scope,
                on_depth=lambda d, k=key: self.canvas.set_depth(k, d),
            )
        except Exception:
            self.canvas.remove_panel(key)
            raise
        panel.scene_key = key
        self._track(panel)
        if raise_later:  # created after startup: re-raise it like the first ones
            for delay in raise_delays()[:1]:
                GLib.timeout_add(delay, self._raise_one, panel)
        return panel

    def _destroy_panel(self, index: int) -> None:
        panel = self.panels[index]
        self.panels[index] = None
        self.canvas.remove_panel(panel.scene_key)
        self._destroy(panel)

    def _raise_panels(self) -> bool:
        """Re-map the live panels so they stack above the canvas (see RAISE_DELAY_MS)."""
        if not self._closed:
            for panel in self.live_panels():
                panel.raise_to_top()
        return False

    def _raise_one(self, panel: EdgePanel) -> bool:
        # The panel may have been rebuilt or removed during the delay: only raise live ones.
        if panel in self.panels:
            panel.raise_to_top()
        return False

    # ---- windows --------------------------------------------------------------------------
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
        """Apply a reload in place: restyle the canvas and panels, then reconcile the panels
        against the newly resolved layout (the diff's panel kinds only say that it changed)."""
        theme = config.theme_for(self.name)
        if any(change.kind == "restyle" for change in changes):
            self.canvas.set_theme(theme)
            for strip in self.strips:  # the border width changes what the strips reserve
                strip.apply_theme(theme)
            for panel in self.live_panels():
                panel.apply_theme(theme)
        self._sync_panels(config, theme, startup=False)

    def close(self) -> None:
        self._closed = True
        for window in self.windows:
            self._release(window)
        self.windows.clear()
        self.panels.clear()
        self._resolved.clear()
