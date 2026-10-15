"""settings.controller: the menu bar, the window's actions and the unsaved-changes question. The
controller is a plain Gtk.Box: no window is created, and the dialogs are a fake (no dialog
runs)."""

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
pytest.importorskip("tomlkit")

from gi.repository import Gtk  # noqa: E402

if not Gtk.init_check()[0]:
    pytest.skip("no display", allow_module_level=True)

from settings import files  # noqa: E402
from settings.controller import SettingsController  # noqa: E402
from settings.fileops import Answer  # noqa: E402
from settings.session import SettingsSession  # noqa: E402

USER = """\
# gate config
[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]
panel = "edge"
name = "dock"
widget = "dock"
"""
SHELL = ("monitors", "HDMI-A-1", "shell")
DEPTH = ("monitors", "HDMI-A-1", "panels", 0, "depth")


class FakeDialogs:
    """Records every question and answers from its attributes; never shows anything."""

    def __init__(self):
        self.calls = []
        self.unsaved = Answer.CANCEL
        self.revert_ok = False

    def ask_unsaved(self, _parent, path):
        self.calls.append(("unsaved", path))
        return self.unsaved

    def confirm_revert(self, _parent, text):
        self.calls.append(("revert", text))
        return self.revert_ok


@pytest.fixture
def make(tmp_path, fake_registry):
    path = tmp_path / "config.toml"
    path.write_text(USER)
    made = []

    def _make():
        quits = []
        dialogs = FakeDialogs()
        c = SettingsController(
            path, SettingsSession(path), [], dialogs, quit=lambda: quits.append(1)
        )
        c.dialogs_, c.quits = dialogs, quits
        made.append(c)
        return c, path

    yield _make
    for c in made:
        c.destroy()


@pytest.fixture
def pending(monkeypatch):
    """Spin pauses never fire on their own: a typed value stays pending until flushed."""
    import settings.fields as fields

    monkeypatch.setattr(fields.GLib, "timeout_add", lambda _ms, _fn: 3)
    monkeypatch.setattr(fields.GLib, "source_remove", lambda _id: None)


def row(c, path):
    return next(r for r in c.view.rows if r.path == path)


def on(c, name):
    return c.actions.lookup_action(name).get_enabled()


def run(c, name):
    c.actions.activate_action(name, None)


def menu_items(c, title):
    return [i for i in c.menus[title].get_children() if not isinstance(i, Gtk.SeparatorMenuItem)]


def test_the_menu_bar_shows_the_menus_and_their_shortcuts(make):
    c, _ = make()
    assert [i.get_label() for i in c.menubar.get_children()] == ["_File", "_Edit", "_Help"]
    edit = menu_items(c, "Edit")
    assert [i.get_label() for i in edit] == [
        "_Undo",
        "_Redo",
        "Cu_t",
        "_Copy",
        "_Paste",
        "Re_vert all…",
    ]
    assert [i.get_action_name() for i in edit][:2] == ["win.undo", "win.redo"]
    key, mods = edit[1].get_child().get_accel()  # the first of Redo's two shortcuts
    assert Gtk.accelerator_name(key, mods) == "<Primary><Shift>z"
    save = menu_items(c, "File")[2]
    assert save.get_label() == "_Save" and save.get_action_name() == "win.save"
    assert Gtk.accelerator_name(*save.get_child().get_accel()) == "<Primary>s"


def test_the_menus_have_separators_between_their_groups(make):
    c, _ = make()

    def shape(menu):
        return [
            "-" if isinstance(i, Gtk.SeparatorMenuItem) else "item" for i in menu.get_children()
        ]

    assert shape(c.menus["File"]) == ["item"] * 2 + ["-"] + ["item"] * 2 + ["-"] + ["item"] * 2
    assert shape(c.menus["Edit"]) == ["item"] * 2 + ["-"] + ["item"] * 3 + ["-", "item"]
    assert shape(c.menus["Help"]) == ["item"]


def test_items_follow_the_session(make):
    c, _ = make()
    # Save and Undo work whenever a config is open (a pending value is applied first)
    assert on(c, "save") and on(c, "undo") and not on(c, "redo") and not on(c, "revert")
    undo_item = menu_items(c, "Edit")[0]
    assert undo_item.get_sensitive()  # the menu item follows its action
    c.view._on_change(DEPTH, 90)
    assert on(c, "undo") and on(c, "save") and on(c, "revert") and not on(c, "redo")
    run(c, "undo")
    assert on(c, "redo") and not on(c, "revert")  # back at the start: nothing to revert


def test_the_top_bars_undo_button_is_the_undo_action(make):
    c, path = make()
    button = c.view.undo_button
    assert button.get_action_name() == "win.undo"
    assert button.get_sensitive() == on(c, "undo") is True  # enabled whenever Undo is
    c.view._on_change(DEPTH, 90)
    c.view._on_change(SHELL, "both")
    button.clicked()  # one click is one undo (not the action and a handler of its own)
    assert 'shell = "edge"' in path.read_text() and "depth = 90" in path.read_text()
    c.actions.lookup_action("undo").set_enabled(False)
    assert not button.get_sensitive()  # it follows the action, not the history
    c.sync()
    assert button.get_sensitive()


def test_save_and_undo_stay_on_while_a_value_is_pending(make, pending):
    c, path = make()
    row(c, DEPTH).editor.widget.set_value(120)  # typed, inside the spin's pause: no history yet
    assert not c.session.history and not c.session.dirty
    assert on(c, "save") and on(c, "undo")
    run(c, "undo")  # Ctrl+Z applies the pending value first, then undoes it
    assert path.read_text() == USER and on(c, "redo")


