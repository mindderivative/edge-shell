"""settings.menus: the menu bar as data, its accelerators and when each item works (pure)."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from settings.menus import (
    ACCELS,
    ACTIONS,
    MENUS,
    TITLE,
    MenuState,
    clipboard_enabled,
    enabled,
    menu_state,
    window_title,
)


def plain(label):
    return label.replace("_", "").rstrip("…")


def test_the_menus_follow_phils_list():
    assert [plain(m.label) for m in MENUS] == ["File", "Edit", "Help"]
    assert [[plain(i.label) if i else "-" for i in m.items] for m in MENUS] == [
        ["New", "Open", "-", "Save", "Save As", "-", "Close", "Exit"],
        ["Undo", "Redo", "-", "Cut", "Copy", "Paste", "-", "Revert all"],
        ["About Edge Shell"],
    ]


def test_every_action_is_named_once():
    assert len(ACTIONS) == len(set(ACTIONS)) == 13


def test_the_accelerators():
    assert ACCELS == {
        "win.new": ["<Primary>n"],
        "win.open": ["<Primary>o"],
        "win.save": ["<Primary>s"],
        "win.save-as": ["<Primary><Shift>s"],
        "win.close": ["<Primary>w"],
        "win.exit": ["<Primary>q"],
        "win.undo": ["<Primary>z"],
        "win.redo": ["<Primary><Shift>z", "<Primary>y"],
    }


def test_clipboard_shortcuts_are_shown_but_left_to_the_focused_widget():
    items = {i.action: i for m in MENUS for i in m.items if i}
    for action, accel in (("cut", "<Primary>x"), ("copy", "<Primary>c"), ("paste", "<Primary>v")):
        assert items[action].accels == (accel,) and not items[action].bound
        assert f"win.{action}" not in ACCELS


def test_no_shortcut_is_used_twice():
    accels = [a for m in MENUS for i in m.items if i for a in i.accels]
    assert len(accels) == len(set(accels))


def test_mnemonics_are_unique_within_each_menu():
    def key(label):
        return label[label.index("_") + 1].lower()

    assert len({key(m.label) for m in MENUS}) == len(MENUS)
    for menu in MENUS:
        keys = [key(i.label) for i in menu.items if i]
        assert len(keys) == len(set(keys)), menu.label


def test_every_shortcut_is_a_valid_gtk_accelerator():
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    for accel in (a for m in MENUS for i in m.items if i for a in i.accels):
        key, mods = Gtk.accelerator_parse(accel)
        assert key != 0, accel


def test_with_no_config_open_only_new_open_exit_and_about_work():
    on = {name for name, ok in enabled(MenuState()).items() if ok}
    assert on == {"new", "open", "exit", "about"}
    assert set(enabled(MenuState())) == set(ACTIONS)


@pytest.mark.parametrize(
    "state, on",
    [
        # Save and Undo work whenever a config is open: a value typed but not yet applied is
        # no change in the session yet, and both apply it first
        (MenuState(open=True), {"save", "save-as", "close", "undo"}),
        (MenuState(open=True, dirty=True), {"save", "save-as", "close", "undo"}),
        (MenuState(open=True, can_undo=True), {"save", "save-as", "close", "undo"}),
        (MenuState(open=True, can_redo=True), {"save", "save-as", "close", "undo", "redo"}),
        (MenuState(open=True, can_revert=True), {"save", "save-as", "close", "undo", "revert"}),
        (
            MenuState(open=True, copy=True, paste=True),
            {"save", "save-as", "close", "undo", "copy", "paste"},
        ),
        (MenuState(open=False, dirty=True, can_undo=True, can_revert=True), set()),
    ],
)
def test_items_follow_the_state(state, on):
    always = {"new", "open", "exit", "about"}
    assert {name for name, ok in enabled(state).items() if ok} == always | on


def test_redo_needs_a_config_even_when_the_state_says_it_can():
    assert not enabled(MenuState(open=False, can_redo=True))["redo"]
    assert enabled(MenuState(open=True, can_redo=True))["redo"]


@pytest.mark.parametrize(
    "focused, editable, selected, cut, copy, paste",
    [
        (False, False, False, False, False, False),  # a button or nothing has the focus
        (False, True, True, False, False, False),
        (True, True, False, False, False, True),  # an entry, nothing selected
        (True, True, True, True, True, True),
        (True, False, True, False, True, False),  # a read-only text: copy only
        (True, False, False, False, False, False),
    ],
)
def test_clipboard_enabled(focused, editable, selected, cut, copy, paste):
    assert clipboard_enabled(focused, editable, selected) == {
        "cut": cut,
        "copy": copy,
        "paste": paste,
    }


def session(**kw):
    base = dict(dirty=False, history=[], redo_history=[], text="a", start_text="a")
    return SimpleNamespace(**(base | kw))


def test_menu_state_reads_the_session():
    assert menu_state(None) == MenuState()
    assert menu_state(None, {"cut": False, "copy": True, "paste": False}) == MenuState(copy=True)
    assert menu_state(session()) == MenuState(open=True)
    state = menu_state(session(dirty=True, history=["x"], redo_history=["y"], text="b"))
    assert state == MenuState(open=True, dirty=True, can_undo=True, can_redo=True, can_revert=True)
    # Revert all follows the text, not the history: an invalid hand edit has no history but
    # can be reverted; a change typed back to the start has history but nothing to revert
    assert menu_state(session(text="b")).can_revert
    assert not menu_state(session(history=["x"])).can_revert


def test_menu_state_keeps_the_clipboard_flags_of_an_open_config():
    clip = {"cut": True, "copy": True, "paste": False}
    assert menu_state(session(), clip) == MenuState(open=True, cut=True, copy=True)


def test_menu_state_undo_and_redo_follow_their_own_histories():
    undo_only = menu_state(session(history=["x"]))
    assert undo_only.can_undo and not undo_only.can_redo
    redo_only = menu_state(session(redo_history=["y"]))
    assert redo_only.can_redo and not redo_only.can_undo


def test_menu_state_dirty_does_not_come_from_the_history():
    assert menu_state(session(dirty=True)).dirty
    assert not menu_state(session(history=["x"])).dirty


HOME = Path("/home/phil")


@pytest.mark.parametrize(
    "path, dirty, title",
    [
        (None, False, "Edge Shell settings"),
        (HOME / ".config/edge-shell/config.toml", False, "~/.config/edge-shell/config.toml"),
        (HOME / ".config/edge-shell/config.toml", True, "*~/.config/edge-shell/config.toml"),
        (Path("/tmp/edge-settings.toml"), True, "*/tmp/edge-settings.toml"),
    ],
)
def test_window_title(path, dirty, title):
    expected = title if path is None else f"{title} - {TITLE}"
    assert window_title(path, dirty, home=HOME) == expected
    assert TITLE == "Edge Shell settings"
