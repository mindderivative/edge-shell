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
        self.paths = {}  # what each file chooser "returns" by kind; missing: cancelled
        self.chosen = None  # (kind, folder, suggested name) of the last chooser

    def ask_unsaved(self, _parent, path):
        self.calls.append(("unsaved", path))
        return self.unsaved

    def confirm_revert(self, _parent, text):
        self.calls.append(("revert", text))
        return self.revert_ok

    def _choose(self, kind, folder, name):
        self.chosen = (kind, folder, name)
        return self.paths.get(kind)

    def choose_new(self, _parent, folder, name):
        return self._choose("new", folder, name)

    def choose_open(self, _parent, folder):
        return self._choose("open", folder, None)

    def choose_save_as(self, _parent, folder, name):
        return self._choose("save-as", folder, name)

    def about(self, _parent, info):
        self.calls.append(("about", info))


@pytest.fixture
def make(tmp_path, fake_registry):
    path = tmp_path / "config.toml"
    path.write_text(USER)
    made = []

    def _make(user_path=None):
        quits, launches, titles = [], [], []
        dialogs = FakeDialogs()
        c = SettingsController(
            path,
            SettingsSession(path),
            [],
            dialogs,
            quit=lambda: quits.append(1),
            launch=launches.append,  # nothing is spawned
            user_path=user_path or tmp_path / "home" / "edge-shell" / "config.toml",
            on_title=titles.append,
        )
        c.dialogs_, c.quits, c.launches, c.titles = dialogs, quits, launches, titles
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


# ---- New, Open, Save As, Close (Task 6) ------------------------------------------------------
def test_close_shows_the_empty_page_where_only_new_open_and_exit_work(make):
    c, path = make()
    run(c, "close")
    assert c.view is None and c.session is None
    assert c.body.get_visible_child_name() == "empty"
    for name in ("save", "save-as", "close", "undo", "redo", "revert"):
        assert not on(c, name), name
    assert on(c, "new") and on(c, "open") and on(c, "exit")
    c.file_changed()  # the watcher still reports the file: nothing to do
    path.write_text(USER + "# by hand\n")
    c.file_changed()
    assert c.view is None


def test_close_with_unsaved_changes_asks_and_cancel_keeps_the_config(make):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    run(c, "close")
    assert c.view is not None and c.dialogs_.calls == [("unsaved", path)]
    c.dialogs_.unsaved = Answer.DISCARD
    run(c, "close")
    assert c.view is None and path.read_text() == USER


def test_open_shows_another_file_in_its_own_window_and_closes_this_one(make, tmp_path):
    c, _ = make()
    other = tmp_path / "other.toml"
    other.write_text(USER)
    c.dialogs_.paths["open"] = other
    run(c, "open")
    assert c.dialogs_.chosen == ("open", tmp_path / "home" / "edge-shell", None)
    assert c.launches == [other] and c.quits == [1]


def test_open_asks_about_unsaved_changes_first(make, tmp_path):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    other = tmp_path / "other.toml"
    other.write_text(USER)
    c.dialogs_.paths["open"] = other
    run(c, "open")  # answered Cancel
    assert c.launches == [] and c.quits == [] and c.dialogs_.calls == [("unsaved", path)]


def test_a_cancelled_chooser_does_nothing(make):
    c, _ = make()
    for name in ("open", "new", "save-as"):
        run(c, name)
    assert c.launches == [] and c.quits == [] and c.view is not None


def test_open_of_this_windows_own_file_only_says_so(make):
    c, path = make()
    c.dialogs_.paths["open"] = path
    run(c, "open")
    assert c.launches == [] and "already open" in c.view.banner_label.get_text()


def test_open_refuses_a_file_it_cannot_read(make, tmp_path):
    c, _ = make()
    binary = tmp_path / "image.png"
    binary.write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe")
    c.dialogs_.paths["open"] = binary
    run(c, "open")
    assert c.launches == [] and "Cannot open it" in c.view.banner_label.get_text()


