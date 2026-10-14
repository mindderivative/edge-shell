"""Headless pixel tests for draw_handle (shell/handle_draw.py)."""

import math

import cairo
import pytest

from shell import handle as hd
from shell import handle_draw as hdraw
from shell.theme import hex_to_rgba

W = H = 80
WHITE = (1.0, 1.0, 1.0, 1.0)
EDGES = ["top", "bottom", "left", "right"]
FILLED, EMPTY = 128, 20


def render(shape, edge, morph=0.0, size=15, weight=3, rgba=WHITE, max_across=6):  # band_room(10)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(surface)
    hdraw.draw_handle(cr, shape, size, weight, rgba, morph, edge, 40, 40, max_across)
    surface.flush()
    return surface


def pixel(surface, x, y):
    """(b, g, r, a) bytes of the pixel containing device point (x, y)."""
    off = int(math.floor(y)) * surface.get_stride() + int(math.floor(x)) * 4
    return tuple(surface.get_data()[off : off + 4])


def alpha(surface, x, y):
    return pixel(surface, x, y)[3]


def at(edge, u, v, across=3):
    """Device point of canonical (u along, v towards the desktop) around the centre (40, 40)
    as draw_handle snaps it for a 3 px weight and a shape `across` px wide."""
    cx, cy = hdraw.snap_centre(edge, 40, 40, 3, across)
    return hdraw.handle_matrix(edge, cx, cy).transform_point(u, v)


def lit(surface):
    data, stride = surface.get_data(), surface.get_stride()
    w, h = surface.get_width(), surface.get_height()
    return [(x, y) for y in range(h) for x in range(w) if data[y * stride + x * 4 + 3]]


@pytest.mark.parametrize("edge", EDGES)
def test_dots_are_three_crisp_dots_along_the_edge(edge):
    s = render("dots", edge)
    for u in (-6, 0, 6):  # 3 px dots, 3 px gaps: today's look
        assert alpha(s, *at(edge, u, 0)) == 255
    for u in (-3, 3, -9, 9):
        assert alpha(s, *at(edge, u, 0)) < EMPTY
    assert alpha(s, *at(edge, 0, 2)) < EMPTY and alpha(s, *at(edge, 0, -2)) < EMPTY


@pytest.mark.parametrize("edge", EDGES)
def test_bar_is_one_rounded_line(edge):
    s = render("bar", edge, size=20)
    for u in range(-8, 9):
        assert alpha(s, *at(edge, u, 0)) > FILLED
    assert alpha(s, *at(edge, -11, 0)) < EMPTY and alpha(s, *at(edge, 11, 0)) < EMPTY
    assert alpha(s, *at(edge, 0, 2)) < EMPTY and alpha(s, *at(edge, 0, -2)) < EMPTY


@pytest.mark.parametrize("edge", EDGES)
def test_chevron_points_where_the_panel_opens_then_morphs_back(edge):
    closed, flat, open_ = (render("chevron", edge, m) for m in (0.0, 0.5, 1.0))
    # height = min(15 / 2, 6 - 3) = 3: the tip is 1.5 px from the centre, the arm ends -1.5;
    # 2 * 1.5 + 3 = 6 px across in all (an even extent: the centre snaps to a pixel edge)
    assert alpha(closed, *at(edge, 0, 1.5, 6)) > FILLED  # tip towards the desktop
    assert alpha(closed, *at(edge, 0, -1.5, 6)) < EMPTY
    assert alpha(closed, *at(edge, 6, -1.5, 6)) > FILLED  # arm ends towards the screen edge
    assert alpha(flat, *at(edge, 0, 0)) > FILLED  # half way: a flat bar, 3 px across
    assert alpha(flat, *at(edge, 0, 2)) < EMPTY and alpha(flat, *at(edge, 0, -2)) < EMPTY
    assert alpha(open_, *at(edge, 0, -1.5, 6)) > FILLED  # extended: points back to the edge
    assert alpha(open_, *at(edge, 0, 1.5, 6)) < EMPTY


def test_the_tip_direction_matches_the_edge():
    # bottom panel collapsed: the chevron (6 px across) is centred on (40.5, 40) and points
    # up, into the screen
    s = render("chevron", "bottom", 0.0)
    assert alpha(s, 40.5, 38) > FILLED and alpha(s, 40.5, 42) < EMPTY
    s = render("chevron", "right", 0.0)
    assert alpha(s, 38, 40.5) > FILLED and alpha(s, 42, 40.5) < EMPTY


