"""The settings window's content: a top bar (Undo, Revert all, the file path), a banner for
errors and notices, and beside the tree (settings.tree: Theme, the monitors) the page the tree
selects (panel/widget spec 7). The Theme page and each monitor page have tabs (General,
Borders, Shadows, Handle, Layout: settings.form.theme_tabs); a monitor page's values override
the Theme for that monitor, and it has a Panels tab with its shell mode and its panel list. A
plain Gtk.Box, so it is tested without creating a window; settings.window puts it in the
toplevel.

Every page is built at each rebuild (as before: every row exists, so flush() and refresh()
reach every row, on any page); the tree only chooses which one is shown, so switching pages
never drops a pending value. A rebuild keeps the shown page (by its name, settings.pages) and
each page's tab (by its title).

Every edit goes through SettingsSession.apply: a valid one is written to the user config and
the running shell reloads it; an invalid one is shown under its row and not written."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk

from settings.dialogs import GtkDialogs
from settings.document import UserDocument
from settings.fields import DEBOUNCE_MS, FieldRow
from settings.form import (
    MODE_HINTS,
    SectionSpec,
    TabSpec,
    config_form,
    registry_widgets,
    theme_tabs,
)
from settings.pages import THEME, fallback_page, monitor_page, parse_page, tree_entries
from settings.panels import PanelEditor
from settings.queue import RESET, EditQueue, QueuedEdit, describe, path_text
from settings.session import ChangedOutside, SettingsSession, check_text
from settings.tree import SettingsTree
from settings.values import field_value, layout_preview, lookup, panel_ops
from shell.config.models import ConfigError
from shell.outputs import Output
from shell.registry import requests_for

Edit = Callable[[UserDocument], Any]

# The once-only info note must not depend on the theme: GTK's own infobar colours turn the
# text orange in a focused window and white in an unfocused one. A blue background with light
# text, with the :backdrop (unfocused) state spelled out, reads the same either way.
INFO_NOTE_CLASS = "info-note"
INFO_NOTE_CSS = """
infobar.info-note,
infobar.info-note > revealer > box,
infobar.info-note:backdrop,
infobar.info-note:backdrop > revealer > box {
    background-color: #2b5c8a;
    background-image: none;
}
infobar.info-note label,
infobar.info-note:backdrop label {
    color: #ffffff;
}
"""
_info_note_provider: Gtk.CssProvider | None = None


def install_info_note_css() -> Gtk.CssProvider:
    """Add the info note's CSS to the screen (USER priority), once; later calls reuse it."""
    global _info_note_provider
    if _info_note_provider is None:
        provider = Gtk.CssProvider()
        provider.load_from_data(INFO_NOTE_CSS.encode())
        screen = Gdk.Screen.get_default()
        if screen is not None:
            Gtk.StyleContext.add_provider_for_screen(
                screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
            )
        _info_note_provider = provider
    return _info_note_provider


# shown in a panel's expander title (panel_title), or deciding its rows (widget: the kind
# and the Widget rows; panel: the kind's rows; corner: the edge choices): a change rebuilds
# the page and keeps that panel open
MAX_NAMED = 8  # the most dropped edits the banner names (then "... and N more")
TITLE_KEYS = ("name", "widget", "panel", "edge", "align", "corner", "width", "height")


