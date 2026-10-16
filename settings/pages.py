"""The settings window's pages and the tree that selects them (panel/widget spec 7). Pure: no
GTK.

A page is named by a string, its Gtk.Stack child name: "theme", "monitor:NAME" and
"panel:NAME:INDEX" (INDEX: the entry's place in [[monitors.NAME.panels]], 0-based; panels are
tracked by index, spec 3.1). The tree lists Theme, then one row per monitor (connected ones
first in kscreen order, then the ones only in the config, "(not connected)"), each with its
panels by name as children.
"""

from __future__ import annotations

from dataclasses import dataclass

from settings.values import monitor_names
from shell.config.models import Config
from shell.outputs import Output

THEME = "theme"
NOT_CONNECTED = " (not connected)"


def monitor_page(name: str) -> str:
    return f"monitor:{name}"


def panel_page(name: str, index: int) -> str:
    return f"panel:{name}:{index}"


@dataclass(frozen=True)
class PageRef:
    kind: str  # "theme" | "monitor" | "panel"
    monitor: str | None = None
    index: int | None = None


def parse_page(page: str) -> PageRef:
    """The parts of a page name; ValueError for anything that is not one."""
    if page == THEME:
        return PageRef("theme")
    kind, sep, rest = page.partition(":")
    if kind == "monitor" and sep and rest:
        return PageRef("monitor", rest)
    if kind == "panel":
        name, sep, index = rest.rpartition(":")
        if sep and name and index.isascii() and index.isdigit() and str(int(index)) == index:
            return PageRef("panel", name, int(index))
    raise ValueError(f"not a settings page: {page!r}")


def screen_of(page: str | None) -> str | None:
    """The monitor a page belongs to (the toolbar's screen): a monitor page's own, a panel
    page's monitor; None for the Theme page or no page."""
    return None if page is None else parse_page(page).monitor


def fallback_page(page: str) -> str:
    """The page shown when `page` is gone after a rebuild (its panel removed, by an undo or a
    hand edit; its monitor no longer listed): a panel's monitor page, else the Theme page. The
    caller checks that the monitor page still exists."""
    ref = parse_page(page)
    return monitor_page(ref.monitor) if ref.kind == "panel" else THEME


@dataclass(frozen=True)
class TreeEntry:
    page: str
    title: str
    children: tuple[TreeEntry, ...] = ()


def tree_entries(config: Config | None, outputs: list[Output]) -> tuple[TreeEntry, ...]:
    """The tree's rows. `config` None (the file is invalid: read-only) lists only Theme. A
    monitor that is connected is listed whether or not the config has it; one only in the
    config is "NAME (not connected)". A monitor's children are its panels by `name`, in the
    order of its [[panels]] entries."""
    entries = [TreeEntry(THEME, "Theme")]
    if config is None:
        return tuple(entries)
    for name, connected in monitor_names(config, outputs):
        panels = tuple(
            TreeEntry(panel_page(name, i), entry.name)
            for i, entry in enumerate(config.monitor(name).panels)
        )
        title = name if connected else name + NOT_CONNECTED
        entries.append(TreeEntry(monitor_page(name), title, panels))
    return tuple(entries)
