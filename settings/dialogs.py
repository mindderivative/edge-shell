"""The settings window's dialogs, behind one small seam: the window and the view get a `Dialogs`
object and never build a dialog themselves, so tests pass a fake and no dialog ever runs
there. `GtkDialogs` is the real one: native file choosers (Gtk.FileChooserNative: KDE's own
dialog through the desktop portal, main.py sets GTK_USE_PORTAL=1 for the settings process) and
modal message dialogs. Each method runs its dialog to the end and returns the answer."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from settings.fileops import Answer, unsaved_question

TOML_FILTERS = (("TOML files", "*.toml"), ("All files", "*"))


class Dialogs(Protocol):
    def ask_unsaved(self, parent: Any, path: Path) -> Answer: ...

    def confirm_revert(self, parent: Any, text: str) -> bool: ...

    def choose_new(self, parent: Any, folder: Path, name: str) -> Path | None: ...

    def choose_open(self, parent: Any, folder: Path) -> Path | None: ...

    def choose_save_as(self, parent: Any, folder: Path, name: str) -> Path | None: ...


def _window(parent: Any) -> Gtk.Window | None:
    return parent if isinstance(parent, Gtk.Window) else None


class GtkDialogs:
    def ask_unsaved(self, parent: Any, path: Path) -> Answer:
        primary, secondary = unsaved_question(path)
        dialog = Gtk.MessageDialog(
            transient_for=_window(parent),
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text=primary,
        )
        dialog.format_secondary_text(secondary)
        dialog.add_buttons(
            "_Cancel",
            Gtk.ResponseType.CANCEL,
            "_Discard",
            Gtk.ResponseType.REJECT,
            "_Save",
            Gtk.ResponseType.ACCEPT,
        )
        discard = dialog.get_widget_for_response(Gtk.ResponseType.REJECT)
        discard.get_style_context().add_class("destructive-action")
        dialog.set_default_response(Gtk.ResponseType.ACCEPT)
        response = dialog.run()
        dialog.destroy()
        answers = {Gtk.ResponseType.ACCEPT: Answer.SAVE, Gtk.ResponseType.REJECT: Answer.DISCARD}
        return answers.get(response, Answer.CANCEL)  # Escape or the close button: Cancel

    def confirm_revert(self, parent: Any, text: str) -> bool:
        dialog = Gtk.MessageDialog(
            transient_for=_window(parent),
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text="Revert every change made in this window?",
        )
        dialog.format_secondary_text(text)
        answer = dialog.run()
        dialog.destroy()
        return answer == Gtk.ResponseType.OK

    def choose_new(self, parent: Any, folder: Path, name: str) -> Path | None:
        # no overwrite question: New never replaces a file (the window refuses an existing one)
        return self._choose(
            parent,
            "New config file",
            Gtk.FileChooserAction.SAVE,
            "_Create",
            folder,
            name,
            overwrite=False,
        )

    def choose_open(self, parent: Any, folder: Path) -> Path | None:
        return self._choose(
            parent,
            "Open a config file",
            Gtk.FileChooserAction.OPEN,
            "_Open",
            folder,
            None,
            overwrite=False,
        )

    def choose_save_as(self, parent: Any, folder: Path, name: str) -> Path | None:
        return self._choose(
            parent,
            "Save the config as",
            Gtk.FileChooserAction.SAVE,
            "_Save",
            folder,
            name,
            overwrite=True,
        )

    @staticmethod
    def _choose(parent, title, action, accept, folder, name, overwrite) -> Path | None:
        chooser = Gtk.FileChooserNative.new(title, _window(parent), action, accept, "_Cancel")
        chooser.set_modal(True)
        if folder.is_dir():
            chooser.set_current_folder(str(folder))
        if name is not None:
            chooser.set_current_name(name)
        if action == Gtk.FileChooserAction.SAVE:
            chooser.set_do_overwrite_confirmation(overwrite)
        for label, pattern in TOML_FILTERS:
            choice = Gtk.FileFilter()
            choice.set_name(label)
            choice.add_pattern(pattern)
            chooser.add_filter(choice)
        try:
            response = chooser.run()
            filename = chooser.get_filename()
        finally:
            chooser.destroy()
        if response != Gtk.ResponseType.ACCEPT or not filename:
            return None  # cancelled, or a file that is not local (the portal gave a URI)
        return Path(filename)
