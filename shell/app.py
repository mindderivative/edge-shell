"""Application wiring: config -> monitors -> windows."""

from __future__ import annotations

import logging
import signal
import subprocess
from collections import defaultdict

import gi

gi.require_version("Gtk", "3.0")
from fabric import Application

from shell import plan
from shell.config.diff import diff_configs
from shell.config.store import ConfigStore
from shell.config.watcher import ConfigWatcher
from shell.monitors import MonitorShell, monitors_by_name
from shell.theme import scope_class, to_css

log = logging.getLogger(__name__)


class EdgeShellApp:
    def __init__(self, store: ConfigStore):
        self.store = store
        self.app: Application | None = None
        self.shells: dict[str, MonitorShell] = {}
        self._watcher: ConfigWatcher | None = None
        self._early: list = []  # windows created before the Application exists

    @property
    def config(self):
        return self.store.config

    def register_window(self, window) -> None:
        if self.app is None:
            self._early.append(window)
        else:
            self.app.add_window(window)

    def sync_monitors(self) -> None:
        connected = monitors_by_name()
        wanted = plan.desired_shells(self.config, connected)
        desired = {name: connected[name] for name in wanted}
        active = {name: shell.monitor for name, shell in self.shells.items()}
        close, open_ = plan.reconcile(active, desired)
        for name in close:
            log.info("closing Edge Shell on %s", name)
            self.shells.pop(name).close()
        for name in open_:
            log.info("opening Edge Shell on %s", name)
            self.shells[name] = MonitorShell(name, desired[name], self.config, self.register_window)
        if close or open_:
            self.refresh_css()

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
        result = self.store.reload()
        if result is None:
            if self.store.last_error:
                self._report_error(self.store.last_error)
            return
        old, new = result
        changes = diff_configs(old, new)
        log.info("config reloaded: %d change(s)", len(changes))
        rebuild = {c.monitor for c in changes if c.kind == "rebuild-monitor"}
        for name in rebuild & set(self.shells):
            self.shells.pop(name).close()
        self.sync_monitors()  # opens rebuilt/new monitors with the new config
        grouped: dict[str, list] = defaultdict(list)
        for change in changes:
            if change.monitor not in rebuild:
                grouped[change.monitor].append(change)
        for name, items in grouped.items():
            if name in self.shells:
                self.shells[name].apply(new, items)
        self.refresh_css()

    def _report_error(self, message: str) -> None:
        log.error("config not applied (keeping the previous config):\n%s", message)
        try:
            subprocess.Popen(
                ["notify-send", "-a", "Edge Shell", "Config not applied", message[:400]]
            )
        except OSError:
            pass  # no notify-send; the log line above is enough

    def run(self) -> None:
        self.sync_monitors()
        self.app = Application("edge-shell", *self._early)
        self._early.clear()
        self.app.set_stylesheet_from_string(self.css(), compile=False)
        self.app.hold()  # stay alive even with no windows (e.g. all monitors set to plasma)
        self.start_watching()
        signal.signal(signal.SIGINT, signal.SIG_DFL)  # Ctrl+C quits
        self.app.run()
