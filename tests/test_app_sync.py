"""Display-free tests for EdgeShellApp.sync_monitors and the hot-plug timer bookkeeping."""

from types import SimpleNamespace

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import shell.app as app_mod  # noqa: E402


class FakeShell:
    opened: list = []
    closed: list = []
    applied: list = []
    fail_apply: set = set()
    layout_warnings: list = []
    measure_pending = False
    fail_open: set = set()

    def __init__(
        self, name, monitor, config, register, unregister=None, on_layout=None, on_error=None
    ):
        self.name = name
        self.monitor = monitor
        self.on_layout = on_layout
        self.on_error = on_error
        if name in FakeShell.fail_open:
            raise RuntimeError("cannot build")
        FakeShell.opened.append(name)

    def close(self):
        FakeShell.closed.append(self.name)

    def apply(self, config, changes):
        if self.name in FakeShell.fail_apply:
            raise RuntimeError("boom")
        FakeShell.applied.append((self.name, [c.kind for c in changes]))


@pytest.fixture(autouse=True)
def _reset_fake_shell(monkeypatch):
    """FakeShell keeps its state on the class: give every test fresh values (restored after)."""
    for attr, value in (
        ("opened", []),
        ("closed", []),
        ("applied", []),
        ("fail_apply", set()),
        ("fail_open", set()),
        ("layout_warnings", []),
        ("measure_pending", False),
    ):
        monkeypatch.setattr(FakeShell, attr, value)


@pytest.fixture
def env(monkeypatch, make_config):
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
        def __init__(self, name, monitor, config, register, unregister=None, **callbacks):
            super().__init__(name, monitor, config, register)
            got["unregister"] = unregister

    monkeypatch.setattr(app_mod, "MonitorShell", Capturing)
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    assert got["unregister"] == app.unregister_window


# ---- reload ----------------------------------------------------------------------


def mon(shell="edge", panels=()):
    return {"shell": shell, "panels": list(panels), "theme": {}}


class ReloadStore:
    def __init__(self, config):
        self.config = config
        self.path = None
        self.last_error = None
        self.pending = None

    def reload(self):
        if self.pending is None:
            return None
        old, self.config = self.config, self.pending
        self.pending = None
        return old, self.config


@pytest.fixture
def renv(monkeypatch, make_config, fake_registry):
    mapping = {"HDMI-A-1": object()}
    monkeypatch.setattr(app_mod, "monitors_by_name", lambda: mapping)
    monkeypatch.setattr(app_mod, "MonitorShell", FakeShell)
    errors = []
    monkeypatch.setattr(app_mod.EdgeShellApp, "_report_error", lambda self, m: errors.append(m))
    store = ReloadStore(make_config(monitors={"HDMI-A-1": mon(panels=[{"widget": "dock"}])}))
    app = app_mod.EdgeShellApp(store)
    app.sync_monitors()
    FakeShell.opened.clear()
    return app, store, errors, mapping, make_config


def test_sync_reports_what_it_opened_and_closed(env):
    app, mapping = env
    mapping["HDMI-A-1"] = object()
    assert app.sync_monitors() == (set(), {"HDMI-A-1"})
    mapping["HDMI-A-1"] = object()
    assert app.sync_monitors() == ({"HDMI-A-1"}, {"HDMI-A-1"})
    assert app.sync_monitors() == (set(), set())


def test_reload_rebuild_monitor_closes_and_reopens_without_apply(renv):
    app, store, errors, _, make_config = renv
    store.pending = make_config(
        theme={"thickness": 12}, monitors={"HDMI-A-1": mon(panels=[{"widget": "dock"}])}
    )
    app.reload()
    assert FakeShell.closed == ["HDMI-A-1"]
    assert FakeShell.opened == ["HDMI-A-1"]
    assert FakeShell.applied == []
    assert errors == []


def test_reload_applies_grouped_changes_to_existing_shell(renv):
    app, store, _, _, make_config = renv
    store.pending = make_config(
        theme={"accent": "#112233"},
        monitors={"HDMI-A-1": mon(panels=[{"widget": "dock", "state": "collapsed"}])},
    )
    app.reload()
    assert FakeShell.applied == [("HDMI-A-1", ["restyle", "panel-state"])]
    assert FakeShell.closed == [] and FakeShell.opened == []


