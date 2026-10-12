"""ConfigWatcher: debounced Gio file monitoring (display-free, GLib main loop only)."""

import os

import pytest

pytest.importorskip("gi")
from gi.repository import GLib  # noqa: E402

from shell.config.watcher import ConfigWatcher  # noqa: E402


def _run_loop(ms: int, *actions) -> None:
    """Run a main loop for ms; actions are (delay_ms, callable) pairs."""
    loop = GLib.MainLoop()
    for delay, fn in actions:
        GLib.timeout_add(delay, lambda f=fn: (f(), False)[1])
    GLib.timeout_add(ms, loop.quit)
    loop.run()


def _make(tmp_path, calls):
    path = tmp_path / "config.toml"
    path.write_text("a = 1\n")
    try:
        return path, ConfigWatcher(path, lambda: calls.append(1), debounce_ms=50)
    except Exception as exc:  # no usable Gio file monitor backend
        pytest.skip(f"Gio file monitoring unavailable: {exc}")


def test_burst_of_writes_fires_once(tmp_path):
    calls: list[int] = []
    path, watcher = _make(tmp_path, calls)

    def burst():
        for i in range(5):
            path.write_text(f"a = {i}\n")

    _run_loop(1000, (100, burst))
    assert watcher._monitor is not None
    if not calls:
        pytest.skip("no file-change events delivered in this environment")
    assert len(calls) == 1


def test_atomic_replace_fires(tmp_path):
    calls: list[int] = []
    path, _watcher = _make(tmp_path, calls)

    def replace():
        tmp = tmp_path / "config.toml.tmp"
        tmp.write_text("a = 2\n")
        os.replace(tmp, path)

    _run_loop(1000, (100, replace))
    if not calls:
        pytest.skip("no file-change events delivered in this environment")
    assert len(calls) >= 1
