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
    faded: list = []  # (name, ms) of every fade_out call
    finished: list = []  # every shell finish_fade was called on
    fail_apply: set = set()
    layout_warnings: list = []
    build_failures: list = []
    measure_pending = False
    fail_open: set = set()

    def __init__(
        self,
        name,
        monitor,
        config,
        register,
        unregister=None,
        on_layout=None,
        on_error=None,
        on_settings=None,
        fade_ms=0,
        on_fade_in=None,
        reserve_now=True,
    ):
        self.name = name
        self.reserve_now = reserve_now
        self.monitor = monitor
        self.on_layout = on_layout
        self.on_error = on_error
        self.on_settings = on_settings
        self.fade_ms = fade_ms
        self.on_fade_in = on_fade_in
        self.fade_state = "waiting" if fade_ms > 0 else "shown"  # as MonitorShell
        self.on_done = None
        self.detached = False
        self.reserved_again = 0
        if name in FakeShell.fail_open:
            raise RuntimeError("cannot build")
        FakeShell.opened.append(name)

    def close(self):
        FakeShell.closed.append(self.name)
        self.fade_state = "done"

    @property
    def fading_out(self):
        return self.fade_state in ("fading-out", "done")

    def detach(self):
        self.detached = True

    def reserve_again(self):
        """MonitorShell.reserve_again: a held shell gets its zone strips back."""
        self.reserved_again += 1

    def finish_fade(self):
        FakeShell.finished.append(self)
        if self.fade_state == "fading-in":
            self.fade_state = "shown"

    def fade_out(self, ms, on_done):
        """MonitorShell.fade_out: closed at once with 0 ms or while still invisible."""
        FakeShell.faded.append((self.name, ms))
        if ms <= 0 or self.fade_state in ("waiting", "done"):
            self.close()
            on_done(self)
            return
        self.detached = True
        self.fade_state = "fading-out"
        self.on_done = on_done

    def fade_in(self):
        """Test helper: the real shell became ready and starts its fade-in."""
        self.fade_state = "shown"
        if self.on_fade_in is not None:
            self.on_fade_in(self)

    def faded_out(self):
        """Test helper: the real shell's fade-out reached 0 and it closed itself."""
        self.close()
        self.on_done(self)

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
        ("faded", []),
        ("finished", []),
        ("fail_apply", set()),
        ("fail_open", set()),
        ("layout_warnings", []),
        ("build_failures", []),
        ("measure_pending", False),
    ):
        monkeypatch.setattr(FakeShell, attr, value)


@pytest.fixture(autouse=True)
def _no_notify_send(monkeypatch):
    """No test here starts notify-send (a monitor-name warning would show on the desktop);
    a test that checks the command patches Popen itself."""
    monkeypatch.setattr(app_mod.subprocess, "Popen", lambda *_a, **_k: None)


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
    store = ReloadStore(
        make_config(
            monitors={"HDMI-A-1": mon(panels=[{"panel": "edge", "name": "dock", "widget": "dock"}])}
        )
    )
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


def test_opened_shells_get_the_settings_opener(env):
    app, mapping = env
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    assert app.shells["HDMI-A-1"].on_settings == app.open_settings


def test_reload_rebuild_monitor_closes_and_reopens_without_apply(renv):
    """With fade_ms 0 a rebuild is what it always was: closed, then opened (spec 21)."""
    app, store, errors, _, make_config = renv
    store.pending = make_config(
        theme={"thickness": 12, "fade_ms": 0},
        monitors={"HDMI-A-1": mon(panels=[{"panel": "edge", "name": "dock", "widget": "dock"}])},
    )
    app.reload()
    assert FakeShell.closed == ["HDMI-A-1"]
    assert FakeShell.opened == ["HDMI-A-1"]
    assert FakeShell.applied == [] and FakeShell.faded == []
    assert errors == [] and app._leaving == {}


def test_reload_applies_grouped_changes_to_existing_shell(renv):
    app, store, _, _, make_config = renv
    store.pending = make_config(
        theme={"accent": "#112233"},
        monitors={
            "HDMI-A-1": mon(
                panels=[{"panel": "edge", "name": "dock", "widget": "dock", "state": "collapsed"}]
            )
        },
    )
    app.reload()
    assert FakeShell.applied == [("HDMI-A-1", ["restyle", "panel-state"])]
    assert FakeShell.closed == [] and FakeShell.opened == []


def test_reload_does_not_apply_to_a_shell_opened_by_its_own_sync(renv):
    app, store, _, _, make_config = renv
    app.shells.pop("HDMI-A-1")  # e.g. a hot-plug sync has not run yet
    store.pending = make_config(
        monitors={
            "HDMI-A-1": mon(
                panels=[
                    {"panel": "edge", "name": "dock", "widget": "dock"},
                    {"panel": "edge", "name": "clock", "widget": "clock"},
                ]
            )
        }
    )
    app.reload()
    assert FakeShell.opened == ["HDMI-A-1"]  # built from the new config
    assert FakeShell.applied == []  # a panel-add on top would duplicate the clock


