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

from shell import geometry
from shell.canvas.canvas import ShapeCanvas
from shell.canvas.scene import PanelShape
from shell.config.diff import Change
from shell.config.models import Config
from shell.edge_panel import EdgePanel
from shell.frame import EDGES, FrameEdge
from shell.outputs import match_geometries, parse_kscreen, read_kscreen_json
from shell.panel_layout import Layout, layout_monitor
from shell.panel_spec import PanelGeometry, PanelRequest
from shell.registry import requests_for, widget_class
from shell.theme import scope_class

log = logging.getLogger(__name__)

# Timing workaround, not an event-driven fix (core build): KWin restacks same-layer surfaces
# when it first configures them, which put the old frame strips above the panels. The strips
# now live on the bottom layer, but the canvas shares the panels' layer, so the re-map stays:
# Gate 1 item 7 showed it is still needed (collapsed handle dots are hidden without it).
# Empirical: 50 ms was too early, 500 ms reliable; the
# second raise is a safety net for a slow compositor; both are no-ops after close().
RAISE_DELAY_MS = 500
RAISE_FALLBACK_MS = 2000


def raise_delays(env=os.environ) -> tuple[int, ...]:
    """Re-raise delays. EDGE_SHELL_RAISE_MS=0 turns the re-raise off. It is a debug switch for
    checking the stacking without the delayed re-raise, not a supported setting."""
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
        on_layout=None,
        on_error=None,
    ):
        """`on_layout(shell)` is called after a re-layout this shell starts by itself (content
        measured, monitor geometry changed), so the app can report new layout warnings;
        `on_error(shell)` when such a re-layout raised (logged here; the app rebuilds us)."""
        self.name = name
        self.monitor = monitor
        self._register = register_window
        self._unregister = unregister_window or (lambda _window: None)
        self._on_layout = on_layout or (lambda _shell: None)
        self._on_error = on_error or (lambda _shell: None)
        self._scope = scope_class(name)
        self._closed = False
        self.windows: list = []
        self.strips: list = []  # the 4 zone strips (also in `windows`)
        # Config order; None = not shown (rejected by shell.panel_layout, see layout_warnings).
        self.panels: list[EdgePanel | None] = []
        self._resolved: list[PanelGeometry | None] = []
        self.layout_warnings: list[str] = []
        self._keys = itertools.count()  # scene keys for the canvas
        self._config = config
        self._theme = config.theme_for(name)
        self._requests: list[PanelRequest] = []  # of the last layout, config order
        # Measured "content" lengths: index -> ((widget, horizontal), px). Kept across
        # re-layouts; an entry only counts while the same widget sits at that index.
        self._natural: dict[int, tuple[tuple[str, bool], int]] = {}
        self._remeasure: set[int] = set()  # built since the last measurement (or restyled)
        self._measure_id = 0  # pending idle measurement
        try:
            self._build(config)
        except BaseException:
            self.close()  # never leave a half-built monitor's windows on screen
            raise

    def _build(self, config: Config) -> None:
        theme = config.theme_for(self.name)
        monitor = self.monitor
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
        self._requests = requests_for(config, self.name)
        return layout_monitor(
            self._requests,
            g.width,
            g.height,
            theme.thickness,
            theme.radius,
            config.layout_for(self.name).gap,
            self._measured(),
            where=f"monitors.{self.name}",
        )

    def _measured(self) -> dict[int, int]:
        """Measured natural lengths that still belong to the widget at each index."""
        out = {}
        for i, req in enumerate(self._requests):
            got = self._natural.get(i)
            if got is not None and got[0] == _measure_key(req):
                out[i] = got[1]
        return out

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
        self._schedule_measure()

    # ---- "content" lengths ----------------------------------------------------------------
    def _to_measure(self) -> list[int]:
        """Live "content" panels built since the last measurement (or restyled), or without a
        measurement for the widget now at their index. A "content" panel hidden at its default
        length is never built, so it is never measured and stays hidden."""
        known = self._measured()
        return [
            i
            for i, (panel, req) in enumerate(zip(self.panels, self._requests, strict=True))
            if panel is not None
            and req.length == "content"
            and (i in self._remeasure or i not in known)
        ]

    def _schedule_measure(self) -> None:
        """Measure "content" panels when the main loop is next idle: by then the app's
        stylesheet is applied (EdgeShellApp.run sets it after building the shells), so fonts
        have their real size. Only new, restyled or unmeasured panels are measured; an
        unchanged size changes nothing."""
        if self._measure_id or self._closed:
            return
        if self._to_measure():
            self._measure_id = GLib.idle_add(self._measure)

    def _measure(self) -> bool:
        self._measure_id = 0
        if self._closed:
            return False
        try:
            todo = self._to_measure()
            self._remeasure.clear()
            changed = False
            for i in todo:
                entry = (_measure_key(self._requests[i]), self.panels[i].natural_length())
                if self._natural.get(i) != entry:
                    self._natural[i] = entry
                    changed = True
            if changed:
                self._sync_panels(self._config, self._theme, startup=False)
                self._on_layout(self)
        except Exception:  # a GLib callback: never raise into the main loop (decision 11)
            log.exception("measuring the content panels of %s failed", self.name)
            try:
                self._on_error(self)
            except Exception:
                log.exception("handling the measurement failure of %s failed", self.name)
        return False

    @property
    def measure_pending(self) -> bool:
        """True while a "content" measurement is queued: lengths are still provisional and
        on_layout will fire after it."""
        return bool(self._measure_id)

    def _new_panel(self, index: int, geo: PanelGeometry, theme, raise_later: bool) -> EdgePanel:
        self._remeasure.add(index)  # measured when idle if it is a "content" panel
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
        self._config, self._theme = config, theme
        if any(change.kind == "restyle" for change in changes):
            self.canvas.set_theme(theme)
            for strip in self.strips:  # the border width changes what the strips reserve
                strip.apply_theme(theme)
            for panel in self.live_panels():
                panel.apply_theme(theme)
            self._remeasure.update(range(len(self.panels)))  # fonts may have changed
        self._sync_panels(config, theme, startup=False)

    def close(self) -> None:
        self._closed = True
        if self._measure_id:
            GLib.source_remove(self._measure_id)
            self._measure_id = 0
        for window in self.windows:
            self._release(window)
        self.windows.clear()
        self.panels.clear()
        self._resolved.clear()


def _measure_key(req: PanelRequest) -> tuple[str, bool]:
    """A measurement belongs to a widget at an orientation (along a horizontal edge or not)."""
    return req.widget, geometry.is_horizontal(req.edge)