def test_reload_does_not_apply_to_a_shell_opened_by_its_own_sync(renv):
    app, store, _, _, make_config = renv
    app.shells.pop("HDMI-A-1")  # e.g. a hot-plug sync has not run yet
    store.pending = make_config(
        monitors={"HDMI-A-1": mon(panels=[{"widget": "dock"}, {"widget": "clock"}])}
    )
    app.reload()
    assert FakeShell.opened == ["HDMI-A-1"]  # built from the new config
    assert FakeShell.applied == []  # a panel-add on top would duplicate the clock


def test_reload_apply_failure_closes_reports_and_rebuilds(renv):
    app, store, errors, _, make_config = renv
    FakeShell.fail_apply = {"HDMI-A-1"}
    store.pending = make_config(
        theme={"accent": "#112233"}, monitors={"HDMI-A-1": mon(panels=[{"widget": "dock"}])}
    )
    app.reload()
    assert FakeShell.closed == ["HDMI-A-1"]
    assert FakeShell.opened == ["HDMI-A-1"]  # rebuilt from the new config
    assert "HDMI-A-1" in app.shells
    assert len(errors) == 1 and "HDMI-A-1" in errors[0]


def test_reload_bad_config_reports_and_changes_nothing(renv):
    app, store, errors, _, _ = renv
    store.last_error = "theme.accent: must be a #rrggbb hex color"
    app.reload()  # store.reload() returns None
    assert errors == [store.last_error]
    assert FakeShell.opened == [] and FakeShell.closed == [] and FakeShell.applied == []


def test_reload_unexpected_exception_is_contained_and_reported(renv, monkeypatch):
    app, store, errors, _, make_config = renv
    store.pending = make_config(monitors={"HDMI-A-1": mon()})

    def explode():
        raise OSError("kscreen gone")

    monkeypatch.setattr(app, "sync_monitors", explode)
    app.reload()  # must not raise inside a GLib callback
    assert len(errors) == 1 and "kscreen gone" in errors[0]


def test_run_refuses_a_second_instance_before_creating_windows(env, monkeypatch, capsys):
    app, mapping = env
    mapping["HDMI-A-1"] = object()
    monkeypatch.setattr(app_mod, "_already_running", lambda: True)
    created = []
    monkeypatch.setattr(app_mod, "Application", lambda *a, **k: created.append(a))
    assert app.run() == 1
    assert FakeShell.opened == [] and created == []
    assert "already running" in capsys.readouterr().err


def test_notify_send_body_cannot_be_parsed_as_option(env, monkeypatch):
    app, _ = env
    calls = []
    monkeypatch.setattr(app_mod.subprocess, "Popen", lambda argv: calls.append(argv))
    app._report_error("--urgency=critical looks like an option")
    argv = calls[0]
    assert argv[0] == "notify-send"
    assert argv.index("--") < argv.index("--urgency=critical looks like an option")


def test_layout_warnings_are_notified_when_a_shell_opens(env, monkeypatch):
    app, mapping = env
    notes = []
    monkeypatch.setattr(
        app_mod.EdgeShellApp, "_notify", lambda self, title, msg: notes.append((title, msg))
    )
    monkeypatch.setattr(FakeShell, "layout_warnings", ["monitors.HDMI-A-1.panels.1 (dock): x"])
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    assert notes == [("Panels adjusted", "monitors.HDMI-A-1.panels.1 (dock): x")]


def test_no_notification_without_layout_warnings(env, monkeypatch):
    app, mapping = env
    notes = []
    monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, *a: notes.append(a))
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    assert notes == []


def test_layout_warnings_are_notified_only_when_they_change(renv, monkeypatch):
    app, _, _, _, _ = renv
    notes = []
    monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, title, msg: notes.append(msg))
    shell = app.shells["HDMI-A-1"]
    for warnings in (["w1"], ["w1"], ["w1", "w2"], [], ["w1"]):
        shell.layout_warnings = warnings
        app._report_layout("HDMI-A-1", shell)
    assert notes == ["w1", "w1\nw2", "w1"]  # unchanged: silent; cleared: silent; back: again


