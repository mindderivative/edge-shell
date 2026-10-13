import math

import cairo
import pytest

from shell.canvas import effects
from shell.canvas.effects import (
    MAX_REACH_PX,
    draw_border,
    draw_scene,
    draw_shadow_reach,
    draw_shadow_uniform,
    reach_px,
    shadow_levels,
)
from shell.canvas.outline import fill_mass

W, H, T, R = 600, 400, 10, 14
MASS = (0.04, 0.05, 0.05, 1.0)
ACCENT = (0.56, 0.83, 0.71, 1.0)  # #8fd3b6
# One top panel, centred, clear of the screen corners: (edge, pos, length, depth_full, d_now)
PANEL = [("top", 200, 200, 40, 40.0)]
BUMP_DEPTH = 40


def new_surface():
    return cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)


def pixels(surface):
    surface.flush()
    data = surface.get_data()
    stride = surface.get_stride()
    return lambda x, y: tuple(data[y * stride + x * 4 : y * stride + x * 4 + 4])  # B, G, R, A


def shadow_surface(pct, alpha=0.5, panels=PANEL):
    s = new_surface()
    draw_shadow_uniform(cairo.Context(s), W, H, T, R, panels, pct, (0, 0, 0, alpha))
    return s


def target(k, alpha, elevation):
    sigma = elevation / 2.5
    return alpha * 0.5 * math.erfc(k / (sigma * math.sqrt(2)))


def cumulative(levels, k):
    """Cumulative alpha at distance k as 0..1, simulating cairo's 8-bit OVER, widest layer first."""
    d = 0
    for i in range(len(levels), k, -1):
        a = round(levels[i - 1] * 255)
        t = d * (255 - a) + 0x80
        d = a + ((t + (t >> 8)) >> 8)
    return d / 255


# ---- shadow: profile -----------------------------------------------------------------------


@pytest.mark.parametrize(("elevation", "alpha"), [(8, 0.25), (16, 0.35), (32, 0.45), (48, 0.35)])
def test_shadow_levels_half_at_edge_monotonic_zero_at_elevation(elevation, alpha):
    levels = shadow_levels(elevation, alpha)
    assert len(levels) == elevation and all(0 <= a <= 1 for a in levels)
    cum = [cumulative(levels, k) for k in range(elevation + 1)]
    assert abs(cum[0] - alpha / 2) <= 1.5 / 255
    assert all(cum[k] >= cum[k + 1] - 1e-9 for k in range(elevation))
    assert cum[elevation] == 0
    for k in range(elevation + 1):  # follows the erfc model
        assert abs(cum[k] - target(k, alpha, elevation)) <= 2 / 255


def test_shadow_rendered_profile_matches_model():
    elevation, alpha = reach_px(50), 0.45
    px = pixels(shadow_surface(50, alpha))
    col = [px(100, T + k)[3] for k in range(elevation + 4)]
    steps = [col[i] - col[i + 1] for i in range(len(col) - 1)]
    assert all(st >= 0 for st in steps), col
    assert col[-1] == 0 and col[-2] == 0 and col[elevation] <= 1
    assert abs(col[0] - 255 * alpha / 2) <= 6, (col[0], 255 * alpha / 2)
    ideal = [round(255 * target(k + 0.5, alpha, elevation)) for k in range(len(col))]
    assert max(abs(c - i) for c, i in zip(col, ideal, strict=True)) <= 3


@pytest.mark.parametrize("pct", [17, 33, 67])
def test_shadow_is_uniform_on_all_four_sides(pct):
    elevation = reach_px(pct)
    px = pixels(shadow_surface(pct, 0.45))
    for k in range(elevation + 1):
        sides = {
            "left": px(T + k, 200)[3],
            "right": px(W - 1 - T - k, 200)[3],
            "top": px(100, T + k)[3],
            "bottom": px(100, H - 1 - T - k)[3],
        }
        spread = max(sides.values()) - min(sides.values())
        assert spread <= 1, f"k={k}: not uniform {sides}"


def test_shadow_colour_is_used():
    s = new_surface()
    draw_shadow_uniform(cairo.Context(s), W, H, T, R, PANEL, 33, (1.0, 0.0, 0.0, 0.5))
    b, g, r, a = pixels(s)(100, T)
    assert g == 0 and b == 0 and r == a > 0  # premultiplied pure red