def test_new_creates_the_file_and_opens_it_in_its_own_window(make, tmp_path):
    from settings.fileops import NEW_TEXT

    c, _ = make()
    new = tmp_path / "home" / "edge-shell" / "config.toml"
    c.dialogs_.paths["new"] = new
    run(c, "new")
    assert c.dialogs_.chosen == ("new", new.parent, "config.toml")
    assert new.read_text() == NEW_TEXT and c.launches == [new] and c.quits == [1]


def test_new_never_replaces_a_file(make, tmp_path):
    c, path = make()
    c.dialogs_.paths["new"] = path
    run(c, "new")
    assert path.read_text() == USER and c.launches == []
    assert "already exists" in c.view.banner_label.get_text()


def test_save_as_copies_the_changes_and_puts_this_file_back_as_last_saved(make, tmp_path):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    copy = tmp_path / "copy.toml"
    c.dialogs_.paths["save-as"] = copy
    run(c, "save-as")
    assert c.dialogs_.chosen == ("save-as", tmp_path / "home" / "edge-shell", "config.toml")
    assert "depth = 90" in copy.read_text() and path.read_text() == USER
    assert c.launches == [copy] and c.quits == [1]


def test_save_as_onto_this_file_is_save(make):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    c.dialogs_.paths["save-as"] = path
    run(c, "save-as")
    assert not c.session.dirty and "depth = 90" in path.read_text() and c.launches == []


def test_open_from_the_empty_page_shows_this_windows_file_here(make):
    c, path = make()
    run(c, "close")
    c.dialogs_.paths["open"] = path
    run(c, "open")
    assert c.view is not None and c.launches == [] and c.quits == []
    assert c.body.get_visible_child_name() == "config" and on(c, "close")


def test_a_window_that_cannot_be_started_is_shown_and_this_one_stays(make, tmp_path):
    c, _ = make()

    def fail(_path):
        raise OSError("no such interpreter")

    c.launch = fail
    other = tmp_path / "other.toml"
    other.write_text(USER)
    c.dialogs_.paths["open"] = other
    run(c, "open")
    assert c.quits == [] and "no such interpreter" in c.view.banner_label.get_text()


def test_an_error_on_the_empty_page_is_shown_there(make, tmp_path):
    c, _ = make()
    run(c, "close")
    c.dialogs_.paths["open"] = tmp_path / "missing.toml"
    run(c, "open")
    assert c.notice.get_visible() and "does not exist" in c.notice.get_text()


def test_new_asks_about_unsaved_changes_before_creating_the_file(make, tmp_path):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    new = tmp_path / "home" / "edge-shell" / "fresh.toml"
    c.dialogs_.paths["new"] = new
    run(c, "new")  # answered Cancel
    assert not new.exists() and c.launches == [] and c.dialogs_.calls == [("unsaved", path)]


def test_the_empty_pages_error_goes_away_when_the_file_is_shown_again(make, tmp_path):
    c, path = make()
    run(c, "close")
    c.dialogs_.paths["open"] = tmp_path / "missing.toml"
    run(c, "open")
    assert c.notice.get_visible()
    c.dialogs_.paths["open"] = path
    run(c, "open")
    assert not c.notice.get_visible()


# ---- the review of Tasks 5 and 6 ---------------------------------------------------------------
def _typed_depth(c, value=90):
    """Depth typed into its spin and written (flushed); returns the value it showed before."""
    widget = row(c, DEPTH).editor.widget
    before = widget.get_value()
    widget.set_value(value)
    c.view.flush()
    assert f"depth = {value}" in c.session.text
    return before


def test_a_discard_followed_by_a_window_that_cannot_start_shows_the_saved_values(make, tmp_path):
    c, path = make()
    before = _typed_depth(c)

    def fail(_path):
        raise OSError("no such interpreter")

    c.launch = fail
    other = tmp_path / "other.toml"
    other.write_text(USER)
    c.dialogs_.paths["open"] = other
    c.dialogs_.unsaved = Answer.DISCARD
    run(c, "open")
    assert path.read_text() == USER and not c.session.dirty and c.quits == []
    assert row(c, DEPTH).editor.widget.get_value() == before  # not the discarded 90
    widget = row(c, DEPTH).editor.widget
    widget.set_value(90)  # typing it again is a real change, not a no-op on a stale row
    c.view.flush()
    assert "depth = 90" in path.read_text()


