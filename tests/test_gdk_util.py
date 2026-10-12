from types import SimpleNamespace

import pytest

pytest.importorskip("gi")

from shell.gdk_util import monitor_index  # noqa: E402


class FakeMonitor:
    def __init__(self, x, y, w, h):
        self._g = SimpleNamespace(x=x, y=y, width=w, height=h)

    def get_geometry(self):
        return self._g


class FakeDisplay:
    def __init__(self, monitors):
        self._m = monitors

    def get_n_monitors(self):
        return len(self._m)

    def get_monitor(self, i):
        return self._m[i]


def _display():
    return FakeDisplay([FakeMonitor(0, 0, 1920, 1080), FakeMonitor(0, 1080, 1920, 1080)])


def test_found_by_identity():
    d = _display()
    assert monitor_index(d.get_monitor(1), d) == 1


def test_found_by_geometry():
    assert monitor_index(FakeMonitor(0, 1080, 1920, 1080), _display()) == 1


def test_not_found():
    with pytest.raises(ValueError):
        monitor_index(FakeMonitor(5, 5, 10, 10), _display())
