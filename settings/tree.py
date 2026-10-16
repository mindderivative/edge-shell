"""The settings window's left column (panel/widget spec 7): a Detect monitors button above a
tree of Theme, one expandable row per monitor and, under it, its panels by name. Selecting a
row asks for its page (`on_select(page)`); the view shows it. The selected panel row shows
three small buttons at its right edge, Move up, Move down and Remove (`on_action(page,
action)`; Phil, 2026-10-15: "on the tree to the right of the tree item label"); the toolbar has
the same three.

A Gtk.ListBox of rows, not a Gtk.TreeView: a tree view's cells cannot hold buttons (a clickable
icon renderer needs the pointer position, which tests cannot give without a window), while
real buttons in a list row are focusable, have tooltips and are clicked in tests. A monitor's
panels are rows below it, indented, hidden while it is collapsed. Keyboard: Up/Down move (and
select), Left collapses a monitor or goes from a panel to its monitor, Right (or +) expands,
- collapses, Tab reaches the selected row's buttons. A plain Gtk.Box: tested without a window.

The rows are set with show(entries) after every rebuild of the pages. When the pages are the
same as before (a rename, a refresh), only the titles change, so the selection and the
expansion stay as they are; otherwise the rows are made again and a monitor the user collapsed
stays collapsed (by its page name)."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango

from settings.pages import TreeEntry

MIN_WIDTH = 200
NO_MONITORS = "No monitor found. Connect one and press Detect monitors."
# (action, icon, tooltip) of the buttons of a selected panel row (and of the toolbar)
PANEL_ACTIONS = (
    ("up", "go-up-symbolic", "Move this panel up"),
    ("down", "go-down-symbolic", "Move this panel down"),
    ("remove", "list-remove-symbolic", "Remove this panel"),
)
_OPEN, _CLOSED = "pan-down-symbolic", "pan-end-symbolic"


class TreeRow(Gtk.ListBoxRow):
    """One row: Theme, a monitor (with an expander arrow when it has panels) or a panel."""

    def __init__(self, page: str, title: str, parent: str | None, on_action, on_arrow):
        super().__init__()
        self.page, self.parent_page = page, parent
        self.children: list[TreeRow] = []
        box = Gtk.Box(spacing=4)
        box.set_margin_start(24 if parent else 0)
        self.arrow: Gtk.Button | None = None
        if parent is None:
            self.arrow = Gtk.Button.new_from_icon_name(_OPEN, Gtk.IconSize.MENU)
            self.arrow.set_relief(Gtk.ReliefStyle.NONE)
            self.arrow.set_focus_on_click(False)
            self.arrow.set_tooltip_text("Show or hide its panels")
            self.arrow.connect("clicked", lambda _b: on_arrow(self))
            box.pack_start(self.arrow, False, False, 0)
        self.label = Gtk.Label(label=title, xalign=0)
        self.label.set_ellipsize(Pango.EllipsizeMode.END)  # a long name never widens the tree
        box.pack_start(self.label, True, True, 0)
        self.buttons: dict[str, Gtk.Button] = {}
        if parent is not None:
            for action, icon, tip in PANEL_ACTIONS:
                button = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.MENU)
                button.set_relief(Gtk.ReliefStyle.NONE)
                button.set_tooltip_text(tip)
                # a press must not move the focus: a name entry's focus-out would rebuild the
                # pages under the click
                button.set_focus_on_click(False)
                button.connect("clicked", lambda _b, a=action: on_action(self.page, a))
                box.pack_end(button, False, False, 0)
                self.buttons[action] = button
        self.add(box)
        self.show_all()
        for button in self.buttons.values():
            button.set_no_show_all(True)
            button.hide()  # shown on the selected row only
        self.set_no_show_all(True)  # the tree decides (a collapsed monitor's panels)

    @property
    def title(self) -> str:
        return self.label.get_text()


class SettingsTree(Gtk.Box):
    def __init__(
        self,
        on_select: Callable[[str], None],
        on_action: Callable[[str, str], None] | None = None,
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_size_request(MIN_WIDTH, -1)
        self._on_select = on_select
        self._on_action = on_action or (lambda _page, _action: None)
        self._quiet = False  # rows or the selection set by the program: no callbacks
        self._rows: list[TreeRow] = []  # parents before their children
        self.collapsed: set[str] = set()  # monitor pages the user collapsed
        self.detect_button = Gtk.Button(label="Detect monitors")
        self.detect_button.set_tooltip_text(
            "Look for connected monitors again (kscreen-doctor) and list them with the "
            "monitors in your config"
        )
        self.list = Gtk.ListBox()
        self.list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list.get_accessible().set_name("Settings pages")
        self.list.connect("row-selected", self._selected)
        self.list.connect("key-press-event", self._key)
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.add(self.list)
        self.hint = Gtk.Label(label=NO_MONITORS, xalign=0, wrap=True)
        self.hint.get_style_context().add_class("dim-label")
        self.hint.set_no_show_all(True)
        self.pack_start(self.detect_button, False, False, 0)
        self.pack_start(scroller, True, True, 0)
        self.pack_start(self.hint, False, False, 0)

    # ---- rows ------------------------------------------------------------------------------
    def show(self, entries: tuple[TreeEntry, ...]) -> None:
        """Show these rows (settings.pages.tree_entries)."""
        shape = [p for e in entries for p in (e.page, *(c.page for c in e.children))]
        self._quiet = True
        try:
            if shape == [r.page for r in self._rows]:
                titles = {e.page: e.title for e in entries}
                titles.update((c.page, c.title) for e in entries for c in e.children)
                for row in self._rows:
                    row.label.set_text(titles[row.page])
            else:
                self._fill(entries)
        finally:
            self._quiet = False
        self.hint.set_visible(len(entries) < 2)  # Theme alone: no monitor to show

    def _fill(self, entries: tuple[TreeEntry, ...]) -> None:
        retired, self._rows = self._rows, []
        for row in retired:
            self.list.remove(row)
        if retired:
            # destroyed when the loop is idle: show() runs inside a row button's "clicked"
            # (Remove, Move), which GTK finishes on that button afterwards
            GLib.idle_add(_destroy_all, retired)
        for entry in entries:
            parent = self._add(entry.page, entry.title, None)
            for i, child in enumerate(entry.children):
                row = self._add(child.page, child.title, entry.page)
                row.buttons["up"].set_sensitive(i > 0)
                row.buttons["down"].set_sensitive(i < len(entry.children) - 1)
                parent.children.append(row)
            self._expand(parent, entry.page not in self.collapsed)

    def _add(self, page: str, title: str, parent: str | None) -> TreeRow:
        row = TreeRow(page, title, parent, self._on_action, self._toggle)
        self.list.add(row)
        row.show()
        self._rows.append(row)
        return row

    def _expand(self, row: TreeRow, expanded: bool) -> None:
        if row.arrow is not None:
            row.arrow.set_visible(bool(row.children))
            icon = _OPEN if expanded else _CLOSED
            row.arrow.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU))
        for child in row.children:
            child.set_visible(expanded)
        if expanded:
            self.collapsed.discard(row.page)
        elif row.children:
            self.collapsed.add(row.page)

    def _toggle(self, row: TreeRow) -> None:
        """The arrow of a monitor row (or Left/Right on it)."""
        self._expand(row, row.page in self.collapsed)
        selected = self.list.get_selected_row()
        if selected is not None and not selected.get_visible():
            self.select(row.page)  # the selected panel was hidden: its monitor
            self._on_select(row.page)

    def rows(self) -> list[tuple[str, str]]:
        """(page, title) of every row, parents before their children (hidden ones too)."""
        return [(r.page, r.title) for r in self._rows]

    def row_of(self, page: str) -> TreeRow | None:
        return next((r for r in self._rows if r.page == page), None)

    def is_expanded(self, page: str) -> bool:
        row = self.row_of(page)
        return row is not None and bool(row.children) and page not in self.collapsed

    # ---- selection -------------------------------------------------------------------------
    def selected(self) -> str | None:
        row = self.list.get_selected_row()
        return None if row is None else row.page

    def select(self, page: str) -> bool:
        """Select the row of `page` (no callback); a panel's monitor is expanded to show it.
        False when there is no such row."""
        row = self.row_of(page)
        if row is None:
            return False
        self._quiet = True
        try:
            if row.parent_page is not None:
                self._expand(self.row_of(row.parent_page), True)
            self.list.select_row(row)
            self._show_buttons(row)
        finally:
            self._quiet = False
        return True

    def _selected(self, _list, row: TreeRow | None) -> None:
        self._show_buttons(row)
        if not self._quiet and row is not None:
            self._on_select(row.page)

    def _show_buttons(self, selected: TreeRow | None) -> None:
        for row in self._rows:
            for button in row.buttons.values():
                button.set_visible(row is selected)

    def _key(self, _list, event: Gdk.EventKey) -> bool:
        row = self.list.get_selected_row()
        if row is None:
            return False
        key = event.keyval
        if key in (Gdk.KEY_Left, Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
            if row.parent_page is not None:  # a panel: to its monitor
                self.select(row.parent_page)
                self._on_select(row.parent_page)
            elif row.page not in self.collapsed and row.children:
                self._toggle(row)
            return True
        if key in (Gdk.KEY_Right, Gdk.KEY_plus, Gdk.KEY_KP_Add):
            if row.children and row.page in self.collapsed:
                self._toggle(row)
            return True
        return False


def _destroy_all(rows: list[TreeRow]) -> bool:
    for row in rows:
        row.destroy()
    return GLib.SOURCE_REMOVE