def test_new_onto_an_existing_file_asks_nothing_and_keeps_the_edits(make):
    c, path = make()
    _typed_depth(c)
    c.dialogs_.paths["new"] = path
    c.dialogs_.unsaved = Answer.DISCARD
    run(c, "new")
    assert c.dialogs_.calls == [] and "depth = 90" in path.read_text() and c.session.dirty
    assert "already exists" in c.view.banner_label.get_text() and c.launches == []


def test_new_adds_toml_to_a_name_without_a_suffix(make, tmp_path):
    c, _ = make()
    folder = tmp_path / "home" / "edge-shell"
    c.dialogs_.paths["new"] = folder / "fresh"
    run(c, "new")
    assert (folder / "fresh.toml").exists() and not (folder / "fresh").exists()
    assert c.launches == [folder / "fresh.toml"]


def test_new_of_a_name_of_only_dots_launches_the_file_it_created(make, tmp_path):
    c, _ = make()
    folder = tmp_path / "home" / "edge-shell"
    c.dialogs_.paths["new"] = folder / "..."
    run(c, "new")
    assert c.launches == [folder / "config.toml"] and c.launches[0].exists()
    assert not (folder / ".toml").exists()


def test_new_launches_the_path_create_new_returns(make, monkeypatch, tmp_path):
    import settings.controller as ctl

    c, _ = make()
    other = tmp_path / "elsewhere.toml"
    monkeypatch.setattr(ctl, "create_new", lambda _p: other)
    c.dialogs_.paths["new"] = tmp_path / "home" / "edge-shell" / "x"
    run(c, "new")
    assert c.launches == [other]


def test_the_leave_warning_rearms_after_the_state_changes(make, pending):
    c, path = make()
    row(c, DEPTH).editor.widget.set_value(120)
    path.write_text(USER.replace('shell = "edge"', 'shell = "both"'))  # by hand
    assert c.can_leave() is False  # the first warning
    assert c.can_leave() is True  # asked again, it goes on
    c.open_session(SettingsSession(path))  # a new state, then a later unrelated failure
    row(c, DEPTH).editor.widget.set_value(130)
    path.write_text(USER.replace('shell = "edge"', 'shell = "edge"\n# again'))
    assert c.can_leave() is False  # warns once again


def test_the_leave_warning_rearms_after_a_clean_flush(make, pending):
    c, path = make()
    row(c, DEPTH).editor.widget.set_value(120)
    path.write_text(USER.replace('shell = "edge"', 'shell = "both"'))
    assert c.can_leave() is False  # warned
    c.view.save_failed = False
    c.view.refused_outside = False
    assert c.can_leave() is True  # clean: consumed
    assert c._leave_warned is False


def test_save_as_applies_a_pending_value_first(make, pending, tmp_path):
    c, _ = make()
    row(c, DEPTH).editor.widget.set_value(120)  # typed, inside the spin's pause
    copy = tmp_path / "copy.toml"
    c.dialogs_.paths["save-as"] = copy
    run(c, "save-as")
    assert "depth = 120" in copy.read_text()


@pytest.mark.parametrize("failure", ["config", "outside"])
def test_save_as_where_the_file_cannot_be_put_back_stays_and_says_so(make, tmp_path, failure):
    from settings.session import ChangedOutside
    from shell.config.models import ConfigError

    c, path = make()
    c.view._on_change(DEPTH, 90)
    copy = tmp_path / "copy.toml"
    c.dialogs_.paths["save-as"] = copy
    error = ConfigError("denied") if failure == "config" else ChangedOutside("changed")

    def boom():
        raise error

    c.session.discard = boom
    run(c, "save-as")
    assert "depth = 90" in copy.read_text()  # the copy was written
    assert c.launches == [] and c.quits == []  # but the window stays
    text = c.view.banner_label.get_text()
    assert "was not put back" in text and str(copy) in text