def test_shadow_leaves_mass_untouched_and_does_not_leak_under_it():
    s = new_surface()
    fill_mass(cairo.Context(s), W, H, T, R, PANEL, MASS)
    px = pixels(s)
    snapshot = {(x, y): px(x, y) for y in range(H) for x in range(W)}
    draw_shadow_uniform(cairo.Context(s), W, H, T, R, PANEL, 33, (0, 0, 0, 0.5))
    after = pixels(s)
    checked = 0
    for (x, y), v in snapshot.items():
        if v[3] == 255:
            checked += 1
            assert after(x, y) == v, f"mass pixel changed at ({x},{y})"
    assert checked > 10000
    solo = pixels(shadow_surface(33))  # shadow alone: nothing on any fully-mass pixel
    for (x, y), v in snapshot.items():
        if v[3] == 255:
            assert solo(x, y)[3] == 0, f"shadow leaked under the mass at ({x},{y})"


# ---- elevation percentage ------------------------------------------------------------------


def test_max_reach_is_48_px():
    assert MAX_REACH_PX == 48  # calibrated with Phil (spec 18); the only place it is pinned


def test_reach_mapping():
    m = MAX_REACH_PX
    assert (reach_px(0), reach_px(100)) == (0, m)
    assert reach_px(50) == round(m * 0.5) and reach_px(25) == round(m * 0.25)
    vals = [reach_px(p) for p in range(101)]
    assert all(isinstance(v, int) for v in vals)
    assert vals == sorted(vals)  # monotonic
    assert all(v == round(m * p / 100) for p, v in enumerate(vals))  # integer-rounded


def test_reach_mapping_reads_the_constant(monkeypatch):
    monkeypatch.setattr(effects, "MAX_REACH_PX", 96)
    assert (reach_px(0), reach_px(50), reach_px(100)) == (0, 48, 96)
    monkeypatch.setattr(effects, "MAX_REACH_PX", 20)
    assert (reach_px(50), reach_px(100)) == (10, 20)


def test_reach_out_of_range_is_clamped():
    assert reach_px(-20) == 0 and reach_px(250) == MAX_REACH_PX


def test_zero_percent_draws_nothing():
    assert bytes(shadow_surface(0, 0.9).get_data()) == bytes(new_surface().get_data())
    with_none = new_surface()
    draw_scene(cairo.Context(with_none), W, H, T, R, PANEL, MASS)
    with_zero = new_surface()
    draw_scene(cairo.Context(with_zero), W, H, T, R, PANEL, MASS, shadow=(0, (0, 0, 0, 0.9)))
    assert bytes(with_none.get_data()) == bytes(with_zero.get_data())


def test_reach_matches_percentage_at_100_and_50_percent():
    for pct in (100, 50):
        reach = reach_px(pct)
        col = [pixels(shadow_surface(pct, 0.6))(100, T + k)[3] for k in range(reach + 3)]
        assert col[reach - 1] > 0 or col[reach - 2] > 0  # still reaching just inside
        assert col[reach] <= 1 and col[reach + 1] == 0 and col[reach + 2] == 0


def test_higher_percent_never_smaller_alpha_at_any_distance():
    pcts = [10, 25, 40, 50, 75, 100]
    cols = [
        [pixels(shadow_surface(p, 0.45))(100, T + k)[3] for k in range(MAX_REACH_PX + 4)]
        for p in pcts
    ]
    for lo, hi in zip(cols, cols[1:], strict=False):
        assert all(b >= a for a, b in zip(lo, hi, strict=True)), (lo, hi)


# ---- border --------------------------------------------------------------------------------


def mass_with_border(width, rgba):
    s = new_surface()
    cr = cairo.Context(s)
    fill_mass(cr, W, H, T, R, PANEL, MASS)
    draw_border(cr, W, H, T, R, PANEL, width, rgba)
    return s


def border_only(width, rgba):
    s = new_surface()
    draw_border(cairo.Context(s), W, H, T, R, PANEL, width, rgba)
    return s


