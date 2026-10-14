"""Corner panels in the one union outline (spec 19), against an independent reference: the
mass drawn as a union of simple filled pieces (frame bands, screen-corner pieces, the corner
panel's body, its free-end fillet and its lifted screen-corner piece, legacy edge panels)."""

import math

import cairo
import pytest

from shell import geometry as g
from shell.canvas.effects import draw_border, draw_shadow_reach
from shell.canvas.outline import fill_mass, outline_path
from tests.legacy_draw import draw_panel, draw_screen_corner
from tests.test_canvas_outline import alpha_bytes, surface_origin

W, H, T, R = 400, 300, 10, 14
RGBA = (0.04, 0.05, 0.05, 1.0)
ALONG, DEPTH = 120, 100
CORNER_EDGES = [
    (corner, edge)
    for corner in ("top-left", "top-right", "bottom-left", "bottom-right")
    for edge in corner.split("-")
]


def _offsets(radius):
    return {
        "top-left": (T, T),
        "top-right": (W - T - radius, T),
        "bottom-left": (T, H - T - radius),
        "bottom-right": (W - T - radius, H - T - radius),
    }


def pq_matrix(corner, edge):
    """(p, q) from the corner (p along `edge`, q away from its screen edge) -> screen."""
    sx = 1 if corner.endswith("left") else -1
    sy = 1 if corner.startswith("top") else -1
    x0 = 0 if sx == 1 else W
    y0 = 0 if sy == 1 else H
    if g.is_horizontal(edge):
        return cairo.Matrix(sx, 0, 0, sy, x0, y0)
    return cairo.Matrix(0, sy, sx, 0, x0, y0)


def draw_corner_reference(cr, corner, edge, along, d, radius=R):
    """The corner panel's pieces in (p, q), each filled on its own."""
    cr.save()
    cr.transform(pq_matrix(corner, edge))
    cr.set_source_rgba(*RGBA)
    # the screen-corner piece, lifted d px along the other edge
    cr.move_to(T, T + d)
    cr.line_to(T + radius, T + d)
    cr.arc_negative(T + radius, T + d + radius, radius, -0.5 * math.pi, -math.pi)
    cr.close_path()
    cr.fill()
    if d > 0:
        r = g.join_radius(d, radius)
        # the body: from the screen corner, its free corner rounded by r
        cr.move_to(0, 0)
        cr.line_to(along, 0)
        cr.line_to(along, T + d - r)
        cr.arc(along - r, T + d - r, r, 0, 0.5 * math.pi)
        cr.line_to(0, T + d)
        cr.close_path()
        cr.fill()
        # the concave fillet where its free side meets the band of `edge`
        cr.move_to(along, T)
        cr.line_to(along + r, T)
        cr.arc_negative(along + r, T + r, r, -0.5 * math.pi, -math.pi)
        cr.close_path()
        cr.fill()
    cr.restore()


def render_reference(corners, panels=(), radius=R):
    """corners: [(corner, edge, along, d)], panels: [(edge, pos, length, depth, d)]."""
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(s)
    cr.set_source_rgba(*RGBA)
    for rect in [(0, 0, W, T), (0, H - T, W, T), (0, 0, T, H), (W - T, 0, T, H)]:
        cr.rectangle(*rect)
    cr.fill()
    taken = {c for c, _e, _a, _d in corners}
    for name, (ox, oy) in _offsets(radius).items():
        if name not in taken:
            cr.save()
            cr.translate(ox, oy)
            draw_screen_corner(cr, name, radius, RGBA)
            cr.restore()
    for corner, edge, along, d in corners:
        draw_corner_reference(cr, corner, edge, along, d, radius)
    for edge, pos, length, depth, d in panels:
        ox, oy = surface_origin(edge, pos, length, depth)
        cr.save()
        cr.translate(ox, oy)
        draw_panel(cr, edge, length, depth, d, T, radius, RGBA)
        cr.restore()
    return alpha_bytes(s)


def render_canvas(corners, panels=(), radius=R):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    spans = [(c, e, a, DEPTH, d) for c, e, a, d in corners]
    fill_mass(cairo.Context(s), W, H, T, radius, list(panels), RGBA, spans)
    return alpha_bytes(s)