def test_colours_rest_hover_and_alpha():
    s = render("dots", "bottom", rgba=hex_to_rgba("#e6e8ea"))
    assert pixel(s, *at("bottom", 0, 0)) == (0xEA, 0xE8, 0xE6, 255)  # ARGB32 is BGRA in memory
    s = render("dots", "bottom", rgba=hex_to_rgba("#ffffff80"))
    assert pixel(s, *at("bottom", 0, 0)) == (128, 128, 128, 128)  # premultiplied


def band_profile(shape, edge, morph, size, weight, thickness, d):
    """Render like EdgePanel does: in its hd.hit_size target (44 x 14 at any thickness) at
    hd.shape_centre, at most hd.shape_room(thickness) px across. Returns
    {(along px, px from the box's screen-side edge): alpha} of every lit pixel."""
    along, across = hd.hit_size(thickness, size, 560)
    w, h = (along, across) if edge in ("top", "bottom") else (across, along)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cx, cy = hd.shape_centre(edge, w, h, thickness, d)
    hdraw.draw_handle(
        cairo.Context(surface),
        shape,
        size,
        weight,
        WHITE,
        morph,
        edge,
        cx,
        cy,
        hd.shape_room(thickness),
    )
    surface.flush()
    data, stride = surface.get_data(), surface.get_stride()
    out = {}
    for x, y in lit(surface):
        key = {"top": (x, y), "bottom": (x, h - 1 - y), "left": (y, x), "right": (y, w - 1 - x)}
        out[key[edge]] = data[y * stride + x * 4 + 3]
    return out


MORPHS = (0.0, 0.25, 0.5, 0.75, 1.0)


@pytest.mark.parametrize("shape", ["dots", "bar", "chevron"])
@pytest.mark.parametrize("edge", EDGES)
@pytest.mark.parametrize(("size", "weight"), [(4, 1), (15, 3), (40, 8)])
@pytest.mark.parametrize(("thickness", "clear"), [(10, 2), (6, 1), (20, 2), (64, 2)])
def test_the_shape_never_touches_the_band_edges(shape, edge, size, weight, thickness, clear):
    # The band (the last T px of the mass, ending on the body's inner edge at T + d px from
    # the screen edge) in box px is `first`..`first + T - 1`, clipped to the 14 px box. At
    # T = 10: box px 0..9 collapsed, the last 10 px of the box extended (d = 64). Decision
    # 12: `clear` px stay empty on both sides (band px 0, 1, T-2, T-1 at T = 10; 0 and T-1 on
    # the thin T = 6 band), also for the biggest size and weight (clamped to hd.shape_room).
    # Thick frames (20, 64): the shape stays 2 px inside the body's inner edge and inside the
    # box, wherever the box sits in the band (Gate B).
    box = hd.hit_size(thickness, size, 560)[1]
    for d in (0, 64):
        first = d - hd.hit_inset(thickness, d, box)  # band's screen-side px in box px
        for m in MORPHS:
            profile = band_profile(shape, edge, m, size, weight, thickness, d)
            assert profile, (d, m)
            across = {v for _, v in profile}
            low = max(first, 0) + clear
            high = min(first + thickness, box) - 1 - clear
            assert min(across) >= low and max(across) <= high, (d, m, across)


@pytest.mark.parametrize("edge", EDGES)
@pytest.mark.parametrize("thickness", [20, 64])
def test_a_thick_frame_draws_the_default_frame_shape(edge, thickness):
    # Gate B: at T = 64 the chevron's tip-to-arm extent grew and the shape sat mid-band. Now
    # every lit pixel (and its alpha) matches the default 10 px frame: extended the box sits
    # in the same place on both; collapsed the thick frame matches the default extended.
    for shape in ("dots", "bar", "chevron"):
        for m in MORPHS:
            default = band_profile(shape, edge, m, 15, 3, 10, 64)
            assert band_profile(shape, edge, m, 15, 3, thickness, 64) == default, (shape, m)
            assert band_profile(shape, edge, m, 15, 3, thickness, 0) == default, (shape, m)


@pytest.mark.parametrize("edge", EDGES)
def test_the_chevron_extent_does_not_grow_with_the_frame(edge):
    def rows(thickness):
        across = {v for _, v in band_profile("chevron", edge, 0.0, 15, 3, thickness, 0)}
        return max(across) - min(across) + 1

    assert rows(10) == 6  # 2 * 1.5 + 3 px: tip to arm ends, stroke included
    assert rows(20) == rows(64) == rows(10)
    assert rows(6) == 4  # a thin frame still shrinks it (band_room(6) = 4)


