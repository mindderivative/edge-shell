"""Corner panel geometry (spec 19): surface, body, content, hit target, input, damage box."""

import pytest

from shell import corner as cn
from shell import handle as hd
from shell.panel_spec import Interaction

T, R = 10, 14
HIT = hd.hit_size(T, 15, 290)  # (44, 14) for the default 300 px panel
ALL, NONE = Interaction(), Interaction(False, False, False)


@pytest.mark.parametrize(
    ("corner", "edge", "expected"),
    [
        ("bottom-left", "bottom", (5, 1075)),
        ("bottom-right", "bottom", (1915, 1075)),
        ("top-left", "top", (5, 5)),
        ("top-right", "top", (1915, 5)),
        ("bottom-left", "left", (5, 1075)),
        ("top-right", "right", (1915, 5)),
    ],
)
def test_to_xy_maps_from_the_corner(corner, edge, expected):
    assert cn.to_xy(corner, edge, 5, 5, 1920, 1080) == expected


def test_p_runs_along_the_opening_edge_and_q_across_it():
    assert cn.to_xy("bottom-left", "bottom", 300, 10, 1920, 1080) == (300, 1070)
    assert cn.to_xy("bottom-left", "left", 300, 10, 1920, 1080) == (10, 780)


def test_the_window_is_a_rectangle_in_the_corner():
    assert cn.anchor("bottom-left") == "bottom left"
    assert cn.anchor("top-right") == "top right"
    assert cn.surface_size("bottom", 300, 380, T) == (300, 390)
    assert cn.surface_size("left", 300, 380, T) == (390, 300)


@pytest.mark.parametrize(
    ("corner", "edge", "d", "expected"),
    [
        ("bottom-left", "bottom", 0, (0, 380, 300, 10)),
        ("bottom-left", "bottom", 380, (0, 0, 300, 390)),
        ("bottom-left", "bottom", 14.5, (0, 365, 300, 25)),
        ("top-right", "top", 0, (0, 0, 300, 10)),
        ("bottom-left", "left", 0, (0, 0, 10, 300)),
        ("top-right", "right", 100, (280, 0, 110, 300)),
    ],
)
def test_body_rect(corner, edge, d, expected):
    assert cn.body_rect(corner, edge, 300, 380, d, T) == expected


@pytest.mark.parametrize(
    ("corner", "edge", "expected"),
    [
        ("bottom-left", "bottom", (10, 0, 290, 380)),
        ("bottom-right", "bottom", (0, 0, 290, 380)),
        ("top-left", "top", (10, 10, 290, 380)),
        ("top-right", "right", (0, 10, 380, 290)),
    ],
)
def test_the_content_sits_past_both_frame_bands(corner, edge, expected):
    assert cn.content_rect(corner, edge, 300, 380, T) == expected


@pytest.mark.parametrize(
    ("corner", "edge", "d", "offset", "expected"),
    [
        ("bottom-left", "bottom", 0, 0, (133, 376, 44, 14)),
        ("bottom-left", "bottom", 380, 0, (133, 0, 44, 14)),
        ("bottom-right", "bottom", 0, 0, (123, 376, 44, 14)),
        ("bottom-right", "bottom", 0, 30, (153, 376, 44, 14)),  # + = right, as on edges
        ("bottom-left", "bottom", 0, 30, (163, 376, 44, 14)),
        ("bottom-left", "bottom", 0, 9999, (256, 376, 44, 14)),  # clamped to the body
        ("top-left", "left", 0, -20, (0, 113, 14, 44)),  # - = up, as on edges
        ("bottom-left", "left", 0, -20, (0, 103, 14, 44)),
    ],
)
def test_hit_rect_centres_on_the_body_past_the_band(corner, edge, d, offset, expected):
    assert cn.hit_rect(corner, edge, 300, 380, d, T, HIT, offset) == expected


def test_the_hit_target_stays_inside_the_body_past_the_band():
    for offset in (-9999, 9999):
        x, _y, w, _h = cn.hit_rect("bottom-left", "bottom", 300, 380, 0, T, HIT, offset)
        assert T <= x and x + w <= 300


def test_input_with_hover_is_the_body_plus_the_hover_zone():
    assert cn.input_rects("bottom-left", "bottom", 300, 380, 0, T, 16, ALL, HIT, 0) == [
        (0, 364, 300, 26)
    ]
    assert cn.input_rects("bottom-left", "bottom", 300, 380, 200, T, 16, ALL, HIT, 0) == [
        (0, 180, 300, 210)
    ]


def test_input_without_hover_is_the_body_and_the_hit_target():
    click = Interaction(hover=False)
    assert cn.input_rects("bottom-left", "bottom", 300, 380, 0, T, 16, click, HIT, 0) == [
        (133, 376, 44, 14)
    ]
    assert cn.input_rects("bottom-left", "bottom", 300, 380, 50, T, 16, click, HIT, 0) == [
        (0, 330, 300, 60),
        (133, 330, 44, 14),
    ]


