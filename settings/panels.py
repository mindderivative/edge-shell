"""GTK editor for one monitor's panel list: an expander per [[panels]] entry with its fields,
plus add, remove and reorder buttons. Edge and corner panels (spec 19) share the list; each
entry shows the rows of its kind, the panel type row when its widget can be shown in more than
one kind, and a "Widget" frame with the widget's own properties (panel/widget spec 3.7).
Structural edits go through `on_edit` (the window applies them with the session and rebuilds);
field rows come from the window's `make_rows`."""

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
from shell.registry import supported_kinds

Edit = Callable[[UserDocument], Any]


def panel_title(index: int, req: PanelRequest | CornerRequest) -> str:
    """'1. Dock: bottom, center', or for a corner panel '2. Summary: bottom-left, from bottom,
    300x390': the entry's name (1-based, as the list reads)."""
    if isinstance(req, CornerRequest):
        where = f"{req.corner}, from {req.edge}, {req.width}x{req.height}"
        return f"{index + 1}. {req.name}: {where}"
    return f"{index + 1}. {req.name}: {req.edge}, {req.align}"


def panel_section(form: ConfigForm, req: PanelRequest | CornerRequest) -> SectionSpec:
    """The rows of one entry: its kind's; a corner panel's edge row offers only the two edges
    of the corner it is in; the panel type row only when the widget supports several kinds."""
    corner = req.corner if isinstance(req, CornerRequest) else None
    kind = "edge" if corner is None else "corner"
    return form.panel_for(kind, corner, supported_kinds(req.widget))


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
            prefix = ("monitors", monitor, "panels", i)
            body.pack_start(make_rows(panel_section(form, req), prefix), False, False, 0)
            props = form.widget_props(req.widget)
            if props is not None:  # the widget's own keys: in the same entry (same prefix)
                frame = Gtk.Frame(label=props.label)
                inner = make_rows(props, prefix)
                inner.set_margin_start(8)
                inner.set_margin_end(8)
                inner.set_margin_bottom(8)
                frame.add(inner)
                body.pack_start(frame, False, False, 6)
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
        """A new entry with its widget's first kind, a name made from the widget's title that
        is unique on this monitor, and the widget (a summary block's entry is {"panel":
        "corner", "name": "Summary", "widget": "summary"}: its corner and size are the
        widget's)."""
        if widget:
            self._on_edit(
                lambda d: d.add_panel(self.monitor, new_panel_entry(d.data, self.monitor, widget)),
                self._count,
            )

    def remove(self, index: int) -> None:
        self._on_edit(lambda d: d.remove_panel(self.monitor, index), None)

    def move(self, index: int, to: int) -> None:
        self._on_edit(lambda d: d.move_panel(self.monitor, index, to), to)
