"""Minimum geometry rules (spec 17): corner clearance and separation, so the outline never
self-intersects. Pixel tests pin the boundary cases to the legacy per-window renderers."""

import cairo
import pytest

from shell import geometry as g
from shell.canvas.outline import fill_mass
from shell.panel_layout import resolve_layout
from shell.panel_spec import PanelGeometry
from tests.legacy_draw import draw_panel, draw_screen_corner

W, H, T, R = 1920, 1080, 10, 14


def geo(widget="dock", edge="bottom", pos=None, length=560, depth=64, state="extended"):
    return PanelGeometry(widget, edge, pos, length, depth, state, widget)


def test_defaults_are_untouched_and_centred_panels_get_an_exact_pos():
    layout = resolve_layout(
        [geo(), geo("clock", "top", None, 168, 46), geo("bar", "right", 600, 300, 56)],
        W,
        H,
        T,
        R,
    )
    assert layout.warnings == []
    assert [(p.edge, p.pos, p.length) for p in layout.panels] == [
        ("bottom", 680, 560),
        ("top", 876, 168),
        ("right", 600, 300),
    ]


def test_centred_pos_matches_the_layer_shell_centring_of_the_old_surface():
    # the old window was (length + 2R) wide and centred by the compositor; body = surface + R
    for length in (168, 560, 561):
        p = resolve_layout([geo(length=length)], W, H, T, R).panels[0]
        assert p.pos == (W - (length + 2 * R)) // 2 + R


@pytest.mark.parametrize(
    ("pos", "expected"), [(0, 38), (37, 38), (38, 38), (5000, 1920 - 38 - 560)]
)
def test_pos_is_clamped_to_the_corner_clearance(pos, expected):
    layout = resolve_layout([geo(pos=pos)], W, H, T, R, where="monitors.HDMI-A-1")
    assert layout.panels[0].pos == expected
    if pos == expected:
        assert layout.warnings == []
    else:
        assert layout.warnings == [
            f"monitors.HDMI-A-1.panels.0 (dock): pos {pos} would run into a screen corner; "
            f"moved to {expected}"
        ]


def test_clearance_uses_the_join_radius_of_a_shallow_panel():
    # depth 16 -> r = 8: clearance 10 + 14 + 8 = 32
    assert resolve_layout([geo(pos=0, depth=16)], W, H, T, R).panels[0].pos == 32
    # depth 27 -> r = 13.5: clearance 37.5, rounded up so it is never violated
    assert resolve_layout([geo(pos=0, depth=27)], W, H, T, R).panels[0].pos == 38


def test_too_long_is_shrunk_to_the_free_span():
    layout = resolve_layout([geo("bar", "right", 100, 1500, 56)], W, H, T, R)
    p = layout.panels[0]
    assert (p.pos, p.length) == (38, 1080 - 2 * 38)
    assert "shrunk to 1004" in layout.warnings[0]


def test_no_room_at_all_hides_the_panel():
    layout = resolve_layout([geo("bar", "right", 0, 300, 56)], W, 130, T, R)
    assert layout.panels == [None]
    assert "has no room for it; not shown" in layout.warnings[0]


def test_neighbours_need_a_gap_of_r1_plus_r2():
    a = geo("dock", pos=400, length=300)  # ends at 700, r = 14
    ok = geo("clock", pos=700 + 14 + 8, length=100, depth=16)  # r = 8: gap exactly 22
    tight = geo("clock", pos=700 + 14 + 7, length=100, depth=16)
    assert resolve_layout([a, ok], W, H, T, R).warnings == []
    layout = resolve_layout([a, tight], W, H, T, R, where="monitors.X")
    assert layout.panels[1] is None and layout.panels[0] is not None
    assert layout.warnings[0].startswith(
        "monitors.X.panels.1 (clock): overlaps monitors.X.panels.0"
    )


def test_two_centred_panels_on_one_edge_keep_the_first():
    layout = resolve_layout([geo(), geo("clock", "bottom", None, 168, 46)], W, H, T, R)
    assert layout.panels[1] is None and len(layout.warnings) == 1


def test_deep_panels_on_neighbouring_edges_must_not_cross():
    top = geo("a", "top", 40, 300, 400)  # body x 40..340, y 0..410
    left = geo("b", "left", 40, 300, 400)  # body x 0..410, y 40..340
    layout = resolve_layout([top, left], W, H, T, R)
    assert layout.panels[1] is None
    far = geo("b", "left", 600, 300, 400)
    assert resolve_layout([top, far], W, H, T, R).warnings == []


def test_panels_on_different_edges_far_apart_are_fine():
    layout = resolve_layout(
        [geo("a", "bottom", None), geo("b", "top", None), geo("c", "left", None, 300, 50)],
        W,
        H,
        T,
        R,
    )
    assert layout.warnings == [] and None not in layout.panels


# ---- the rule boundaries render like the legacy per-window code --------------------

SW, SH = 400, 300
RGBA = (0.04, 0.05, 0.05, 1.0)


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


def as_outline(layout, d_fraction=1.0):
    return [(p.edge, p.pos, p.length, p.depth, p.depth * d_fraction) for p in layout.panels if p]


@pytest.mark.parametrize("edge", ["top", "bottom", "left", "right"])
@pytest.mark.parametrize("fraction", [1.0, 0.5, 0.2])
def test_panel_clamped_to_the_corner_renders_like_legacy(edge, fraction):
    layout = resolve_layout([geo("p", edge, 0, 120, 50)], SW, SH, T, R)
    assert layout.panels[0].pos == T + R + 14
    panels = as_outline(layout, fraction)
    assert bad_pixels(legacy(panels), outline(panels)) <= 2


def test_without_the_clamp_the_outline_breaks_inside_the_corner_arc():
    panels = [("top", 20, 120, 50, 50.0)]  # pos - r = 6 < T + R: the fillet hits the arc
    assert bad_pixels(legacy(panels), outline(panels)) > 20


@pytest.mark.parametrize("fraction", [1.0, 0.6, 0.3])
def test_neighbours_at_the_minimum_gap_render_like_legacy(fraction):
    layout = resolve_layout(
        [geo("a", "top", 60, 100, 50), geo("b", "top", 60 + 100 + 28, 80, 50)], SW, SH, T, R
    )
    assert None not in layout.panels and layout.warnings == []
    panels = as_outline(layout, fraction)
    assert bad_pixels(legacy(panels), outline(panels)) <= 2