def test_reload_apply_failure_closes_reports_and_rebuilds(renv):
    app, store, errors, _, make_config = renv
    FakeShell.fail_apply = {"HDMI-A-1"}
    store.pending = make_config(
        theme={"accent": "#112233"},
        monitors={"HDMI-A-1": mon(panels=[{"panel": "edge", "name": "dock", "widget": "dock"}])},
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


def test_the_fabric_dbus_client_is_off(env, monkeypatch):
    """Fabric's org.Fabric.fabric.edge-shell Execute / Evaluate would run any Python sent by
    any session-bus client inside the shell; nothing in Edge Shell uses it."""
    app, _ = env
    made = []

    class FakeApplication:
        def __init__(self, *args, **kwargs):
            made.append((args, kwargs))

        def set_stylesheet_from_string(self, *_a, **_k):
            pass

        def hold(self):
            pass

        def run(self):
            order.append(("run",))

    order: list = []
    monkeypatch.setattr(app_mod, "_already_running", lambda: False)
    monkeypatch.setattr(app_mod, "Application", FakeApplication)
    monkeypatch.setattr(app, "start_watching", lambda: None)
    monkeypatch.setattr(app, "watch_displays", lambda: None)
    monkeypatch.setattr(app_mod.signal, "signal", lambda *a: order.append(("signal", a)))
    monkeypatch.setattr(app, "_watch_quit_signals", lambda: order.append(("watch",)))
    assert app.run() == 0
    ((args, kwargs),) = made
    assert args[0] == app_mod.APP_NAME and kwargs == {"open_client": False}
    # Fabric's own SIGINT handler would quit without the fade: reset before the Gtk main loop
    # starts, and GLib's handlers installed
    sigint = app_mod.signal
    assert order.index(("signal", (sigint.SIGINT, sigint.SIG_DFL))) < order.index(("run",))
    assert ("watch",) in order


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
        theme={"accent": "#112233"},
        monitors={"HDMI-A-1": mon(panels=[{"panel": "edge", "name": "dock", "widget": "dock"}])},
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
        theme={"accent": "#112233"},
        monitors={"HDMI-A-1": mon(panels=[{"panel": "edge", "name": "dock", "widget": "dock"}])},
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
    cfg = make_config(
        monitors={
            "HDMI-A-1": mon(
                panels=[{"panel": "edge", "name": "dock", "widget": "dock", "pos": 100}]
            )
        }
    )
    app_mod.EdgeShellApp(SimpleNamespace(config=cfg))
    lines = [r.getMessage() for r in caplog.records if "deprecated key pos" in r.getMessage()]
    assert len(lines) == 1 and "monitors.HDMI-A-1.panels.0.pos" in lines[0]


def test_deprecated_pos_is_logged_once_per_reload(renv, caplog):
    app, store, _, _, make_config = renv
    caplog.set_level("INFO", logger="shell.app")
    store.pending = make_config(
        monitors={
            "HDMI-A-1": mon(
                panels=[
                    {"panel": "edge", "name": "dock", "widget": "dock", "pos": 100},
                    {"panel": "edge", "name": "dock 2", "widget": "dock"},
                ]
            )
        }
    )
    app.reload()
    store.pending = make_config(
        monitors={"HDMI-A-1": mon(panels=[{"panel": "edge", "name": "dock", "widget": "dock"}])}
    )
    app.reload()  # no pos left: no line
    lines = [r.getMessage() for r in caplog.records if "deprecated key pos" in r.getMessage()]
    assert len(lines) == 1 and lines[0].endswith("monitors.HDMI-A-1.panels.0.pos")


def test_a_moved_system_bar_default_is_logged_once_at_start(make_config, caplog):
    caplog.set_level("INFO", logger="shell.app")
    cfg = make_config(
        monitors={
            "HDMI-A-1": mon(
                panels=[
                    {"panel": "edge", "name": "system_bar", "widget": "system_bar"},
                    {
                        "panel": "edge",
                        "name": "system_bar 2",
                        "widget": "system_bar",
                        "edge": "top",
                    },
                    {
                        "panel": "edge",
                        "name": "system_bar 3",
                        "widget": "system_bar",
                        "length": 524,
                        "pos": 600,
                    },
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
    cfg = make_config(
        monitors={
            "HDMI-A-1": mon(
                panels=[{"panel": "edge", "name": "system_bar", "widget": "system_bar"}]
            )
        }
    )
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


# ---- handle plan: reload kinds and all-off panels ---------------------------------------


def test_a_reload_logs_its_change_kinds(renv, caplog):
    app, store, _, _, make_config = renv
    caplog.set_level("INFO", logger="shell.app")
    store.pending = make_config(
        monitors={
            "HDMI-A-1": mon(
                panels=[
                    {"panel": "edge", "name": "dock", "widget": "dock", "handle": {"shape": "bar"}}
                ]
            )
        }
    )
    app.reload()
    assert "config reloaded: 1 change(s): panel-handle" in caplog.text


def test_all_off_panels_are_logged_once_per_load(renv, caplog):
    app, store, _, _, make_config = renv
    caplog.set_level("INFO", logger="shell.app")
    off = {"click": False, "hover": False, "drag": False}
    store.pending = make_config(
        monitors={
            "HDMI-A-1": mon(
                panels=[
                    {"panel": "edge", "name": "dock", "widget": "dock"},
                    {"panel": "edge", "name": "dock 2", "widget": "dock", "interaction": off},
                ]
            )
        }
    )
    app.reload()
    store.pending = make_config(
        monitors={"HDMI-A-1": mon(panels=[{"panel": "edge", "name": "dock", "widget": "dock"}])}
    )
    app.reload()  # none left: no line
    lines = [r.getMessage() for r in caplog.records if "open only through state" in r.getMessage()]
    assert lines == [
        "panels with click, hover and drag all off (these panels open only through state): "
        "monitors.HDMI-A-1.panels.1"
    ]


class StyledFabricApp(FakeFabricApp):
    def __init__(self):
        super().__init__()
        self.stylesheets = []

    def set_stylesheet_from_string(self, css, compile=True):
        self.stylesheets.append(css)


def test_the_last_edge_monitor_leaving_never_loads_an_empty_stylesheet(env, make_config):
    """Gate A item 9: HDMI-A-1 edge -> plasma left no shell, css() was "", and Fabric's
    load_from_data(bytearray(b"")) hands GTK a NULL pointer: Gtk-CRITICAL 'data != NULL'."""
    app, mapping = env
    app.app = StyledFabricApp()
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    app.store.config = make_config(monitors={"HDMI-A-1": {"shell": "plasma"}})
    app.sync_monitors()
    assert app.shells == {} and len(app.app.stylesheets) == 2
    assert all(css.strip() for css in app.app.stylesheets)


def test_panels_that_could_not_be_built_are_notified_by_name_once(renv, monkeypatch):
    app, _, _, _, _ = renv
    notes = []
    monkeypatch.setattr(
        app_mod.EdgeShellApp, "_notify", lambda self, title, msg: notes.append((title, msg))
    )
    shell = app.shells["HDMI-A-1"]
    failure = "HDMI-A-1: panel 'Top clock' (clock) could not be built and is not shown: boom"
    for failures in ([failure], [failure], [], [failure]):
        shell.build_failures = failures
        app._report_layout("HDMI-A-1", shell)
    assert notes == [("Panel not shown", failure), ("Panel not shown", failure)]


def test_several_panels_that_could_not_be_built_are_all_in_the_notification(renv, monkeypatch):
    app, _, _, _, _ = renv
    notes = []
    monkeypatch.setattr(
        app_mod.EdgeShellApp, "_notify", lambda self, title, msg: notes.append((title, msg))
    )
    shell = app.shells["HDMI-A-1"]
    shell.build_failures = ["HDMI-A-1: panel 'A' failed", "HDMI-A-1: panel 'B' failed"]
    app._report_layout("HDMI-A-1", shell)
    assert notes == [("Panel not shown", "HDMI-A-1: panel 'A' failed\nHDMI-A-1: panel 'B' failed")]


def test_the_notification_body_is_shown_literally(env, monkeypatch):
    app, _ = env
    calls = []
    monkeypatch.setattr(app_mod.subprocess, "Popen", lambda argv: calls.append(argv))
    app._notify("t", "panel 'A & B' <b>x</b>")
    assert calls[0][-1] == "panel 'A &amp; B' &lt;b&gt;x&lt;/b&gt;"
    assert calls[0][-3:-1] == ["--", "t"]


def test_the_notification_is_cut_before_it_is_escaped(env, monkeypatch):
    app, _ = env
    calls = []
    monkeypatch.setattr(app_mod.subprocess, "Popen", lambda argv: calls.append(argv))
    app._notify("t", "a" * 399 + "&" + "zz")  # the cut falls right after the "&"
    assert calls[0][-1] == "a" * 399 + "&amp;"  # never a split "&am"


@pytest.mark.parametrize(
    ("attr", "title"),
    [("build_failures", "Panel not shown"), ("layout_warnings", "Panels adjusted")],
)
def test_a_monitor_that_is_plugged_in_again_notifies_again(
    env, make_config, monkeypatch, attr, title
):
    app, mapping = env
    notes = []
    monkeypatch.setattr(
        app_mod.EdgeShellApp, "_notify", lambda self, title, msg: notes.append((title, msg))
    )
    monkeypatch.setattr(FakeShell, attr, ["HDMI-A-1: the same problem"])
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    app.sync_monitors()
    assert len(notes) == 1  # unchanged: once
    app.store.config = make_config(monitors={"HDMI-A-1": {"shell": "plasma"}})  # unplugged
    app.sync_monitors()
    app.store.config = make_config(monitors={"HDMI-A-1": {"shell": "edge"}})  # plugged in again
    app.sync_monitors()
    assert notes == [(title, "HDMI-A-1: the same problem")] * 2


def test_a_panel_that_fails_again_after_an_in_place_apply_failure_is_notified_again(
    renv, monkeypatch
):
    app, store, _, _, make_config = renv
    notes = []
    monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, title, msg: notes.append(msg))
    failure = "HDMI-A-1: panel 'dock' (dock) could not be built and is not shown: boom"
    monkeypatch.setattr(FakeShell, "build_failures", [failure])
    app._report_layout("HDMI-A-1", app.shells["HDMI-A-1"])
    FakeShell.fail_apply = {"HDMI-A-1"}
    store.pending = make_config(
        theme={"accent": "#112233"},
        monitors={"HDMI-A-1": mon(panels=[{"panel": "edge", "name": "dock", "widget": "dock"}])},
    )
    app.reload()  # the apply fails, the shell is dropped and rebuilt with the same failure
    assert notes == [failure, failure]


def test_a_panel_that_fails_again_after_a_relayout_rebuild_is_notified_again(env, monkeypatch):
    app, mapping = env
    notes = []
    monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, title, msg: notes.append(msg))
    failure = "HDMI-A-1: panel 'dock' (dock) could not be built and is not shown: boom"
    monkeypatch.setattr(FakeShell, "build_failures", [failure])
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    shell = app.shells["HDMI-A-1"]
    shell.on_error(shell)
    assert notes.count(failure) == 2


# ---- monitor names in the config against the connected monitors --------------------------


def test_a_configured_monitor_that_is_not_connected_is_reported_once(env, monkeypatch, caplog):
    app, mapping = env  # the config names HDMI-A-1
    notes = []
    monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, *a: notes.append(a))
    caplog.set_level("WARNING", logger="shell.app")
    mapping["DP-1"] = object()
    app.sync_monitors()
    app.sync_monitors()  # the same mismatch: nothing new
    assert notes == [
        (
            "Monitor not connected",
            "config monitors: HDMI-A-1; connected: DP-1\nUse the connected names in the config.",
        )
    ]
    assert caplog.text.count("config monitors: HDMI-A-1; connected: DP-1") == 1
    assert app.shells == {}  # unchanged behaviour: no frame for a monitor that is not there


def test_the_report_comes_again_after_the_names_matched(env, monkeypatch):
    app, mapping = env
    notes = []
    monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, *a: notes.append(a))
    mapping["DP-1"] = object()
    app.sync_monitors()
    mapping["HDMI-A-1"] = object()  # plugged in: every name matches, nothing said
    app.sync_monitors()
    del mapping["HDMI-A-1"]  # out again: the name is right, the cable is out: nothing new
    app.sync_monitors()
    assert len(notes) == 1
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    del mapping["HDMI-A-1"]
    app.sync_monitors()
    assert len(notes) == 1


def test_a_correctly_named_monitor_unplugged_says_nothing(env, monkeypatch):
    app, mapping = env  # the config names HDMI-A-1
    notes = _notes(monkeypatch)
    mapping["HDMI-A-1"] = object()
    mapping["DP-1"] = object()
    app.sync_monitors()
    del mapping["HDMI-A-1"]  # the cable is out; the name is right
    app.sync_monitors()
    assert notes == []


def test_a_name_never_seen_connected_is_reported_once_even_after_others_came_and_went(
    env, monkeypatch
):
    app, mapping = env  # the config names HDMI-A-1, which was never connected here
    notes = _notes(monkeypatch)
    mapping["DP-1"] = object()  # at startup a typo and an absent monitor look the same
    app.sync_monitors()
    assert len(notes) == 1
    mapping["DP-2"] = object()
    del mapping["DP-1"]  # other monitors come and go: still the same unknown name
    app.sync_monitors()
    assert len(notes) == 1


def test_a_typo_is_still_reported_after_a_correct_name_was_seen(renv, monkeypatch):
    app, store, _errors, mapping, make_config = renv
    notes = _notes(monkeypatch)
    panels = [{"panel": "edge", "name": "dock", "widget": "dock"}]
    store.pending = make_config(monitors={"HDMI-A-1": mon(panels=panels), "HDMI-A-9": mon()})
    app.reload()
    assert [n[1].splitlines()[0] for n in notes] == [
        "config monitors: HDMI-A-9; connected: HDMI-A-1"
    ]  # HDMI-A-1 was seen; HDMI-A-9 never: remembering names must not hide it


def test_a_connected_monitor_the_config_does_not_name_is_fine(env, monkeypatch):
    app, mapping = env
    notes = []
    monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, *a: notes.append(a))
    mapping["HDMI-A-1"] = object()
    mapping["DP-1"] = object()  # not in the config: it keeps plasma
    app.sync_monitors()
    assert notes == []


