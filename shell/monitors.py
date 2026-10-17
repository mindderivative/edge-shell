"""Gdk monitor <-> connector name mapping, and the window set for one monitor (GTK)."""

from __future__ import annotations

import itertools
import logging
import os
import subprocess
from collections.abc import Callable
from dataclasses import replace

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GLib, GtkLayerShell

from shell import geometry
from shell.canvas.canvas import ShapeCanvas
from shell.canvas.scene import shape_for
from shell.config.diff import Change
from shell.config.models import Config
from shell.corner_panel import CornerPanel
from shell.edge_panel import EdgePanel
from shell.fade import Fade
from shell.frame import EDGES, FrameEdge
from shell.outputs import match_geometries, parse_kscreen, read_kscreen_json
from shell.panel_layout import Layout, layout_monitor
from shell.panel_spec import (
    CornerGeometry,
    CornerRequest,
    HandleSpec,
    Interaction,
    PanelGeometry,
    PanelRequest,
)
from shell.registry import requests_for, widget_class
from shell.theme import scope_class
from shell.widget import WidgetProps

log = logging.getLogger(__name__)

# Timing workaround, not an event-driven fix (core build): KWin restacks same-layer surfaces
# when it first configures them, which put the old frame strips above the panels. The strips
# now live on the bottom layer, but the canvas shares the panels' layer, so the re-map stays:
# Gate 1 item 7 showed it is still needed (collapsed handle dots are hidden without it).
# Empirical: 50 ms was too early, 500 ms reliable; the
# second raise is a safety net for a slow compositor; both are no-ops after close().
RAISE_DELAY_MS = 500
RAISE_FALLBACK_MS = 2000
# A resolution change arrives as several notify::geometry signals; re-layout once it settles.
RELAYOUT_DELAY_MS = 250
# A fresh enable (no predecessor) builds the zone strips this long after its fade-in starts, not
# with the shell: the strips make a maximized window shrink, which must not happen before the
# frame is seen (Phil's gate finding 4; building them with the shell shrank it ~0.5 s early, the
# wait for the first re-raise). The window resizes a beat after the frame starts to appear.
RESERVE_DELAY_MS = 50


def raise_delays(env=os.environ) -> tuple[int, ...]:
    """Re-raise delays. EDGE_SHELL_RAISE_MS=0 turns the re-raise off. It is a debug switch for
    checking the stacking without the delayed re-raise, not a supported setting."""
    if env.get("EDGE_SHELL_RAISE_MS", "").strip() == "0":
        return ()
    return (RAISE_DELAY_MS, RAISE_FALLBACK_MS)


def _geometry(monitor) -> tuple[int, int, int, int]:
    g = monitor.get_geometry()
    return (g.x, g.y, g.width, g.height)


