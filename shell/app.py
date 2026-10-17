"""Application wiring: config -> monitors -> windows."""

from __future__ import annotations

import html
import logging
import os
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

from settings.launch import MAIN_PATH, settings_command  # noqa: F401  (shared with the window)
from shell import plan
from shell.canvas.stats import StatsRecorder
from shell.config.diff import diff_configs
from shell.config.store import ConfigStore
from shell.config.watcher import ConfigWatcher
from shell.monitor_check import TITLE as MONITOR_TITLE
from shell.monitor_check import monitor_report, unknown_monitors
from shell.monitors import MonitorShell, monitors_by_name
from shell.registry import all_off_paths, deprecated_pos_paths, moved_default_paths
from shell.theme import scope_class, to_css

log = logging.getLogger(__name__)

APP_NAME = "edge-shell"
EXERCISE_MS = 300  # --stats toggles every panel this often: a 280 ms tween plus a frame
# A quit signal fades every monitor out first (spec 21), waiting at most the longest fade_ms
# plus this; a second signal quits at once.
QUIT_MARGIN_MS = 250


def unix_signal_add(priority: int, signum: int, handler, data) -> int:
    """GLib's Unix signal source: GLibUnix.signal_add (GLib 2.80+; this machine: 2.90), else
    the older GLib.unix_signal_add. `handler(data)` runs in the main loop."""
    try:
        gi.require_version("GLibUnix", "2.0")
        from gi.repository import GLibUnix
    except (ValueError, ImportError):
        return GLib.unix_signal_add(priority, signum, handler, data)
    return GLibUnix.signal_add(priority, signum, handler, data)


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
        self._failures_reported: dict[str, list[str]] = {}  # last notified build failures
        self._relayout_rebuilt: set[str] = set()  # rebuilt after a failed re-layout, until a reload
        self._monitors_reported: list[str] = []  # the unknown configured names last notified
        self._seen_connected: set[str] = set()  # every monitor name connected this session
        # Shells fading out (spec 21), at most one per monitor: out of `shells`, so nothing
        # else (reports, CSS, reloads) sees them; closed by their fade or by _retire.
        self._leaving: dict[str, MonitorShell] = {}
        self._quitting = False  # a quit signal came: fading out, then quit
        self._quit_timer = 0
        self._quit_sent = False
        self._exit_code = 0
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
        try:
            self._check_monitor_names(connected)
        except Exception:  # a warning must never break startup or a reload
            log.exception("checking the monitor names failed")
        for name, shell in list(self._leaving.items()):
            if connected.get(name) is not shell.monitor:  # unplugged or replaced: no fade on it
                self._retire(name)
        wanted = plan.desired_shells(self.config, connected)
        desired = {name: connected[name] for name in wanted}
        active = {name: shell.monitor for name, shell in self.shells.items()}
        close, open_ = plan.reconcile(active, desired)
        for name in close:
            log.info("closing Edge Shell on %s", name)
            # Faded out while its monitor is still there; unplugged or replaced: closed now.
            self._close_shell(name, fade=connected.get(name) is self.shells[name].monitor)
        for name in open_:
            self._open_shell(name, desired[name])
        if close or open_:
            self.refresh_css()
        return set(close), set(open_)

    def _check_monitor_names(self, connected) -> None:
        """Warn (log and one notification) when the config names a monitor that looks like
        a typo: not connected now and never seen connected in this shell session (a name that
        was connected and is unplugged is right, only the cable is out: nothing is said).
        At startup a typo and a monitor that is simply absent look the same, so both are
        reported. Said again only when the set of such names changes, or after every name
        matched in between, so a reload with the same mismatch or a hot-plug says nothing
        new. An empty read (kscreen-doctor failed) compares nothing and changes nothing."""
        if not connected:
            return
        self._seen_connected.update(connected)
        unknown = unknown_monitors(self.config.monitors, self._seen_connected)
        if unknown == self._monitors_reported:
            return
        self._monitors_reported = unknown
        if unknown:
            report = monitor_report(unknown, connected)
            log.warning("monitor names in the config are not connected (%s)", report)
            self._notify(MONITOR_TITLE, f"{report}\nUse the connected names in the config.")

    def _close_shell(self, name: str, fade: bool = True) -> None:
        """Take `name`'s shell out of `shells`. With `fade` it fades out (spec 21; at once
        with fade_ms 0) and is closed when done; without (its monitor is gone), now."""
        self._forget_reports(name)
        shell = self.shells.pop(name)
        if fade:
            self._fade_away(name, shell)
        else:
            self._retire(name)
            shell.close()

    def _leave_shell(self, name: str) -> None:
        """A full rebuild of `name` (spec 21, crossfade): the old shell stays on screen,
        detached (held), until its successor starts fading in; then it fades out over the
        same time (_faded_in). Without a fade it is closed now, as before."""
        if self._fade_ms(name) <= 0:
            self._close_shell(name, fade=False)
            return
        self._forget_reports(name)
        shell = self.shells.pop(name)
        if shell.fade_state == "waiting":
            # never visible: closed now; a shell it was replacing stays held for the next one
            shell.close()
            return
        self._retire(name)  # at most one leaving shell per monitor: an older one goes now
        shell.finish_fade()  # mid fade-in: held fully shown, never two fades at once
        shell.detach()
        self._leaving[name] = shell

    def _faded_in(self, shell: MonitorShell) -> None:
        """`shell` starts fading in: the shell it replaces (held) fades out with it."""
        if self.shells.get(shell.name) is not shell:
            return
        old = self._leaving.get(shell.name)
        if old is not None and not old.fading_out:
            old.fade_out(self._fade_ms(shell.name), self._gone)

    def _release_held(self, only: str | None = None) -> None:
        """A held shell whose monitor got no successor (its rebuild failed, or it was never
        opened) fades out on its own; with `only`, just that monitor's."""
        for name, shell in list(self._leaving.items()):
            if only is not None and name != only:
                continue
            if name not in self.shells and not shell.fading_out:
                shell.fade_out(self._fade_ms(name), self._gone)

    def _fade_away(self, name: str, shell: MonitorShell) -> None:
        if shell.fade_state == "waiting":
            # never visible: closed now, and the shell it was replacing (held, on screen)
            # fades out instead of disappearing
            shell.close()
            self._release_held(name)  # only this monitor's: another may be waiting on a successor
            return
        self._retire(name)  # at most one leaving shell per monitor: an older one goes now
        self._leaving[name] = shell
        shell.fade_out(self._fade_ms(name), self._gone)

    def _retire(self, name: str) -> None:
        """Close `name`'s leaving shell now (its fade, if any, is dropped)."""
        shell = self._leaving.pop(name, None)
        if shell is not None:
            try:
                shell.close()
            except Exception:
                log.exception("closing the leaving shell of %s failed", name)

    def _gone(self, shell: MonitorShell) -> None:
        """A leaving shell finished its fade-out and closed itself."""
        if self._leaving.get(shell.name) is shell:
            del self._leaving[shell.name]
        if self._quitting and not self._leaving and not self.shells:
            self._quit_now()

    def _fade_ms(self, name: str) -> int:
        """The fade of `name`'s next fade in or out (spec 21): the config in effect now (a
        change of fade_ms applies from the next fade on). 0 while --stats measures."""
        if self._stats_seconds:
            return 0
        return self.config.theme_for(name).fade_ms

    def _forget_reports(self, name: str) -> None:
        """A closed shell's notified lists are stale: the monitor, plugged in again with the
        same failing panel, notifies again."""
        self._layout_reported.pop(name, None)
        self._failures_reported.pop(name, None)

    def _open_shell(self, name: str, monitor) -> None:
        log.info("opening Edge Shell on %s", name)
        fade_ms = self._fade_ms(name)
        shell = self.shells[name] = MonitorShell(
            name,
            monitor,
            self.config,
            self.register_window,
            self.unregister_window,
            on_layout=lambda shell, n=name: self._report_layout(n, shell),
            on_error=lambda shell, n=name: self._relayout_failed(n, shell),
            on_settings=self.open_settings,
            fade_ms=fade_ms,
            on_fade_in=self._faded_in,
            # a rebuild's successor reserves the edges at once (the held old shell has no strips
            # any more); a fresh enable, startup or hot-plug only after its fade-in starts
            reserve_now=fade_ms <= 0 or name in self._leaving,
        )
        if not shell.measure_pending:  # else the measurement's on_layout reports, with real sizes
            self._report_layout(name, shell)
        if self.recorder is not None:
            shell.canvas.painter.recorder = self.recorder

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
        if not self._quitting:  # never reopen what the quit is fading out
            self.sync_monitors()
        return GLib.SOURCE_REMOVE

    def css(self) -> str:
        return "\n".join(
            to_css(self.config.theme_for(name), scope_class(name)) for name in sorted(self.shells)
        )

    def refresh_css(self) -> None:
        if self.app is not None:
            # never empty: with no Edge Shell monitor css() is "", and Fabric's
            # load_from_data(bytearray(b"")) hands GTK a NULL pointer (Gtk-CRITICAL
            # 'data != NULL'). A comment replaces the old provider just the same.
            css = self.css() or "/* no Edge Shell monitor */"
            self.app.set_stylesheet_from_string(css, compile=False)

    def start_watching(self) -> None:
        path = self.store.path
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        self._watcher = ConfigWatcher(path, self.reload)

    def reload(self) -> None:
        # Runs from a GLib/watcher callback: never let an exception escape half-applied.
        if self._quitting:  # never reopen what the quit is fading out
            return
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
        kinds = ", ".join(c.kind for c in changes) or "none"
        log.info("config reloaded: %d change(s): %s", len(changes), kinds)
        rebuild = {c.monitor for c in changes if c.kind == "rebuild-monitor"}
        for name in sorted(rebuild & set(self.shells)):
            if plan.has_windows(new, name):
                self._leave_shell(name)  # rebuilt: the old one is held for the crossfade
            else:
                self._close_shell(name)  # turned off (plasma / none): it fades out
        # Shells opened here are built from the new config already: never apply onto them.
        try:
            _, opened = self.sync_monitors()
        finally:
            self._release_held()  # e.g. the new shell failed to build: the old one fades out
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
                if not self.shells[name].measure_pending:
                    self._report_layout(name, self.shells[name])
            except Exception:
                log.exception("applying config to %s failed, rebuilding it", name)
                self._report_error(f"{name}: could not apply the config in place; rebuilt it")
                failed = True
                shell = self.shells.pop(name)
                self._forget_reports(name)
                try:
                    shell.close()
                except Exception:
                    log.exception("closing the half-applied shell on %s failed", name)
        if failed:
            try:
                self.sync_monitors()  # rebuild the dropped shells from the new config
            finally:
                self._release_held()  # no successor (the rebuild raised): the held one fades
        self.refresh_css()

    def _log_deprecated(self, config) -> None:
        """One INFO line per config load listing the entries that still use `pos`, one for
        the system_bar entries whose default placement moved (decision 2: a notification would
        repeat on every start) and one for the panels with every interaction off (handle plan,
        decision 7)."""
        paths = deprecated_pos_paths(config)
        if paths:
            log.info(
                'deprecated key pos (use align = "start" and offset = pos - 38 at the default '
                "theme): %s",
                ", ".join(paths),
            )
        moved = moved_default_paths(config)
        if moved:
            log.info(
                "system_bar entries that set edge, length or depth but no pos/align/offset: "
                'the default placement is now align="end", offset=142 (it was pos = 600, the '
                "same place only at 1080p with edge right, length 300, depth >= 28); add "
                "pos = 600 to keep the old place at 1080p: %s",
                ", ".join(moved),
            )
        off = all_off_paths(config)
        if off:
            log.info(
                "panels with click, hover and drag all off (these panels open only through "
                "state): %s",
                ", ".join(off),
            )

    def _relayout_failed(self, name: str, shell) -> None:
        """A re-layout the shell started by itself raised (MonitorShell._measure / _relayout
        logged it): close that shell and rebuild it from the current config, as a failed
        reload does. Only once per monitor until the next reload, so a widget that always
        fails cannot rebuild forever; a stale call from a closed shell is ignored. The
        rebuild reuses the shell's own monitor (no kscreen-doctor round trip) and never raises
        into the main loop; if it fails, the monitor has no shell and the shell may be
        half-synced until the next reload."""
        if self.shells.get(name) is not shell:
            return
        if name in self._relayout_rebuilt:
            log.error("re-layout of %s failed again; keeping its panels as they are", name)
            return
        self._relayout_rebuilt.add(name)
        log.error("re-layout of %s failed; rebuilding its panels", name)
        self._notify("Panels rebuilt", f"{name}: laying out the panels failed; rebuilt them")
        self.shells.pop(name)
        self._forget_reports(name)
        try:
            shell.close()
        except Exception:
            log.exception("closing the failed shell on %s failed", name)
        try:
            self._open_shell(name, shell.monitor)
            self.refresh_css()
        except Exception:
            log.exception("rebuilding the panels of %s failed", name)
            self._report_error(f"{name}: rebuilding the panels failed")
            self._release_held()  # no successor: a shell held for the crossfade fades out

    def _report_layout(self, name: str, shell) -> None:
        """Notify panels moved, shrunk or hidden by the layout rules (shell.panel_layout), and
        panels whose widget could not be built (by name), but only when that monitor's list
        changed, not on every unrelated reload."""
        failures = list(shell.build_failures)
        if failures != self._failures_reported.get(name, []):
            self._failures_reported[name] = failures
            if failures:
                self._notify("Panel not shown", "\n".join(failures))
        warnings = list(shell.layout_warnings)
        if warnings == self._layout_reported.get(name, []):
            return
        self._layout_reported[name] = warnings
        if warnings:
            self._notify("Panels adjusted", "\n".join(warnings))

    def open_settings(self) -> None:
        """Start the settings window in its own process on this shell's config file (a
        right-click on a panel handle). A window that is already open is brought forward
        (single instance per config file). Never raises into GTK. The child is reaped by a
        GLib child watch when it exits (no zombie for the shell's lifetime)."""
        command = settings_command(None if self.store.path is None else self.store.path.absolute())
        log.info("opening the settings window: %s", " ".join(command))
        try:
            proc = subprocess.Popen(command, start_new_session=True, stdin=subprocess.DEVNULL)
        except OSError as exc:
            log.error("could not open the settings window: %s", exc)
            self._notify("Settings not opened", str(exc))
            return
        GLib.child_watch_add(GLib.PRIORITY_DEFAULT, proc.pid, self._settings_closed, proc)

    @staticmethod
    def _settings_closed(_pid: int, status: int, proc: subprocess.Popen) -> None:
        """GLib reaped the settings process; tell its Popen so it never waits for it again."""
        code = os.waitstatus_to_exitcode(status)  # GLib passes the raw wait status
        proc.returncode = code
        if code == 0:
            log.debug("the settings window closed (status 0)")
        else:
            log.warning(
                "settings window exited with status %d; run `python main.py --settings` "
                "in a terminal to see why",
                code,
            )

    def _notify(self, title: str, message: str) -> None:
        try:
            # notify-send bodies are markup (an `&` or `<b>` in a panel name must show as typed).
            # Cut first, then escape: the cut can never split an entity such as `&amp;`.
            body = html.escape(message[:400], quote=False)
            subprocess.Popen(["notify-send", "-a", "Edge Shell", "--", title, body])
        except (OSError, ValueError):  # ValueError: a NUL in the text
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
        # open_client=False: no Fabric D-Bus client (org.Fabric.fabric.edge-shell's Execute /
        # Evaluate run any Python sent by any session-bus client). The bus name itself stays
        # owned (Gtk.Application), so _already_running still sees a running shell.
        self.app = Application(APP_NAME, *self._early, open_client=False)
        self._early.clear()
        self.refresh_css()
        self.app.hold()  # stay alive even with no windows (e.g. all monitors set to plasma)
        self.start_watching()
        self.watch_displays()
        # Python's own SIGINT handler stays the default, so PyGObject installs no fallback of
        # its own that would quit without the fade; GLib's handler below takes the signal.
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        self._watch_quit_signals()  # Ctrl+C and SIGTERM fade out, then quit
        if self.recorder is not None:
            GLib.timeout_add(EXERCISE_MS, self._exercise)
            GLib.timeout_add(int(self._stats_seconds * 1000), self._stop)
        wall0, cpu0 = time.perf_counter(), time.process_time()
        self.app.run()
        if self.recorder is not None:
            wall, cpu = time.perf_counter() - wall0, time.process_time() - cpu0
            print("\n".join(self.recorder.report(wall, cpu)))
        return self._exit_code

    # ---- quit (spec 21) ---------------------------------------------------------------
    def _watch_quit_signals(self) -> None:
        for signum in (signal.SIGINT, signal.SIGTERM):
            unix_signal_add(GLib.PRIORITY_HIGH, signum, self._on_quit_signal, signum)

    def _on_quit_signal(self, signum: int) -> bool:
        """Fade every monitor out, then quit: when the last fade is done, at the latest the
        longest fade_ms + QUIT_MARGIN_MS later. A second signal quits at once. The exit status
        is the shell's usual one for a signal (128 + its number: 130 for Ctrl+C)."""
        self._exit_code = 128 + signum
        if self._quitting:
            log.info("second quit signal: quitting now")
            self._quit_now()
            return GLib.SOURCE_CONTINUE
        self._quitting = True
        names = sorted({*self.shells, *self._leaving})
        wait = max((self._fade_ms(name) for name in names), default=0)
        log.info("quit signal %d: fading out %s", signum, ", ".join(names) or "nothing")
        for name in sorted(self.shells):
            try:
                self._close_shell(name)
            except Exception:
                log.exception("fading out %s for the quit failed", name)
        if self._leaving:
            self._quit_timer = GLib.timeout_add(wait + QUIT_MARGIN_MS, self._quit_timeout)
        else:
            self._quit_now()
        return GLib.SOURCE_CONTINUE

    def _quit_timeout(self) -> bool:
        self._quit_timer = 0
        log.info("the fade-out did not finish in time: quitting")
        self._quit_now()
        return GLib.SOURCE_REMOVE

    def _quit_now(self) -> None:
        if self._quit_timer:
            GLib.source_remove(self._quit_timer)
            self._quit_timer = 0
        if self.app is not None and not self._quit_sent:
            self._quit_sent = True
            self.app.quit()

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
