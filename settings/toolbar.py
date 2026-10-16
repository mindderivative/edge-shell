"""The per-screen toolbar (panel/widget spec 7): the selected screen's name; the checkboxes
**Enable** (Edge Shell on this screen) and the native desktop (labelled with its name: KDE
Plasma, Hyprland, ...), written together to the monitor's `shell` key (settings.screens); a
one-line note that Edge Shell does not hide or show Plasma's panel yet; and the panel type list
(each widget by display name and panel kind, float listed and greyed out) with **Add**.

It shows the screen of the selected page: a monitor page's, or a panel page's monitor. On the
Theme page, or while the file is invalid, it names no screen and is insensitive. Values shown
with show_screen never call back. A plain Gtk.Box: tested without a window."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

from settings.fields import ChoiceEditor
from settings.form import MODE_HINTS, AddChoice
from settings.screens import SHELL_NOTE, mode_flags, mode_of

NO_SCREEN = "No screen selected"


class ScreenToolbar(Gtk.Box):
    def __init__(
        self,
        choices: tuple[AddChoice, ...],
        native_label: str,
        on_mode: Callable[[str, str], None],
        on_add: Callable[[str, AddChoice], None],
    ):
        """`on_mode(screen, shell_value)`: a checkbox was toggled by the user.
        `on_add(screen, choice)`: Add was pressed with an enabled panel type chosen."""
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.set_property("margin", 6)
        self._on_mode = on_mode
        self._on_add = on_add
        self._quiet = False
        self.screen: str | None = None
        self.choices = {c.id: c for c in choices}
        line = Gtk.Box(spacing=12)
        self.title = Gtk.Label(xalign=0)
        self.edge = Gtk.CheckButton(label="Enable")
        self.edge.set_tooltip_text("Edge Shell's frame and panels on this screen")
        self.native = Gtk.CheckButton(label=native_label)
        self.native.set_tooltip_text(f"{native_label} on this screen")
        for check in (self.edge, self.native):
            check.connect("toggled", self._toggled)
        disabled = tuple(c.id for c in choices if not c.enabled)
        self.kind = ChoiceEditor(
            tuple(self.choices),
            lambda chosen: self.kind.set(chosen),  # a greyed-out pick comes back to this one
            tuple(c.label for c in choices),
            disabled,
        )
        self.kind.widget.set_tooltip_text("The panel type to add to this screen")
        self.kind.set(next(c.id for c in choices if c.enabled))
        self.add_button = Gtk.Button(label="Add")
        self.add_button.set_tooltip_text("Add a panel of this type to this screen")
        self.add_button.set_focus_on_click(False)
        self.add_button.connect("clicked", lambda _b: self._add())
        line.pack_start(self.title, False, False, 0)
        line.pack_start(self.edge, False, False, 0)
        line.pack_start(self.native, False, False, 0)
        line.pack_end(self.add_button, False, False, 0)
        line.pack_end(self.kind.widget, False, False, 0)
        self.note = Gtk.Label(label=SHELL_NOTE, xalign=0, wrap=True)
        self.note.get_style_context().add_class("dim-label")
        self.pack_start(line, False, False, 0)
        self.pack_start(self.note, False, False, 0)
        self.show_screen(None)

    def show_screen(self, screen: str | None, title: str = "", mode: str = "plasma") -> None:
        """Show `screen` (its tree title, its `shell` value in effect), or no screen."""
        self.screen = screen
        self._quiet = True
        try:
            edge, native = mode_flags(mode) if screen is not None else (False, False)
            self.edge.set_active(edge)
            self.native.set_active(native)
        finally:
            self._quiet = False
        text = NO_SCREEN if screen is None else title or screen
        self.title.set_markup(f"<b>{GLib.markup_escape_text(text)}</b>")
        hint = None if screen is None else f'shell = "{mode}": {MODE_HINTS[mode]}'
        self.title.set_tooltip_text(hint)
        for widget in (self.edge, self.native, self.kind.widget, self.add_button):
            widget.set_sensitive(screen is not None)

    def chosen(self) -> AddChoice | None:
        return self.choices.get(self.kind.widget.get_active_id())

    def _toggled(self, _check) -> None:
        if self._quiet or self.screen is None:
            return
        self._on_mode(self.screen, mode_of(self.edge.get_active(), self.native.get_active()))

    def _add(self) -> None:
        choice = self.chosen()
        if self.screen is not None and choice is not None and choice.enabled:
            self._on_add(self.screen, choice)
