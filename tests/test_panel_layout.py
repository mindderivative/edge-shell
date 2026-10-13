"""The layout's minimum geometry renders correctly (spec 17): pixel tests pin panels placed by
shell.panel_layout at the rule boundaries to the legacy per-window renderers. The rules
themselves are in tests/test_layout_resolver.py."""

import cairo
import pytest

from shell import geometry as g
from shell.canvas.outline import fill_mass
from shell.panel_layout import layout_monitor
from shell.panel_spec import PanelRequest
from tests.legacy_draw import draw_panel, draw_screen_corner

T, R = 10, 14
SW, SH = 400, 300
RGBA = (0.04, 0.05, 0.05, 1.0)
EDGES = ["top", "bottom", "left", "right"]


def req(edge, align="center", offset=0, pos=None, length=120, depth=50):
    return PanelRequest(
        "p", edge, align, offset, pos, 0, length, None, None, depth, "extended", "p", length
    )


def alpha_rows(surface):
    surface.flush()
    data, stride = surface.get_data(), surface.get_stride()
    return [[data[y * stride + x * 4 + 3] for x in range(SW)] for y in range(SH)]


def legacy(panels):
    """Strips + corner pieces + each panel at its EdgePanel surface origin (union of fills)."""
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, SW, SH)
    cr = cairo.Context(s)
    cr.set_source_rgba(*RGBA)
    for rect in [(0, 0, SW, T), (0, SH - T, SW, T), (0, 0, T, SH), (SW - T, 0, T, SH)]:
        cr.rectangle(*rect)
    cr.fill()
    for corner, (ox, oy) in {
        "top-left": (T, T),
        "top-right": (SW - T - R, T),
        "bottom-left": (T, SH - T - R),
        "bottom-right": (SW - T - R, SH - T - R),
    }.items():
        cr.save()
        cr.translate(ox, oy)
        draw_screen_corner(cr, corner, R, RGBA)
        cr.restore()
    for edge, pos, length, depth, d in panels:
        sw, sh = g.surface_size(edge, length, depth, T, R)
        along = sw if g.is_horizontal(edge) else sh
        _, margin = g.anchor_and_margin(edge, pos, along, R, SW if g.is_horizontal(edge) else SH)
        top_m, _, _, left_m = (int(m[:-2]) for m in margin.split())
        origin = {
            "top": (left_m, 0),
            "bottom": (left_m, SH - sh),
            "left": (0, top_m),
            "right": (SW - sw, top_m),
        }[edge]
        cr.save()
        cr.translate(*origin)
        draw_panel(cr, edge, length, depth, d, T, R, RGBA)
        cr.restore()
    return alpha_rows(s)


def outline(panels):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, SW, SH)
    fill_mass(cairo.Context(s), SW, SH, T, R, panels, RGBA)
    return alpha_rows(s)


def bad_pixels(a, b):
    return sum(1 for y in range(SH) for x in range(SW) if abs(a[y][x] - b[y][x]) > 24)


def resolved(*requests, gap=8):
    layout = layout_monitor(list(requests), SW, SH, T, R, gap)
    assert None not in layout.panels and layout.warnings == []
    return layout.panels


def as_outline(panels, d_fraction=1.0):
    return [(p.edge, p.pos, p.length, p.depth, p.depth * d_fraction) for p in panels]


@pytest.mark.parametrize("edge", EDGES)
@pytest.mark.parametrize("fraction", [1.0, 0.5, 0.2])
def test_start_aligned_panel_at_the_corner_renders_like_legacy(edge, fraction):
    (p,) = resolved(req(edge, "start"))
    assert p.pos == T + R + 14
    panels = as_outline([p], fraction)
    assert bad_pixels(legacy(panels), outline(panels)) <= 2


@pytest.mark.parametrize("edge", EDGES)
@pytest.mark.parametrize("fraction", [1.0, 0.5, 0.2])
def test_end_aligned_panel_next_to_the_corner_renders_like_legacy(edge, fraction):
    (p,) = resolved(req(edge, "end"))
    extent = SW if g.is_horizontal(edge) else SH
    assert p.pos + p.length == extent - (T + R + 14)  # exactly at the clearance
    panels = as_outline([p], fraction)
    assert bad_pixels(legacy(panels), outline(panels)) <= 2


def test_pos_clamped_to_the_corner_renders_like_legacy():
    layout = layout_monitor([req("top", pos=0)], SW, SH, T, R, 8)
    assert layout.panels[0].pos == T + R + 14 and len(layout.warnings) == 1
    panels = as_outline(layout.panels)
    assert bad_pixels(legacy(panels), outline(panels)) <= 2


@pytest.mark.parametrize(
    "panels",
    [
        [("top", 20, 120, 50, 50.0)],  # start: pos - r = 6 < T + R, the fillet hits the arc
        [("top", SW - 20 - 120, 120, 50, 50.0)],  # end: the same at the other corner
    ],
)
def test_without_the_clearance_the_outline_breaks_inside_the_corner_arc(panels):
    assert bad_pixels(legacy(panels), outline(panels)) > 20


@pytest.mark.parametrize("fraction", [1.0, 0.6, 0.3])
def test_slot_neighbours_at_gap_zero_render_like_legacy(fraction):
    a = req("top", "start", offset=22, length=100)
    b = req("top", "start", length=80)
    pa, pb = resolved(a, b, gap=0)
    assert (pa.pos, pb.pos) == (60, 60 + 100 + 28)  # touching joins: r1 + r2 apart
    panels = as_outline([pa, pb], fraction)
    assert bad_pixels(legacy(panels), outline(panels)) <= 2
