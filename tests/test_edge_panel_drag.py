"""Drag bookkeeping of EdgePanel, called on a stand-in object (no window needed)."""

from types import SimpleNamespace

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

from gi.repository import Gdk  # noqa: E402

import shell.edge_panel as ep  # noqa: E402


def stub(dragging, d=40.0, depth=60):
    s = SimpleNamespace(
        spec=SimpleNamespace(depth=depth, edge="bottom"),
        _press=(1.0, 1.0),
        _dragging=dragging,
        _d=d,
        _extended=False,
        _suppress_click=True,
        retargets=0,
        _clear_suppress=lambda: None,
    )

    def retarget():
        assert s._dragging is False  # must be cleared before retargeting
        s.retargets += 1

    s._retarget = retarget
    s._finish_drag = lambda: ep.EdgePanel._finish_drag(s)
    return s


def test_finish_drag_snaps_retargets_and_schedules_suppress_clear(monkeypatch):
    idle = []
    monkeypatch.setattr(ep.GLib, "idle_add", lambda fn: idle.append(fn))
    s = stub(dragging=True, d=40.0)  # past 50% of 60
    ep.EdgePanel._finish_drag(s)
    assert s._extended is True
    assert s._press is None and s._dragging is False
    assert s.retargets == 1
    assert len(idle) == 1


def test_finish_drag_without_drag_only_clears_the_press(monkeypatch):
    idle = []
    monkeypatch.setattr(ep.GLib, "idle_add", lambda fn: idle.append(fn))
    s = stub(dragging=False)
    ep.EdgePanel._finish_drag(s)
    assert s._press is None and s.retargets == 0 and idle == []


def test_lost_release_in_motion_finishes_like_a_release(monkeypatch):
    idle = []
    monkeypatch.setattr(ep.GLib, "idle_add", lambda fn: idle.append(fn))
    s = stub(dragging=True, d=10.0)  # below 50%: snaps collapsed
    s._extended = True
    event = SimpleNamespace(state=Gdk.ModifierType(0), x_root=0.0, y_root=0.0)
    assert ep.EdgePanel._on_motion(s, None, event) is False
    assert s._extended is False
    assert s._dragging is False and s._press is None
    assert s.retargets == 1 and len(idle) == 1