def test_a_reload_with_the_same_mismatch_says_nothing_new(renv, monkeypatch):
    app, store, _errors, mapping, make_config = renv
    notes = []
    monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, *a: notes.append(a))
    panels = [{"panel": "edge", "name": "dock", "widget": "dock"}]
    store.pending = make_config(monitors={"HDMI-A-1": mon(panels=panels), "HDMI-A-2": mon()})
    app.reload()
    store.pending = make_config(
        theme={"accent": "#112233"},
        monitors={"HDMI-A-1": mon(panels=panels), "HDMI-A-2": mon()},
    )
    app.reload()  # e.g. the next change from the settings window
    assert [n[1].splitlines()[0] for n in notes] == [
        "config monitors: HDMI-A-2; connected: HDMI-A-1"
    ]


def _notes(monkeypatch):
    notes = []
    monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, *a: notes.append(a))
    return notes


def _name(app, make_config, *names, shell="edge"):
    """The config names exactly these monitors."""
    app.store.config = make_config(monitors={n: {"shell": shell} for n in names})


def test_a_failed_read_does_not_forget_the_report(env, monkeypatch):
    app, mapping = env
    notes = _notes(monkeypatch)
    mapping["DP-1"] = object()
    app.sync_monitors()
    mapping.clear()  # kscreen-doctor failed, no shell open
    app.sync_monitors()
    mapping["DP-1"] = object()
    app.sync_monitors()
    assert len(notes) == 1


