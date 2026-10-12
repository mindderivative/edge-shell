"""Application wiring: config -> monitors -> windows."""

from __future__ import annotations

import logging
import signal

import gi

gi.require_version("Gtk", "3.0")
from fabric import Application

from shell import plan
from shell.config.store import ConfigStore
from shell.monitors import MonitorShell, monitors_by_name
from shell.theme import scope_class, to_css

log = logging.getLogger(__name__)


class EdgeShellApp:
    def __init__(self, store: ConfigStore):
        self.store = store
        self.app: Application | None = None
        self.shells: dict[str, MonitorShell] = {}
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

    def run(self) -> None:
        self.sync_monitors()
        self.app = Application("edge-shell", *self._early)
        self._early.clear()
        self.app.set_stylesheet_from_string(self.css(), compile=False)
        self.app.hold()  # stay alive even with no windows (e.g. all monitors set to plasma)
        signal.signal(signal.SIGINT, signal.SIG_DFL)  # Ctrl+C quits
        self.app.run()