def test_unrelated_reload_does_not_repeat_the_layout_notification(renv, monkeypatch):
    app, store, _, _, make_config = renv
    notes = []
    monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, *a: notes.append(a))
    app.shells["HDMI-A-1"].layout_warnings = ["w"]
    app._report_layout("HDMI-A-1", app.shells["HDMI-A-1"])
    store.pending = make_config(
        theme={"accent": "#112233"}, monitors={"HDMI-A-1": mon(panels=[{"widget": "dock"}])}
    )
    app.reload()
    assert len(notes) == 1


def test_a_reload_with_a_pending_measurement_reports_its_warnings_afterwards(renv, monkeypatch):
    app, store, _, _, make_config = renv
    notes = []
    monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, title, msg: notes.append(msg))
    shell = app.shells["HDMI-A-1"]
    monkeypatch.setattr(FakeShell, "measure_pending", True)
    monkeypatch.setattr(FakeShell, "layout_warnings", ["dock: shrunk"])
    store.pending = make_config(
        theme={"accent": "#112233"}, monitors={"HDMI-A-1": mon(panels=[{"widget": "dock"}])}
    )
    app.reload()
    assert notes == []  # provisional lengths: waits for the measurement
    shell.on_layout(shell)  # the measurement changed nothing, but still reports
    assert notes == ["dock: shrunk"]


# ---- --stats ---------------------------------------------------------------------


def test_exercise_toggles_every_live_panel_and_repeats(env):
    app, _ = env
    toggled = []
    panel = type("P", (), {"toggle": lambda self: toggled.append(self)})()
    app.shells["HDMI-A-1"] = type("S", (), {"live_panels": lambda self: [panel, panel]})()
    assert app._exercise() is True
    assert toggled == [panel, panel]


def test_stop_quits_once(env):
    app, _ = env
    quits = []
    app.app = type("A", (), {"quit": lambda self: quits.append(1)})()
    assert app._stop() is False and quits == [1]


def test_recorder_is_attached_to_every_opened_canvas(env, monkeypatch):
    app, mapping = env
    painter = type("Painter", (), {"recorder": None})()

    class WithCanvas(FakeShell):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.canvas = type("C", (), {"painter": painter})()

    monkeypatch.setattr(app_mod, "MonitorShell", WithCanvas)
    app.recorder = object()
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    assert painter.recorder is app.recorder


# ---- pos deprecation ------------------------------------------------------------------


def test_deprecated_pos_is_logged_once_at_start(make_config, caplog):
    caplog.set_level("INFO", logger="shell.app")
    cfg = make_config(monitors={"HDMI-A-1": mon(panels=[{"widget": "dock", "pos": 100}])})
    app_mod.EdgeShellApp(SimpleNamespace(config=cfg))
    lines = [r.getMessage() for r in caplog.records if "deprecated key pos" in r.getMessage()]
    assert len(lines) == 1 and "monitors.HDMI-A-1.panels.0.pos" in lines[0]


def test_deprecated_pos_is_logged_once_per_reload(renv, caplog):
    app, store, _, _, make_config = renv
    caplog.set_level("INFO", logger="shell.app")
    store.pending = make_config(
        monitors={"HDMI-A-1": mon(panels=[{"widget": "dock", "pos": 100}, {"widget": "dock"}])}
    )
    app.reload()
    store.pending = make_config(monitors={"HDMI-A-1": mon(panels=[{"widget": "dock"}])})
    app.reload()  # no pos left: no line
    lines = [r.getMessage() for r in caplog.records if "deprecated key pos" in r.getMessage()]
    assert len(lines) == 1 and lines[0].endswith("monitors.HDMI-A-1.panels.0.pos")


def test_a_moved_system_bar_default_is_logged_once_at_start(make_config, caplog):
    caplog.set_level("INFO", logger="shell.app")
    cfg = make_config(
        monitors={
            "HDMI-A-1": mon(
                panels=[
                    {"widget": "system_bar"},
                    {"widget": "system_bar", "edge": "top"},
                    {"widget": "system_bar", "length": 524, "pos": 600},
                ]
            )
        }
    )
    app_mod.EdgeShellApp(SimpleNamespace(config=cfg))
    lines = [r.getMessage() for r in caplog.records if "default placement" in r.getMessage()]
    assert len(lines) == 1
    assert 'align="end"' in lines[0] and "offset=142" in lines[0] and "pos = 600" in lines[0]
    assert "monitors.HDMI-A-1.panels.1" in lines[0] and "panels.0" not in lines[0]
    assert "panels.2" not in lines[0]


