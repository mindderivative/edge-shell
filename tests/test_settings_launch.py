"""settings.launch: the command that opens a settings window, and starting it (nothing is
really spawned here)."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import settings.launch as launch


def test_the_command_uses_this_interpreter_and_main_py(tmp_path):
    cfg = tmp_path / "c.toml"
    assert launch.settings_command(cfg) == [
        sys.executable,
        str(Path(launch.__file__).resolve().parents[1] / "main.py"),
        "--settings",
        "--config",
        str(cfg),
    ]
    assert launch.settings_command(None)[-1] == "--settings"


def test_the_shell_uses_the_same_command():
    pytest.importorskip("fabric")
    import shell.app

    assert shell.app.settings_command is launch.settings_command


def test_spawn_starts_its_own_session_and_reaps_the_child(monkeypatch, tmp_path):
    pytest.importorskip("gi")
    from gi.repository import GLib

    started, watched = [], []

    def popen(command, **kw):
        started.append((command, kw))
        return SimpleNamespace(pid=4242, returncode=None)

    monkeypatch.setattr(launch.subprocess, "Popen", popen)
    monkeypatch.setattr(GLib, "child_watch_add", lambda *a: watched.append(a))
    monkeypatch.chdir(tmp_path)
    launch.spawn_settings(Path("rel.toml"))
    command, kw = started[0]
    assert command[-2:] == ["--config", str(tmp_path / "rel.toml")]  # absolute
    assert kw["start_new_session"] is True
    assert kw["stdin"] is launch.subprocess.DEVNULL
    _prio, pid, callback, proc = watched[0]
    assert pid == 4242
    callback(4242, 0, proc)
    assert proc.returncode == 0
    callback(4242, 3 << 8, proc)  # GLib's raw wait status of an exit with code 3
    assert proc.returncode == 3


def test_a_window_killed_by_a_signal_is_logged_with_a_negative_code(caplog):
    proc = SimpleNamespace(returncode=None)
    with caplog.at_level("WARNING"):
        launch._reaped(1, 9, proc)  # raw wait status 9: killed by SIGKILL
    assert proc.returncode == -9 and "status -9" in caplog.text
    caplog.clear()
    launch._reaped(1, 0, proc)
    assert caplog.text == ""
