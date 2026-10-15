"""settings.app: the window's own process (never run here: Gtk.Application.run would take the
session bus name)."""

import sys
from pathlib import Path

import pytest

pytest.importorskip("gi")

import settings.app as app_mod  # noqa: E402


def test_connected_outputs_from_kscreen(monkeypatch):
    text = (
        '{"outputs": [{"name": "HDMI-A-1", "enabled": true, "scale": 1,'
        ' "pos": {"x": 0, "y": 0}, "size": {"width": 1920, "height": 1080}}]}'
    )
    monkeypatch.setattr(app_mod, "read_kscreen_json", lambda: text)
    assert [(o.name, o.width) for o in app_mod.connected_outputs()] == [("HDMI-A-1", 1920)]


def test_connected_outputs_is_empty_when_kscreen_fails(monkeypatch, caplog):
    def fail():
        raise OSError("no kscreen-doctor")

    monkeypatch.setattr(app_mod, "read_kscreen_json", fail)
    assert app_mod.connected_outputs() == []
    assert "kscreen-doctor failed" in caplog.text


def test_app_id_depends_on_the_config_path(tmp_path):
    """A second --settings on ANOTHER file must open its own window, not raise the first one
    (which edits a different file); the same file through a symlink is the same window."""
    from gi.repository import Gio

    a, b = tmp_path / "a.toml", tmp_path / "b.toml"
    a.write_text("")
    link = tmp_path / "link.toml"
    link.symlink_to(a)
    assert app_mod.app_id(a) != app_mod.app_id(b)
    assert app_mod.app_id(a) == app_mod.app_id(link)
    assert app_mod.app_id(a).startswith(app_mod.APP_ID + ".c")
    assert Gio.Application.id_is_valid(app_mod.app_id(a))


def test_a_second_launch_does_not_import_the_widgets(monkeypatch, tmp_path):
    """The second instance only asks the first to come forward: no Fabric import."""
    pytest.importorskip("tomlkit")

    class Remote:
        failed = False

        def __init__(self, path, default_path):
            self.path = path

        def register(self, _cancellable):
            return True

        def get_is_remote(self):
            return True

        def run(self, argv):
            return 0

    monkeypatch.setattr(app_mod, "SettingsApp", Remote)
    monkeypatch.delitem(sys.modules, "widgets", raising=False)
    assert app_mod.run_settings(tmp_path / "c.toml") == 0
    assert "widgets" not in sys.modules


def test_without_tomlkit_the_window_explains_how_to_install_it(monkeypatch, tmp_path, capsys):
    monkeypatch.setitem(sys.modules, "tomlkit", None)  # import tomlkit -> ImportError
    assert app_mod.run_settings(tmp_path / "c.toml") == 2
    assert "pip install" in capsys.readouterr().err


def test_an_unreadable_config_fails_without_a_window(tmp_path, capsys, fake_registry):
    pytest.importorskip("tomlkit")
    folder = tmp_path / "config.toml"
    folder.mkdir()  # reading it raises IsADirectoryError
    app = app_mod.SettingsApp.__new__(app_mod.SettingsApp)  # not registered on the bus
    app.path, app.default_path = folder, app_mod.DEFAULT_PATH
    app.window, app.failed, app._watcher = None, False, None
    app_mod.SettingsApp.do_activate(app)
    assert app.failed and app.window is None
    assert "cannot open the settings" in capsys.readouterr().err


