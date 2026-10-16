"""A monitor's panels in the settings window: each entry's title and rows (edge and corner
panels share the list, spec 19; a widget of several kinds gets the panel type row, panel/widget
spec 3.7), and the structural edits the tree and the toolbar make (add, remove, move up or
down) with the page to show after each. Pure: no GTK (settings.view builds the panel pages;
the session applies the edits and the view rebuilds)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from settings.document import UserDocument
from settings.form import ConfigForm, SectionSpec
from settings.pages import monitor_page, panel_page
from settings.values import new_panel_entry
from shell.panel_spec import CornerRequest, PanelRequest
from shell.registry import supported_kinds

Edit = Callable[[UserDocument], Any]
ACTIONS = ("up", "down", "remove")


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


def add_step(monitor: str, count: int, widget: str, kind: str | None = None) -> tuple[Edit, str]:
    """Add a panel of `widget` (as `kind`) after the `count` entries `monitor` has: the edit
    (a free name, settings.values.new_panel_entry) and the new panel's page."""

    def edit(doc: UserDocument) -> None:
        doc.add_panel(monitor, new_panel_entry(doc.data, monitor, widget, kind))

    return edit, panel_page(monitor, count)


def panel_step(monitor: str, index: int, count: int, action: str) -> tuple[Edit, str] | None:
    """Move entry `index` of `monitor`'s `count` up or down, or remove it: the edit and the page
    to show after it (the moved panel's; after a remove, the monitor's). None when there is
    nothing to do (the first panel up, the last one down, an index that is gone)."""
    if not 0 <= index < count:
        return None
    if action == "remove":
        return (lambda d: d.remove_panel(monitor, index)), monitor_page(monitor)
    to = {"up": index - 1, "down": index + 1}.get(action)
    if to is None:
        raise ValueError(f"unknown panel action {action!r}")
    if not 0 <= to < count:
        return None
    return (lambda d: d.move_panel(monitor, index, to)), panel_page(monitor, to)