def test_save_as_stops_when_the_flush_was_refused(make, pending, tmp_path):
    c, path = make()
    row(c, DEPTH).editor.widget.set_value(120)
    path.write_text(USER.replace('shell = "edge"', 'shell = "both"'))  # by hand
    copy = tmp_path / "copy.toml"
    c.dialogs_.paths["save-as"] = copy
    run(c, "save-as")
    assert c.dialogs_.chosen is None and not copy.exists() and c.launches == []


def test_save_as_stays_open_when_the_flush_could_not_write(make, pending, tmp_path, monkeypatch):
    c, path = make()
    row(c, DEPTH).editor.widget.set_value(120)  # pending; its write will fail

    def boom(_path):
        raise PermissionError("denied")

    monkeypatch.setattr(files, "write_backup", boom)
    copy = tmp_path / "copy.toml"
    c.dialogs_.paths["save-as"] = copy
    run(c, "save-as")
    assert not copy.exists() and c.launches == [] and c.quits == []
    assert c.dialogs_.chosen is None  # not even asked where to save


def test_save_as_does_not_copy_a_file_changed_by_hand_while_the_chooser_was_open(make, tmp_path):
    c, path = make()
    c.view._on_change(DEPTH, 90)
    copy = tmp_path / "copy.toml"
    hand = USER.replace('shell = "edge"', 'shell = "both"')

    def choose(_parent, _folder, _name):
        path.write_text(hand)  # by hand, while the chooser was open
        return copy

    c.dialogs_.choose_save_as = choose
    run(c, "save-as")
    assert not copy.exists() and c.launches == [] and c.quits == []
    assert path.read_text() == hand and not c.session.changed_outside()
    assert row(c, SHELL).editor.widget.get_active_id() == "both"  # shown from the hand edit
    assert "changed outside" in c.view.banner_label.get_text()


def test_save_as_of_an_unreadable_file_says_so(make, tmp_path, monkeypatch):
    from shell.config.models import ConfigError

    c, _ = make()
    c.dialogs_.paths["save-as"] = tmp_path / "copy.toml"

    def boom():
        raise ConfigError("unreadable")

    monkeypatch.setattr(c.session, "changed_outside", boom)
    run(c, "save-as")
    assert not (tmp_path / "copy.toml").exists() and "Not saved" in c.view.banner_label.get_text()


def test_dropping_the_view_discards_its_rows_and_cancels_its_deferred_rebuild(make):
    from gi.repository import GLib

    c, _ = make()
    view, rows = c.view, list(c.view.rows)
    view._rebuild_soon(defer=True)  # an idle rebuild is waiting
    source = view._rebuild_idle
    assert source and GLib.MainContext.default().find_source_by_id(source) is not None
    c._drop_view()
    assert view._rebuild_idle == 0
    assert GLib.MainContext.default().find_source_by_id(source) is None
    assert rows and all(r._discarding for r in rows)
    assert view.get_parent() is None  # out of the stack
    view.destroy()


def test_reopen_of_a_file_that_cannot_be_read_shows_an_error(make):
    c, path = make()
    run(c, "close")
    path.unlink()
    path.mkdir()  # reading it now raises
    c.reopen()
    assert c.view is None and c.notice.get_visible()
    assert "Cannot open it" in c.notice.get_text()


def test_a_new_session_clears_the_leave_warning(make):
    c, path = make()
    c._leave_warned = True
    c.open_session(SettingsSession(path))
    assert c._leave_warned is False


# ---- Cut, Copy, Paste (Task 7) ---------------------------------------------------------------
def clip_on(c):
    return {name for name in ("cut", "copy", "paste") if on(c, name)}


def focus(c, widget):
    c.focus_widget = lambda: widget
    c.sync_clipboard()


def recording(widget):
    """Record the widget's clipboard signals and stop them there: the real clipboard (Phil's
    desktop) is never touched."""
    from gi.repository import GObject

    seen = []

    def record(w, name):
        seen.append(name)
        GObject.signal_stop_emission_by_name(w, name)

    for name in ("cut-clipboard", "copy-clipboard", "paste-clipboard"):
        widget.connect(name, record, name)
    return seen