def test_the_settings_process_never_imports_fabric_windows():
    """The settings window is a plain xdg toplevel: importing its modules must not pull in
    GtkLayerShell or Fabric (checked in a fresh interpreter; sys.modules here is shared)."""
    import subprocess

    code = (
        "import sys, settings.window, settings.app;"
        "bad = [m for m in sys.modules if m.split('.')[0] in ('fabric', 'widgets')"
        " or m == 'gi.repository.GtkLayerShell'];"
        "print(bad); sys.exit(1 if bad else 0)"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr


def test_a_failed_activation_makes_the_exit_code_2(monkeypatch, tmp_path):
    pytest.importorskip("tomlkit")

    class Failing:
        failed = True

        def __init__(self, path, default_path):
            pass

        def register(self, _cancellable):
            return True

        def get_is_remote(self):
            return False

        def run(self, argv):
            return 0  # Gtk.Application.run returns 0 when activate just returns

    monkeypatch.setattr(app_mod, "SettingsApp", Failing)
    assert app_mod.run_settings(tmp_path / "c.toml") == 2


def test_closing_the_window_flushes_and_ctrl_z_undoes(tmp_path, fake_registry):
    """Built but never shown: only the toplevel's signals and its win.undo action are used."""
    pytest.importorskip("tomlkit")
    from gi.repository import Gdk, Gtk

    if not Gtk.init_check()[0]:
        pytest.skip("no display")
    from settings.fileops import Answer
    from settings.session import SettingsSession
    from settings.view import SettingsView
    from settings.window import TITLE, SettingsWindow

    assert TITLE == "Edge Shell settings"
    calls = []

    class Cancel:  # the unsaved-changes question, answered Cancel (no dialog runs)
        def ask_unsaved(self, _parent, _path):
            calls.append("asked")
            return Answer.CANCEL

        def confirm_revert(self, _parent, _text):
            return False

    monkey = pytest.MonkeyPatch()
    monkey.setattr(SettingsView, "flush", lambda self: calls.append("flush"))
    monkey.setattr(SettingsView, "undo", lambda self: calls.append("undo"))
    try:
        cfg = tmp_path / "c.toml"
        cfg.write_text("")
        session = SettingsSession(cfg)
        session.apply(lambda d: d.set(("theme", "accent"), "#112233"))  # something to undo
        win = SettingsWindow(session, [], dialogs=Cancel())
        assert win.get_title() == TITLE
        win.controller.actions.lookup_action("undo").activate(None)
        assert calls == ["undo"]
        # unsaved changes, answered Cancel: the window stays open
        assert win.emit("delete-event", Gdk.Event.new(Gdk.EventType.DELETE)) is True
        assert calls == ["undo", "flush", "asked"]
    finally:
        monkey.undo()
        win.destroy()


def test_the_first_instance_loads_the_widget_registry(monkeypatch, tmp_path):
    """Without `import widgets` the registry is empty and every config with panels is invalid."""
    pytest.importorskip("tomlkit")
    import widgets  # noqa: F401  (loaded, so it can be put back below)

    class First:
        failed = False

        def __init__(self, path, default_path):
            pass

        def register(self, _cancellable):
            return True

        def get_is_remote(self):
            return False

        def run(self, argv):
            return 0

    monkeypatch.setattr(app_mod, "SettingsApp", First)
    monkeypatch.delitem(sys.modules, "widgets")
    assert app_mod.run_settings(tmp_path / "c.toml") == 0
    assert "widgets" in sys.modules


def _activatable(path, default_path=None):
    """A SettingsApp that is built but never registered on the bus, with `present` stubbed."""
    app = app_mod.SettingsApp(path, default_path or app_mod.DEFAULT_PATH)
    return app


@pytest.fixture
def gtk_app(monkeypatch, tmp_path, fake_registry):
    pytest.importorskip("tomlkit")
    from gi.repository import Gtk

    if not Gtk.init_check()[0]:
        pytest.skip("no display")
    from settings.window import SettingsWindow

    presented = []
    monkeypatch.setattr(SettingsWindow, "present", lambda self: presented.append(self))
    monkeypatch.setattr(app_mod, "connected_outputs", lambda: [])
    apps = []

    def make(path):
        app = _activatable(path)
        apps.append(app)
        return app

    make.presented = presented
    yield make
    for app in apps:
        if app.window is not None:
            app.window.destroy()


def test_activation_sets_the_undo_accel_watches_the_file_and_presents_once(gtk_app, tmp_path):
    app = gtk_app(tmp_path / "sub" / "c.toml")
    app_mod.SettingsApp.do_activate(app)
    assert app.get_accels_for_action("win.undo") == ["<Primary>z"]
    assert app.get_accels_for_action("win.redo") == ["<Primary><Shift>z", "<Primary>y"]
    assert app.get_accels_for_action("win.save") == ["<Primary>s"]
    assert app.get_accels_for_action("win.copy") == []  # the focused widget's own binding
    assert app._watcher is not None
    first = app.window
    seen = []
    first.file_changed = lambda: seen.append("changed")  # what the watcher reports reaches it
    app._watcher._on_change()
    assert seen == ["changed"]
    app_mod.SettingsApp.do_activate(app)  # a second launch: the open window comes forward
    assert app.window is first
    assert gtk_app.presented == [first, first]


def test_an_uncreatable_config_folder_exits_cleanly_without_a_window(gtk_app, capsys):
    app = gtk_app(Path("/proc/nope/c.toml"))
    app_mod.SettingsApp.do_activate(app)
    assert app.failed
    assert app.window is None and app.get_windows() == []
    assert "cannot open the settings" in capsys.readouterr().err


def _window_with_view_flush(monkeypatch, tmp_path, fails):
    from settings.session import SettingsSession
    from settings.view import SettingsView
    from settings.window import SettingsWindow

    def flush(self):
        self.save_failed = fails()

    monkeypatch.setattr(SettingsView, "flush", flush)
    cfg = tmp_path / "c.toml"
    cfg.write_text("")
    return SettingsWindow(SettingsSession(cfg), [])


def test_a_failed_save_keeps_the_window_open_once(monkeypatch, tmp_path, fake_registry):
    """The close flush could not write: the banner stays visible; closing again closes."""
    pytest.importorskip("tomlkit")
    from gi.repository import Gdk, Gtk

    if not Gtk.init_check()[0]:
        pytest.skip("no display")
    state = {"fail": True}
    win = _window_with_view_flush(monkeypatch, tmp_path, lambda: state["fail"])
    try:
        close = lambda: win.emit("delete-event", Gdk.Event.new(Gdk.EventType.DELETE))  # noqa: E731
        assert close() is True  # kept open: the error is on screen
        assert close() is False  # asked twice: closes anyway
    finally:
        win.destroy()
    state["fail"] = False
    win = _window_with_view_flush(monkeypatch, tmp_path, lambda: state["fail"])
    try:
        assert win.emit("delete-event", Gdk.Event.new(Gdk.EventType.DELETE)) is False
    finally:
        win.destroy()


# ---- shortcuts reach the window's actions with no focused widget -------------------------------


def _press(win, name):
    """Ctrl+<key> through Gtk.Window.activate_key: what the toplevel does with its
    application's accelerators when no widget handles the key first."""
    from gi.repository import Gdk

    keyval = Gdk.keyval_from_name(name)
    ok, entries = Gdk.Keymap.get_default().get_entries_for_keyval(keyval)
    assert ok
    event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
    event.keyval = keyval
    event.hardware_keycode = entries[0].keycode
    event.group = entries[0].group
    event.state = Gdk.ModifierType.CONTROL_MASK
    return win.activate_key(event.key)  # the event outlives the call


class Dialogs:
    """The window's dialogs, answered from attributes; nothing is ever shown."""

    def __init__(self, answer=None):
        from settings.fileops import Answer

        self.answer = answer or Answer.CANCEL
        self.asked = []

    def ask_unsaved(self, _parent, path):
        self.asked.append(path)
        return self.answer

    def confirm_revert(self, _parent, _text):
        return False


@pytest.fixture
def shortcut_window(tmp_path, fake_registry):
    """A window (built, never shown) in a Gtk.Application that has the real accelerators."""
    pytest.importorskip("tomlkit")
    from gi.repository import Gtk

    if not Gtk.init_check()[0]:
        pytest.skip("no display")
    from settings.menus import ACCELS
    from settings.session import SettingsSession
    from settings.window import SettingsWindow

    cfg = tmp_path / "c.toml"
    cfg.write_text('[theme]\naccent = "#112233"\n')
    app = Gtk.Application(application_id="org.example.shortcuts")
    for action, accels in ACCELS.items():
        app.set_accels_for_action(action, accels)
    made = []

    def make(dialogs=None):
        win = SettingsWindow(
            SettingsSession(cfg), [], application=app, dialogs=dialogs or Dialogs()
        )
        made.append(win)
        return win

    make.cfg = cfg
    yield make
    for win in made:
        win.destroy()


def test_shortcuts_work_with_no_focused_widget(shortcut_window):
    win = shortcut_window()
    assert win.get_focus() is None
    win.view.session.apply(lambda d: d.set(("theme", "accent"), "#445566"))
    win.view.rebuild()
    assert _press(win, "z") is True  # Ctrl+Z
    assert "#112233" in shortcut_window.cfg.read_text()
    assert _press(win, "y") is True  # Ctrl+Y
    assert "#445566" in shortcut_window.cfg.read_text()
    assert _press(win, "s") is True  # Ctrl+S
    assert not win.view.session.dirty


def test_shortcuts_work_after_a_rebuild_removed_the_focused_widget(shortcut_window):
    from gi.repository import Gtk

    win = shortcut_window()
    win.view.session.apply(lambda d: d.set(("theme", "accent"), "#445566"))
    win.view.rebuild()
    spin = next(
        w for r in win.view.rows for w in [r.editor.widget] if isinstance(w, Gtk.SpinButton)
    )
    win.set_focus(spin)
    assert win.get_focus() is spin
    win.view.rebuild()  # the pages (and the focused spin) are removed
    assert win.get_focus() is None
    assert _press(win, "z") is True
    assert "#112233" in shortcut_window.cfg.read_text()
    assert _press(win, "y") is True
    assert "#445566" in shortcut_window.cfg.read_text()
    dialogs = Dialogs()
    win2 = shortcut_window(dialogs)  # Ctrl+Q with unsaved changes goes through the fake
    win2.view.session.apply(lambda d: d.set(("theme", "accent"), "#778899"))
    assert _press(win2, "q") is True
    assert dialogs.asked == [shortcut_window.cfg] and win2.get_realized() is False


def test_the_window_destroys_itself_on_exit_of_a_clean_config(shortcut_window):
    win = shortcut_window()
    destroyed = []
    win.connect("destroy", lambda _w: destroyed.append(1))
    win.controller.exit()
    assert destroyed == [1]
