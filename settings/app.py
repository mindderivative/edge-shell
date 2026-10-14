"""The settings window's own process: a single-instance Gtk.Application per config file (a
second `main.py --settings` on the same file brings the open window forward), separate from the
running shell, which only ever sees the config file change."""

from __future__ import annotations

import hashlib
import logging
import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

from shell.config.loader import DEFAULT_PATH
from shell.outputs import Output, parse_kscreen, read_kscreen_json

log = logging.getLogger(__name__)

APP_ID = "org.edgeshell.Settings"
TOMLKIT_HINT = "the settings window needs tomlkit: scripts/py -m pip install 'tomlkit>=0.15'"


def app_id(path: Path) -> str:
    """One window per config file: the id carries a hash of the resolved path, so a second
    launch on the same file (also through a symlink) raises the open window, and a launch on
    another file (`--config /tmp/x.toml`) opens its own instead of silently showing the first."""
    digest = hashlib.sha1(str(path.resolve()).encode(), usedforsecurity=False).hexdigest()
    return f"{APP_ID}.c{digest[:12]}"


def connected_outputs() -> list[Output]:
    """Connected monitors (names and sizes) from kscreen-doctor; [] when it fails (the window
    then lists only the configured monitors and shows no layout preview)."""
    try:
        return parse_kscreen(read_kscreen_json())
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        log.warning("kscreen-doctor failed, showing configured monitors only: %s", exc)
        return []


class SettingsApp(Gtk.Application):
    def __init__(self, path: Path, default_path: Path = DEFAULT_PATH):
        super().__init__(application_id=app_id(path))
        self.path = path
        self.default_path = default_path
        self.window = None
        self.failed = False  # the config file could not be read: no window, exit code 2
        self._watcher = None

    def do_activate(self) -> None:
        if self.window is None:
            from settings.session import SettingsSession
            from settings.window import SettingsWindow
            from shell.config.models import ConfigError
            from shell.config.watcher import ConfigWatcher

            try:
                session = SettingsSession(self.path, self.default_path)
            except ConfigError as exc:  # unreadable (not invalid: that opens read-only)
                print(f"cannot open the settings: {exc}", file=sys.stderr)
                self.failed = True
                return  # no window and no hold: run() returns
            self.window = SettingsWindow(session, connected_outputs(), application=self)
            self.set_accels_for_action("win.undo", ["<Control>z"])
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._watcher = ConfigWatcher(self.path, self.window.file_changed)
        self.window.present()


def run_settings(path: Path, default_path: Path = DEFAULT_PATH) -> int:
    """Open the settings window on `path` (the shell's config file); returns the exit code.
    The application registers first: a second launch on the same file only asks the first
    one to come forward and exits, without importing the widgets (Fabric) at all."""
    try:
        import tomlkit  # noqa: F401
    except ImportError:
        print(TOMLKIT_HINT, file=sys.stderr)
        return 2
    app = SettingsApp(path, default_path)
    try:
        app.register(None)
    except GLib.Error as exc:  # no session bus
        print(f"cannot open the settings: {exc.message}", file=sys.stderr)
        return 2
    if not app.get_is_remote():
        import widgets  # noqa: F401  (registers the built-in panels: names and defaults)
    code = app.run([sys.argv[0]])
    return 2 if app.failed else code