@pytest.mark.parametrize("width", [1, 2, 4])
def test_border_exactly_width_thick_on_desktop_side_nothing_on_mass(width):
    px = pixels(border_only(width, (1, 1, 1, 0.5)))
    edge = T + BUMP_DEPTH
    # under the panel bump: the band starts at the outline and runs `width` px into the desktop
    lit = [y for y in range(edge - 5, H // 2) if px(300, y)[3] > 60]
    assert abs(len(lit) - width) <= 1 and lit[0] == edge, lit
    assert all(px(300, y)[3] == 0 for y in range(0, edge))  # nothing inside the mass
    # along the frame
    lit_f = [y for y in range(H // 2) if px(100, y)[3] > 60]
    assert abs(len(lit_f) - width) <= 1 and lit_f[0] == T, lit_f
    assert all(px(100, y)[3] == 0 for y in range(0, T))
    assert all(px(100, y)[3] == 0 for y in range(T + width + 1, H - T - width - 1))


@pytest.mark.parametrize("width", [2, 6])
def test_border_never_touches_a_mass_pixel(width):
    plain = new_surface()
    fill_mass(cairo.Context(plain), W, H, T, R, PANEL, MASS)
    bordered = mass_with_border(width, (1, 1, 1, 0.5))
    p0, p1 = pixels(plain), pixels(bordered)
    checked = 0
    for y in range(H):
        for x in range(W):
            if p0(x, y)[3] == 255:
                checked += 1
                assert p1(x, y) == p0(x, y), f"mass pixel changed at ({x},{y})"
    assert checked > 10000


@pytest.mark.parametrize("alpha", [1.0, 0.5, 0.25])
def test_border_alpha_is_the_colour_alpha_blended_once(alpha):
    rgba = (ACCENT[0], ACCENT[1], ACCENT[2], alpha)
    s = border_only(6, rgba)
    px = pixels(s)
    b, g, r, a = px(100, T + 2)  # well inside the 6 px band
    assert abs(a - 255 * alpha) <= 1
    for got, border_c in zip((r, g, b), rgba[:3], strict=True):
        assert abs(got - 255 * border_c * alpha) <= 2, (got, border_c)
    # no pixel anywhere is darker than a single stroke (overlaps at joins / fillets / corners)
    top = max(px(x, y)[3] for y in range(H) for x in range(W))
    assert top <= round(255 * alpha) + 1, top


def test_border_blends_once_at_the_panel_joins_and_fillets():
    px = pixels(border_only(6, (1, 1, 1, 0.5)))
    # the inner join of the panel bump meets the frame near (200, 10) / (400, 10)
    for x in range(180, 230):
        for y in range(T, T + 20):
            assert px(x, y)[3] <= 129, (x, y, px(x, y))
    for x in range(0, 40):  # the screen-corner fillet
        for y in range(0, 40):
            assert px(x, y)[3] <= 129, (x, y, px(x, y))


def test_border_with_zero_width_or_colour_alpha_draws_nothing_on_the_mass():
    s = new_surface()
    fill_mass(cairo.Context(s), W, H, T, R, PANEL, MASS)
    before = bytes(s.get_data())
    draw_border(cairo.Context(s), W, H, T, R, PANEL, 4, (1, 1, 1, 0.0))
    assert bytes(s.get_data()) == before


# ---- shadow measured from the outer border edge ---------------------------------------------


def shadow_reach_surface(reach, alpha, offset=None):
    s = new_surface()
    cr = cairo.Context(s)
    if offset is None:
        draw_shadow_reach(cr, W, H, T, R, PANEL, reach, (0, 0, 0, alpha))
    else:
        draw_shadow_reach(cr, W, H, T, R, PANEL, reach, (0, 0, 0, alpha), offset=offset)
    return s


def test_shadow_offset_zero_is_exactly_the_old_behaviour():
    a = shadow_reach_surface(24, 0.45)
    b = shadow_reach_surface(24, 0.45, offset=0)
    assert bytes(a.get_data()) == bytes(b.get_data())


@pytest.mark.parametrize("offset", [2, 4, 6])
def test_shadow_profile_is_shifted_by_the_offset(offset):
    reach, alpha = 24, 0.45
    base = pixels(shadow_reach_surface(reach, alpha))
    moved = pixels(shadow_reach_surface(reach, alpha, offset=offset))
    for k in range(reach + 3):
        assert abs(moved(100, T + offset + k)[3] - base(100, T + k)[3]) <= 1, k
    # under the border band the shadow is at full edge strength, never beyond it
    edge_alpha = base(100, T)[3]
    for k in range(offset):
        assert abs(moved(100, T + k)[3] - edge_alpha) <= 1
    # and it ends `reach` px past the OUTER border edge
    assert moved(100, T + offset + reach + 1)[3] == 0
    assert moved(100, T + offset + reach - 3)[3] > 0


def test_shadow_offset_stays_off_the_mass():
    moved = pixels(shadow_reach_surface(24, 0.5, offset=5))
    assert all(moved(100, y)[3] == 0 for y in range(0, T))
    assert all(moved(300, y)[3] == 0 for y in range(0, T + BUMP_DEPTH))


def test_draw_scene_shadow_starts_at_the_outer_border_edge():
    width, reach = 4, reach_px(50)
    rgba = (ACCENT[0], ACCENT[1], ACCENT[2], 1.0)
    s = new_surface()
    sh = (50, (0.0, 0.0, 0.0, 0.5))
    draw_scene(cairo.Context(s), W, H, T, R, PANEL, MASS, border=(width, rgba), shadow=sh)
    px = pixels(s)
    ref = pixels(shadow_reach_surface(reach, 0.5))
    for k in range(reach + 2):
        assert abs(px(100, T + width + k)[3] - ref(100, T + k)[3]) <= 1, k
    # the (opaque) border sits over the shadow
    b, g, r, a = px(100, T + 1)
    assert (r, g, b, a) == (*(round(c * 255) for c in ACCENT[:3]), 255)


# ---- scene + damaged region ----------------------------------------------------------------

BORDER = (2, (ACCENT[0], ACCENT[1], ACCENT[2], 0.5))
SHADOW = (33, (0.0, 0.0, 0.0, 0.45))


def scene(depth, clip=None, surface=None):
    s = surface or new_surface()
    panels = [("top", 200, 200, 40, depth)]
    draw_scene(cairo.Context(s), W, H, T, R, panels, MASS, border=BORDER, shadow=SHADOW, clip=clip)
    return s


def snapshot(s):
    px = pixels(s)
    return [[px(x, y) for x in range(W)] for y in range(H)]


def test_draw_scene_order_shadow_under_mass_border_over():
    px = pixels(scene(40.0))
    edge = T + BUMP_DEPTH
    assert px(300, edge - 1)[3] == 255 and px(300, edge - 1)[2] == round(MASS[0] * 255)  # mass
    assert px(300, edge + 1)[2] > 60  # border lit just outside the mass (desktop side)
    assert px(300, edge + 2 + 4)[3] > 0 and px(300, edge + 2 + 4)[2] == 0  # shadow beyond it
    assert px(300, 5)[3] == 255 and px(300, 5)[2] == round(MASS[0] * 255)  # mass


def test_draw_scene_clip_matches_full_redraw_inside_and_keeps_outside():
    clip = (150, 0, 300, 100)
    x0, y0, cw, ch = clip
    s = scene(10.0)  # retained surface at an earlier state
    before = snapshot(s)
    scene(40.0, clip=clip, surface=s)
    got = snapshot(s)
    full = snapshot(scene(40.0))
    changed = 0
    for y in range(H):
        for x in range(W):
            if x0 <= x < x0 + cw and y0 <= y < y0 + ch:
                assert got[y][x] == full[y][x], f"inside clip differs at ({x},{y})"
                changed += got[y][x] != before[y][x]
            else:
                assert got[y][x] == before[y][x], f"outside clip changed at ({x},{y})"
    assert changed > 0


def test_draw_scene_without_options_is_just_the_mass():
    s = new_surface()
    draw_scene(cairo.Context(s), W, H, T, R, PANEL, MASS)
    ref = new_surface()
    fill_mass(cairo.Context(ref), W, H, T, R, PANEL, MASS)
    assert snapshot(s) == snapshot(ref)
