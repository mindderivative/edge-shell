# tests/test_panel_state.py
import pytest

from shell import panel_state as ps


@pytest.mark.parametrize(
    ("extended", "hovered", "expected"),
    [(True, False, 64), (True, True, 64), (False, True, 14), (False, False, 0)],
)
def test_target_depth(extended, hovered, expected):
    assert ps.target_depth(extended, hovered, 64, 14) == expected


def test_peek_never_exceeds_depth():
    assert ps.target_depth(False, True, 10, 14) == 10


@pytest.mark.parametrize(
    ("edge", "delta", "expected"),
    [
        ("bottom", -30, 30),  # dragging up pulls a bottom panel out
        ("bottom", 20, 0),  # dragging down clamps at collapsed
        ("bottom", -500, 64),  # clamps at full depth
        ("top", 30, 30),
        ("right", -30, 30),
        ("left", 30, 30),
        ("left", -30, 0),
    ],
)
def test_drag_depth(edge, delta, expected):
    assert ps.drag_depth(0, delta, 64, edge) == expected


def test_drag_starts_from_current_depth():
    assert ps.drag_depth(40, -10, 64, "bottom") == 50


def test_snap_threshold_is_half_depth():
    assert ps.snap_extended(32, 64) is True
    assert ps.snap_extended(31.9, 64) is False


def test_click_threshold():
    assert ps.is_click(3.9) is True
    assert ps.is_click(4) is False