def test_a_shallow_corner_panel_clamps_the_hover_zone_and_the_peek():
    """MIN_DEPTH (16) is below the largest hover zone and peek (64): both stop at the depth,
    the clamps edge panels already use (input_rects, panel_state.target_depth)."""
    from shell.panel_state import target_depth

    assert cn.input_rects("bottom-left", "bottom", 300, 16, 0, T, 64, ALL, HIT, 0) == [
        (0, 0, 300, 26)
    ]
    assert target_depth(False, True, 16, 64) == 16.0


def test_with_every_interaction_off_a_collapsed_corner_panel_is_click_through():
    assert cn.input_rects("bottom-left", "bottom", 300, 380, 0, T, 16, NONE, HIT, 0) == []


def test_every_input_rect_is_a_plain_rectangle_inside_the_surface():
    """The window is a rectangle, not an L: every region is one or two plain rectangles."""
    for corner in ("top-left", "top-right", "bottom-left", "bottom-right"):
        for edge in corner.split("-"):
            w, h = cn.surface_size(edge, 300, 380, T)
            for d in (0, 7.5, 190, 380):
                for inter in (ALL, Interaction(hover=False), NONE):
                    rects = cn.input_rects(corner, edge, 300, 380, d, T, 16, inter, HIT, 0)
                    for x, y, rw, rh in rects:
                        assert 0 <= x and 0 <= y and x + rw <= w and y + rh <= h


@pytest.mark.parametrize(
    ("corner", "edge", "expected"),
    [
        ("bottom-left", "bottom", (0, 676, 314, 1080)),
        ("bottom-right", "bottom", (1606, 676, 1920, 1080)),
        ("top-left", "left", (0, 0, 404, 314)),
        ("top-right", "right", (1516, 0, 1920, 314)),
    ],
)
def test_corner_box_covers_body_fillet_and_lifted_arc(corner, edge, expected):
    assert cn.corner_box(corner, edge, 300, 380, 1920, 1080, T, R) == expected


def test_corner_box_grows_by_pad_and_rounds_depth_up():
    assert cn.corner_box("bottom-left", "bottom", 300, 20.2, 1920, 1080, T, R, pad=26) == (
        0,
        1009,
        340,
        1080,
    )


def _mx(rect, width):
    x, y, w, h = rect
    return (width - x - w, y, w, h)


def _my(rect, height):
    x, y, w, h = rect
    return (x, height - y - h, w, h)


def _t(rect):
    x, y, w, h = rect
    return (y, x, h, w)


def _all(corner, edge, d, offset):
    """Every pure rect for one placement, as a name -> rects dict."""
    return {
        "body": [cn.body_rect(corner, edge, 300, 380, d, T)],
        "content": [cn.content_rect(corner, edge, 300, 380, T)],
        "hit": [cn.hit_rect(corner, edge, 300, 380, d, T, HIT, offset)],
        "input": sorted(cn.input_rects(corner, edge, 300, 380, d, T, 16, ALL, HIT, offset)),
        "input_click": sorted(
            cn.input_rects(corner, edge, 300, 380, d, T, 16, Interaction(hover=False), HIT, offset)
        ),
    }


@pytest.mark.parametrize("d", [0, 7.5, 190, 380])
@pytest.mark.parametrize("offset", [0, 30, -20, 9999])
def test_x_mirror_bottom_left_vs_bottom_right_negates_the_offset(d, offset):
    left = _all("bottom-left", "bottom", d, offset)
    right = _all("bottom-right", "bottom", d, -offset)
    sw, _sh = cn.surface_size("bottom", 300, 380, T)
    for key, rects in left.items():
        assert sorted(_mx(r, sw) for r in rects) == right[key], key
    lb = cn.corner_box("bottom-left", "bottom", 300, d, 1920, 1080, T, R)
    rb = cn.corner_box("bottom-right", "bottom", 300, d, 1920, 1080, T, R)
    assert (1920 - lb[2], lb[1], 1920 - lb[0], lb[3]) == rb


@pytest.mark.parametrize("d", [0, 7.5, 190, 380])
@pytest.mark.parametrize("offset", [0, 30, -20, 9999])
def test_y_mirror_top_vs_bottom_keeps_the_offset(d, offset):
    bottom = _all("bottom-left", "bottom", d, offset)
    top = _all("top-left", "top", d, offset)
    _sw, sh = cn.surface_size("bottom", 300, 380, T)
    for key, rects in bottom.items():
        assert sorted(_my(r, sh) for r in rects) == top[key], key
    bb = cn.corner_box("bottom-left", "bottom", 300, d, 1920, 1080, T, R)
    tb = cn.corner_box("top-left", "top", 300, d, 1920, 1080, T, R)
    assert (bb[0], 1080 - bb[3], bb[2], 1080 - bb[1]) == tb


@pytest.mark.parametrize("d", [0, 7.5, 190, 380])
@pytest.mark.parametrize("offset", [0, 30, -20, 9999])
def test_transpose_top_left_edge_top_vs_left(d, offset):
    top = _all("top-left", "top", d, offset)
    left = _all("top-left", "left", d, offset)
    for key, rects in top.items():
        assert sorted(_t(r) for r in rects) == left[key], key


def test_corner_box_top_left_on_the_top_edge():
    assert cn.corner_box("top-left", "top", 300, 380, 1920, 1080, T, R) == (0, 0, 314, 404)
