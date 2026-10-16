"""The per-screen toolbar (panel/widget spec 7): the selected screen's name; the checkboxes
**Enable** (Edge Shell on this screen) and the native desktop (labelled with its name: KDE
Plasma, Hyprland, ...), written together to the monitor's `shell` key (settings.screens); a
one-line note that Edge Shell does not hide or show Plasma's panel yet; Move up, Move down and
Remove for the panel page shown (the selected tree row has the same three); and the panel type list
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
from settings.tree import PANEL_ACTIONS

NO_SCREEN = "No screen selected"


class ScreenToolbar(Gtk.Box):
    def __init__(
        self,
        choices: tuple[AddChoice, ...],
        native_label: str,
        on_mode: Callable[[str, str], None],
        on_add: Callable[[str, AddChoice], None],
        on_panel: Callable[[str], None] | None = None,
    ):
        """`on_mode(screen, shell_value)`: a checkbox was toggled by the user.
        `on_add(screen, choice)`: Add was pressed with an enabled panel type chosen.
        `on_panel(action)`: Move up, Move down or Remove ("up", "down", "remove") was pressed
        while a panel page is shown (the view acts on that panel)."""
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.set_property("margin", 6)
        self._on_mode = on_mode
        self._on_add = on_add
        self._on_panel = on_panel or (lambda _action: None)
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
        # the same three as the selected tree row's buttons, for the panel page shown
        self.panel_buttons: dict[str, Gtk.Button] = {}
        for action, icon, tip, name in reversed(PANEL_ACTIONS):
            button = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
            button.set_tooltip_text(tip)
            button.get_accessible().set_name(name)
            button.set_focus_on_click(False)
            button.connect("clicked", lambda _b, a=action: self._on_panel(a))
            line.pack_end(button, False, False, 0)
            self.panel_buttons[action] = button
        self.note = Gtk.Label(label=SHELL_NOTE, xalign=0, wrap=True)
        self.note.get_style_context().add_class("dim-label")
        self.pack_start(line, False, False, 0)
        self.pack_start(self.note, False, False, 0)
        self.show_screen(None)

    def show_screen(
        self,
        screen: str | None,
        title: str = "",
        mode: str = "plasma",
        panel: tuple[int, int] | None = None,
    ) -> None:
        """Show `screen` (its tree title, its `shell` value in effect), or no screen. `panel`:
        (index, count) when a panel page of that screen is shown: Move up, Move down and
        Remove then act on it (the first cannot move up, the last not down); else they are
        insensitive."""
        index, count = panel if panel is not None else (-1, 0)
        self.panel_buttons["up"].set_sensitive(index > 0)
        self.panel_buttons["down"].set_sensitive(0 <= index < count - 1)
        self.panel_buttons["remove"].set_sensitive(index >= 0)
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