class SettingsView(Gtk.Box):
    def __init__(
        self,
        session: SettingsSession,
        outputs: list[Output],
        confirm_revert: Callable[[Any, str], bool] | None = None,
        on_state: Callable[[], None] | None = None,
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.session = session
        # asks before Revert all (parent, text) -> OK?; tests pass a fake, no dialog runs
        self._ask_revert = confirm_revert or GtkDialogs().confirm_revert
        # called after every refresh and rebuild (each write, undo, revert or re-read): the
        # window updates its menu items and title
        self._on_state = on_state or (lambda: None)
        self.outputs = {o.name: o for o in outputs}
        self.form = config_form(registry_widgets())
        self.rows: list[FieldRow] = []
        # monitor -> the labels showing its layout warnings (its page; later its panels' pages)
        self.previews: dict[str, list[Gtk.Label]] = {}
        self._expand: dict[str, int] = {}  # monitor -> panel entry to show open after a rebuild
        self._tab_of: dict[str, str] = {}  # page -> the title of the tab last shown on it
        self.save_failed = False  # the last flush() could not write something (shown on screen)
        # the last flush() met a hand edit: that row and the rest were not applied (warning on
        # screen); the caller must not go on to a structural edit or an undo on the re-read file
        self.refused_outside = False
        self._flushing = False  # while True a rebuild is only noted: flush() does it at the end
        self._rebuild_due = False
        self._rebuild_idle = 0  # the idle source of a deferred rebuild (0: none)
        self.queue = EditQueue()  # every value edit, applied in order (settings.queue)
        self._queue_timer = 0  # the one pause timer of the queued spin edits (0: none)
        # what a drain dropped after a hand edit: (edits, typed paths, the warning). Named on
        # screen by the rebuild that follows, after it has written its own banner.
        self._unapplied: tuple[list[QueuedEdit], list[tuple], str] | None = None
        self._outside_warning = ""  # the last ChangedOutside message

        bar = Gtk.Box(spacing=6, margin=6)
        self.undo_button = Gtk.Button(label="Undo")
        self.undo_button.set_tooltip_text("Undo the last change (Ctrl+Z)")
        self._undo_clicked = self.undo_button.connect("clicked", lambda _b: self.undo())
        self._undo_by_action = False
        self.revert_button = Gtk.Button(label="Revert all")
        self.revert_button.set_tooltip_text("Put back the file as it was when this window opened")
        self.revert_button.connect("clicked", lambda _b: self.confirm_revert())
        where = Gtk.Label(label=str(session.path), xalign=1, selectable=True)
        where.get_style_context().add_class("dim-label")
        bar.pack_start(self.undo_button, False, False, 0)
        bar.pack_start(self.revert_button, False, False, 0)
        bar.pack_end(where, True, True, 0)

        install_info_note_css()
        self.banner = Gtk.InfoBar()
        self.banner_label = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.banner.get_content_area().add(self.banner_label)
        self.banner.set_no_show_all(True)
        self.stack = Gtk.Stack()
        self.tree = SettingsTree(self.show_page)
        self.tree.set_property("margin", 6)
        body = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        body.pack1(self.tree, False, False)  # never narrower than its MIN_WIDTH
        body.pack2(self.stack, True, False)
        self.pack_start(bar, False, False, 0)
        self.pack_start(self.banner, False, False, 0)
        self.pack_start(body, True, True, 0)
        self.connect("destroy", lambda _w: self.retire())  # whichever way the view goes
        self.rebuild()

    # ---- building ------------------------------------------------------------------------
    @property
    def config(self):
        """The config the rows show: the session's, or the defaults while the file is
        invalid (the pages are then insensitive)."""
        return self.session.config or check_text("", self.session.default_path)

    def cancel_deferred_rebuild(self) -> None:
        if self._rebuild_idle:
            GLib.source_remove(self._rebuild_idle)
            self._rebuild_idle = 0

    def rebuild(self) -> None:
        """Rebuild every page (after a panel was added, removed or moved, an undo, a revert
        or a hand edit); keeps the visible page. Edits still queued are applied first (the
        new rows could not show them): this rebuild then runs once, at the end."""
        if len(self.queue) and not self._flushing:
            self._rebuild_due = True
            self._run_queue()
            return
        self.cancel_deferred_rebuild()  # overtaken by this one
        visible = self.stack.get_visible_child_name()
        window = self.get_toplevel()
        focus = window.get_focus() if isinstance(window, Gtk.Window) else None
        if focus is not None and focus.is_ancestor(self.stack):
            window.set_focus(None)  # not left on a removed widget: shortcuts then find no group
        for row in self.rows:
            row.discard()  # typed text goes with the old rows (queued edits stay queued)
        retired = self.stack.get_children()
        for child in retired:
            self.stack.remove(child)
        if retired:
            # destroyed once the loop is idle, not here: a rebuild runs inside the signal of a
            # widget on these pages (a combo's "changed", a panel button's "clicked"), and GTK
            # finishes that emission on the widget afterwards (destroyed and freed here, it
            # printed g_object_notify / g_object_set "G_IS_OBJECT" criticals)
            GLib.idle_add(_destroy_all, retired)
        self.rows, self.previews = [], {}
        valid = self.session.config is not None
        entries = tree_entries(self.session.config, list(self.outputs.values()))
        self._add_page(THEME, self._theme_page(), valid)
        for entry in entries[1:]:
            name = parse_page(entry.page).monitor
            self._add_page(entry.page, self._monitor_page(name, entry.title), True)
        self.stack.show_all()
        page = self._page_to_show(visible)
        self.stack.set_visible_child_name(page)
        # the panel rows come with the panel pages
        self.tree.show(tuple(replace(e, children=()) for e in entries))
        self.tree.select(page)
        if valid:
            self.refresh()
        else:
            self.show_banner(
                f"{self.session.path} is not valid, so it cannot be edited here; fix it in a "
                "text editor (this window reloads it when it is saved), or "
                "run main.py --restore-config to put back the backup config.toml.bak."
                f"\n{self.session.error}",
                Gtk.MessageType.ERROR,
            )
        self._sync_undo_button()
        self._on_state()
        self._tell_unapplied()  # after the banner above, which would replace it

    def use_undo_action(self, name: str) -> None:
        """Hand the Undo button to a window action ("win.undo"): it then clicks through the
        action and is enabled exactly when the menu's Undo is. Without this (the view alone)
        the button undoes by itself and follows the history."""
        self._undo_by_action = True
        self.undo_button.disconnect(self._undo_clicked)
        self.undo_button.set_action_name(name)

    def _sync_undo_button(self) -> None:
        if not self._undo_by_action:
            self.undo_button.set_sensitive(bool(self.session.history))

    def _page_to_show(self, wanted: str | None) -> str:
        """`wanted` if it is still a page; else its fallback (a gone panel's monitor), else the
        Theme page."""
        for page in (wanted, wanted and fallback_page(wanted)):
            if page and self.stack.get_child_by_name(page) is not None:
                return page
        return THEME

    def show_page(self, page: str) -> None:
        """Show `page` (the tree's selection)."""
        if self.stack.get_child_by_name(page) is not None:
            self.stack.set_visible_child_name(page)

    def _add_page(self, name: str, content: Gtk.Widget, sensitive: bool) -> None:
        content.set_sensitive(sensitive)
        self.stack.add_named(content, name)

    def _tabbed(
        self,
        page: str,
        top: list[Gtk.Widget],
        tabs: tuple[TabSpec, ...],
        prefix: tuple,
        extra: tuple[tuple[str, Gtk.Widget], ...] = (),
    ) -> Gtk.Widget:
        """A page: `top` (its heading, a banner) above a notebook with one tab per TabSpec
        (then the `extra` tabs, (title, content)), each tab scrolled on its own. A tab's later
        parts get a heading of their own (the Handle tab: the handle colours, then "Handle
        style"). The tab last shown on `page` is shown again."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_start(16)
        box.set_margin_end(16)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        for widget in top:
            box.pack_start(widget, False, False, 0)
        notebook = Gtk.Notebook(scrollable=True)
        for tab in tabs:
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            content.set_property("margin", 12)
            for i, (key, section) in enumerate(tab.parts):
                if i > 0:
                    content.pack_start(self._heading(section.label), False, False, 6)
                content.pack_start(self.section_rows(section, (*prefix, *key)), False, False, 0)
            self._add_tab(notebook, tab.title, content)
        for title, content in extra:
            self._add_tab(notebook, title, content)
        box.pack_start(notebook, True, True, 0)
        self._keep_tab(page, notebook)
        return box

    @staticmethod
    def _add_tab(notebook: Gtk.Notebook, title: str, content: Gtk.Widget) -> None:
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.add(content)
        scroller.show_all()  # a notebook only switches to a visible page (_keep_tab)
        notebook.append_page(scroller, Gtk.Label(label=title))

    def _keep_tab(self, page: str, notebook: Gtk.Notebook) -> None:
        """Show the tab last shown on `page` (by its title) and remember the user's choice."""
        titles = [notebook.get_tab_label_text(c) for c in notebook.get_children()]
        if self._tab_of.get(page) in titles:
            notebook.set_current_page(titles.index(self._tab_of[page]))
        notebook.connect("switch-page", self._remember_tab, page)

    def _remember_tab(self, notebook: Gtk.Notebook, child: Gtk.Widget, _num, page: str) -> None:
        self._tab_of[page] = notebook.get_tab_label_text(child)

    def section_rows(self, section: SectionSpec, prefix: tuple) -> Gtk.Widget:
        """A box of FieldRows for `section` at key path `prefix`; sub-sections in frames."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for spec in section.fields:
            row = FieldRow(
                spec,
                (*prefix, spec.key),
                self._on_change,
                self._on_reset,
                self._on_queue,
                self.queue.pending,
            )
            self.rows.append(row)
            box.pack_start(row, False, False, 0)
        for sub in section.sections:
            frame = Gtk.Frame(label=sub.label)
            inner = self.section_rows(sub, (*prefix, sub.key))
            inner.set_margin_start(8)
            inner.set_margin_end(8)
            inner.set_margin_bottom(8)
            frame.add(inner)
            box.pack_start(frame, False, False, 6)
        return box

    @staticmethod
    def _heading(text: str) -> Gtk.Label:
        label = Gtk.Label(xalign=0)
        label.set_markup(f"<b>{GLib.markup_escape_text(text)}</b>")
        return label

    def _theme_page(self) -> Gtk.Widget:
        heading = self._heading("Theme (every monitor)")
        return self._tabbed(THEME, [heading], theme_tabs(self.form), ())

    def _preview(self, name: str) -> Gtk.Label:
        """A label for `name`'s layout warnings (shown by refresh when there are any)."""
        preview = Gtk.Label(xalign=0, wrap=True, selectable=True)
        preview.get_style_context().add_class("warning")
        preview.set_no_show_all(True)
        self.previews.setdefault(name, []).append(preview)
        return preview

    def _monitor_page(self, name: str, title: str) -> Gtk.Widget:
        """A monitor's page: the same tabs as the Theme page at [monitors.NAME], under a banner
        saying that they override the Theme; a row that is not set shows the Theme's value
        ("global theme")."""
        prefix = ("monitors", name)
        banner = Gtk.InfoBar(message_type=Gtk.MessageType.INFO)
        banner.get_content_area().add(Gtk.Label(label=override_text(name), xalign=0, wrap=True))
        top = [self._heading(title), banner, self._preview(name)]
        # until the toolbar and the panel pages take them over: the mode and the panel list
        panels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        panels.set_property("margin", 12)
        panels.pack_start(self.section_rows(self.form.monitor, prefix), False, False, 0)
        hints = "\n".join(f"{mode}: {hint}" for mode, hint in MODE_HINTS.items())
        note = Gtk.Label(label=hints, xalign=0, wrap=True)
        note.get_style_context().add_class("dim-label")
        panels.pack_start(note, False, False, 0)
        editor = PanelEditor(
            self.form,
            name,
            requests_for(self.config, name),
            self.section_rows,
            lambda edit, expand, n=name: self._structural(n, edit, expand),
            self._expand.pop(name, None),
        )
        panels.pack_start(editor, False, False, 0)
        tabs = theme_tabs(self.form)
        return self._tabbed(monitor_page(name), top, tabs, prefix, (("Panels", panels),))

    # ---- showing values ------------------------------------------------------------------
    def refresh(self) -> None:
        """Show the session's current values in every row (no rebuild: focus is kept). A row
        holding an edit that is not applied yet keeps it (`keep_pending`): another row's apply
        must neither drop a pending spin value nor reset a typed font list, nor clear a row's
        "Not saved" error (apply() clears the error of the row whose edit went through)."""
        config, user = self.config, self.session.user
        for row in self.rows:
            row.show_value(field_value(config, user, row.path), keep_pending=True)
        for name, labels in self.previews.items():
            out = self.outputs.get(name)
            warnings = layout_preview(config, name, out.width, out.height) if out else []
            for label in labels:
                label.set_text("\n".join(warnings))
                label.set_visible(bool(warnings))
        self._sync_undo_button()
        self._on_state()

    def show_banner(self, text: str, kind: Gtk.MessageType = Gtk.MessageType.ERROR) -> None:
        self.banner.set_message_type(kind)
        context = self.banner.get_style_context()
        if kind == Gtk.MessageType.INFO:
            context.add_class(INFO_NOTE_CLASS)
        else:
            context.remove_class(INFO_NOTE_CLASS)
        self.banner_label.set_text(text)
        self.banner_label.show()
        self.banner.show()

    def hide_banner(self) -> None:
        self.banner.hide()

    # ---- edits ---------------------------------------------------------------------------
    def apply(
        self,
        edit: Edit,
        row: FieldRow | None = None,
        structural: bool = False,
        defer: bool = False,
    ) -> bool:
        """Apply one edit; True when it was written. A rejected edit shows its error under
        `row` (or in the banner); a hand edit since the last read reloads everything."""
        try:
            self.session.apply(edit)
        except ChangedOutside as exc:
            self.refused_outside = True
            self._outside_warning = str(exc)
            self._rebuild_soon()
            self.show_banner(str(exc), Gtk.MessageType.WARNING)
            return False
        except ConfigError as exc:
            self.save_failed = True
            if row is not None:
                # the row goes back to the value in effect at once (the refused value is in no
                # file); the error stays until this row's own next edit or reset
                row.show_value(field_value(self.config, self.session.user, row.path))
                row.show_error(f"Not saved: {exc}")
            else:
                self.show_banner(f"Not saved: {exc}")
            return False
        if row is not None:
            row.show_error(None)  # its own edit or reset went through
        self.hide_banner()
        if structural:
            self._rebuild_soon(defer)
        else:
            self.refresh()
        return True

    def _rebuild_soon(self, defer: bool = False) -> None:
        """Rebuild now, or once the queue is applied (one rebuild for every edit that asks for
        it). `defer`: when the loop is idle, not now (a name entry's focus-out runs this before
        the click that caused it is released: a button unparented by the rebuild would lose
        that click)."""
        if self._flushing:
            self._rebuild_due = True
        elif defer:
            if not self._rebuild_idle:
                self._rebuild_idle = GLib.idle_add(self._rebuild_idle_cb)
        else:
            self.rebuild()

    def _rebuild_idle_cb(self) -> bool:
        """The deferred rebuild: what was queued meanwhile is applied first, then one rebuild."""
        self._rebuild_idle = 0
        self._rebuild_due = True
        self._run_queue()
        return False

    # ---- the edit queue (settings.queue) -------------------------------------------------
    def _on_change(self, path: tuple, value: Any) -> None:
        """An edit of a row (or of the toolbar): applied now, after the edits queued before it."""
        self.queue.push(path, value)
        self._run_queue(defer=True)

    def _on_reset(self, path: tuple) -> None:
        self.queue.push(path, RESET)
        self._run_queue(defer=True)

    def _on_queue(self, path: tuple, value: Any, base: Any) -> None:
        """A spin button's edit: queued and applied with the rest once the user pauses for
        DEBOUNCE_MS (one timer for every row, started again by each edit)."""
        self.queue.push(path, value, base)
        self._cancel_queue_timer()
        if len(self.queue):
            self._queue_timer = GLib.timeout_add(DEBOUNCE_MS, self._queue_due)

    def _queue_due(self) -> bool:
        self._queue_timer = 0
        self._run_queue(defer=True)
        return GLib.SOURCE_REMOVE

    def _cancel_queue_timer(self) -> None:
        if self._queue_timer:
            GLib.source_remove(self._queue_timer)
            self._queue_timer = 0

    def _run_queue(self, defer: bool = False) -> None:
        """Apply every queued edit in order. Inside a running flush() nothing more happens:
        that flush applies the new edit in its turn. A rebuild an edit asks for (a title key)
        waits until the queue is empty: once, `defer`red to the idle loop or not."""
        if self._flushing:
            return
        self.save_failed = False
        self.refused_outside = False
        self._flushing = True
        try:
            self._drain()
        finally:
            self._flushing = False
            if self._rebuild_due:
                self._rebuild_due = False
                self._rebuild_soon(defer)

    def _drain(self) -> None:
        """Apply the queue, oldest edit first. A hand edit met on the way (the file was
        re-read) drops that edit and every later one, and says which on screen."""
        self._cancel_queue_timer()
        while (item := self.queue.pop()) is not None:
            self._apply_queued(item)
            if self.refused_outside:
                typed = [row.path for row in self.rows if row.unsent()]
                self._unapplied = ([item, *self.queue.drop()], typed, self._outside_warning)
                break

    def _apply_queued(self, item: QueuedEdit) -> None:
        """One queued edit: a set or a reset; a panel's own key can be a compound edit
        (settings.values.panel_ops); a key in a panel's title rebuilds the pages."""
        path, value = item.path, item.value
        panel_key = len(path) == 5 and path[2] == "panels"
        titled = panel_key and path[4] in TITLE_KEYS  # the title and rows follow: rebuild
        if panel_key and (value is not RESET or path[4] == "corner"):
            # resetting a corner also drops an edge it cannot hold (panel_ops turns None into
            # an unset for the corner only)
            _, entry = lookup(self.session.user, path[:4])
            ops = panel_ops(entry or {}, path[4], None if value is RESET else value)
            edit = _panel_edit(path[:4], ops)
        elif value is RESET:
            edit = lambda d: d.unset(path)  # noqa: E731
        else:
            edit = lambda d: d.set(path, value)  # noqa: E731
        if titled:
            self._expand[path[1]] = path[3]  # keep that panel open
        if not self.apply(edit, self._row(path), structural=titled):
            self._expand.pop(path[1], None)

    def _tell_unapplied(self) -> None:
        """Name what a drain dropped (see _drain), once the rebuild has written its banner."""
        if self._unapplied is not None:
            (dropped, typed, warning), self._unapplied = self._unapplied, None
            self._tell_dropped(dropped, typed, warning)

    def _tell_dropped(
        self, dropped: list[QueuedEdit], typed: list[tuple], warning: str = ""
    ) -> None:
        """Add to the banner what was not applied because the file changed outside this
        window (never lost silently): the queued edits and the rows with typed text, at most
        MAX_NAMED of them. `warning`: the hand-edit warning, added when the banner no longer
        has it (the rebuild of an invalid file replaced it)."""
        parts = [describe([edit]) for edit in dropped]
        parts += [f"{path_text(path)} (typed text)" for path in typed]
        if not parts:
            return
        if len(parts) > MAX_NAMED:
            parts = [*parts[:MAX_NAMED], f"... and {len(parts) - MAX_NAMED} more"]
        text = self.banner_label.get_text()
        if warning and warning not in text:
            text = f"{text}\n{warning}" if text else warning
        note = "Not applied (made for the file before it changed): " + ", ".join(parts)
        self.show_banner(f"{text}\n{note}" if text else note, Gtk.MessageType.WARNING)

    def retire(self) -> None:
        """The view is going (File > Close, Open, New): no timer or idle rebuild may run on
        it later. Its queue was applied by the leave question's flush; anything left is
        dropped."""
        self.cancel_deferred_rebuild()
        self._cancel_queue_timer()
        self.queue.drop()
        for row in self.rows:
            row.discard()

    def _structural(self, monitor: str, edit: Edit, expand: int | None) -> None:
        """A panel added, removed or moved: row indexes change, so rebuild (never refresh
        rows that may point at an entry that is gone). `expand`: the entry to show open."""
        self.flush()  # pending values go to the row indexes they were typed for, before they move
        if self.refused_outside:
            return  # the file was re-read: these row indexes may mean other panels now
        if expand is not None:
            self._expand[monitor] = expand
        if not self.apply(edit, structural=True):
            self._expand.pop(monitor, None)

    def _row(self, path: tuple) -> FieldRow | None:
        return next((r for r in self.rows if r.path == path), None)

    def _file_action(self, action: Callable[[], bool]) -> bool:
        """Run Undo or Revert all: a hand edit since the last read, an unwritable folder or an
        unreadable file shows in the banner (never an exception in a GTK callback). Returns
        the action's result, False when it was refused."""
        try:
            return action()
        except ChangedOutside as exc:
            self.rebuild()
            self.show_banner(str(exc), Gtk.MessageType.WARNING)
        except ConfigError as exc:
            self.show_banner(f"Not saved: {exc}")
        return False

    def undo(self) -> None:
        self.flush()  # a pending value is applied first (and then undone), never written after
        if self.refused_outside:
            return  # a hand edit was met: the file was re-read, the warning is on screen
        if self._file_action(self.session.undo):
            self.hide_banner()
            self.rebuild()

    def redo(self) -> None:
        """Put back what the last Undo took away. A pending value is applied first, like for
        Undo: it is a new change, so it ends the redo line and Redo then does nothing."""
        self.flush()
        if self.refused_outside:
            return
        if self._file_action(self.session.redo):
            self.hide_banner()
            self.rebuild()

    def save(self) -> bool:
        """File > Save: pending values are applied first, then the file is the saved point
        (and config.toml.bak). True when saved; a hand edit or a failed copy is shown."""
        self.flush()
        if self.refused_outside:
            return False
        if not self._file_action(lambda: self.session.save() or True):
            return False
        self.hide_banner()
        self._on_state()
        return True

    def revert(self) -> None:
        # no flush: queued values are about to be reverted (dropped without a word), and
        # applying them first would re-read a hand edit and hide the "changed outside" warning
        self._cancel_queue_timer()
        typed = [row.path for row in self.rows if row.unsent()]
        dropped = self.queue.drop()
        if self._file_action(lambda: self.session.revert() or True):
            self.hide_banner()
            self.rebuild()
        else:
            self._tell_dropped(dropped, typed)  # refused: nothing was reverted, say what went

    def flush(self, defer: bool = False) -> None:
        """The barrier before anything that must see every edit (a panel added, removed or
        moved, Undo, Redo, Save, leaving the config): each row sends its typed text (a font
        list or a name without Enter, a number without Enter) into the queue, then the whole
        queue is applied in order (a spin edit inside its pause included). A rebuild an edit
        asks for waits until the end (once). Not for Revert all or a hand edit: they drop the
        queue. `save_failed` says whether an edit could not be written (the error is on
        screen); `refused_outside` that a hand edit was met: that edit and the later ones were
        dropped and named on screen (a rebuild follows). `defer`: the rebuild at the end waits
        for the idle loop (see _rebuild_soon)."""
        self.save_failed = False
        self.refused_outside = False
        self._flushing = True
        try:
            for row in list(self.rows):
                row.flush()  # typed text -> the queue (applied below, in its turn)
            self._drain()
        finally:
            self._flushing = False
            if self._rebuild_due:
                self._rebuild_due = False
                self._rebuild_soon(defer)

    def revert_text(self) -> str:
        """What the Revert all dialog says is about to happen."""
        text = (
            f"{self.session.path} goes back to how it was when the window opened (or after "
            "your last valid hand edit)."
        )
        if self.session.keeps_hand_edit():
            name = self.session.path.name
            text += (
                f"\n\nThe file as it is now (your hand edit, which is not valid) is kept as "
                f"{name}.before-revert next to it."
            )
        return text

    def confirm_revert(self) -> None:
        """Revert all, after the confirmation dialog (the button and Edit > Revert all)."""
        if self._ask_revert(self.get_toplevel(), self.revert_text()):
            self.revert()

    def file_changed(self) -> None:
        """The config file changed on disk (the app's ConfigWatcher). Our own writes leave
        nothing to do; a hand edit is re-read (the new starting point for Revert all) and
        every page rebuilt; a file that cannot be read shows in the banner."""
        try:
            if not self.session.changed_outside():
                return
            self.session.rebase()
        except ConfigError as exc:
            self.show_banner(f"Cannot read the config: {exc}")
            return
        # queued edits and typed text were made for the old file: dropped, and named below
        self._cancel_queue_timer()
        dropped = self.queue.drop()
        typed = [row.path for row in self.rows if row.unsent()]
        self.rebuild()
        if self.session.config is not None:
            self.show_banner(
                f"{self.session.path} was changed outside this window; showing the new values",
                Gtk.MessageType.INFO,
            )
        self._tell_dropped(dropped, typed)


def override_text(name: str) -> str:
    """The banner of a monitor's page."""
    return (
        f"These values override the Theme for {name}. A row you have not set here shows the "
        "Theme's value."
    )


def _destroy_all(widgets: list[Gtk.Widget]) -> bool:
    for widget in widgets:
        widget.destroy()
    return GLib.SOURCE_REMOVE


def _panel_edit(entry_path: tuple, ops: list[tuple[str, str, Any]]) -> Edit:
    """One edit from settings.values.panel_ops steps: one write and one reload."""

    def edit(doc: UserDocument) -> None:
        for op, key, value in ops:
            if op == "set":
                doc.set((*entry_path, key), value)
            else:
                doc.unset((*entry_path, key))

    return edit