def panel_class(geo: PanelGeometry | CornerGeometry) -> type[EdgePanel]:
    """The window class of a panel kind: CornerPanel for a corner panel, else EdgePanel."""
    return CornerPanel if isinstance(geo, CornerGeometry) else EdgePanel


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
        on_settings=None,
        fade_ms: int = 0,
        on_fade_in: Callable[[MonitorShell], None] | None = None,
        reserve_now: bool = True,
    ):
        """`on_layout(shell)` is called after a re-layout this shell starts by itself (content
        measured, monitor geometry changed), so the app can report new layout warnings;
        `on_error(shell)` when such a re-layout raised (logged here; the app rebuilds us);
        `on_settings()` is given to every panel (a right-click on its handle).

        `fade_ms` > 0 (spec 21): every window is built at opacity 0 and the panels take no
        input; once the monitor is ready (the first re-raise has run, no "content" measurement
        is pending) all windows fade in together over `fade_ms`, the panels take input from
        the start of the fade, and `on_fade_in(shell)` is called. 0: no fade (as before).

        `reserve_now` False (only with a fade): the 4 zone strips are not built with the shell
        but RESERVE_DELAY_MS after the fade-in starts (a fresh enable, a startup, a hot-plug;
        the maximized windows shrink after the frame appears). True: built at once, as a
        rebuild's successor does (the held old shell already destroyed its own strips, so the
        zone stays continuous). Without a fade they are always built at once."""
        self.name = name
        self.monitor = monitor
        self._register = register_window
        self._unregister = unregister_window or (lambda _window: None)
        self._on_layout = on_layout or (lambda _shell: None)
        self._on_error = on_error or (lambda _shell: None)
        self._on_settings = on_settings
        self._scope = scope_class(name)
        self._closed = False
        self.windows: list = []
        self.strips: list = []  # the 4 zone strips (also in `windows`)
        # Config order; None = not shown (rejected by shell.panel_layout, see layout_warnings).
        self.panels: list[EdgePanel | None] = []
        self._resolved: list[PanelGeometry | CornerGeometry | None] = []
        # Each index's (handle, interaction) as last given to its panel (changed in place).
        self._handles: list[tuple[HandleSpec, Interaction] | None] = []
        # Each index's (name, widget properties) as last built: a change rebuilds the panel.
        self._contents: list[tuple[str, WidgetProps] | None] = []
        self.layout_warnings: list[str] = []
        # Panels whose window or widget could not be built (not shown), as of the last sync.
        self.build_failures: list[str] = []
        # index -> (the entry it failed for, the message): not tried again until it changes
        self._failed: dict[int, tuple[tuple, str]] = {}
        self._keys = itertools.count()  # scene keys for the canvas
        self._config = config
        self._theme = config.theme_for(name)
        # Of the last layout, config order; corner panels (spec 19) are CornerRequests.
        self._requests: list[PanelRequest | CornerRequest] = []
        # Measured "content" lengths: index -> ((widget, horizontal), px). Kept across
        # re-layouts; an entry only counts while the same widget sits at that index.
        self._natural: dict[int, tuple[tuple[str, bool], int]] = {}
        self._remeasure: set[int] = set()  # built since the last measurement (or restyled)
        self._measure_id = 0  # pending idle measurement
        self._relayout_id = 0  # pending geometry re-layout
        self._scale_warned = False
        self._monitor_handlers: list[int] = []
        self._fade_ms = fade_ms
        self._reserve_now = reserve_now or fade_ms <= 0
        self._reserve_id = 0  # pending late build of the strips
        self._on_fade_in = on_fade_in or (lambda _shell: None)
        self._fade: Fade | None = None  # made in _build, right after the canvas
        self._input_live = fade_ms <= 0  # the panels take input (from the fade-in on)
        self._raises_pending = 0  # first re-raises still to run: the monitor is not ready
        self._ready_id = 0  # pending idle readiness check
        self._detached = False  # leaving (detach): no longer follows the config or monitor
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
        # One Tween on the canvas's frame clock sets every window (0 ms: no fade work at all).
        self._fade = Fade(
            self.canvas,
            self._set_opacity,
            self._fade_ms,
            GLib.timeout_add,
            GLib.source_remove,
            on_start=self._faded_in,
        )
        if self._reserve_now:
            self._build_strips(theme)
        self._sync_panels(config, theme, startup=True)
        if self.live_panels():
            for i, delay in enumerate(raise_delays()):
                first = i == 0  # the fallback re-raise is not waited for
                self._raises_pending += first
                GLib.timeout_add(delay, self._raise_panels, first)
        self._monitor_handlers.append(monitor.connect("notify::geometry", self._on_geometry))
        if self._fade.state == "waiting":  # checked once the build has returned to the loop
            self._ready_id = GLib.idle_add(self._ready_idle)

    def _build_strips(self, theme) -> None:
        """The 4 zone strips, each tracked (and so registered) as soon as it exists."""
        for edge in EDGES:
            strip = FrameEdge(edge, self.monitor, theme, self._scope)
            self.strips.append(strip)
            self._track(strip)

    def _reserve(self) -> bool:
        """RESERVE_DELAY_MS after the fade-in started: build the strips from the current theme,
        unless the shell was closed or detached meanwhile."""
        self._reserve_id = 0
        if self._closed or self._detached or self.strips:
            return False
        try:
            self._build_strips(self._theme)
        except Exception:  # a GLib callback: never raise into the main loop (decision 11)
            log.exception("reserving the edges of %s failed", self.name)
        return False

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
        """Make the panels match the resolved layout: rebuild a panel whose resolved geometry,
        name or widget properties changed (also when a neighbour's change moved or hid it),
        retarget a state change. A panel that could not be built is left out (None) and
        listed in `build_failures`; it is tried again only when its entry (kind, widget, name
        or properties) changes. Does nothing while the monitor reports no size (being
        unplugged: the hot-plug sync closes this shell), so no 0 px layout hides every panel."""
        g = self.monitor.get_geometry()
        if g.width <= 0 or g.height <= 0:
            return
        layout = self._layout(config, theme)
        self.layout_warnings = list(layout.warnings)
        self.build_failures = []
        for message in layout.warnings:
            log.warning("%s", message)
        wanted = layout.panels
        while len(self.panels) > len(wanted):  # removed at the end of the list
            if self.panels[-1] is not None:
                self._destroy_panel(len(self.panels) - 1)
            self.panels.pop()
            self._resolved.pop()
            self._handles.pop()
            self._contents.pop()
            self._failed.pop(len(self.panels), None)
        for i, geo in enumerate(wanted):
            if i == len(self.panels):
                self.panels.append(None)
                self._resolved.append(None)
                self._handles.append(None)
                self._contents.append(None)
            old, panel = self._resolved[i], self.panels[i]
            req = self._requests[i]
            handles = (req.handle, req.interaction)
            content = (req.name, req.props)
            if geo is None:
                if panel is not None:
                    self._destroy_panel(i)
            elif (
                panel is None
                or old is None
                or replace(old, state=geo.state) != geo
                or self._contents[i] != content
            ):
                if panel is not None:
                    self._destroy_panel(i)
                failed = self._failed.get(i)
                if failed is not None and failed[0] == _entry_key(req):
                    self.build_failures.append(failed[1])  # same entry: not tried again
                else:
                    self._failed.pop(i, None)
                    self.panels[i] = self._new_panel(i, geo, theme, raise_later=not startup)
            else:  # same geometry: the live panel changes in place (spec 15: never a rebuild)
                if self._handles[i] != handles:
                    panel.set_handle(*handles)
                if old.state != geo.state:
                    panel.set_state(geo.state)
            self._resolved[i] = geo
            self._handles[i] = handles
            self._contents[i] = content
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
            and isinstance(req, PanelRequest)  # corner panels have no "content" length
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
            # always: the app skips its own report while a measurement is pending
            self._on_layout(self)
        except Exception:  # a GLib callback: never raise into the main loop (decision 11)
            log.exception("measuring the content panels of %s failed", self.name)
            try:
                self._on_error(self)
            except Exception:
                log.exception("handling the measurement failure of %s failed", self.name)
        self._check_ready()
        return False

    # ---- monitor geometry -----------------------------------------------------------------
    def _on_geometry(self, *_args) -> None:
        """The monitor's resolution (or position) changed: re-layout once it settles."""
        if self._closed or self._detached:
            return
        if self._relayout_id:
            GLib.source_remove(self._relayout_id)
        self._relayout_id = GLib.timeout_add(RELAYOUT_DELAY_MS, self._relayout)

    def _relayout(self) -> bool:
        self._relayout_id = 0
        if self._closed:
            return False
        try:
            g = self.monitor.get_geometry()
            if g.width <= 0 or g.height <= 0:  # being unplugged: the hot-plug sync closes us
                log.debug("ignoring %dx%d geometry of %s", g.width, g.height, self.name)
                return False
            log.info("re-laying out %s for %dx%d", self.name, g.width, g.height)
            if self.monitor.get_scale_factor() != 1 and not self._scale_warned:
                self._scale_warned = True
                log.warning(
                    "scale %d is not supported yet: %s is laid out at scale 1",
                    self.monitor.get_scale_factor(),
                    self.name,
                )
            self._sync_panels(self._config, self._theme, startup=False)
            if not self.measure_pending:  # else the measurement reports afterwards
                self._on_layout(self)
        except Exception:  # a GLib callback: never raise into the main loop (decision 11)
            log.exception("re-laying out %s after a geometry change failed", self.name)
            try:
                self._on_error(self)
            except Exception:
                log.exception("handling the re-layout failure of %s failed", self.name)
        return False

    @property
    def measure_pending(self) -> bool:
        """True while a "content" measurement is queued: lengths are still provisional and
        on_layout will fire after it."""
        return bool(self._measure_id)

    def _new_panel(
        self, index: int, geo: PanelGeometry | CornerGeometry, theme, raise_later: bool
    ) -> EdgePanel | None:
        """Build one panel window (edge or corner: `panel_class` of the geometry) showing a
        new instance of the request's widget (`widget_class`), and its canvas shape. A window
        or widget that fails to build is logged, listed in `build_failures` (the app notifies
        it by the panel's name) and left out: None, never an exception that would take the
        monitor's other panels down."""
        self._remeasure.add(index)  # measured when idle if it is a "content" panel
        key = next(self._keys)
        self.canvas.add_panel(key, shape_for(geo))
        req = self._requests[index]
        log.debug("building panel %d %r (%s) on %s", index, req.name, geo.widget, self.name)
        try:
            panel = panel_class(geo)(
                geo,
                theme,
                self.monitor,
                index,
                self._scope,
                on_depth=lambda d, k=key: self.canvas.set_depth(k, d),
                handle=req.handle,
                interaction=req.interaction,
                on_settings=self._on_settings,
                widget=widget_class(geo.widget)(),
                props=req.props,
            )
        except Exception as exc:
            self.canvas.remove_panel(key)
            log.exception(
                "building panel %d %r (%s) on %s failed", index, req.name, geo.widget, self.name
            )
            message = (
                f"{self.name}: panel {req.name!r} ({geo.widget}) could not be built and is not "
                f"shown: {str(exc) or type(exc).__name__}"
            )
            self.build_failures.append(message)
            self._failed[index] = (_entry_key(req), message)
            return None
        panel.scene_key = key
        if not self._input_live:  # invisible until the fade-in: no input either
            panel.set_input_enabled(False)
        self._track(panel)
        if raise_later:  # created after startup: re-raise it like the first ones
            for delay in raise_delays()[:1]:
                self._raises_pending += 1
                GLib.timeout_add(delay, self._raise_one, panel)
        return panel

    def _destroy_panel(self, index: int) -> None:
        panel = self.panels[index]
        self.panels[index] = None
        self.canvas.remove_panel(panel.scene_key)
        self._destroy(panel)

    def _raise_panels(self, first: bool = False) -> bool:
        """Re-map the live panels so they stack above the canvas (see RAISE_DELAY_MS). The
        `first` one is waited for by the fade-in: a re-map is a visible blink."""
        if not self._closed and not self._detached:  # a leaving shell is never re-mapped
            for panel in self.live_panels():
                panel.raise_to_top()
        if first:
            self._raised()
        return False

    def _raise_one(self, panel: EdgePanel) -> bool:
        # The panel may have been rebuilt or removed during the delay: only raise live ones.
        if panel in self.panels and not self._detached:
            panel.raise_to_top()
        self._raised()
        return False

    # ---- fade (spec 21) -------------------------------------------------------------------
    def _raised(self) -> None:
        self._raises_pending = max(0, self._raises_pending - 1)
        self._check_ready()

    def _ready_idle(self) -> bool:
        self._ready_id = 0
        self._check_ready()
        return False

    def _check_ready(self) -> None:
        """Fade in once nothing that re-maps or resizes a window is pending (Fade.ready only
        acts while waiting; its own timeout fades in anyway)."""
        if self._closed or self._detached or self._fade is None:
            return
        if self._raises_pending or self._measure_id:
            return
        self._fade.ready()

    def _faded_in(self) -> None:
        """The fade-in starts: the panels take input from now on (what is seen is clicked)."""
        self._input_live = True
        for panel in self.live_panels():
            try:
                panel.set_input_enabled(True)
            except Exception:  # one failing panel must not leave the others without input
                log.exception("could not enable the input of a panel on %s", self.name)
        if not self._reserve_now and not self.strips and not self._reserve_id:
            self._reserve_id = GLib.timeout_add(RESERVE_DELAY_MS, self._reserve)
        self._on_fade_in(self)

    @property
    def fade_state(self) -> str:
        """The fade's state (shell.fade.State); "done" once closed."""
        if self._closed:
            return "done"
        return "shown" if self._fade is None else self._fade.state

    @property
    def fading_out(self) -> bool:
        """True once fade_out has started (or the shell is closed)."""
        return self.fade_state in ("fading-out", "done")

    def finish_fade(self) -> None:
        """Complete a fade-in in progress now (fully shown). A shell replaced in the middle of
        its fade-in (a second reload) is held at full opacity: fades never stack."""
        if not self._closed and self._fade is not None and self._fade.state == "fading-in":
            self._fade.finish()

    def detach(self, keep_strips: bool = False) -> None:
        """Stop following the config and the monitor: the shell is leaving (fade_out, or a
        rebuild replaces it). Pending measurements, re-layouts and readiness checks are
        dropped, re-raises do nothing (a re-map would blink), the monitor's geometry is no
        longer watched, and the zone strips are destroyed now, so the edges are reserved by
        the successor's strips alone (never twice). Everything else stays on screen, as it
        is, until fade_out or close. Once only.

        `keep_strips` (fade_out, a leaving shell with no successor): the strips stay, and are
        closed with the other windows, so a maximized window grows only when the frame is
        gone (it would show its square corners through the fading frame's rounded ones)."""
        if self._detached or self._closed:
            return
        self._detached = True
        self._cancel_sources()
        self._disconnect_monitor()
        if not keep_strips:
            for strip in self.strips:
                self._destroy(strip)
            self.strips = []

    def fade_out(self, duration_ms: int, on_done: Callable[[MonitorShell], None]) -> None:
        """Fade every window out over `duration_ms` from the opacity it has, then close and
        call on_done(self). From now on the shell is detached and its panels take no input
        (clicks reach the successor or the desktop). With 0 ms, or when nothing was visible
        yet (still waiting to fade in), it is closed at once, as close() does. A second call
        while fading out is ignored (the first on_done runs)."""
        if self._closed or duration_ms <= 0 or self.fade_state == "waiting":
            self.close()
            self._call_done(on_done)
            return
        if self.fading_out:
            return
        self.detach(keep_strips=True)  # the zones go with the frame, at the end
        for panel in self.live_panels():
            try:
                panel.set_input_enabled(False)
            except Exception:  # the fade-out must start whatever one panel does
                log.exception("could not disable the input of a panel on %s", self.name)
        self._fade.fade_out(duration_ms, lambda: self._faded_out(on_done))

    def _faded_out(self, on_done: Callable[[MonitorShell], None]) -> None:
        try:
            self.close()
        except Exception:  # in a frame-clock tick: never raise into GTK
            log.exception("closing %s after its fade-out failed", self.name)
        self._call_done(on_done)

    def _call_done(self, on_done: Callable[[MonitorShell], None]) -> None:
        try:
            on_done(self)
        except Exception:
            log.exception("the fade-out callback of %s failed", self.name)

    def _set_opacity(self, value: float) -> None:
        """One frame of the fade: every window of the monitor, in the same tick."""
        for window in self.windows:
            self._apply_opacity(window, value)

    def _apply_opacity(self, window, value: float) -> None:
        try:
            window.set_opacity(value)  # GTK 3 paints a toplevel's opacity as a group alpha
        except Exception:  # one window going away must not stop the others
            log.debug("could not set the opacity of a window on %s", self.name, exc_info=True)

    # ---- windows --------------------------------------------------------------------------
    def _track(self, window) -> None:
        self.windows.append(window)
        if self._fade is not None and self._fade.state != "shown":
            self._apply_opacity(window, self._fade.value)  # before its first frame is drawn
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

    def _cancel_sources(self) -> None:
        for source in (self._measure_id, self._relayout_id, self._ready_id, self._reserve_id):
            if source:
                GLib.source_remove(source)
        self._measure_id = self._relayout_id = self._ready_id = self._reserve_id = 0

    def _disconnect_monitor(self) -> None:
        for handler in self._monitor_handlers:
            try:
                self.monitor.disconnect(handler)
            except Exception:  # the monitor may be gone already (unplugged)
                log.debug("could not disconnect from %s", self.name, exc_info=True)
        self._monitor_handlers.clear()

    def close(self) -> None:
        self._closed = True
        if self._fade is not None:
            self._fade.cancel()  # before the canvas (its frame clock) is destroyed
        self._cancel_sources()
        self._disconnect_monitor()
        for window in self.windows:
            self._release(window)
        self.windows.clear()
        self.strips = []  # released with the windows
        self.panels.clear()
        self._resolved.clear()
        self._handles.clear()
        self._contents.clear()
        self._failed.clear()


def _entry_key(req: PanelRequest | CornerRequest) -> tuple:
    """What a failed build is remembered by: the entry's kind, widget, name and properties.
    A change of any of them (a reload) tries the panel again; a move does not."""
    return type(req).__name__, req.widget, req.name, req.props


def _measure_key(req: PanelRequest | CornerRequest) -> tuple[str, bool]:
    """A measurement belongs to a widget at an orientation (along a horizontal edge or not)."""
    return req.widget, geometry.is_horizontal(req.edge)
