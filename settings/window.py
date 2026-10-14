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
        self.connect("delete-event", lambda *_a: self.view.flush() or False)
        self.view.show_all()

    def file_changed(self) -> None:
        self.view.file_changed()