def test_a_failed_read_after_a_match_says_nothing(env, monkeypatch, make_config):
    app, mapping = env
    _name(
        app, make_config, "HDMI-A-1", shell="plasma"
    )  # no shell opens: the empty read is not skipped
    notes = _notes(monkeypatch)
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()  # the name matches
    mapping.clear()  # kscreen-doctor failed
    app.sync_monitors()
    assert notes == []


def test_notify_survives_a_value_error(env, monkeypatch):
    app, _mapping = env

    def refuse(*_a, **_k):
        raise ValueError("embedded null byte")

    monkeypatch.setattr(app_mod.subprocess, "Popen", refuse)
    app._notify("t", "m")  # no raise


def test_a_control_character_in_a_monitor_name_does_not_break_the_sync(
    env, monkeypatch, make_config
):
    app, mapping = env
    _name(app, make_config, "HDMI\x00X")
    mapping["DP-1"] = object()

    def popen(argv, **_kw):
        if any("\x00" in part for part in argv):
            raise ValueError("embedded null byte")

    monkeypatch.setattr(app_mod.subprocess, "Popen", popen)
    app.sync_monitors()  # must not raise


def test_a_failing_name_check_never_breaks_the_sync(env, monkeypatch, caplog):
    app, mapping = env
    mapping["HDMI-A-1"] = object()

    def boom(*_a):
        raise RuntimeError("boom")

    monkeypatch.setattr(app_mod, "unknown_monitors", boom)
    app.sync_monitors()
    assert "HDMI-A-1" in app.shells
    assert "boom" in caplog.text


def test_an_unconfigured_monitor_coming_and_going_does_not_warn(env, monkeypatch, make_config):
    app, mapping = env
    _name(app, make_config, "HDMI-A-1")
    notes = _notes(monkeypatch)
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()  # the name matches
    mapping["DP-2"] = object()  # not in the config: plugged in, out, in
    app.sync_monitors()
    del mapping["DP-2"]
    app.sync_monitors()
    mapping["DP-2"] = object()
    app.sync_monitors()
    assert notes == []


def test_an_existing_typo_is_not_reported_on_every_hot_plug(env, monkeypatch):
    app, mapping = env  # the config names HDMI-A-1, which is a typo here
    notes = _notes(monkeypatch)
    mapping["DP-1"] = object()
    app.sync_monitors()
    mapping["DP-2"] = object()  # another monitor plugged in
    app.sync_monitors()
    del mapping["DP-1"]
    app.sync_monitors()
    assert len(notes) == 1


def test_a_new_typo_is_reported_when_the_unknown_set_changes(env, monkeypatch, make_config):
    app, mapping = env
    notes = _notes(monkeypatch)
    mapping["DP-1"] = object()
    app.sync_monitors()
    _name(app, make_config, "HDMI-A-1", "HDMI-A-9")
    app.sync_monitors()
    assert len(notes) == 2
    assert "HDMI-A-1, HDMI-A-9" in notes[1][1]


def test_the_names_to_use_survive_the_notification_cut(env, monkeypatch, make_config):
    app, mapping = env
    _name(app, make_config, *[f"BAD-{n:02d}" for n in range(60)])
    notes = _notes(monkeypatch)
    mapping["DP-1"] = object()
    app.sync_monitors()
    assert "connected: DP-1" in notes[0][1][:400]


def test_a_name_with_a_stray_space_is_visible(env, monkeypatch, make_config):
    app, mapping = env
    _name(app, make_config, " HDMI-A-1")
    notes = _notes(monkeypatch)
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    assert "' HDMI-A-1'" in notes[0][1]


def test_a_plasma_mode_monitor_that_is_not_connected_is_still_reported(
    env, monkeypatch, make_config
):
    app, mapping = env
    _name(app, make_config, "DP-1", shell="plasma")
    notes = _notes(monkeypatch)
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    assert notes and "config monitors: DP-1" in notes[0][1]


# ---- the fade (spec 21) ---------------------------------------------------------------


class QuitRecorder:
    def __init__(self):
        self.quits = 0

    def quit(self):
        self.quits += 1


@pytest.fixture
def timers(monkeypatch):
    """GLib.timeout_add / source_remove of shell.app, recorded: {id: (ms, fn)}."""
    pending: dict = {}
    ids = iter(range(100, 1000))

    def add(ms, fn, *args):
        timer = next(ids)
        pending[timer] = (ms, fn)
        return timer

    monkeypatch.setattr(app_mod.GLib, "timeout_add", add)
    monkeypatch.setattr(app_mod.GLib, "source_remove", lambda t: pending.pop(t))
    return pending


def test_shells_open_with_their_monitors_fade_and_none_while_measuring(env, make_config):
    app, mapping = env
    mapping["HDMI-A-1"] = object()
    app.store.config = make_config(monitors={"HDMI-A-1": {"shell": "edge"}})
    app.sync_monitors()
    assert app.shells["HDMI-A-1"].fade_ms == 50  # the default
    app.store.config = make_config(
        monitors={"HDMI-A-1": {"shell": "edge", "theme": {"fade_ms": 300}}}
    )
    mapping["HDMI-A-1"] = object()  # replugged: reopened with the monitor's own fade
    app.sync_monitors()
    assert app.shells["HDMI-A-1"].fade_ms == 300
    stats = app_mod.EdgeShellApp(app.store, stats_seconds=2)  # --stats: never a fade
    stats.sync_monitors()
    assert stats.shells["HDMI-A-1"].fade_ms == 0


def test_disabling_a_monitor_fades_it_out_and_closes_it_when_done(renv):
    app, store, errors, _, make_config = renv
    shell = app.shells["HDMI-A-1"]
    shell.fade_in()
    store.pending = make_config(monitors={"HDMI-A-1": mon("plasma")})
    app.reload()
    assert FakeShell.faded == [("HDMI-A-1", 50)] and FakeShell.closed == []
    assert app.shells == {} and app._leaving == {"HDMI-A-1": shell}
    shell.faded_out()
    assert FakeShell.closed == ["HDMI-A-1"] and app._leaving == {} and errors == []


