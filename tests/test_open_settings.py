"""Opening the settings window from the shell: a right-click on a panel handle (stand-ins only;
nothing is spawned)."""

import logging
import signal
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

from gi.repository import Gdk  # noqa: E402

import shell.app as app_mod  # noqa: E402
import shell.edge_panel as ep  # noqa: E402


def press(button, type_=None):
    return SimpleNamespace(
        button=button,
        x_root=5.0,
        y_root=5.0,
        type=Gdk.EventType.BUTTON_PRESS if type_ is None else type_,
    )


def panel_stub(on_settings):
    return SimpleNamespace(
        _on_settings=on_settings,
        _interaction=SimpleNamespace(drag=True),
        _press=None,
        _d=0.0,
        _press_depth=None,
        _dragging=False,
        _suppress_click=False,
    )


def test_a_right_click_on_the_handle_opens_the_settings():
    calls = []
    s = panel_stub(lambda: calls.append(1))
    assert ep.EdgePanel._on_press(s, None, press(3)) is True
    assert calls == [1] and s._press is None  # not the start of a drag


def test_a_right_click_without_a_settings_callback_does_nothing():
    s = panel_stub(None)
    assert ep.EdgePanel._on_press(s, None, press(3)) is False
    assert s._press is None


@pytest.mark.parametrize("kind", [Gdk.EventType._2BUTTON_PRESS, Gdk.EventType._3BUTTON_PRESS])
def test_a_double_or_triple_right_click_opens_nothing_more(kind):
    calls = []
    s = panel_stub(lambda: calls.append(1))
    assert ep.EdgePanel._on_press(s, None, press(3, kind)) is True
    assert calls == [] and s._press is None


def test_a_middle_press_is_not_a_settings_click():
    calls = []
    s = panel_stub(lambda: calls.append(1))
    assert ep.EdgePanel._on_press(s, None, press(2)) is False
    assert calls == []


def test_a_left_double_click_is_handled_as_before():
    s = panel_stub(None)
    assert ep.EdgePanel._on_press(s, None, press(1, Gdk.EventType._2BUTTON_PRESS)) is False
    assert s._press == (5.0, 5.0)


def test_a_left_press_still_starts_a_drag():
    calls = []
    s = panel_stub(lambda: calls.append(1))
    assert ep.EdgePanel._on_press(s, None, press(1)) is False
    assert s._press == (5.0, 5.0) and calls == []


def test_settings_command_uses_this_interpreter_and_the_config(tmp_path):
    cfg = tmp_path / "c.toml"
    assert app_mod.settings_command(cfg) == [
        sys.executable,
        str(Path(app_mod.__file__).resolve().parents[1] / "main.py"),
        "--settings",
        "--config",
        str(cfg),
    ]
    assert app_mod.settings_command(None)[-1] == "--settings"


def test_a_corner_panel_handle_opens_the_settings_too():
    """Spec 19: CornerPanel inherits EdgePanel's press handler (the right-click included)."""
    from shell.corner_panel import CornerPanel

    assert CornerPanel._on_press is ep.EdgePanel._on_press


def test_open_settings_starts_its_own_process_and_reaps_it(monkeypatch, make_config, tmp_path):
    spawned, watched = [], []
    proc = SimpleNamespace(pid=4242, returncode=None)

    def popen(cmd, **kw):
        spawned.append((cmd, kw))
        return proc

    monkeypatch.setattr(app_mod.subprocess, "Popen", popen)
    monkeypatch.setattr(app_mod.GLib, "child_watch_add", lambda *a: watched.append(a) or 1)
    store = SimpleNamespace(config=make_config(), path=tmp_path / "c.toml")
    app_mod.EdgeShellApp(store).open_settings()
    ((cmd, kw),) = spawned
    assert cmd[-3:] == ["--settings", "--config", str(tmp_path / "c.toml")]
    assert Path(cmd[-1]).is_absolute()
    assert kw["start_new_session"] is True
    assert kw["stdin"] is subprocess.DEVNULL  # Ctrl+C on the shell leaves the window open
    ((_priority, pid, callback, data),) = watched
    assert pid == 4242 and data is proc
    callback(4242, 0, proc)  # GLib reaped it: Popen must not wait for it again
    assert proc.returncode == 0


def test_open_settings_failure_is_notified_not_raised(monkeypatch, make_config, tmp_path):
    notified = []

    def fail(cmd, **kw):
        if cmd[0] == "notify-send":
            notified.append(cmd)
            return None
        raise OSError("no such interpreter")

    monkeypatch.setattr(app_mod.subprocess, "Popen", fail)
    store = SimpleNamespace(config=make_config(), path=tmp_path / "c.toml")
    app_mod.EdgeShellApp(store).open_settings()
    assert notified and "Settings not opened" in notified[0]


def test_a_relative_config_path_is_passed_absolute(monkeypatch, make_config, tmp_path):
    spawned = []
    monkeypatch.setattr(
        app_mod.subprocess, "Popen", lambda cmd, **kw: spawned.append(cmd) or SimpleNamespace(pid=1)
    )
    monkeypatch.setattr(app_mod.GLib, "child_watch_add", lambda *a: 1)
    monkeypatch.chdir(tmp_path)
    store = SimpleNamespace(config=make_config(), path=Path("rel.toml"))
    app_mod.EdgeShellApp(store).open_settings()
    assert spawned[0][-1] == str(tmp_path / "rel.toml")


def test_the_wait_status_is_decoded_to_an_exit_code():
    proc = SimpleNamespace(returncode=None)
    app_mod.EdgeShellApp._settings_closed(1, 3 << 8, proc)  # GLib hands over the raw status
    assert proc.returncode == 3
    app_mod.EdgeShellApp._settings_closed(1, signal.SIGTERM, proc)
    assert proc.returncode == -signal.SIGTERM


def test_a_failed_settings_exit_is_logged_with_a_hint(caplog):
    proc = SimpleNamespace(returncode=None)
    with caplog.at_level(logging.DEBUG, logger=app_mod.log.name):
        app_mod.EdgeShellApp._settings_closed(1, 3 << 8, proc)
    (rec,) = [r for r in caplog.records if r.levelno == logging.WARNING]
    msg = rec.getMessage()
    assert "status 3" in msg and "main.py --settings" in msg


def test_a_clean_settings_exit_is_only_debug(caplog):
    with caplog.at_level(logging.DEBUG, logger=app_mod.log.name):
        app_mod.EdgeShellApp._settings_closed(1, 0, SimpleNamespace(returncode=None))
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
