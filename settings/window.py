"""The settings toplevel: a normal xdg window (never a layer surface; KWin places it, usually
on the monitor with the pointer) holding a SettingsController (menu bar, actions, view). Its
close button is File > Exit: pending values are applied, and with changes since the last save
it asks Save / Discard / Cancel."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from settings.controller import SettingsController
from settings.dialogs import Dialogs, GtkDialogs
from settings.session import SettingsSession
from shell.outputs import Output

TITLE = "Edge Shell settings"


class SettingsWindow(Gtk.ApplicationWindow):
    def __init__(
        self,
        session: SettingsSession,
        outputs: list[Output],
        application=None,
        dialogs: Dialogs | None = None,
    ):
        super().__init__(application=application, title=TITLE)
        self.set_default_size(860, 680)
        self.controller = SettingsController(
            session.path, session, outputs, dialogs or GtkDialogs(), quit=self.destroy
        )
        self.add(self.controller)
        # the shortcuts are application accelerators for "win.<action>"; the toplevel finds the
        # group from the focused widget up, so with nothing focused it must have it itself
        self.insert_action_group("win", self.controller.actions)
        self.connect("delete-event", self._on_delete)
        # Cut, Copy and Paste follow the focused widget (after the default handler: the new
        # focus is set by then)
        self.connect_after("set-focus", lambda *_a: self.controller.sync_clipboard())
        self.controller.show_all()

    @property
    def view(self):
        return self.controller.view

    def _on_delete(self, *_args) -> bool:
        return not self.controller.can_leave()  # True: stay open

    def file_changed(self) -> None:
        self.controller.file_changed()
