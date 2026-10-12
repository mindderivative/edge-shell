"""Display-free tests for EdgeShellApp.sync_monitors and the hot-plug timer bookkeeping."""

from types import SimpleNamespace

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import shell.app as app_mod  # noqa: E402


class FakeShell:
    opened: list = []
    closed: list = []

    def __init__(self, name, monitor, config, register, unregister=None):
        self.name = name
        self.monitor = monitor
        FakeShell.opened.append(name)

    def close(self):
        FakeShell.closed.append(self.name)


@pytest.fixture
def env(monkeypatch, make_config):
    FakeShell.opened = []
    FakeShell.closed = []
    mapping: dict = {}
    monkeypatch.setattr(app_mod, "monitors_by_name", lambda: mapping)
    monkeypatch.setattr(app_mod, "MonitorShell", FakeShell)
    store = SimpleNamespace(config=make_config(monitors={"HDMI-A-1": {"shell": "edge"}}))
    app = app_mod.EdgeShellApp(store)
    return app, mapping


def test_opens_shell_for_connected_edge_monitor(env):
    app, mapping = env
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    assert FakeShell.opened == ["HDMI-A-1"]
    assert set(app.shells) == {"HDMI-A-1"}


def test_sync_is_idempotent(env):
    app, mapping = env
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    app.sync_monitors()
    assert FakeShell.opened == ["HDMI-A-1"]
    assert FakeShell.closed == []


def test_empty_mapping_keeps_active_shells(env):
    app, mapping = env
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    mapping.clear()
    app.sync_monitors()
    assert FakeShell.closed == []
    assert set(app.shells) == {"HDMI-A-1"}


def test_empty_mapping_without_shells_is_a_noop(env):
    app, _ = env
    app.sync_monitors()
    assert FakeShell.opened == [] and FakeShell.closed == []
    assert app.shells == {}


def test_replugged_connector_is_reopened(env):
    app, mapping = env
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    assert FakeShell.closed == ["HDMI-A-1"]
    assert FakeShell.opened == ["HDMI-A-1", "HDMI-A-1"]


def test_unconfigured_connected_monitor_is_ignored(env):
    app, mapping = env
    mapping["DP-1"] = object()  # default mode is plasma, so no Edge Shell
    app.sync_monitors()
    assert FakeShell.opened == []


def test_configured_but_disconnected_monitor_is_ignored(env):
    app, mapping = env
    mapping["DP-1"] = object()
    app.sync_monitors()
    assert "HDMI-A-1" not in app.shells


def test_sync_once_syncs_and_drops_its_own_timer_id(env):
    app, mapping = env
    mapping["HDMI-A-1"] = object()
    app._sync_timers = [7, 8]
    assert app._sync_once(7) is False  # GLib.SOURCE_REMOVE
    assert app._sync_timers == [8]
    assert FakeShell.opened == ["HDMI-A-1"]


def test_schedule_sync_only_removes_pending_ids(env, monkeypatch):
    app, _ = env
    removed = []
    ids = iter(range(100, 110))
    monkeypatch.setattr(app_mod.GLib, "source_remove", removed.append)
    monkeypatch.setattr(app_mod.GLib, "timeout_add", lambda ms, fn, *a: next(ids))
    app._schedule_sync()
    assert app._sync_timers == [100, 101]
    app._sync_once(100)  # fired: no longer pending
    app._schedule_sync()
    assert removed == [101]
    assert app._sync_timers == [102, 103]


class FakeFabricApp:
    def __init__(self):
        self.windows = []

    def add_window(self, window):
        self.windows.append(window)

    def remove_window(self, window):
        self.windows.remove(window)  # like Fabric: ValueError if absent


def test_unregister_before_application_exists_drops_early_window(env):
    app, _ = env
    win = object()
    app.register_window(win)
    app.unregister_window(win)
    assert app._early == []


def test_unregister_after_application_removes_it_from_fabric(env):
    app, _ = env
    app.app = FakeFabricApp()
    win = object()
    app.register_window(win)
    assert app.app.windows == [win]
    app.unregister_window(win)
    assert app.app.windows == []


def test_shell_receives_unregister_callback(env, monkeypatch):
    app, mapping = env
    got = {}

    class Capturing(FakeShell):
        def __init__(self, name, monitor, config, register, unregister=None):
            super().__init__(name, monitor, config, register)
            got["unregister"] = unregister

    monkeypatch.setattr(app_mod, "MonitorShell", Capturing)
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    assert got["unregister"] == app.unregister_window
