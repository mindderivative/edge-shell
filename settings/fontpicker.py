"""A searchable font dropdown (Phil: "list system available fonts in a dropdown that is
searchable by typing. Default should be the system selected font"): a button showing the font,
opening a popover with a search entry above the list of families (settings.fonts). Typing
filters the list (any part of the name, without case); Enter picks the first row shown; a click
picks a row. The list is a GTK popover, drawn inside the settings window, sized to its rows up
to POPUP_HEIGHT (then it scrolls): it is not a compositor popup, so it opens at its size.

The installed families are read once per process, when a list is first opened
(installed_families, cached); tests pass their own list. Values shown with set() never call
back."""

from __future__ import annotations

import functools
from collections.abc import Callable, Sequence

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
try:
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import PangoCairo
except (ValueError, ImportError):  # no PangoCairo typelib: the list holds no installed family
    PangoCairo = None
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from settings.fonts import (  # noqa: E402
    Entry,
    first_match,
    font_families,
    matches,
    picker_entries,
    system_font,
)

POPUP_HEIGHT = 360  # px: the most the list takes before it scrolls
POPUP_WIDTH = 280
FONT_CHARS = 22  # the button's label; a longer name is cut, the whole name is the tooltip


@functools.cache
def installed_families() -> tuple[str, ...]:
    """Every installed font family (Pango's font map), as settings.fonts.font_families lists
    them. Read once: a font installed while the window is open shows after a restart."""
    if PangoCairo is None:
        return ()
    return font_families(f.get_name() for f in PangoCairo.FontMap.get_default().list_families())


def family_of(font_name: str) -> str:
    """The family of a Pango font name: "Noto Sans Bold 10" -> "Noto Sans"."""
    return Pango.FontDescription.from_string(font_name).get_family() or ""


def system_family() -> str:
    """The desktop's font family (Gtk.Settings gtk-font-name, which KDE sets to its General
    font); "" when unknown, or a name the config could not hold or a list of families. Cleaned
    like the installed families (settings.fonts.system_font): "Sans" is "sans-serif"."""
    settings = Gtk.Settings.get_default()
    name = settings.props.gtk_font_name if settings is not None else None
    return system_font(family_of(name)) if name else ""


