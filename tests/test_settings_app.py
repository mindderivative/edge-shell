"""settings.app: the window's own process (never run here: Gtk.Application.run would take the
session bus name)."""

import sys

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
    from settings.session import SettingsSession
    from settings.view import SettingsView
    from settings.window import TITLE, SettingsWindow

    assert TITLE == "Edge Shell settings"
    calls = []
    monkey = pytest.MonkeyPatch()
    monkey.setattr(SettingsView, "flush", lambda self: calls.append("flush"))
    monkey.setattr(SettingsView, "undo", lambda self: calls.append("undo"))
    try:
        cfg = tmp_path / "c.toml"
        cfg.write_text("")
        win = SettingsWindow(SettingsSession(cfg), [])
        assert win.get_title() == TITLE
        win.lookup_action("undo").activate(None)
        assert calls == ["undo"]
        assert win.emit("delete-event", Gdk.Event.new(Gdk.EventType.DELETE)) is False
        assert calls == ["undo", "flush"]
    finally:
        monkey.undo()
