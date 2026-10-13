import pytest

from shell import geometry as g

L, D, T, R = 560, 64, 10, 14


@pytest.mark.parametrize(
    ("edge", "size"),
    [("bottom", (588, 74)), ("top", (588, 74)), ("left", (74, 588)), ("right", (74, 588))],
)
def test_surface_size(edge, size):
    assert g.surface_size(edge, L, D, T, R) == size


def test_join_radius_grows_from_zero_and_caps_at_R():
    assert g.join_radius(7, R) == 3.5
    assert g.join_radius(27, R) == 13.5
    assert g.join_radius(28, R) == 14
    assert g.join_radius(30, R) == 14
    assert g.join_radius(-3, R) == 0


@pytest.mark.parametrize(
    ("edge", "u", "v", "expected"),
    [
        ("bottom", 14, 0, (14, 0)),
        ("top", 14, 0, (14, 74)),
        ("left", 14, 0, (74, 14)),
        ("right", 14, 0, (0, 14)),
        ("left", 14, 74, (0, 14)),
        ("right", 14, 74, (74, 14)),
    ],
)
def test_to_canvas(edge, u, v, expected):
    assert g.to_canvas(edge, u, v, 588, 74) == expected


@pytest.mark.parametrize("edge", ["top", "bottom", "left", "right"])
def test_cairo_matrix_agrees_with_to_canvas(edge):
    m = g.cairo_matrix(edge, 74)
    for u, v in [(0, 0), (14, 3), (300, 60), (588, 74)]:
        assert m.transform_point(u, v) == pytest.approx(g.to_canvas(edge, u, v, 588, 74))


@pytest.mark.parametrize(
    ("edge", "d", "rect"),
    [
        ("bottom", 64, (14, 0, 560, 74)),
        ("top", 64, (14, 0, 560, 74)),
        ("left", 64, (0, 14, 74, 560)),
        ("right", 64, (0, 14, 74, 560)),
        ("bottom", 0, (14, 64, 560, 10)),
        ("top", 0, (14, 0, 560, 10)),
        ("left", 0, (0, 14, 10, 560)),
        ("right", 0, (64, 14, 10, 560)),
        ("bottom", 3.5, (14, 60, 560, 14)),  # fractional depth rounds outward
    ],
)
def test_body_rect(edge, d, rect):
    assert g.body_rect(edge, L, D, d, T, R) == rect


def test_input_rect_grows_collapsed_hover_zone():
    assert g.input_rect("bottom", L, D, 0, T, R, 16) == (14, 48, 560, 26)
    assert g.input_rect("bottom", L, D, 64, T, R, 16) == (14, 0, 560, 74)
    # a shallow panel cannot have a hover zone deeper than itself
    assert g.input_rect("bottom", L, 10, 0, T, R, 16) == g.body_rect("bottom", L, 10, 10, T, R)


@pytest.mark.parametrize(
    ("edge", "pos", "expected"),
    [
        ("right", 600, ("right top", "586px 0px 0px 0px")),
        ("left", 150, ("left top", "136px 0px 0px 0px")),
        ("bottom", 0, ("bottom left", "0px 0px 0px 0px")),
        ("top", 200, ("top left", "0px 0px 0px 186px")),
    ],
)
def test_anchor_positioned(edge, pos, expected):
    # body starts at pos, so the surface starts R earlier (never negative)
    assert (
        g.anchor_and_margin(edge, pos, 328, R, 1080 if edge in ("left", "right") else 1920)
        == expected
    )


def test_pos_beyond_screen_is_clamped():  # Review Focus 3
    assert g.anchor_and_margin("right", 5000, 328, R, 1080) == ("right top", "752px 0px 0px 0px")
    assert g.anchor_and_margin("bottom", 99999, 588, R, 1920) == (
        "bottom left",
        "0px 0px 0px 1332px",
    )


def test_panel_longer_than_screen_does_not_go_negative():
    assert g.anchor_and_margin("bottom", 500, 3000, R, 1920) == ("bottom left", "0px 0px 0px 0px")
