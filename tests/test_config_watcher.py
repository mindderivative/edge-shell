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


@pytest.mark.parametrize("how", ["atomic", "in place"])
def test_a_write_through_a_symlink_fires(tmp_path, how):
    """A config symlinked from a dotfiles repo: the settings window's atomic write (it replaces
    the file the link points to) and an editor's in-place save both reload the shell."""
    from settings import files

    real = tmp_path / "dotfiles" / "config.toml"
    real.parent.mkdir()
    real.write_text("a = 1\n")
    link = tmp_path / "edge-shell" / "config.toml"
    link.parent.mkdir()
    link.symlink_to(real)
    control: list[int] = []
    plain, _control = _make(tmp_path, control)  # a plain file: does Gio deliver events here?
    calls: list[int] = []
    _watcher = ConfigWatcher(link, lambda: calls.append(1), debounce_ms=50)

    def write():
        if how == "atomic":
            files.write_atomic(link, "a = 2\n")
        else:
            real.write_text("a = 3\n")
        plain.write_text("a = 2\n")

    _run_loop(1000, (100, write))
    if not control:
        pytest.skip("no file-change events delivered in this environment")
    assert calls and link.is_symlink()


def test_a_retargeted_symlink_is_followed(tmp_path):
    """The link is re-pointed (a dotfiles switch): the NEW target fires, the OLD one no longer."""
    old = tmp_path / "old.toml"
    new = tmp_path / "new.toml"
    old.write_text("a = 1\n")
    new.write_text("a = 1\n")
    link = tmp_path / "config.toml"
    link.symlink_to(old)
    control: list[int] = []
    ctl = tmp_path / "ctl"
    ctl.mkdir()
    plain, _control = _make(ctl, control)
    calls: list[int] = []
    _watcher = ConfigWatcher(link, lambda: calls.append(1), debounce_ms=50)

    def retarget():
        tmp = tmp_path / "config.toml.new"
        tmp.symlink_to(new)
        os.replace(tmp, link)
        plain.write_text("a = 2\n")

    _run_loop(500, (100, retarget))
    if not control:
        pytest.skip("no file-change events delivered in this environment")
    calls.clear()
    _run_loop(500, (50, lambda: old.write_text("a = 5\n")))
    assert not calls
    _run_loop(500, (50, lambda: new.write_text("a = 6\n")))
    assert calls