def test_the_fade_out_uses_the_fade_of_the_config_that_turns_it_off(renv):
    app, store, _, _, make_config = renv
    app.shells["HDMI-A-1"].fade_in()
    store.pending = make_config(
        monitors={"HDMI-A-1": {"shell": "plasma", "theme": {"fade_ms": 300}}}
    )
    app.reload()
    assert FakeShell.faded == [("HDMI-A-1", 300)]


def test_with_fade_0_a_disabled_monitor_closes_at_once_as_before(renv):
    app, store, _, _, make_config = renv
    app.shells["HDMI-A-1"].fade_in()
    store.pending = make_config(theme={"fade_ms": 0}, monitors={"HDMI-A-1": mon("plasma")})
    app.reload()
    assert FakeShell.faded == [("HDMI-A-1", 0)] and FakeShell.closed == ["HDMI-A-1"]
    assert app.shells == {} and app._leaving == {}


def test_an_unplugged_or_replaced_monitor_is_closed_at_once_without_a_fade(env):
    app, mapping = env
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    app.shells["HDMI-A-1"].fade_in()
    mapping["HDMI-A-1"] = object()  # a new Gdk monitor: the old one is gone
    app.sync_monitors()
    assert FakeShell.faded == [] and FakeShell.closed == ["HDMI-A-1"]
    del mapping["HDMI-A-1"]
    mapping["DP-1"] = object()  # unplugged (DP-1 keeps the mapping non-empty)
    app.sync_monitors()
    assert FakeShell.faded == [] and FakeShell.closed == ["HDMI-A-1", "HDMI-A-1"]


def test_run_takes_sigint_and_sigterm_through_glib(env, monkeypatch):
    app, _ = env
    added = []
    monkeypatch.setattr(app_mod, "unix_signal_add", lambda *a: added.append(a))
    app._watch_quit_signals()
    high, signals = app_mod.GLib.PRIORITY_HIGH, app_mod.signal
    sigint, sigterm = signals.SIGINT, signals.SIGTERM
    assert added == [
        (high, sigint, app._on_quit_signal, sigint),
        (high, sigterm, app._on_quit_signal, sigterm),
    ]


def test_a_quit_signal_fades_every_shell_out_then_quits(renv, timers):
    app, _, _, _, _ = renv
    app.app = QuitRecorder()
    shell = app.shells["HDMI-A-1"]
    shell.fade_in()
    assert app._on_quit_signal(app_mod.signal.SIGINT) is True  # the handler stays
    assert FakeShell.faded == [("HDMI-A-1", 50)] and app.app.quits == 0
    assert [ms for ms, _ in timers.values()] == [50 + app_mod.QUIT_MARGIN_MS]
    shell.faded_out()
    assert app.app.quits == 1 and timers == {}  # the bound is dropped
    assert app._exit_code == 130


def test_the_quit_waits_at_most_the_fade_plus_the_margin(renv, timers):
    app, _, _, _, _ = renv
    app.app = QuitRecorder()
    app.shells["HDMI-A-1"].fade_in()
    app._on_quit_signal(app_mod.signal.SIGTERM)
    ((_, fn),) = timers.values()
    assert fn() is False  # the fade never finished (no frames): quit anyway
    assert app.app.quits == 1 and app._exit_code == 143


def test_a_second_quit_signal_quits_at_once(renv, timers):
    app, _, _, _, _ = renv
    app.app = QuitRecorder()
    app.shells["HDMI-A-1"].fade_in()
    app._on_quit_signal(app_mod.signal.SIGINT)
    app._on_quit_signal(app_mod.signal.SIGINT)
    assert app.app.quits == 1 and timers == {}


def test_without_any_fade_a_quit_signal_quits_at_once(renv, timers):
    app, store, _, _, make_config = renv
    store.config = make_config(theme={"fade_ms": 0}, monitors={"HDMI-A-1": mon()})
    app.app = QuitRecorder()
    app.shells["HDMI-A-1"].fade_in()
    app._on_quit_signal(app_mod.signal.SIGINT)
    assert FakeShell.closed == ["HDMI-A-1"] and app.app.quits == 1 and timers == {}


def test_a_monitor_without_a_fade_never_cuts_the_others_fade_short(env, make_config, timers):
    """HDMI-A-1 has fade 0 and closes inside the quit loop: the quit must still wait for
    HDMI-A-2's fade (it is not even started yet when HDMI-A-1 is gone)."""
    app, mapping = env
    app.store.config = make_config(
        monitors={
            "HDMI-A-1": {"shell": "edge", "theme": {"fade_ms": 0}},
            "HDMI-A-2": {"shell": "edge"},
        }
    )
    mapping.update({"HDMI-A-1": object(), "HDMI-A-2": object()})
    app.sync_monitors()
    for shell in app.shells.values():
        shell.fade_in()
    second = app.shells["HDMI-A-2"]
    app.app = QuitRecorder()
    app._on_quit_signal(app_mod.signal.SIGINT)
    assert FakeShell.faded == [("HDMI-A-1", 0), ("HDMI-A-2", 50)] and app.app.quits == 0
    second.faded_out()
    assert app.app.quits == 1


def test_reloads_and_hot_plug_syncs_are_ignored_while_quitting(renv, timers):
    app, store, _, mapping, make_config = renv
    app.app = QuitRecorder()
    app.shells["HDMI-A-1"].fade_in()
    app._on_quit_signal(app_mod.signal.SIGINT)
    store.pending = make_config(monitors={"HDMI-A-1": mon()})
    app.reload()
    app._sync_timers = [7]
    app._sync_once(7)
    assert FakeShell.opened == [] and app.shells == {}  # nothing reopened


def test_a_monitor_turned_off_twice_closes_its_older_leaving_shell_at_once(renv):
    app, store, _, _, make_config = renv
    first = app.shells["HDMI-A-1"]
    first.fade_in()
    store.pending = make_config(monitors={"HDMI-A-1": mon("plasma")})
    app.reload()
    assert app._leaving == {"HDMI-A-1": first} and first.fade_state == "fading-out"
    store.pending = make_config(monitors={"HDMI-A-1": mon()})
    app.reload()  # on again
    second = app.shells["HDMI-A-1"]
    second.fade_in()
    store.pending = make_config(monitors={"HDMI-A-1": mon("plasma")})
    app.reload()  # off again while the first is still fading
    assert first.fade_state == "done" and app._leaving == {"HDMI-A-1": second}


