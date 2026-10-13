"""Application wiring: config -> monitors -> windows."""

from __future__ import annotations

import logging
import signal
import subprocess
import sys
import time
import traceback
from collections import defaultdict

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from fabric import Application
from fabric.core.application import FABRIC_DBUS_INTERFACE_NAME
from gi.repository import Gdk, GLib

from shell import plan
from shell.canvas.stats import StatsRecorder
from shell.config.diff import diff_configs
from shell.config.store import ConfigStore
from shell.config.watcher import ConfigWatcher
from shell.monitors import MonitorShell, monitors_by_name
from shell.registry import deprecated_pos_paths
from shell.theme import scope_class, to_css

log = logging.getLogger(__name__)

APP_NAME = "edge-shell"
EXERCISE_MS = 300  # --stats toggles every panel this often: a 280 ms tween plus a frame


def _already_running() -> bool:
    # Fabric refuses a second Application with the same id, but only after the windows exist.
    return Application.name_running(FABRIC_DBUS_INTERFACE_NAME + f".{APP_NAME}")


class EdgeShellApp:
    def __init__(self, store: ConfigStore, stats_seconds: float | None = None):
        """`stats_seconds`: measure for that long (main.py --stats), print, then quit."""
        self.store = store
        self._stats_seconds = stats_seconds
        self.recorder: StatsRecorder | None = None
        self.app: Application | None = None
        self.shells: dict[str, MonitorShell] = {}
        self._watcher: ConfigWatcher | None = None
        self._early: list = []  # windows created before the Application exists
        self._sync_timers: list[int] = []  # pending hot-plug sync timer ids
        self._layout_reported: dict[str, list[str]] = {}  # last notified warnings per monitor
        self._relayout_rebuilt: set[str] = set()  # rebuilt after a failed re-layout, until a reload
        self._log_deprecated(store.config)

    @property
    def config(self):
        return self.store.config

    def register_window(self, window) -> None:
        if self.app is None:
            self._early.append(window)
        else:
            self.app.add_window(window)

    def unregister_window(self, window) -> None:
        """Forget a window that is about to be destroyed (Fabric's window list holds it forever)."""
        if window in self._early:
            self._early.remove(window)
        elif self.app is not None:
            self.app.remove_window(window)  # call before destroy(): Gtk still lists it

    def sync_monitors(self) -> tuple[set[str], set[str]]:
        """Open/close shells to match the config; return (closed, opened) connector names."""
        connected = monitors_by_name()
        if not connected and self.shells:
            # kscreen-doctor failed or a hot-plug flap; closing all would blank every frame
            log.warning("monitor mapping unavailable, keeping current shells")
            return set(), set()
        wanted = plan.desired_shells(self.config, connected)
        desired = {name: connected[name] for name in wanted}
        active = {name: shell.monitor for name, shell in self.shells.items()}
        close, open_ = plan.reconcile(active, desired)
        for name in close:
            log.info("closing Edge Shell on %s", name)
            self.shells.pop(name).close()
        for name in open_:
            log.info("opening Edge Shell on %s", name)
            self.shells[name] = MonitorShell(
                name,
                desired[name],
                self.config,
                self.register_window,
                self.unregister_window,
                on_layout=lambda shell, n=name: self._report_layout(n, shell),
                on_error=lambda shell, n=name: self._relayout_failed(n, shell),
            )
            self._report_layout(name, self.shells[name])
            if self.recorder is not None:
                self.shells[name].canvas.painter.recorder = self.recorder
        if close or open_:
            self.refresh_css()
        return set(close), set(open_)

    def watch_displays(self) -> None:
        display = Gdk.Display.get_default()
        if display is None:
            log.warning("no Gdk display, monitor hot-plug will not be watched")
            return
        display.connect("monitor-added", self._schedule_sync)
        display.connect("monitor-removed", self._schedule_sync)

    def _schedule_sync(self, *_) -> None:
        # kscreen-doctor can lag the Gdk signal, so sync twice; sync is idempotent.
        for timer in self._sync_timers:  # only still-pending ids: fired ones removed themselves
            GLib.source_remove(timer)
        self._sync_timers = [self._arm_sync(600), self._arm_sync(2500)]

    def _arm_sync(self, delay_ms: int) -> int:
        holder: list[int] = []
        holder.append(GLib.timeout_add(delay_ms, lambda: self._sync_once(holder[0])))
        return holder[0]

    def _sync_once(self, timer: int) -> bool:
        if timer in self._sync_timers:
            self._sync_timers.remove(timer)
        self.sync_monitors()
        return GLib.SOURCE_REMOVE

    def css(self) -> str:
        return "\n".join(
            to_css(self.config.theme_for(name), scope_class(name)) for name in sorted(self.shells)
        )

    def refresh_css(self) -> None:
        if self.app is not None:
            self.app.set_stylesheet_from_string(self.css(), compile=False)

    def start_watching(self) -> None:
        path = self.store.path
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        self._watcher = ConfigWatcher(path, self.reload)

    def reload(self) -> None:
        # Runs from a GLib/watcher callback: never let an exception escape half-applied.
        try:
            self._reload()
        except Exception:
            log.exception("config reload failed")
            self._report_error(f"reload failed:\n{traceback.format_exc(limit=-3)}")

    def _reload(self) -> None:
        result = self.store.reload()
        if result is None:
            if self.store.last_error:
                self._report_error(self.store.last_error)
            return
        old, new = result
        self._log_deprecated(new)
        self._relayout_rebuilt.clear()  # a new config may fix the failing widget
        changes = diff_configs(old, new)
        log.info("config reloaded: %d change(s)", len(changes))
        rebuild = {c.monitor for c in changes if c.kind == "rebuild-monitor"}
        for name in rebuild & set(self.shells):
            self.shells.pop(name).close()
        # Shells opened here are built from the new config already: never apply onto them.
        _, opened = self.sync_monitors()
        grouped: dict[str, list] = defaultdict(list)
        for change in changes:
            if change.monitor not in rebuild:
                grouped[change.monitor].append(change)
        failed = False
        for name, items in grouped.items():
            if name in opened or name not in self.shells:
                continue
            try:
                self.shells[name].apply(new, items)
                self._report_layout(name, self.shells[name])
            except Exception:
                log.exception("applying config to %s failed, rebuilding it", name)
                self._report_error(f"{name}: could not apply the config in place; rebuilt it")
                failed = True
                shell = self.shells.pop(name)
                try:
                    shell.close()
                except Exception:
                    log.exception("closing the half-applied shell on %s failed", name)
        if failed:
            self.sync_monitors()  # rebuild the dropped shells from the new config
        self.refresh_css()

    def _log_deprecated(self, config) -> None:
        """One INFO line per config load listing the entries that still use `pos` (decision 2:
        a notification would repeat on every start)."""
        paths = deprecated_pos_paths(config)
        if paths:
            log.info(
                'deprecated key pos (use align = "start" and offset = pos - 38 at the default '
                "theme): %s",
                ", ".join(paths),
            )

    def _relayout_failed(self, name: str, shell) -> None:
        """A re-layout the shell started by itself raised (MonitorShell._measure / _relayout
        logged it): close that shell and rebuild it from the current config, as a failed
        reload does. Only once per monitor until the next reload, so a widget that always
        fails cannot rebuild forever; a stale call from a closed shell is ignored."""
        if self.shells.get(name) is not shell:
            return
        if name in self._relayout_rebuilt:
            log.error("re-layout of %s failed again; keeping its panels as they are", name)
            return
        self._relayout_rebuilt.add(name)
        log.error("re-layout of %s failed; rebuilding its panels", name)
        self._notify("Panels rebuilt", f"{name}: laying out the panels failed; rebuilt them")
        self.shells.pop(name)
        try:
            shell.close()
        except Exception:
            log.exception("closing the failed shell on %s failed", name)
        self.sync_monitors()  # reopens it from self.config (and refreshes the CSS)

    def _report_layout(self, name: str, shell) -> None:
        """Notify panels moved, shrunk or hidden by the layout rules (shell.panel_layout), but
        only when that monitor's warnings changed, not on every unrelated reload."""
        warnings = list(shell.layout_warnings)
        if warnings == self._layout_reported.get(name, []):
            return
        self._layout_reported[name] = warnings
        if warnings:
            self._notify("Panels adjusted", "\n".join(warnings))

    def _notify(self, title: str, message: str) -> None:
        try:
            subprocess.Popen(["notify-send", "-a", "Edge Shell", "--", title, message[:400]])
        except OSError:
            pass  # no notify-send; the log line is enough

    def _report_error(self, message: str) -> None:
        log.error("config not applied (keeping the previous config):\n%s", message)
        self._notify("Config not applied", message)

    def run(self) -> int:
        """Run until quit; returns the process exit code."""
        if _already_running():  # check before any window is created (no flash of a 2nd frame)
            print(
                "edge-shell is already running (close the other instance first; "
                "fg/Ctrl+C if it is a suspended job)",
                file=sys.stderr,
            )
            return 1
        if self._stats_seconds:
            self.recorder = StatsRecorder(GLib.get_monotonic_time)
        self.sync_monitors()
        self.app = Application(APP_NAME, *self._early)
        self._early.clear()
        self.app.set_stylesheet_from_string(self.css(), compile=False)
        self.app.hold()  # stay alive even with no windows (e.g. all monitors set to plasma)
        self.start_watching()
        self.watch_displays()
        signal.signal(signal.SIGINT, signal.SIG_DFL)  # Ctrl+C quits
        if self.recorder is not None:
            GLib.timeout_add(EXERCISE_MS, self._exercise)
            GLib.timeout_add(int(self._stats_seconds * 1000), self._stop)
        wall0, cpu0 = time.perf_counter(), time.process_time()
        self.app.run()
        if self.recorder is not None:
            wall, cpu = time.perf_counter() - wall0, time.process_time() - cpu0
            print("\n".join(self.recorder.report(wall, cpu)))
        return 0

    def _exercise(self) -> bool:
        """--stats: keep every panel animating (collapse <-> extend)."""
        for shell in self.shells.values():
            for panel in shell.live_panels():
                panel.toggle()
        return True

    def _stop(self) -> bool:
        if self.app is not None:
            self.app.quit()
        return False