@pytest.mark.parametrize("shape", ["dots", "bar", "chevron"])
@pytest.mark.parametrize("thickness", [10, 20, 64])
def test_the_four_edges_mirror_each_other(shape, thickness):
    # the same pixels on every edge, measured from the screen edge (alpha may differ by a
    # few levels: cairo's anti-aliasing is not exactly mirror-symmetric)
    for d in (0, 64):
        for m in MORPHS:
            top, bottom, left, right = (
                band_profile(shape, e, m, 15, 3, thickness, d) for e in EDGES
            )
            for a, b in ((top, bottom), (left, right), (top, left)):
                assert set(a) == set(b), (d, m)
                assert all(abs(a[k] - b[k]) <= 16 for k in a), (d, m)


@pytest.mark.parametrize(
    ("shape", "rgba", "max_across"),
    [("none", WHITE, 8), ("dots", (1.0, 1.0, 1.0, 0.0), 8), ("bar", WHITE, 0)],
)
def test_nothing_is_drawn(shape, rgba, max_across):
    assert lit(render(shape, "bottom", rgba=rgba, max_across=max_across)) == []


def test_snap_aligns_odd_extents_to_pixel_centres_and_even_ones_to_pixel_edges():
    assert hdraw.snap(40, 3) == 40.5 and hdraw.snap(40.9, 3) == 40.5
    assert hdraw.snap(40.4, 2) == 40.0 and hdraw.snap(40.6, 4) == 41.0
    assert hdraw.snap(40.5, 2) == 41.0  # halves round up (round() would give 40)
    assert hdraw.snap(-9, 3) == -8.5


def test_snap_centre_rounds_across_from_the_screen_edge():
    # the same 3 px shape, 5 px from the screen edge of a 14 px deep box, on every edge:
    # always 5.5 px from that edge (pixels 4-6)
    assert hdraw.snap_centre("top", 22, 5, 3, 3) == (22.5, 5.5)
    assert hdraw.snap_centre("bottom", 22, 9, 3, 3) == (22.5, 8.5)  # 14 - 8.5 = 5.5
    assert hdraw.snap_centre("left", 5, 22, 3, 3) == (5.5, 22.5)
    assert hdraw.snap_centre("right", 9, 22, 3, 3) == (8.5, 22.5)
    assert hdraw.snap_centre("bottom", 22, 9, 3, 8) == (22.5, 9.0)  # even: a pixel edge


def test_the_review_sheet(tmp_path, capsys):
    out = tmp_path / "handles.png"
    assert hdraw.main(["--sheet", str(out)]) == 0
    assert out.stat().st_size > 0
    assert "handles.png (3360x4032)" in capsys.readouterr().out


def test_the_review_sheet_grows_its_cells_for_a_thick_frame(tmp_path, capsys):
    # T = 64: cells of 64 + 16 (sheet depth) + 8 = 88 px, 96 with the gap; 10 x 12 cells, x 6
    out = tmp_path / "thick.png"
    assert hdraw.main(["--sheet", str(out), "--thickness", "64"]) == 0
    assert "thick.png (5760x6912)" in capsys.readouterr().out


@pytest.mark.parametrize("shape", ["star", "auto"])
def test_unknown_or_undrawable_shapes_are_rejected(shape):
    with pytest.raises(ValueError, match="unknown handle shape"):
        render(shape, "bottom")


def test_a_path_left_open_by_the_caller_is_not_filled():
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(surface)
    cr.rectangle(2, 2, 10, 10)  # left open, far from the handle at (40, 40)
    hdraw.draw_handle(cr, "dots", 15, 3, WHITE, 0.0, "bottom", 40, 40, 6)
    surface.flush()
    assert alpha(surface, 6, 6) == 0


def test_even_sized_dots_keep_the_outer_dots_on_whole_pixels():
    s = render("dots", "top", size=16)
    cx, cy = hdraw.snap_centre("top", 40, 40, 3, 3)
    for u in (-7, 7):  # outer dot centres on pixel centres, so a 3 px dot covers whole pixels
        assert alpha(s, cx + u, cy) == 255
    assert alpha(s, cx + 7 + 2, cy) < EMPTY and alpha(s, cx - 7 - 2, cy) < EMPTY


def test_the_sheet_reports_an_unwritable_path_cleanly(tmp_path, capsys):
    assert hdraw.main(["--sheet", str(tmp_path / "missing-dir" / "x.png")]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("\n") == 1 and "x.png" in captured.err