def test_a_rebuild_that_keeps_the_windows_holds_the_old_shell_too(renv):
    app, store, _, _, make_config = renv
    old = app.shells["HDMI-A-1"]
    old.fade_in()
    store.pending = make_config(theme={"thickness": 9}, monitors={"HDMI-A-1": mon()})
    app.reload()  # a structural change: rebuilt from the new config, crossfaded
    assert FakeShell.faded == [] and FakeShell.closed == [] and app._leaving == {"HDMI-A-1": old}
    assert app.shells["HDMI-A-1"] is not old


# ---- the quit and the leaving shells: guards (spec 21) ---------------------------------


def two_monitors(env, make_config, first=None, second=None):
    app, mapping = env
    app.store.config = make_config(
        monitors={
            "HDMI-A-1": {"shell": "edge", "theme": first or {}},
            "HDMI-A-2": {"shell": "edge", "theme": second or {}},
        }
    )
    mapping.update({"HDMI-A-1": object(), "HDMI-A-2": object()})
    app.sync_monitors()
    for shell in app.shells.values():
        shell.fade_in()
    return app


def test_the_quit_waits_for_the_longest_fade_plus_the_margin(env, make_config, timers):
    app = two_monitors(env, make_config, {"fade_ms": 50}, {"fade_ms": 300})
    app.app = QuitRecorder()
    app._on_quit_signal(app_mod.signal.SIGINT)
    assert [ms for ms, _ in timers.values()] == [300 + app_mod.QUIT_MARGIN_MS]
    assert app_mod.QUIT_MARGIN_MS == 250


def test_a_failing_fade_out_at_quit_still_fades_the_others_and_quits_after_the_bound(
    env, make_config, timers, caplog
):
    app = two_monitors(env, make_config)
    app.app = QuitRecorder()

    def broken(_ms, _on_done):
        raise RuntimeError("cannot fade")

    app.shells["HDMI-A-1"].fade_out = broken
    app._on_quit_signal(app_mod.signal.SIGTERM)
    assert (
        FakeShell.faded == [("HDMI-A-2", 50)]
        and "fading out HDMI-A-1 for the quit failed" in caplog.text
    )
    assert app.app.quits == 0
    ((_, fn),) = timers.values()
    assert fn() is False
    assert app.app.quits == 1 and app._exit_code == 143


def test_a_leaving_shell_that_cannot_close_is_logged_and_does_not_stop_the_next(renv, caplog):
    app, store, _, _, make_config = renv
    first = app.shells["HDMI-A-1"]
    first.fade_in()
    store.pending = make_config(monitors={"HDMI-A-1": mon("plasma")})
    app.reload()
    assert app._leaving == {"HDMI-A-1": first}

    def broken():
        raise RuntimeError("cannot close")

    first.close = broken
    store.pending = make_config(monitors={"HDMI-A-1": mon()})
    app.reload()
    second = app.shells["HDMI-A-1"]
    second.fade_in()
    store.pending = make_config(monitors={"HDMI-A-1": mon("plasma")})
    app.reload()  # retires the first, whose close raises
    assert "closing the leaving shell of HDMI-A-1 failed" in caplog.text
    assert app._leaving == {"HDMI-A-1": second} and second.fade_state == "fading-out"


def test_a_monitor_replaced_while_its_older_shell_leaves_closes_both_at_once(renv):
    app, store, _, mapping, make_config = renv
    first = app.shells["HDMI-A-1"]
    first.fade_in()
    store.pending = make_config(monitors={"HDMI-A-1": mon("plasma")})
    app.reload()
    store.pending = make_config(monitors={"HDMI-A-1": mon()})
    app.reload()  # on again, while the first still fades
    second = app.shells["HDMI-A-1"]
    assert app._leaving == {"HDMI-A-1": first} and first.fade_state == "fading-out"
    mapping["HDMI-A-1"] = object()  # a new Gdk monitor: the second is closed now
    app.sync_monitors()
    assert first.fade_state == "done" and second.fade_state == "done"
    assert app._leaving == {} and FakeShell.closed.count("HDMI-A-1") == 2


def test_a_monitor_turned_off_just_before_the_quit_is_waited_for(env, make_config, timers):
    app = two_monitors(env, make_config)
    app.store.config = make_config(
        monitors={
            "HDMI-A-1": {"shell": "plasma", "theme": {"fade_ms": 300}},
            "HDMI-A-2": {"shell": "edge"},
        }
    )
    app.sync_monitors()  # HDMI-A-1 is off: fading out, only in _leaving
    leaving = app._leaving["HDMI-A-1"]
    assert "HDMI-A-1" not in app.shells and leaving.fade_state == "fading-out"
    app.app = QuitRecorder()
    app._on_quit_signal(app_mod.signal.SIGINT)
    assert [ms for ms, _ in timers.values()] == [300 + app_mod.QUIT_MARGIN_MS]
    leaving.faded_out()
    assert app.app.quits == 0 and "HDMI-A-2" in app._leaving  # still waiting for the other


# ---- crossfade on a rebuild (spec 21) -------------------------------------------------


def thicker(make_config, **theme):
    return make_config(
        theme={"thickness": 12, **theme},
        monitors={"HDMI-A-1": mon(panels=[{"panel": "edge", "name": "dock", "widget": "dock"}])},
    )


def test_a_rebuild_holds_the_old_shell_until_the_new_one_fades_in(renv):
    app, store, errors, _, make_config = renv
    old = app.shells["HDMI-A-1"]
    old.fade_in()
    store.pending = thicker(make_config)
    app.reload()
    new = app.shells["HDMI-A-1"]
    assert new is not old and FakeShell.opened == ["HDMI-A-1"]
    assert old.detached and FakeShell.closed == [] and FakeShell.faded == []  # held, on screen
    assert app._leaving == {"HDMI-A-1": old} and new.on_fade_in == app._faded_in
    new.fade_in()  # the new shell is ready: both fade, the old one out
    assert FakeShell.faded == [("HDMI-A-1", 50)] and old.fading_out
    assert old.reserved_again == 0  # the successor reserves the zone: never two sets
    old.faded_out()
    assert FakeShell.closed == ["HDMI-A-1"] and app._leaving == {} and errors == []


def test_only_a_shell_without_a_predecessor_reserves_its_edges_late(renv):
    """Phil's gate finding 4: a fresh enable builds the zone strips 50 ms after the fade-in
    starts; a rebuild's successor builds them at once (the held shell has none any more)."""
    app, store, _, _, make_config = renv
    old = app.shells["HDMI-A-1"]
    assert old.fade_ms == 50 and old.reserve_now is False  # fresh, fading: late
    old.fade_in()
    store.pending = thicker(make_config)
    app.reload()
    assert app.shells["HDMI-A-1"].reserve_now is True  # a predecessor is held


