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


def test_apply_depth_moves_handle_and_region_then_reports_to_the_canvas():
    calls = []
    s = SimpleNamespace(
        _place_handle=lambda d: calls.append(("handle", d)),
        _update_input_region=lambda d: calls.append(("region", d)),
        _on_depth=lambda d: calls.append(("canvas", d)),
    )
    ep.EdgePanel._apply_depth(s, 7.5)
    assert s._d == 7.5
    assert calls == [("handle", 7.5), ("region", 7.5), ("canvas", 7.5)]
    s._on_depth = None
    ep.EdgePanel._apply_depth(s, 1.0)  # no canvas callback: nothing breaks
    assert s._d == 1.0


def test_panels_no_longer_draw_their_own_body():
    assert not hasattr(ep.EdgePanel, "_on_draw")


def test_on_depth_is_stored_before_the_tweens_exist():
    # __init__ creates the depth Tween and calls jump_to, which runs _apply_depth and needs
    # self._on_depth. Building a real EdgePanel would map a window on Phil's screen, so this
    # display-free test checks the statement order in the source instead.
    import inspect

    src = inspect.getsource(ep.EdgePanel.__init__)
    assert src.index("self._on_depth = on_depth") < src.index("Tween(")
