"""Pins the legacy per-window renderers (tests/legacy_draw.py), the reference that
tests/test_canvas_outline.py compares the shape canvas with."""

import cairo
import pytest

from shell import geometry as g
from tests.legacy_draw import draw_panel, draw_screen_corner

L, DEPTH, T, R = 100, 50, 10, 14
RGBA = (0.04, 0.05, 0.05, 1.0)
EDGES = ["top", "bottom", "left", "right"]


def render_panel(edge, d):
    w, h = g.surface_size(edge, L, DEPTH, T, R)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surface)
    draw_panel(cr, edge, L, DEPTH, d, T, R, RGBA)
    surface.flush()
    return surface


def alpha(surface, x, y):
    stride = surface.get_stride()
    return surface.get_data()[int(y) * stride + int(x) * 4 + 3]


def canon_alpha(surface, edge, u, v):
    """Alpha at canonical (u, v) in the panel's bottom-edge space."""
    x, y = g.to_canvas(edge, u, v, L + 2 * R, T + DEPTH)
    return alpha(surface, x, y)


FILLED, EMPTY = 200, 20


@pytest.mark.parametrize("edge", EDGES)
def test_extended_panel(edge):
    s = render_panel(edge, DEPTH)  # canonical: x0=14, body x 14..114, y 0..60, join y 36..50
    assert canon_alpha(s, edge, 64.5, 30.5) > FILLED  # body
    assert canon_alpha(s, edge, 64.5, 55.5) > FILLED  # frame strip under the body
    assert canon_alpha(s, edge, 64.5, 0.5) > FILLED  # straight top edge
    assert canon_alpha(s, edge, 14.5, 0.5) < EMPTY  # rounded top-left corner cut away
    assert canon_alpha(s, edge, 113.5, 0.5) < EMPTY  # rounded top-right corner cut away
    assert canon_alpha(s, edge, 2.5, 2.5) < EMPTY  # far outside


@pytest.mark.parametrize("edge", EDGES)
def test_curved_joins_are_concave_fillets(edge):
    s = render_panel(edge, DEPTH)
    assert canon_alpha(s, edge, 13.5, 49.5) > FILLED  # left join, corner against the frame
    assert canon_alpha(s, edge, 0.5, 36.5) < EMPTY  # left join, circle centre stays clear
    assert canon_alpha(s, edge, 114.5, 49.5) > FILLED  # right join
    assert canon_alpha(s, edge, 127.5, 36.5) < EMPTY
    assert canon_alpha(s, edge, 5.5, 55.5) < EMPTY  # frame strip is another window


@pytest.mark.parametrize("edge", EDGES)
def test_collapsed_panel_is_just_the_frame_strip(edge):
    s = render_panel(edge, 0)
    assert canon_alpha(s, edge, 64.5, 55.5) > FILLED
    assert canon_alpha(s, edge, 64.5, 45.5) < EMPTY
    assert canon_alpha(s, edge, 5.5, 45.5) < EMPTY  # no joins at depth 0
    assert canon_alpha(s, edge, 5.5, 55.5) < EMPTY


@pytest.mark.parametrize("edge", EDGES)
def test_shallow_panel_joins_shrink_to_its_depth(edge):
    s = render_panel(edge, 7)  # join radius 3.5: square x 10.5..14, y 46.5..50
    assert canon_alpha(s, edge, 13.5, 49.5) > FILLED
    assert canon_alpha(s, edge, 10.5, 46.5) < EMPTY  # circle centre stays clear
    assert canon_alpha(s, edge, 7.5, 48.5) < EMPTY  # nothing sticks out past the shallow join
    assert canon_alpha(s, edge, 12.5, 44.5) < EMPTY  # nor above it


SILHOUETTE_DEPTHS = [2, 4, 7, 10, 14, 20, 27, 28, 40]


@pytest.mark.parametrize("edge", EDGES)
@pytest.mark.parametrize("d", SILHOUETTE_DEPTHS)
def test_silhouette_is_one_contiguous_symmetric_run(edge, d):
    import math

    s = render_panel(edge, d)
    span = L + 2 * R
    first_row = math.ceil(DEPTH - d)
    for v in range(first_row, DEPTH):  # rows strictly above the frame line (v < across - T)
        mask = [canon_alpha(s, edge, u + 0.5, v + 0.5) > 128 for u in range(span)]
        runs = sum(1 for u in range(span) if mask[u] and (u == 0 or not mask[u - 1]))
        assert runs == 1, f"row {v}: {runs} runs"
        for u in range(span):
            mirror = span - 1 - u
            near = mask[max(0, mirror - 1) : mirror + 2]
            assert mask[u] in near, f"row {v}: asymmetric at u={u}"


@pytest.mark.parametrize(
    ("corner", "outer", "inner"),
    [
        ("top-left", (0, 0), (13, 13)),
        ("top-right", (13, 0), (0, 13)),
        ("bottom-left", (0, 13), (13, 0)),
        ("bottom-right", (13, 13), (0, 0)),
    ],
)
def test_screen_corner(corner, outer, inner):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, R, R)
    draw_screen_corner(cairo.Context(surface), corner, R, RGBA)
    surface.flush()
    assert alpha(surface, *outer) > FILLED  # the desktop's outer corner is frame-colored
    assert alpha(surface, *inner) < EMPTY  # the rounded desktop area is clear
