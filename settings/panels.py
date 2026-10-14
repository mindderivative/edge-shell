"""GTK editor for one monitor's panel list: an expander per [[panels]] entry with its fields,
plus add, remove and reorder buttons. Edge and corner panels (spec 19) share the list; each
entry shows the rows of its widget's kind. Structural edits go through `on_edit` (the window
applies them with the session and rebuilds); field rows come from the window's `make_rows`."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from settings.document import UserDocument
from settings.fields import wheel_scrolls_the_page
from settings.form import ConfigForm, SectionSpec
from settings.values import new_panel_entry
from shell.panel_spec import CornerRequest, PanelRequest
from shell.registry import widget_kind

Edit = Callable[[UserDocument], Any]


def panel_title(index: int, req: PanelRequest | CornerRequest) -> str:
    """'1. dock: bottom, center', or for a corner panel '2. summary: bottom-left, from
    bottom, 300x390' (1-based, as the list reads)."""
    if isinstance(req, CornerRequest):
        where = f"{req.corner}, from {req.edge}, {req.width}x{req.height}"
        return f"{index + 1}. {req.widget}: {where}"
    return f"{index + 1}. {req.widget}: {req.edge}, {req.align}"


def panel_section(form: ConfigForm, req: PanelRequest | CornerRequest) -> SectionSpec:
    """The rows of one entry: its widget's kind; a corner panel's edge row offers only the two
    edges of the corner it is in."""
    corner = req.corner if isinstance(req, CornerRequest) else None
    return form.panel_for(widget_kind(req.widget), corner)


class PanelEditor(Gtk.Box):
    def __init__(
        self,
        form: ConfigForm,
        monitor: str,
        requests: list[PanelRequest | CornerRequest],
        make_rows: Callable[[SectionSpec, tuple], Gtk.Widget],
        on_edit: Callable[[Edit, int | None], None],
        expand: int | None = None,
    ):
        """`requests`: registry.requests_for(config, monitor), one per entry in config order.
        `on_edit(edit, open_index)`: apply a structural edit, then show entry `open_index`
        open (None: none). `expand`: the entry to show open now."""
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.monitor = monitor
        self._on_edit = on_edit
        self._count = len(requests)
        self.expanders: list[Gtk.Expander] = []
        last = len(requests) - 1
        for i, req in enumerate(requests):
            expander = Gtk.Expander(label=panel_title(i, req), expanded=i == expand)
            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_start=18)
            buttons = Gtk.Box(spacing=6)
            for icon, tip, sensitive, action in (
                ("go-up-symbolic", "Move up", i > 0, lambda _b, i=i: self.move(i, i - 1)),
                ("go-down-symbolic", "Move down", i < last, lambda _b, i=i: self.move(i, i + 1)),
                ("list-remove-symbolic", "Remove this panel", True, lambda _b, i=i: self.remove(i)),
            ):
                button = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
                button.set_tooltip_text(tip)
                button.set_sensitive(sensitive)
                button.connect("clicked", action)
                buttons.pack_start(button, False, False, 0)
            body.pack_start(buttons, False, False, 0)
            rows = make_rows(panel_section(form, req), ("monitors", monitor, "panels", i))
            body.pack_start(rows, False, False, 0)
            expander.add(body)
            self.expanders.append(expander)
            self.pack_start(expander, False, False, 0)
        adder = Gtk.Box(spacing=6)
        self.widget_choice = Gtk.ComboBoxText()
        widget = form.edge_panel.field("widget")
        for name, label in zip(widget.choices, widget.labels or widget.choices, strict=True):
            self.widget_choice.append(name, label)
        self.widget_choice.set_active(0)
        wheel_scrolls_the_page(self.widget_choice)
        add = Gtk.Button(label="Add panel")
        add.connect("clicked", lambda _b: self.add(self.widget_choice.get_active_id()))
        adder.pack_start(self.widget_choice, False, False, 0)
        adder.pack_start(add, False, False, 0)
        self.pack_start(adder, False, False, 0)

    def add(self, widget: str | None) -> None:
        """A new entry with its kind, a name unique on this monitor and its widget, edge or
        corner kind alike (a corner widget's entry is {"panel": "corner", "name": "summary",
        "widget": "summary"}: its corner and size are the widget's)."""
        if widget:
            self._on_edit(
                lambda d: d.add_panel(self.monitor, new_panel_entry(d.data, self.monitor, widget)),
                self._count,
            )

    def remove(self, index: int) -> None:
        self._on_edit(lambda d: d.remove_panel(self.monitor, index), None)

    def move(self, index: int, to: int) -> None:
        self._on_edit(lambda d: d.move_panel(self.monitor, index, to), to)