def test_a_shell_opened_while_the_previous_one_fades_out_reserves_late(renv):
    """The fading-out shell keeps its strips until its fade ends: a second set built at once
    would stack the zones, so the new shell builds its own 50 ms after its fade-in starts."""
    app, store, _, _, make_config = renv
    first = app.shells["HDMI-A-1"]
    first.fade_in()
    store.pending = make_config(monitors={"HDMI-A-1": mon("plasma")})
    app.reload()
    assert first.fade_state == "fading-out" and app._leaving == {"HDMI-A-1": first}
    store.pending = make_config(monitors={"HDMI-A-1": mon()})
    app.reload()  # enabled again, the first still fading out
    assert app.shells["HDMI-A-1"].reserve_now is False


def test_an_enable_after_a_finished_disable_reserves_late_again(renv):
    app, store, _, _, make_config = renv
    app.shells["HDMI-A-1"].fade_in()
    store.pending = make_config(monitors={"HDMI-A-1": mon("plasma")})
    app.reload()
    app._leaving["HDMI-A-1"].faded_out()  # gone: nothing is held
    store.pending = make_config(monitors={"HDMI-A-1": mon()})
    app.reload()
    assert app.shells["HDMI-A-1"].reserve_now is False


def test_without_a_fade_the_strips_are_reserved_at_once(renv):
    app, store, _, _, make_config = renv
    store.pending = thicker(make_config, fade_ms=0)
    app.reload()
    assert app.shells["HDMI-A-1"].fade_ms == 0 and app.shells["HDMI-A-1"].reserve_now is True


def test_a_held_shell_whose_waiting_successor_is_turned_off_keeps_its_zone(renv):
    """Gate item 7: change the thickness, then untick Enable before the new frame appears."""
    app, store, _, _, make_config = renv
    old = app.shells["HDMI-A-1"]
    old.fade_in()
    store.pending = thicker(make_config)
    app.reload()
    new = app.shells["HDMI-A-1"]
    assert new.fade_state == "waiting" and old.reserved_again == 0  # held: no strips
    store.pending = make_config(monitors={"HDMI-A-1": mon("plasma")})
    app.reload()
    assert new.fade_state == "done" and old.fading_out
    assert old.reserved_again == 1  # its strips are back before the fade-out starts


def test_the_old_shell_fades_out_over_the_new_configs_fade(renv):
    app, store, _, _, make_config = renv
    app.shells["HDMI-A-1"].fade_in()
    store.pending = thicker(make_config, fade_ms=300)
    app.reload()
    app.shells["HDMI-A-1"].fade_in()
    assert FakeShell.faded == [("HDMI-A-1", 300)]
    assert app.shells["HDMI-A-1"].fade_ms == 300


def test_a_held_shell_is_out_of_every_report_and_reload(renv, monkeypatch):
    app, store, _, _, make_config = renv
    old = app.shells["HDMI-A-1"]
    old.fade_in()
    store.pending = thicker(make_config)
    app.reload()
    new = app.shells["HDMI-A-1"]
    old.on_error(old)  # a stale re-layout failure of the held shell: ignored
    assert app.shells["HDMI-A-1"] is new and FakeShell.opened == ["HDMI-A-1"]
    store.pending = thicker(make_config, accent="#112233")
    app.reload()  # a restyle: applied to the new shell only, never a fade
    assert FakeShell.applied == [("HDMI-A-1", ["restyle"])] and FakeShell.faded == []
    assert app._leaving == {"HDMI-A-1": old} and not old.fading_out  # still held


def test_a_held_shell_whose_successor_fails_to_build_fades_out(renv):
    app, store, errors, _, make_config = renv
    old = app.shells["HDMI-A-1"]
    old.fade_in()
    FakeShell.fail_open = {"HDMI-A-1"}
    store.pending = thicker(make_config)
    app.reload()  # the new shell raises: reported, and the old one must not stay held
    assert len(errors) == 1 and "cannot build" in errors[0]
    assert app.shells == {} and FakeShell.faded == [("HDMI-A-1", 50)] and old.fading_out
    assert old.reserved_again == 1  # no successor: it keeps the zone until it has faded out
    old.faded_out()
    assert app._leaving == {}


def test_a_fade_in_of_a_shell_that_is_not_the_current_one_does_not_fade_the_held_out(renv):
    app, store, _, _, make_config = renv
    old = app.shells["HDMI-A-1"]
    old.fade_in()
    store.pending = thicker(make_config)
    app.reload()
    app._faded_in(SimpleNamespace(name="HDMI-A-1"))  # a late ready of a replaced shell
    assert FakeShell.faded == [] and not old.fading_out and app._leaving == {"HDMI-A-1": old}


# ---- a held shell is always released (no shell is held forever) -----------------------


def test_a_failed_relayout_rebuild_releases_the_held_shell(renv):
    app, store, errors, _, make_config = renv
    old = app.shells["HDMI-A-1"]
    old.fade_in()
    store.pending = thicker(make_config)
    app.reload()
    new = app.shells["HDMI-A-1"]
    FakeShell.fail_open = {"HDMI-A-1"}
    new.on_error(new)  # its own re-layout fails and the rebuild raises
    assert app.shells == {} and len(errors) == 1 and "rebuilding the panels" in errors[0]
    assert FakeShell.faded == [("HDMI-A-1", 50)] and old.fading_out
    assert old.reserved_again == 1
    old.faded_out()
    assert app._leaving == {}


def test_a_failed_apply_and_failed_rebuild_release_the_held_shell(renv):
    app, store, errors, _, make_config = renv
    old = app.shells["HDMI-A-1"]
    old.fade_in()
    store.pending = thicker(make_config)
    app.reload()  # the old shell is held, the new one waits
    FakeShell.fail_apply = {"HDMI-A-1"}
    FakeShell.fail_open = {"HDMI-A-1"}
    store.pending = thicker(make_config, accent="#112233")  # a restyle, applied in place
    app.reload()
    assert app.shells == {} and len(errors) >= 1 and "cannot build" in errors[-1]
    assert FakeShell.faded == [("HDMI-A-1", 50)] and old.fading_out
    old.faded_out()
    assert app._leaving == {}


# ---- a reload or a hot-plug during a fade (spec 21) -----------------------------------


def held_rebuild(renv):
    """The old shell shown, then a rebuild: (old held, new still waiting)."""
    app, store, _, _, make_config = renv
    old = app.shells["HDMI-A-1"]
    old.fade_in()
    store.pending = thicker(make_config)
    app.reload()
    return old, app.shells["HDMI-A-1"]


