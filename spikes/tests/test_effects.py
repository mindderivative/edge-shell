import cairo
import pytest

from spikes.canvas.effects import draw_border, draw_shadow, shadow_alphas
from spikes.canvas.outline import fill_mass

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


def shadow_surface(layers, opacity=0.55, panels=PANEL):
    s = new_surface()
    cr = cairo.Context(s)
    draw_shadow(cr, W, H, T, R, panels, layers, opacity, (0, 0, 0))
    return s


def cumulative(alphas, k):
    """Cumulative alpha at distance k (layer i covers distances < i)."""
    rest = 1.0
    for i, a in enumerate(alphas, start=1):
        if i > k:
            rest *= 1 - a
    return 1 - rest


@pytest.mark.parametrize("layers", [8, 16, 24])
def test_shadow_alphas_cumulative_follows_falloff(layers):
    alphas = shadow_alphas(layers, 0.55)
    assert len(alphas) == layers
    assert all(0 <= a <= 1 for a in alphas)
    cum = [cumulative(alphas, k) for k in range(layers + 1)]
    assert all(cum[k] >= cum[k + 1] - 1e-9 for k in range(layers))  # monotonic
    assert abs(cum[0] - 0.55) <= 1 / 255
    assert cum[layers] == 0


def test_shadow_alphas_scale_with_opacity():
    low = shadow_alphas(16, 0.2)
    high = shadow_alphas(16, 0.8)
    assert cumulative(low, 0) == pytest.approx(0.2, abs=1 / 255)
    assert cumulative(high, 0) == pytest.approx(0.8, abs=1 / 255)


def column_alpha(surface, x, y0, y1):
    px = pixels(surface)
    return [px(x, y)[3] for y in range(y0, y1)]


@pytest.mark.parametrize("layers", [8, 16, 24])
def test_shadow_monotonic_and_banding(layers):
    s = shadow_surface(layers)
    # Under the panel bump (bottom edge at y = T + 40) and through empty frame (inner edge y = T).
    lines = {
        "panel": column_alpha(s, 300, T + BUMP_DEPTH, T + BUMP_DEPTH + layers + 2),
        "frame": column_alpha(s, 100, T, T + layers + 2),
    }
    target = shadow_alphas(layers, 0.55)
    for name, col in lines.items():
        steps = [col[i] - col[i + 1] for i in range(len(col) - 1)]
        assert all(st >= 0 for st in steps), f"{name} layers={layers} not monotonic: {col}"
        assert col[-1] == 0 and col[-2] == 0
        # Ideal 8-bit falloff of the model: compare the measured steps to the ideal steps. The
        # peak slope of the falloff itself is steeper than 2/255 at small elevations (a 140/255
        # drop over 8 px cannot be smoother), so banding is the deviation from the smooth model.
        ideal = [round(255 * cumulative(target, k + 0.5)) for k in range(len(col))]
        worst = max(abs(c - i) for c, i in zip(col, ideal, strict=True))
        ideal_steps = [ideal[i] - ideal[i + 1] for i in range(len(ideal) - 1)]
        dev = max(abs(a - b) for a, b in zip(steps, ideal_steps, strict=True))
        print(
            f"BANDING layers={layers} {name}: max adjacent step={max(steps)}/255 "
            f"ideal max step={max(ideal_steps)}/255 step deviation={dev} value deviation={worst}"
        )
        assert dev <= 2, f"{name} layers={layers}: step deviation {dev}/255 from the smooth model"


@pytest.mark.parametrize("layers", [8, 16, 24])
def test_shadow_symmetric_left_right(layers):
    s = shadow_surface(layers)
    px = pixels(s)
    # The panel is centred: spans 200..400 in a 600 wide screen, so x and W-1-x mirror.
    worst_curved = 0
    for y in range(0, T + BUMP_DEPTH + layers + 2):
        for x in range(0, W // 2):
            d = abs(px(x, y)[3] - px(W - 1 - x, y)[3])
            straight = 40 <= x <= 160 or 240 <= x <= 299  # away from every arc
            if straight:
                assert d <= 1, f"asymmetry on a straight run at ({x},{y}): {d}/255"
            worst_curved = max(worst_curved, d)
    # Edge pixels on arcs differ by cairo's arc tessellation, not by the method.
    print(f"SYMMETRY layers={layers}: worst arc-edge pixel difference {worst_curved}/255")
    assert worst_curved <= 8


def test_shadow_leaves_mass_untouched():
    s = new_surface()
    cr = cairo.Context(s)
    fill_mass(cr, W, H, T, R, PANEL, MASS)
    before = pixels(s)
    snapshot = {(x, y): before(x, y) for y in range(H) for x in range(W)}
    cr2 = cairo.Context(s)
    draw_shadow(cr2, W, H, T, R, PANEL, 16, 0.55, (0, 0, 0))
    after = pixels(s)
    checked = 0
    for (x, y), v in snapshot.items():
        if v[3] == 255:
            checked += 1
            assert after(x, y) == v, f"mass pixel changed at ({x},{y})"
    assert checked > 10000


def test_border_exactly_width_on_mass_side_and_nothing_on_desktop():
    width = 3
    s = new_surface()
    cr = cairo.Context(s)
    fill_mass(cr, W, H, T, R, PANEL, MASS)
    draw_border(cr, W, H, T, R, PANEL, width, ACCENT)
    px = pixels(s)
    x = 300  # through the middle of the bump
    edge = T + BUMP_DEPTH
    accent = [y for y in range(H // 2) if px(x, y)[2] > 100]  # R channel: accent ~143, mass ~10
    assert len(accent) == width, accent
    assert accent == list(range(edge - width, edge))
    assert all(px(x, y)[3] == 0 for y in range(edge, H - T - 1))  # desktop side stays transparent
    # And through plain frame (inner edge at y = T) the same holds.
    accent_f = [y for y in range(H // 2) if px(100, y)[2] > 100]
    assert accent_f == list(range(T - width, T))
    assert all(px(100, y)[3] == 0 for y in range(T, H - T - 1))
