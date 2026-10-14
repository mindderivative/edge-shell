"""The settings toplevel: a normal xdg window (never a layer surface; KWin places it, usually
on the monitor with the pointer) holding a SettingsView, plus the Ctrl+Z undo action."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, Gtk

from settings.session import SettingsSession
from settings.view import SettingsView
from shell.outputs import Output

TITLE = "Edge Shell settings"


class SettingsWindow(Gtk.ApplicationWindow):
    def __init__(self, session: SettingsSession, outputs: list[Output], application=None):
        super().__init__(application=application, title=TITLE)
        self.set_default_size(860, 680)
        self.view = SettingsView(session, outputs)
        self.add(self.view)
        undo = Gio.SimpleAction.new("undo", None)  # Ctrl+Z (SettingsApp sets the accel)
        undo.connect("activate", lambda *_a: self.view.undo())
        self.add_action(undo)
        # closing applies what is still pending (a spin inside its pause, a typed font list)
        # a value that could not be written (or a hand edit met while applying) keeps the
        # window open once, so its error is seen
        self._close_warned = False
        self.connect("delete-event", self._on_delete)
        self.view.show_all()

    def _on_delete(self, *_args) -> bool:
        self.view.flush()
        if (self.view.save_failed or self.view.refused_outside) and not self._close_warned:
            self._close_warned = True
            return True  # stay open; closing again closes anyway
        return False

    def file_changed(self) -> None:
        self.view.file_changed()