def test_undo_and_redo_from_the_menu(make):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    run(c, "undo")
    assert path.read_text() == USER
    run(c, "redo")
    assert "depth = 90" in path.read_text()
    assert row(c, DEPTH).editor.widget.get_value() == 90


def test_redo_applies_a_pending_value_first_which_ends_the_redo_line(make, pending):
    c, path = make()
    c.view._on_change(SHELL, "both")
    run(c, "undo")
    row(c, DEPTH).editor.widget.set_value(120)  # typed, inside the spin's pause
    run(c, "redo")
    assert "depth = 120" in path.read_text() and 'shell = "edge"' in path.read_text()
    assert not on(c, "redo")


def test_save_from_the_menu_sets_the_saved_point(make):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    run(c, "save")
    assert not c.session.dirty
    assert path.with_name("config.toml.bak").read_text() == path.read_text()


def test_save_applies_a_pending_value_first(make, pending):
    c, path = make()
    row(c, DEPTH).editor.widget.set_value(120)
    c.save()  # Ctrl+S while the spin is in its pause
    assert "depth = 120" in path.read_text() and not c.session.dirty


def test_a_failed_save_is_shown_and_keeps_the_changes_unsaved(make, monkeypatch):
    c, path = make()
    c.view._on_change(DEPTH, 90)

    def boom(_path):
        raise PermissionError("denied")

    monkeypatch.setattr(files, "write_backup", boom)
    run(c, "save")
    assert c.session.dirty and on(c, "save")
    assert "cannot write" in c.view.banner_label.get_text() and c.view.banner.get_visible()


def test_revert_all_from_the_menu_asks_first(make):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    run(c, "revert")
    assert c.dialogs_.calls[0][0] == "revert" and "depth = 90" in path.read_text()
    c.dialogs_.revert_ok = True
    run(c, "revert")
    assert path.read_text() == USER


def test_exit_of_a_clean_config_quits_without_asking(make):
    c, _ = make()
    run(c, "exit")
    assert c.quits == [1] and c.dialogs_.calls == []


def test_exit_with_unsaved_changes_asks_and_cancel_stays(make):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    run(c, "exit")
    assert c.dialogs_.calls == [("unsaved", path)] and c.quits == []
    assert "depth = 90" in path.read_text()


def test_exit_discard_puts_the_saved_file_back_and_quits(make):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    c.dialogs_.unsaved = Answer.DISCARD
    run(c, "exit")
    assert path.read_text() == USER and c.quits == [1]


def test_exit_save_keeps_the_changes_and_quits(make):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    c.dialogs_.unsaved = Answer.SAVE
    run(c, "exit")
    assert "depth = 90" in path.read_text() and c.quits == [1]
    assert path.with_name("config.toml.bak").read_text() == path.read_text()


def test_a_pending_value_counts_as_a_change_when_leaving(make, pending):
    c, path = make()
    row(c, DEPTH).editor.widget.set_value(120)
    assert c.can_leave() is False  # applied, then asked (answered Cancel)
    assert "depth = 120" in path.read_text() and c.dialogs_.calls == [("unsaved", path)]


def test_leaving_stays_open_once_after_a_refused_flush(make, pending):
    c, path = make()
    row(c, DEPTH).editor.widget.set_value(120)
    path.write_text(USER.replace('shell = "edge"', 'shell = "both"'))  # by hand
    assert c.can_leave() is False  # stays open once, the warning is on screen
    assert "changed outside" in c.view.banner_label.get_text()
    assert c.can_leave() is True  # the hand edit is the saved point: nothing to ask
    assert c.dialogs_.calls == []


def test_a_discard_that_meets_a_hand_edit_stays_and_says_so(make):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    hand = USER.replace('shell = "edge"', 'shell = "both"')

    def ask(_parent, p):
        path.write_text(hand)  # edited by hand while the question was open
        return Answer.DISCARD

    c.dialogs_.ask_unsaved = ask
    assert c.can_leave() is False and path.read_text() == hand
    assert "nothing was discarded" in c.view.banner_label.get_text()
    # the rows were rebuilt from the hand edit, not left showing the old value
    assert row(c, SHELL).editor.widget.get_active_id() == "both"


def test_a_hand_edit_that_makes_the_file_invalid_updates_the_items(make):
    c, path = make()
    assert not on(c, "revert")
    path.write_text("[theme\n")  # by hand: invalid, the pages go insensitive
    c.file_changed()
    assert c.session.config is None and on(c, "revert")  # the invalid text can be reverted


def test_leaving_updates_the_items_after_a_discard(make):
    c, _ = make()
    c.view._on_change(DEPTH, 90)
    assert on(c, "revert")
    c.dialogs_.unsaved = Answer.DISCARD
    assert c.can_leave() is True
    assert not on(c, "revert")  # the file is back at the start


def test_exit_answered_save_where_the_save_fails_stays_and_says_so(make, monkeypatch):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    c.dialogs_.unsaved = Answer.SAVE

    def boom(_path):
        raise PermissionError("denied")

    monkeypatch.setattr(files, "write_backup", boom)
    assert c.can_leave() is False
    run(c, "exit")
    assert c.quits == [] and c.session.dirty
    assert c.view.banner.get_visible() and "Not saved" in c.view.banner_label.get_text()
