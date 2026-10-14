"""Opening the settings window from the shell: a right-click on a panel handle (stand-ins only;
nothing is spawned)."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import shell.app as app_mod  # noqa: E402
import shell.edge_panel as ep  # noqa: E402


def press(button):
    return SimpleNamespace(button=button, x_root=5.0, y_root=5.0)


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
    assert kw["start_new_session"] is True  # Ctrl+C on the shell leaves the window open
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