def test_no_moved_default_line_without_a_candidate(make_config, caplog):
    caplog.set_level("INFO", logger="shell.app")
    cfg = make_config(monitors={"HDMI-A-1": mon(panels=[{"widget": "system_bar"}])})
    app_mod.EdgeShellApp(SimpleNamespace(config=cfg))
    assert not [r for r in caplog.records if "default placement" in r.getMessage()]


def test_a_relayout_started_by_the_shell_reports_through_the_app(env, monkeypatch):
    app, mapping = env
    notes = []
    monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, title, msg: notes.append(msg))
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    shell = app.shells["HDMI-A-1"]
    shell.layout_warnings = ["monitors.HDMI-A-1.panels.0 (dock): shrunk"]
    shell.on_layout(shell)  # what MonitorShell calls after measuring or a geometry change
    assert notes == ["monitors.HDMI-A-1.panels.0 (dock): shrunk"]


def test_a_failed_relayout_rebuilds_the_shell_once(env, monkeypatch):
    app, mapping = env
    notes = []
    monkeypatch.setattr(
        app_mod.EdgeShellApp, "_notify", lambda self, title, msg: notes.append(title)
    )
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    shell = app.shells["HDMI-A-1"]
    shell.on_error(shell)  # what MonitorShell calls when _measure or _relayout raised
    rebuilt = app.shells["HDMI-A-1"]
    assert rebuilt is not shell and notes == ["Panels rebuilt"]
    assert FakeShell.closed == ["HDMI-A-1"] and FakeShell.opened == ["HDMI-A-1", "HDMI-A-1"]
    rebuilt.on_error(rebuilt)  # fails again before the next reload: logged, shell kept
    shell.on_error(shell)  # a late call from the closed shell: ignored
    assert app.shells["HDMI-A-1"] is rebuilt and FakeShell.closed == ["HDMI-A-1"]


def test_a_failed_relayout_rebuilds_from_the_same_monitor_without_kscreen(env, monkeypatch):
    app, mapping = env
    monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, title, msg: None)
    monitor = mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    shell = app.shells["HDMI-A-1"]
    calls = []
    monkeypatch.setattr(app_mod, "monitors_by_name", lambda: calls.append(1) or {})
    shell.on_error(shell)
    assert calls == []
    assert app.shells["HDMI-A-1"] is not shell
    assert app.shells["HDMI-A-1"].monitor is monitor


def test_a_failed_relayout_rebuild_refreshes_the_css(env, monkeypatch):
    app, mapping = env
    monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, title, msg: None)
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    refreshed = []
    monkeypatch.setattr(app, "refresh_css", lambda: refreshed.append(1))
    shell = app.shells["HDMI-A-1"]
    shell.on_error(shell)
    assert refreshed == [1]


def test_a_failed_rebuild_never_escapes_and_is_reported(env, monkeypatch):
    app, mapping = env
    notes, errors = [], []
    monkeypatch.setattr(
        app_mod.EdgeShellApp, "_notify", lambda self, title, msg: notes.append(title)
    )
    monkeypatch.setattr(app_mod.EdgeShellApp, "_report_error", lambda self, msg: errors.append(msg))
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    shell = app.shells["HDMI-A-1"]
    monkeypatch.setattr(FakeShell, "fail_open", {"HDMI-A-1"})  # the second construction raises
    shell.on_error(shell)  # must not raise
    assert len(errors) == 1 and "HDMI-A-1" in errors[0]
    assert "HDMI-A-1" not in app.shells


def test_layout_report_waits_for_a_pending_measurement(env, monkeypatch):
    app, mapping = env
    notes = []
    monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, title, msg: notes.append(msg))
    monkeypatch.setattr(FakeShell, "measure_pending", True)
    monkeypatch.setattr(FakeShell, "layout_warnings", ["transient: hidden at its default length"])
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    assert notes == []
    shell = app.shells["HDMI-A-1"]
    shell.on_layout(shell)  # the measurement finished
    assert notes == ["transient: hidden at its default length"]