def test_cut_copy_and_paste_follow_the_focused_entry(make):
    c, _ = make()
    entry = Gtk.Entry(text="Sans, Noto Sans")
    focus(c, entry)
    assert clip_on(c) == {"paste"}  # nothing selected
    entry.select_region(0, 4)
    focus(c, entry)
    assert clip_on(c) == {"cut", "copy", "paste"}
    entry.set_editable(False)
    focus(c, entry)
    assert clip_on(c) == {"copy"}
    focus(c, Gtk.Button(label="Add"))
    assert clip_on(c) == set()
    focus(c, None)
    assert clip_on(c) == set()


def test_a_spin_button_and_a_text_view_count_as_text(make):
    c, _ = make()
    spin = Gtk.SpinButton.new_with_range(0, 100, 1)
    focus(c, spin)
    assert "paste" in clip_on(c)
    view = Gtk.TextView()
    buffer = view.get_buffer()
    buffer.set_text("hello")
    buffer.select_range(buffer.get_start_iter(), buffer.get_iter_at_offset(2))
    focus(c, view)
    assert clip_on(c) == {"cut", "copy", "paste"}


def test_the_items_emit_the_focused_widgets_own_clipboard_signals(make):
    c, _ = make()
    entry = Gtk.Entry(text="Sans")
    entry.select_region(0, 2)
    seen = recording(entry)
    focus(c, entry)
    for name in ("copy", "cut", "paste"):
        run(c, name)
    assert seen == ["copy-clipboard", "cut-clipboard", "paste-clipboard"]


def test_with_no_text_focused_the_items_do_nothing(make):
    c, _ = make()
    entry = Gtk.Entry(text="Sans")
    seen = recording(entry)
    focus(c, Gtk.Button())
    run(c, "paste")  # disabled: nothing runs
    c._clip("paste-clipboard")  # and even if called, only a text widget is asked
    assert seen == []


def test_opening_the_edit_menu_refreshes_cut_copy_and_paste(make):
    c, _ = make()
    entry = Gtk.Entry(text="Sans")
    entry.select_region(0, 2)
    c.focus_widget = lambda: entry  # the focus moved, nothing refreshed yet
    assert clip_on(c) == set()
    edit = c.menus["Edit"]
    edit.show()  # what popping the menu up does first (its popup window stays hidden)
    assert clip_on(c) == {"cut", "copy", "paste"}
    edit.hide()


# ---- About, the title, the default-config note (Task 8) ----------------------------------------
def test_the_title_names_the_file_and_marks_unsaved_changes(make):
    from settings.menus import window_title

    c, path = make()
    clean, dirty = window_title(path, False), window_title(path, True)
    assert clean.endswith(" - Edge Shell settings") and dirty == "*" + clean
    assert c.titles == [clean]
    c.view._on_change(DEPTH, 90)
    assert c.titles[-1] == dirty
    run(c, "undo")  # back at the saved point
    assert c.titles[-1] == clean
    c.view._on_change(DEPTH, 90)
    run(c, "save")
    assert c.titles[-1] == clean
    run(c, "close")
    assert c.titles[-1] == "Edge Shell settings"


def test_about_shows_the_projects_information(make):
    c, _ = make()
    assert on(c, "about")
    run(c, "about")
    (kind, info), *_ = c.dialogs_.calls
    from settings.about import about_info

    assert kind == "about" and info == about_info()  # this checkout's, not another folder's
    assert info.name == "Edge Shell" and info.version


def test_a_config_other_than_the_default_says_so_once(make):
    c, _ = make()
    assert c.view.banner.get_visible()
    assert "not the default config" in c.view.banner_label.get_text()
    c.view._on_change(DEPTH, 90)
    assert not c.view.banner.get_visible()  # gone after the next good change


def test_an_invalid_file_keeps_its_error_banner_not_the_note(make):
    c, path = make()  # a non-default path
    path.write_text("[theme\n")
    c.reopen()
    assert c.session.config is None and c.view.banner.get_visible()
    assert "not the default config" not in c.view.banner_label.get_text()


def test_the_default_config_has_no_note(make, tmp_path):
    c, _ = make(user_path=tmp_path / "config.toml")  # the window's own file
    assert not c.view.banner.get_visible()