def test_a_second_rebuild_mid_crossfade_never_stacks_fades(renv):
    app, store, _, _, make_config = renv
    first, second = held_rebuild(renv)
    second.fade_in()  # crossfade: the first one fades out
    assert first.fading_out
    store.pending = thicker(make_config, radius=16)
    app.reload()
    third = app.shells["HDMI-A-1"]
    assert FakeShell.closed == ["HDMI-A-1"]  # the first one (half faded) goes at once
    assert FakeShell.finished == [first, second] and second.detached  # held, fully shown
    assert app._leaving == {"HDMI-A-1": second} and not second.fading_out
    third.fade_in()
    assert FakeShell.faded == [("HDMI-A-1", 50), ("HDMI-A-1", 50)] and second.fading_out


def test_a_rebuild_while_the_new_shell_is_still_invisible_keeps_the_held_one(renv):
    app, store, _, _, make_config = renv
    first, second = held_rebuild(renv)  # the second has not faded in yet
    store.pending = thicker(make_config, radius=16)
    app.reload()
    third = app.shells["HDMI-A-1"]
    assert FakeShell.closed == ["HDMI-A-1"] and second.fade_state == "done"  # never seen
    assert app._leaving == {"HDMI-A-1": first} and not first.fading_out  # still on screen
    third.fade_in()
    assert FakeShell.faded == [("HDMI-A-1", 50)] and first.fading_out


def test_a_rebuild_before_the_first_fade_in_just_replaces_the_invisible_shell(renv):
    app, store, _, _, make_config = renv
    store.pending = thicker(make_config)  # the shell from startup has not faded in yet
    app.reload()
    assert FakeShell.closed == ["HDMI-A-1"] and FakeShell.opened == ["HDMI-A-1"]
    assert app._leaving == {} and FakeShell.faded == []


def test_turning_a_monitor_off_while_its_new_shell_waits_fades_the_held_one(renv):
    app, store, _, _, make_config = renv
    first, second = held_rebuild(renv)
    store.pending = make_config(monitors={"HDMI-A-1": mon("plasma")})
    app.reload()
    assert second.fade_state == "done" and FakeShell.closed == ["HDMI-A-1"]  # never seen
    assert FakeShell.faded == [("HDMI-A-1", 50)] and first.fading_out  # the visible one fades
    first.faded_out()
    assert app.shells == {} and app._leaving == {}


def test_unplugging_a_monitor_mid_fade_closes_its_leaving_shell_at_once(renv):
    app, store, _, mapping, make_config = renv
    shell = app.shells["HDMI-A-1"]
    shell.fade_in()
    store.pending = make_config(monitors={"HDMI-A-1": mon("plasma")})
    app.reload()
    assert app._leaving == {"HDMI-A-1": shell} and FakeShell.closed == []
    del mapping["HDMI-A-1"]
    mapping["DP-1"] = object()
    app.sync_monitors()
    assert FakeShell.closed == ["HDMI-A-1"] and app._leaving == {}  # no fade on a dead output


def test_a_replaced_monitor_drops_the_held_shell_and_the_new_one_opens(renv):
    app, store, _, mapping, make_config = renv
    first, second = held_rebuild(renv)
    second.fade_in()
    mapping["HDMI-A-1"] = object()  # replugged: a new Gdk monitor
    app.sync_monitors()
    assert FakeShell.closed == ["HDMI-A-1", "HDMI-A-1"]  # both old shells, at once
    assert app._leaving == {} and FakeShell.opened[-1] == "HDMI-A-1"


def test_a_quit_while_a_shell_is_held_releases_it_and_never_hangs(renv, timers):
    app, _, _, _, _ = renv
    old, new = held_rebuild(renv)  # the new shell has never been visible
    app.app = QuitRecorder()
    app._on_quit_signal(app_mod.signal.SIGINT)
    assert new.fade_state == "done" and old.fading_out  # the new one closed, the held one fades
    assert FakeShell.faded == [("HDMI-A-1", 50)] and app.app.quits == 0
    assert old.reserved_again == 1
    old.faded_out()
    assert app._leaving == {} and app.shells == {} and app.app.quits == 1 and timers == {}


def test_a_quit_mid_crossfade_closes_the_old_one_and_fades_the_new_one(renv, timers):
    app, _, _, _, _ = renv
    old, new = held_rebuild(renv)
    app.app = QuitRecorder()
    new.fade_in()  # crossfading: the old one is fading out
    app._on_quit_signal(app_mod.signal.SIGINT)
    assert old.fade_state == "done" and new.fading_out  # nothing left behind
    assert app._leaving == {"HDMI-A-1": new} and app.app.quits == 0
    new.faded_out()
    assert app._leaving == {} and app.app.quits == 1 and timers == {}


def test_a_reload_only_releases_the_held_shell_of_its_own_monitor(env, make_config):
    """One reload rebuilds A and turns B off while B's shell still waits: B's never-seen shell
    closes, but A's held shell stays on screen until A's successor fades in."""
    app, mapping = env
    mapping.update({"HDMI-A-1": object(), "HDMI-A-2": object()})
    store = ReloadStore(make_config(monitors={"HDMI-A-1": mon(), "HDMI-A-2": mon("plasma")}))
    app.store = store
    app.sync_monitors()
    a_old = app.shells["HDMI-A-1"]
    a_old.fade_in()
    store.pending = make_config(monitors={"HDMI-A-1": mon(), "HDMI-A-2": mon()})
    app.reload()  # B on: a waiting shell
    b_waiting = app.shells["HDMI-A-2"]
    assert b_waiting.fade_state == "waiting"
    store.pending = make_config(
        monitors={
            "HDMI-A-1": {"shell": "edge", "panels": [], "theme": {"thickness": 12}},
            "HDMI-A-2": mon("plasma"),
        }
    )
    app.reload()  # A rebuilt (its old shell held), B turned off
    a_new = app.shells["HDMI-A-1"]
    assert a_new is not a_old and a_new.fade_state == "waiting"
    assert b_waiting.fade_state == "done"
    assert app._leaving == {"HDMI-A-1": a_old}
    assert not a_old.fading_out and a_old.fade_state == "shown"  # A still shows a frame
    a_new.fade_in()
    assert a_old.fading_out


def test_a_fading_out_shell_whose_monitor_is_replaced_is_closed_at_once(env, make_config):
    app, mapping = env
    store = ReloadStore(make_config(monitors={"HDMI-A-1": mon()}))
    app.store = store
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    shell = app.shells["HDMI-A-1"]
    shell.fade_in()
    store.pending = make_config(monitors={"HDMI-A-1": mon("plasma")})
    app.reload()
    assert app._leaving == {"HDMI-A-1": shell} and shell.fade_state == "fading-out"
    mapping["HDMI-A-1"] = object()  # a new Gdk monitor while it fades: its output is gone
    app.sync_monitors()
    assert shell.fade_state == "done" and app._leaving == {}
