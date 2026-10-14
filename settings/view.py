"""The settings window's content: a top bar (Undo, Revert all, the file path), a banner for
errors and notices, and a page per topic (the global theme and layout, then one page per
monitor: shell mode, panels, theme and layout overrides). A plain Gtk.Box, so it is tested
without creating a window; settings.window puts it in the toplevel.

Every edit goes through SettingsSession.apply: a valid one is written to the user config and
the running shell reloads it; an invalid one is shown under its row and not written."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from settings.document import UserDocument
from settings.fields import FieldRow
from settings.form import MODE_HINTS, SectionSpec, config_form
from settings.panels import PanelEditor
from settings.session import ChangedOutside, SettingsSession, check_text
from settings.values import field_value, layout_preview, lookup, monitor_names, panel_ops
from shell.config.models import ConfigError
from shell.outputs import Output
from shell.registry import requests_for, widget_kind, widget_names

Edit = Callable[[UserDocument], Any]
# shown in a panel's expander title (panel_title), or deciding its rows (widget: the kind;
# corner: the edge choices): a change rebuilds the page and keeps that panel open
TITLE_KEYS = ("widget", "edge", "align", "corner", "width", "height")


class SettingsView(Gtk.Box):
    def __init__(self, session: SettingsSession, outputs: list[Output]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.session = session
        self.outputs = {o.name: o for o in outputs}
        names = tuple(widget_names())
        corner = tuple(n for n in names if widget_kind(n) == "corner")
        self.form = config_form(names, corner)
        self.rows: list[FieldRow] = []
        self.previews: dict[str, Gtk.Label] = {}
        self._expand: dict[str, int] = {}  # monitor -> panel entry to show open after a rebuild

        bar = Gtk.Box(spacing=6, margin=6)
        self.undo_button = Gtk.Button(label="Undo")
        self.undo_button.set_tooltip_text("Undo the last change (Ctrl+Z)")
        self.undo_button.connect("clicked", lambda _b: self.undo())
        revert = Gtk.Button(label="Revert all")
        revert.set_tooltip_text("Put back the file as it was when this window opened")
        revert.connect("clicked", lambda _b: self._confirm_revert())
        where = Gtk.Label(label=str(session.path), xalign=1, selectable=True)
        where.get_style_context().add_class("dim-label")
        bar.pack_start(self.undo_button, False, False, 0)
        bar.pack_start(revert, False, False, 0)
        bar.pack_end(where, True, True, 0)

        self.banner = Gtk.InfoBar()
        self.banner_label = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.banner.get_content_area().add(self.banner_label)
        self.banner.set_no_show_all(True)
        self.stack = Gtk.Stack()
        sidebar = Gtk.StackSidebar(stack=self.stack)
        body = Gtk.Box()
        body.pack_start(sidebar, False, False, 0)
        body.pack_start(self.stack, True, True, 0)
        self.pack_start(bar, False, False, 0)
        self.pack_start(self.banner, False, False, 0)
        self.pack_start(body, True, True, 0)
        self.rebuild()

    # ---- building ------------------------------------------------------------------------
    @property
    def config(self):
        """The config the rows show: the session's, or the defaults while the file is
        invalid (the pages are then insensitive)."""
        return self.session.config or check_text("", self.session.default_path)

    def rebuild(self) -> None:
        """Rebuild every page (after a panel was added, removed or moved, an undo, a revert
        or a hand edit); keeps the visible page."""
        visible = self.stack.get_visible_child_name()
        for child in self.stack.get_children():
            self.stack.remove(child)
            child.destroy()
        self.rows, self.previews = [], {}
        valid = self.session.config is not None
        self._page("theme", "Theme", self._theme_page(), valid)
        if valid:
            for name, connected in monitor_names(self.config, list(self.outputs.values())):
                title = name if connected else f"{name} (not connected)"
                self._page(f"monitor:{name}", title, self._monitor_page(name), True)
        self.stack.show_all()
        if visible and self.stack.get_child_by_name(visible) is not None:
            self.stack.set_visible_child_name(visible)
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
        self.undo_button.set_sensitive(bool(self.session.history))

    def _page(self, name: str, title: str, content: Gtk.Widget, sensitive: bool) -> None:
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        content.set_margin_start(16)
        content.set_margin_end(16)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        scroller.add(content)
        scroller.set_sensitive(sensitive)
        self.stack.add_titled(scroller, name, title)

    def section_rows(self, section: SectionSpec, prefix: tuple) -> Gtk.Widget:
        """A box of FieldRows for `section` at key path `prefix`; sub-sections in frames."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for spec in section.fields:
            row = FieldRow(spec, (*prefix, spec.key), self._on_change, self._on_reset)
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
        label.set_markup(f"<b>{text}</b>")
        return label

    def _theme_page(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.pack_start(self._heading("Theme (every monitor)"), False, False, 0)
        box.pack_start(self.section_rows(self.form.theme, ("theme",)), False, False, 0)
        box.pack_start(self._heading("Layout"), False, False, 0)
        box.pack_start(self.section_rows(self.form.layout, ("layout",)), False, False, 0)
        return box

    def _monitor_page(self, name: str) -> Gtk.Widget:
        prefix = ("monitors", name)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.pack_start(self.section_rows(self.form.monitor, prefix), False, False, 0)
        hints = "\n".join(f"{mode}: {hint}" for mode, hint in MODE_HINTS.items())
        note = Gtk.Label(label=hints, xalign=0, wrap=True)
        note.get_style_context().add_class("dim-label")
        box.pack_start(note, False, False, 0)
        box.pack_start(self._heading("Panels"), False, False, 0)
        editor = PanelEditor(
            self.form,
            name,
            requests_for(self.config, name),
            self.section_rows,
            lambda edit, expand, n=name: self._structural(n, edit, expand),
            self._expand.pop(name, None),
        )
        box.pack_start(editor, False, False, 0)
        preview = Gtk.Label(xalign=0, wrap=True, selectable=True)
        preview.get_style_context().add_class("warning")
        preview.set_no_show_all(True)
        self.previews[name] = preview
        box.pack_start(preview, False, False, 0)
        for key, title, section in (
            ("theme", "Theme override (this monitor only)", self.form.theme),
            ("layout", "Layout override (this monitor only)", self.form.layout),
        ):
            expander = Gtk.Expander(label=title)
            expander.add(self.section_rows(section, (*prefix, key)))
            box.pack_start(expander, False, False, 0)
        return box

    # ---- showing values ------------------------------------------------------------------
    def refresh(self) -> None:
        """Show the session's current values in every row (no rebuild: focus is kept). A row
        holding an edit that is not applied yet keeps it (`keep_pending`): another row's apply
        must neither drop a pending spin value nor reset a typed font list."""
        config, user = self.config, self.session.user
        for row in self.rows:
            row.show_value(field_value(config, user, row.path), keep_pending=True)
        for name, label in self.previews.items():
            out = self.outputs.get(name)
            warnings = layout_preview(config, name, out.width, out.height) if out else []
            label.set_text("\n".join(warnings))
            label.set_visible(bool(warnings))
        self.undo_button.set_sensitive(bool(self.session.history))

    def show_banner(self, text: str, kind: Gtk.MessageType = Gtk.MessageType.ERROR) -> None:
        self.banner.set_message_type(kind)
        self.banner_label.set_text(text)
        self.banner_label.show()
        self.banner.show()

    def hide_banner(self) -> None:
        self.banner.hide()

    # ---- edits ---------------------------------------------------------------------------
    def apply(self, edit: Edit, row: FieldRow | None = None, structural: bool = False) -> bool:
        """Apply one edit; True when it was written. A rejected edit shows its error under
        `row` (or in the banner); a hand edit since the last read reloads everything."""
        try:
            self.session.apply(edit)
        except ChangedOutside as exc:
            self.rebuild()
            self.show_banner(str(exc), Gtk.MessageType.WARNING)
            return False
        except ConfigError as exc:
            if row is not None:
                row.show_error(f"Not saved: {exc}")
            else:
                self.show_banner(f"Not saved: {exc}")
            return False
        self.hide_banner()
        if structural:
            self.rebuild()
        else:
            self.refresh()
        return True

    def _on_change(self, path: tuple, value: Any) -> None:
        titled = len(path) == 5 and path[2] == "panels" and path[4] in TITLE_KEYS
        if titled:  # the panel's expander title shows these: rebuild, keep that panel open
            self._expand[path[1]] = path[3]
        if len(path) == 5 and path[2] == "panels":  # a panel's own key: maybe a compound edit
            _, entry = lookup(self.session.user, path[:4])
            edit = _panel_edit(path[:4], panel_ops(entry or {}, path[4], value))
        else:
            edit = lambda d: d.set(path, value)  # noqa: E731
        if not self.apply(edit, self._row(path), structural=titled):
            self._expand.pop(path[1], None)

    def _on_reset(self, path: tuple) -> None:
        if len(path) == 5 and path[2] == "panels" and path[4] == "corner":
            _, entry = lookup(self.session.user, path[:4])  # resetting a corner also drops an
            # edge it cannot hold (panel_ops only turns None into an unset for the corner)
            self.apply(
                _panel_edit(path[:4], panel_ops(entry or {}, path[4], None)), self._row(path)
            )
        else:
            self.apply(lambda d: d.unset(path), self._row(path))

    def _structural(self, monitor: str, edit: Edit, expand: int | None) -> None:
        """A panel added, removed or moved: row indexes change, so rebuild (never refresh
        rows that may point at an entry that is gone). `expand`: the entry to show open."""
        self.flush()  # pending values go to the row indexes they were typed for, before they move
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
        if self._file_action(self.session.undo):
            self.hide_banner()
            self.rebuild()

    def revert(self) -> None:
        self.flush()
        if self._file_action(lambda: self.session.revert() or True):
            self.hide_banner()
            self.rebuild()

    def flush(self) -> None:
        """Apply what is typed or pending in any row (a spin button inside its 400 ms pause,
        a font list without Enter): the window is closing, or the rows are about to be rebuilt
        (a panel added, removed or moved, Undo, Revert all, a hand edit). Rows keep their pending
        edit through the refresh after each apply, so every row is applied in turn."""
        for row in list(self.rows):
            row.flush()

    def _confirm_revert(self) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text="Revert every change made in this window?",
        )
        dialog.format_secondary_text(
            f"{self.session.path} goes back to how it was when the window opened (or when it "
            "was last changed by hand)."
        )
        answer = dialog.run()
        dialog.destroy()
        if answer == Gtk.ResponseType.OK:
            self.revert()

    def file_changed(self) -> None:
        """The config file changed on disk (the app's ConfigWatcher). Our own writes leave
        nothing to do; a hand edit is re-read (the new starting point for Revert all) and
        every page rebuilt; a file that cannot be read shows in the banner."""
        try:
            if not self.session.changed_outside():
                return
            self.flush()  # pending values are applied to the right paths before the rows go
            self.session.rebase()
        except ConfigError as exc:
            self.show_banner(f"Cannot read the config: {exc}")
            return
        self.rebuild()
        if self.session.config is not None:
            self.show_banner(
                f"{self.session.path} was changed outside this window; showing the new values",
                Gtk.MessageType.INFO,
            )


def _panel_edit(entry_path: tuple, ops: list[tuple[str, str, Any]]) -> Edit:
    """One edit from settings.values.panel_ops steps: one write and one reload."""

    def edit(doc: UserDocument) -> None:
        for op, key, value in ops:
            if op == "set":
                doc.set((*entry_path, key), value)
            else:
                doc.unset((*entry_path, key))

    return edit
