"""The Gtk.MenuBar built from settings.menus.MENUS. Each item is a Gtk.Actionable bound to
"win.<action>", so it follows that action's enabled state, and shows its first shortcut (the
shortcuts themselves are application accelerators, set by SettingsApp from ACCELS)."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from settings.menus import MENUS, Menu


def build_menubar(menus: tuple[Menu, ...] = MENUS) -> tuple[Gtk.MenuBar, dict[str, Gtk.Menu]]:
    """The menu bar, and each menu by its plain label ("Edit": the window refreshes Cut, Copy
    and Paste when that menu opens)."""
    bar = Gtk.MenuBar()
    submenus: dict[str, Gtk.Menu] = {}
    for menu in menus:
        top = Gtk.MenuItem.new_with_mnemonic(menu.label)
        sub = Gtk.Menu()
        for item in menu.items:
            if item is None:
                sub.append(Gtk.SeparatorMenuItem())
                continue
            entry = Gtk.MenuItem.new_with_mnemonic(item.label)
            entry.set_action_name(f"win.{item.action}")
            if item.accels:
                key, mods = Gtk.accelerator_parse(item.accels[0])
                entry.get_child().set_accel(key, mods)
            sub.append(entry)
        top.set_submenu(sub)
        bar.append(top)
        submenus[menu.label.replace("_", "")] = sub
    return bar, submenus