def bad_pixels(a, b):
    return [
        (x, y, a[y][x], b[y][x])
        for y in range(H)
        for x in range(W)
        if abs(a[y][x] - b[y][x]) > 24  # antialiasing tolerance on edge pixels only
    ]


@pytest.mark.parametrize(("corner", "edge"), CORNER_EDGES)
@pytest.mark.parametrize(
    ("d", "radius", "along"),
    [
        (0, R, ALONG),
        (3, R, ALONG),
        (14, R, ALONG),
        (27.5, R, ALONG),
        (60, R, ALONG),
        (100, R, ALONG),
        # a large theme radius at the layout's minimum along, T + R + r (Task 6): 80 and 90
        (60, 40, 80),
        (100, 40, 90),
    ],
)
def test_a_corner_panel_matches_the_reference_union(corner, edge, d, radius, along):
    bad = bad_pixels(
        render_reference([(corner, edge, along, d)], radius=radius),
        render_canvas([(corner, edge, along, d)], radius=radius),
    )
    assert len(bad) < 40, bad[:10]


def test_four_corner_panels_at_once():
    corners = [
        ("bottom-left", "bottom", ALONG, 60),
        ("bottom-right", "right", ALONG, 40),
        ("top-right", "top", ALONG, 100),
        ("top-left", "left", ALONG, 7),
    ]
    bad = bad_pixels(render_reference(corners), render_canvas(corners))
    assert len(bad) < 60, bad[:10]


def test_corner_panels_next_to_edge_panels_cleared_by_the_layout():
    # bottom: the edge panel starts at along + r_c + r_p = 120 + 14 + 14 = 148 (gap 12 more);
    # left: the bottom-left panel lifts the corner arc to T + R + depth = 124 px from the bottom
    # (y 176), and the left panel's fillet ends at 40 + 80 + 14 = 134
    corners = [("bottom-left", "bottom", ALONG, DEPTH)]
    panels = [("bottom", 160, 100, 40, 40), ("left", 40, 80, 30, 30)]
    bad = bad_pixels(render_reference(corners, panels), render_canvas(corners, panels))
    assert len(bad) < 60, bad[:10]


def test_with_every_depth_zero_the_path_is_the_plain_frame():
    def ops(corners):
        cr = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H))
        outline_path(cr, W, H, T, R, [("top", 120, 140, 50, 28)], corners)
        return list(cr.copy_path_flat())

    collapsed = [(c, e, ALONG, DEPTH, 0.0) for c, e in CORNER_EDGES[::2]]
    assert ops(collapsed) == ops([])


def test_the_outline_stays_one_closed_path_with_corner_panels():
    cr = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H))
    corners = [("bottom-left", "bottom", ALONG, DEPTH, 50), ("top-right", "right", ALONG, DEPTH, 9)]
    outline_path(cr, W, H, T, R, [], corners)
    kinds = [kind for kind, _ in cr.copy_path()]
    assert kinds.count(cairo.PATH_CLOSE_PATH) == 1 and kinds.count(cairo.PATH_MOVE_TO) == 2


def test_the_border_never_touches_the_corner_panels_mass():
    corners = [("bottom-left", "bottom", ALONG, DEPTH, 60)]
    mass = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    fill_mass(cairo.Context(mass), W, H, T, R, [], RGBA, corners)
    border = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    draw_border(cairo.Context(border), W, H, T, R, [], 3, (1, 1, 1, 1), corners)
    m, b = alpha_bytes(mass), alpha_bytes(border)
    assert not [(x, y) for y in range(H) for x in range(W) if m[y][x] == 255 and b[y][x]]
    # and it follows the lifted outline: the pixel just above the body's inner edge is border
    assert b[H - T - 60 - 2][60] == 255


def test_the_shadow_follows_the_corner_panel_and_stays_off_its_mass():
    corners = [("bottom-left", "bottom", ALONG, DEPTH, 60)]
    shadow = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    draw_shadow_reach(cairo.Context(shadow), W, H, T, R, [], 12, (0, 0, 0, 0.5), 0, corners)
    s = alpha_bytes(shadow)
    assert s[H - T - 60 - 1][60] > 0  # just outside the body's inner edge
    assert s[H - T - 30][60] == 0  # inside the body: never under the mass
