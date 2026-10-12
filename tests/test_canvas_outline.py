"""Contract: the one union outline equals the legacy per-window renderers (tests/legacy_draw.py)."""

import cairo
import pytest

from shell import geometry as g
from shell.canvas.outline import fill_mass, outline_path
from tests.legacy_draw import draw_panel, draw_screen_corner

W, H, T, R = 400, 300, 10, 14
RGBA = (0.04, 0.05, 0.05, 1.0)
EDGES = ["top", "bottom", "left", "right"]


def alpha_bytes(surface):
    surface.flush()
    data = surface.get_data()
    stride = surface.get_stride()
    return [
        [data[y * stride + x * 4 + 3] for x in range(surface.get_width())]
        for y in range(surface.get_height())
    ]


def surface_origin(edge, pos, length, depth):
    """Where EdgePanel puts the surface (geometry.anchor_and_margin + layer-shell anchoring)."""
    sw, sh = g.surface_size(edge, length, depth, T, R)
    along = sw if g.is_horizontal(edge) else sh
    extent = W if g.is_horizontal(edge) else H
    _, margin = g.anchor_and_margin(edge, pos, along, R, extent)
    top_m, _, _, left_m = (int(m[:-2]) for m in margin.split())
    if edge == "top":
        return left_m, 0
    if edge == "bottom":
        return left_m, H - sh
    if edge == "left":
        return 0, top_m
    return W - sw, top_m


def render_legacy(edge, pos, length, depth, d):
    """Frame strips + corner pieces + one panel, drawn the way the per-window code does today."""
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(s)
    cr.set_source_rgba(*RGBA)
    for rect in [(0, 0, W, T), (0, H - T, W, T), (0, 0, T, H), (W - T, 0, T, H)]:
        cr.rectangle(*rect)
    cr.fill()
    for corner, (ox, oy) in {
        "top-left": (T, T),
        "top-right": (W - T - R, T),
        "bottom-left": (T, H - T - R),
        "bottom-right": (W - T - R, H - T - R),
    }.items():
        cr.save()
        cr.translate(ox, oy)
        draw_screen_corner(cr, corner, R, RGBA)
        cr.restore()
    ox, oy = surface_origin(edge, pos, length, depth)
    cr.save()
    cr.translate(ox, oy)
    draw_panel(cr, edge, length, depth, d, T, R, RGBA)
    cr.restore()
    return alpha_bytes(s)


def render_canvas(panels):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    fill_mass(cairo.Context(s), W, H, T, R, panels, RGBA)
    return alpha_bytes(s)


@pytest.mark.parametrize("edge", EDGES)
@pytest.mark.parametrize("d", [0, 5, 14, 28, 50])
def test_canvas_matches_per_window_renderers(edge, d):
    pos, length, depth = 120, 140, 50
    a = render_legacy(edge, pos, length, depth, d)
    b = render_canvas([(edge, pos, length, depth, d)])
    bad = [
        (x, y, a[y][x], b[y][x])
        for y in range(H)
        for x in range(W)
        if abs(a[y][x] - b[y][x]) > 24  # antialiasing tolerance on edge pixels only
    ]
    assert len(bad) < 40, bad[:10]  # allow a few antialiased edge pixels, not shape errors


def test_outline_is_one_closed_path():
    cr = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H))
    panels = [("top", 120, 140, 50, 28), ("left", 60, 100, 50, 14), ("bottom", 200, 90, 50, 50)]
    outline_path(cr, W, H, T, R, panels)
    kinds = [kind for kind, _ in cr.copy_path()]
    assert kinds[0] == cairo.PATH_MOVE_TO
    # cairo appends a MOVE_TO after CLOSE_PATH, so exactly one real MOVE_TO plus that one
    assert kinds.count(cairo.PATH_CLOSE_PATH) == 1
    assert kinds.count(cairo.PATH_MOVE_TO) == 2
    assert kinds[-1] == cairo.PATH_MOVE_TO and kinds[-2] == cairo.PATH_CLOSE_PATH


def test_multiple_panels_do_not_double_fill():
    panels = [("top", 120, 140, 50, 50), ("left", 60, 100, 50, 28), ("bottom", 200, 90, 50, 14)]
    single_max = max(max(row) for row in render_canvas([panels[0]]))
    multi = render_canvas(panels)
    assert max(max(row) for row in multi) <= single_max
    bare = render_canvas([])
    assert sum(map(sum, multi)) > sum(map(sum, bare))
