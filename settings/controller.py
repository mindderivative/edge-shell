"""The settings window's content: the menu bar and the SettingsView, with the window's actions
(the "win" group the menu items and the shortcuts use). A plain Gtk.Box, so it is tested
without creating a window; settings.window puts it in the toplevel. Every dialog goes through
`dialogs` (settings.dialogs), so tests answer with a fake and no dialog runs."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, Gtk

from settings.dialogs import Dialogs
from settings.fileops import leave
from settings.menubar import build_menubar
from settings.menus import ACTIONS, enabled, menu_state
from settings.session import ChangedOutside, SettingsSession
from settings.view import SettingsView
from shell.config.models import ConfigError
from shell.outputs import Output


class SettingsController(Gtk.Box):
    def __init__(
        self,
        path: Path,
        session: SettingsSession,
        outputs: list[Output],
        dialogs: Dialogs,
        quit: Callable[[], None] | None = None,
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.path = path  # the window's file (its application id is made from it)
        self.outputs = list(outputs)
        self.dialogs = dialogs
        self.quit = quit or (lambda: None)  # closes the window (File > Exit)
        self.session: SettingsSession | None = None
        self.view: SettingsView | None = None
        self._clipboard: dict[str, bool] | None = None
        # leaving after a flush that could not write (or met a hand edit) stays once, so the
        # error is seen; asked again, it goes on
        self._leave_warned = False
        self.handlers: dict[str, Callable[[], None]] = {
            "save": self.save,
            "exit": self.exit,
            "undo": self.undo,
            "redo": self.redo,
            "revert": self.revert,
        }
        self.actions = Gio.SimpleActionGroup()
        for name in ACTIONS:
            if name in self.handlers:
                action = Gio.SimpleAction.new(name, None)
                action.connect("activate", lambda _a, _p, n=name: self.handlers[n]())
                self.actions.add_action(action)
        self.insert_action_group("win", self.actions)
        self.menubar, self.menus = build_menubar()
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.pack_start(self.menubar, False, False, 0)
        self.pack_start(self.body, True, True, 0)
        self.open_session(session)

    def open_session(self, session: SettingsSession) -> None:
        self.session = session
        self._leave_warned = False
        self.view = SettingsView(
            session, self.outputs, confirm_revert=self.dialogs.confirm_revert, on_state=self.sync
        )
        self.body.pack_start(self.view, True, True, 0)
        self.view.show_all()
        self.sync()

    def sync(self) -> None:
        """Every action's enabled state from the session (after each write, undo, revert,
        save or re-read; the view calls it after every refresh and rebuild)."""
        for name, ok in enabled(menu_state(self.session, self._clipboard)).items():
            action = self.actions.lookup_action(name)
            if action is not None:
                action.set_enabled(ok)

    # ---- File ------------------------------------------------------------------------------
    def save(self) -> None:
        if self.view is not None:
            self.view.save()
        self.sync()

    def exit(self) -> None:
        if self.can_leave():
            self.quit()

    def can_leave(self) -> bool:
        """May the window leave its config (Exit, the close button)? Pending values are
        applied first; a flush that could not write, or met a hand edit, stays once (its
        message is on screen). With changes since the last save, asks Save / Discard /
        Cancel; a save or discard that fails is shown and stays."""
        if self.view is None:
            return True
        self.view.flush()
        if (self.view.save_failed or self.view.refused_outside) and not self._leave_warned:
            self._leave_warned = True
            return False
        session = self.session
        try:
            return leave(
                session, lambda: self.dialogs.ask_unsaved(self.get_toplevel(), session.path)
            )
        except ChangedOutside as exc:
            self.view.rebuild()
            self.view.show_banner(str(exc), Gtk.MessageType.WARNING)
            return False
        except ConfigError as exc:
            self.view.show_banner(f"Not saved: {exc}")
            return False
        finally:
            self.sync()

    # ---- Edit ------------------------------------------------------------------------------
    def undo(self) -> None:
        if self.view is not None:
            self.view.undo()

    def redo(self) -> None:
        if self.view is not None:
            self.view.redo()

    def revert(self) -> None:
        if self.view is not None:
            self.view.confirm_revert()

    # ---- the file on disk ------------------------------------------------------------------
    def file_changed(self) -> None:
        if self.view is not None:
            self.view.file_changed()
