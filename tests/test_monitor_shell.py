"""Display-free tests for MonitorShell bookkeeping (windows are fakes)."""

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import shell.monitors as mon_mod  # noqa: E402


class FakeWindow:
    def __init__(self, raises=False):
        self.destroyed = False
        self.raises = raises
        self.raised = 0
        self.title = "w"

    def destroy(self):
        self.destroyed = True
        if self.raises:
            raise RuntimeError("already gone")

    def raise_to_top(self):
        self.raised += 1

    def get_title(self):
        return self.title


def bare_shell(windows, panels=(), unregister=None):
    shell = mon_mod.MonitorShell.__new__(mon_mod.MonitorShell)
    shell.name = "HDMI-A-1"
    shell.windows = list(windows)
    shell.panels = list(panels)
    shell.corners = []
    shell._closed = False
    shell._unregister = unregister or (lambda _w: None)
    return shell


def test_close_unregisters_then_destroys_every_window():
    seen = []
    wins = [FakeWindow(), FakeWindow()]

    def unregister(w):
        seen.append((w, w.destroyed))

    shell = bare_shell(wins, unregister=unregister)
    shell.close()
    assert [w for w, _ in seen] == wins
    assert all(not destroyed for _, destroyed in seen)  # unregistered before destroy
    assert all(w.destroyed for w in wins)
    assert shell.windows == [] and shell.panels == []


def test_destroy_panel_unregisters_it():
    panel = FakeWindow()
    gone = []
    shell = bare_shell([panel], [panel], unregister=gone.append)
    shell._destroy(panel)
    assert gone == [panel] and panel.destroyed
    assert shell.windows == []


def test_unregister_failure_does_not_block_destroy():
    def boom(_w):
        raise ValueError("not in list")

    win = FakeWindow()
    shell = bare_shell([win], unregister=boom)
    shell.close()
    assert win.destroyed


def test_destroy_error_is_contained():
    shell = bare_shell([FakeWindow(raises=True), FakeWindow()])
    shell.close()  # must not raise
    assert shell.windows == []
