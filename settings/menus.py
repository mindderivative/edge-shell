"""The settings window's menu bar as data, and when each item can be used. Pure (no GTK):
settings.menubar builds the Gtk.MenuBar from MENUS, settings.app registers ACCELS, and the
window sets each action's enabled state from `enabled(menu_state(...))`.

Every item names an action of the window's "win" group. `accels` are GTK accelerator
strings; the first one is shown next to the item. A `bound` item's accels are registered as
application accelerators (they work wherever the focus is in the window, a text entry
included: Ctrl+Z is the document's Undo, the entries have no undo of their own). Cut, Copy and
Paste are not bound: Ctrl+X/C/V stay the focused widget's own key bindings, which do exactly
what the menu items do, also in a selectable label the menu items do not cover."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Item:
    label: str  # with a mnemonic underscore
    action: str  # the action's name in the window's "win" group
    accels: tuple[str, ...] = ()
    bound: bool = True  # False: shown only; the focused widget's own key binding does it


@dataclass(frozen=True)
class Menu:
    label: str
    items: tuple[Item | None, ...]  # None: a separator


MENUS: tuple[Menu, ...] = (
    Menu(
        "_File",
        (
            Item("_New…", "new", ("<Primary>n",)),
            Item("_Open…", "open", ("<Primary>o",)),
            None,
            Item("_Save", "save", ("<Primary>s",)),
            Item("Save _As…", "save-as", ("<Primary><Shift>s",)),
            None,
            Item("_Close", "close", ("<Primary>w",)),
            Item("E_xit", "exit", ("<Primary>q",)),
        ),
    ),
    Menu(
        "_Edit",
        (
            Item("_Undo", "undo", ("<Primary>z",)),
            Item("_Redo", "redo", ("<Primary><Shift>z", "<Primary>y")),
            None,
            Item("Cu_t", "cut", ("<Primary>x",), bound=False),
            Item("_Copy", "copy", ("<Primary>c",), bound=False),
            Item("_Paste", "paste", ("<Primary>v",), bound=False),
            None,
            Item("Re_vert all…", "revert"),
        ),
    ),
    Menu("_Help", (Item("_About Edge Shell", "about"),)),
)

ACTIONS: tuple[str, ...] = tuple(i.action for m in MENUS for i in m.items if i is not None)
# "win.save" -> ["<Primary>s"]: what SettingsApp passes to Gtk.Application.set_accels_for_action
ACCELS: dict[str, list[str]] = {
    f"win.{i.action}": list(i.accels)
    for m in MENUS
    for i in m.items
    if i is not None and i.bound and i.accels
}


@dataclass(frozen=True)
class MenuState:
    """What the items depend on: a config is open (not the empty window after Close), it has
    changes since the last save, there is something to undo, redo or revert, and what the
    focused widget allows for Cut, Copy and Paste (clipboard_enabled)."""

    open: bool = False
    dirty: bool = False
    can_undo: bool = False
    can_redo: bool = False
    can_revert: bool = False
    cut: bool = False
    copy: bool = False
    paste: bool = False


def clipboard_enabled(text_focused: bool, editable: bool, selected: bool) -> dict[str, bool]:
    """Cut needs an editable text widget with a selection, Copy a selection, Paste an editable
    text widget; with no text widget focused (a button, a combo box, nothing) all three are
    off."""
    return {
        "cut": text_focused and editable and selected,
        "copy": text_focused and selected,
        "paste": text_focused and editable,
    }


def menu_state(session: Any, clipboard: dict[str, bool] | None = None) -> MenuState:
    """The MenuState of a SettingsSession (None: no config open)."""
    clip = clipboard or {}
    if session is None:
        return MenuState(**clip)
    return MenuState(
        open=True,
        dirty=session.dirty,
        can_undo=bool(session.history),
        can_redo=bool(session.redo_history),
        can_revert=session.text != session.start_text,
        **clip,
    )


def enabled(state: MenuState) -> dict[str, bool]:
    """Action name -> enabled, for every action in MENUS. New, Open, Exit and About always
    work; Save needs changes since the last save; Save As and Close need an open config;
    Undo, Redo and Revert all need something to undo, redo or revert."""
    return {
        "new": True,
        "open": True,
        "save": state.open and state.dirty,
        "save-as": state.open,
        "close": state.open,
        "exit": True,
        "undo": state.open and state.can_undo,
        "redo": state.open and state.can_redo,
        "cut": state.cut,
        "copy": state.copy,
        "paste": state.paste,
        "revert": state.open and state.can_revert,
        "about": True,
    }