class FontPicker:
    """`on_pick(value)` runs when the user picks a row whose value is not the one shown: a
    family name, or None for the inherited row (`inherit_label`, e.g. "Theme font"). `button`
    is the widget to pack. `families` and `system` (None: installed_families and
    system_family, looked up when the list opens, so tests can replace them) give the list."""

    def __init__(
        self,
        on_pick: Callable[[str | None], None],
        families: Callable[[], Sequence[str]] | None = None,
        system: Callable[[], str] | None = None,
        inherit_label: str | None = None,
    ):
        self._on_pick = on_pick
        self._families = families
        self._system = system
        self.inherit_label = inherit_label
        self.value: str | None = None
        self.entries: tuple[Entry, ...] = ()
        self._scroll_handler = 0  # the list's size-allocate handler while a scroll waits for it
        self._scroll_idle = 0  # the pending idle source of that scroll
        self._destroyed = False
        self._built: tuple[str | None, tuple[Entry, ...]] | None = None
        self.label = Gtk.Label(xalign=0)
        self.label.set_ellipsize(Pango.EllipsizeMode.END)
        self.label.set_max_width_chars(FONT_CHARS)
        self.label.set_width_chars(FONT_CHARS)
        face = Gtk.Box(spacing=4)
        face.pack_start(self.label, True, True, 0)
        face.pack_start(
            Gtk.Image.new_from_icon_name("pan-down-symbolic", Gtk.IconSize.BUTTON), False, False, 0
        )
        self.button = Gtk.MenuButton()
        self.button.add(face)
        self.search = Gtk.Entry(placeholder_text="Type to search")
        self.search.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "edit-find-symbolic")
        self.list = Gtk.ListBox(activate_on_single_click=True)
        self.list.set_filter_func(self._shown)
        self.scroller = scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_propagate_natural_height(True)  # the popover fits its rows ...
        scroller.set_max_content_height(POPUP_HEIGHT)  # ... up to this height
        scroller.set_min_content_width(POPUP_WIDTH)
        scroller.add(self.list)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_property("margin", 6)
        box.pack_start(self.search, False, False, 0)
        box.pack_start(scroller, True, True, 0)
        box.show_all()
        self.popover = Gtk.Popover(relative_to=self.button)
        self.popover.add(box)
        self.button.set_popover(self.popover)
        self._handlers: list[tuple[Gtk.Widget, int]] = []
        self._connect(self.button, "toggled", self._toggled)
        self._connect(self.button, "destroy", lambda _b: self._destroyed_now())
        self._connect(self.search, "changed", lambda _e: self.list.invalidate_filter())
        self._connect(self.search, "activate", self._pick_first)
        self._connect(
            self.list, "row-activated", lambda _l, row: self._pick(self.entries[row.get_index()])
        )

    def _connect(self, widget: Gtk.Widget, signal: str, handler: Callable) -> None:
        self._handlers.append((widget, widget.connect(signal, handler)))

    def release(self) -> None:
        """The picker is retired (its row was discarded by a rebuild). Its widgets keep
        handlers that close over the picker, and GTK holds the list's filter function (a
        bound method of the picker) in C, where Python's collector cannot see it: left as
        they are, the picker and all its widgets stay alive for the life of the window."""
        self._destroyed_now()  # what its "destroy" handler does, as that is disconnected below
        for widget, handler in self._handlers:
            widget.disconnect(handler)
        self._handlers.clear()
        self.list.set_filter_func(None)

    def set(self, value: str | None) -> None:
        """Show `value` (None: the inherited row's label)."""
        self.value = value
        text = value if value is not None else (self.inherit_label or "")
        self.label.set_text(text)
        self.button.set_tooltip_text(text or None)

    def _toggled(self, button: Gtk.MenuButton) -> None:
        if button.get_active():
            self.fill()

    def fill(self) -> None:
        """Open the list: clear the search, select the shown row and scroll to it (the button
        runs this when the list opens). The rows are rebuilt only when the value or the family
        list changed since they were built (2000 families take ~160 ms to build)."""
        families = (self._families or installed_families)()
        system = (self._system or system_family)()
        entries = picker_entries(families, system, self.value, self.inherit_label)
        if self._built != (self.value, entries):
            self._built = (self.value, entries)
            self.entries = entries
            for row in self.list.get_children():
                self.list.remove(row)
            for _value, label in self.entries:
                self.list.add(Gtk.Label(label=label, xalign=0))
            self.list.show_all()
        self.search.set_text("")
        shown = next((i for i, e in enumerate(self.entries) if self._is_shown(e[0])), None)
        if shown is not None:
            self.list.select_row(self.list.get_row_at_index(shown))
            self._scroll_when_allocated()
        self.search.grab_focus()

    def _is_shown(self, value: str | None) -> bool:
        """Is `value` the row of the value shown? Without case, as "not installed" is decided
        (a configured "noto sans" selects the installed "Noto Sans"; the config keeps its
        spelling until the user picks)."""
        if value is None or self.value is None:
            return value is self.value
        return value.casefold() == self.value.casefold()

    def _scroll_when_allocated(self) -> None:
        """Scroll to the selected row once the list has its size. On Wayland the popover gets
        its first allocation after the button's toggled signal, so a bare idle callback can run
        before it (the list stayed at the top on a first opening): wait for the list's own
        size-allocate, scroll once, and stop listening. An open (allocated) list scrolls at
        once."""
        self._cancel_scroll()
        if self.list.get_mapped():
            self._scroll_idle = GLib.idle_add(self._scroll_to_selected)
        else:
            self._scroll_handler = self.list.connect("size-allocate", self._allocated)

    def _allocated(self, _list: Gtk.ListBox, _allocation) -> None:
        if self._scroll_handler:
            self.list.disconnect(self._scroll_handler)  # once: later allocations do not scroll
            self._scroll_handler = 0
        # after this allocation pass: the viewport has its adjustment values by then
        self._scroll_idle = GLib.idle_add(self._scroll_to_selected)

    def _destroyed_now(self) -> None:
        self._destroyed = True
        self._cancel_scroll()

    def _cancel_scroll(self) -> None:
        """Forget a scroll that has not happened (the list was opened again, or the button is
        destroyed: nothing may run on freed widgets)."""
        if self._scroll_handler:
            if self.list.handler_is_connected(self._scroll_handler):
                self.list.disconnect(self._scroll_handler)
            self._scroll_handler = 0
        if self._scroll_idle:
            GLib.source_remove(self._scroll_idle)
            self._scroll_idle = 0

    def _scroll_to_selected(self) -> bool:
        """Put the selected row in the middle of the list's view; False: run once."""
        self._scroll_idle = 0
        if self._destroyed:
            return False
        row = self.list.get_selected_row()
        if row is not None:
            area = row.get_allocation()
            adjustment = self.scroller.get_vadjustment()
            middle = area.y + area.height / 2 - adjustment.get_page_size() / 2
            top = max(adjustment.get_upper() - adjustment.get_page_size(), 0)
            adjustment.set_value(min(max(middle, 0), top))
        return False

    def visible_labels(self) -> list[str]:
        """The labels of the rows the search leaves shown (tests, and the reviewer's eye)."""
        return [label for _v, label in self.entries if matches(label, self.search.get_text())]

    def _shown(self, row: Gtk.ListBoxRow) -> bool:
        return matches(self.entries[row.get_index()][1], self.search.get_text())

    def _pick_first(self, _entry: Gtk.Entry) -> None:
        entry = first_match(self.entries, self.search.get_text())
        if entry is not None:
            self._pick(entry)

    def _pick(self, entry: Entry) -> None:
        self.popover.popdown()
        value = entry[0]
        if value != self.value:
            self.set(value)
            self._on_pick(value)
