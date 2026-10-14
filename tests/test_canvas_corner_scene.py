"""Corner panels in the scene, the painter's damage and the headless simulation (spec 19)."""

import random

import cairo
import pytest

from shell.canvas.painter import CanvasPainter
from shell.canvas.scene import CornerShape, PanelShape, Scene, box_to_rect, shape_for, union_boxes
from shell.canvas.simulate import compare, simulate
from shell.canvas.style import style_for
from shell.panel_spec import CornerGeometry, PanelGeometry

W, H, T, R = 1920, 1080, 10, 14
BOX = CornerShape("bottom-left", "bottom", 300, 380)

# One scene with a corner panel in three corners (both opening edges used) and edge panels
# next to them, cleared as shell.panel_layout would (640 x 400, T 10, R 14).
MIXED = [
    CornerShape("bottom-left", "bottom", 140, 90),
    CornerShape("top-right", "right", 120, 80),
    CornerShape("top-left", "left", 100, 60),
    PanelShape("bottom", 300, 150, 64),
    PanelShape("right", 180, 100, 40),
]
THEMES = [
    {},
    {"shadow": {"enabled": True, "elevation": 50}},
    {
        "shadow": {"enabled": True, "elevation": 60, "color": "#000000a0"},
        "border": {"enabled": True, "width": 6, "color": "#ffffffa0"},
    },
]


def test_adding_a_corner_panel_damages_its_box():
    scene = Scene(W, H, T, R)
    assert scene.add_panel("c", BOX) == (0, 1080 - 24, 314, 1080)  # collapsed: band + R


def test_set_depth_damages_old_and_new_corner_box():
    scene = Scene(W, H, T, R, pad=5)
    scene.add_panel("c", BOX)
    assert scene.set_depth("c", 100) == (0, 1080 - 129, 319, 1080)
    assert scene.set_depth("c", 40) == (0, 1080 - 129, 319, 1080)  # the old, deeper footprint
    assert scene.set_depth("c", 40) is None


def test_outline_lists_keep_edge_and_corner_panels_apart():
    scene = Scene(W, H, T, R)
    scene.add_panel(1, PanelShape("bottom", 680, 560, 64), 10)
    scene.add_panel(2, BOX, 20)
    assert scene.outline_panels() == [("bottom", 680, 560, 64, 10.0)]
    assert scene.outline_corners() == [("bottom-left", "bottom", 300, 380, 20.0)]


def test_shape_for_maps_both_kinds_of_geometry():
    assert shape_for(PanelGeometry("dock", "bottom", 680, 560, 64, "extended", "dock")) == (
        PanelShape("bottom", 680, 560, 64)
    )
    assert shape_for(
        CornerGeometry("box", "top-right", "right", 200, 190, 150, "extended", "box")
    ) == CornerShape("top-right", "right", 200, 150)


def test_the_painter_draws_the_corner_panels(make_config):
    theme = make_config().theme
    scene = Scene(640, 400, T, R)
    scene.add_panel("c", CornerShape("bottom-left", "bottom", 140, 90), 90)
    with_corner = cairo.ImageSurface(cairo.FORMAT_ARGB32, 640, 400)
    CanvasPainter(scene, style_for(theme), lambda _b: None).draw(cairo.Context(with_corner), None)
    with_corner.flush()
    data = with_corner.get_data()
    stride = with_corner.get_stride()
    assert data[(400 - 50) * stride + 60 * 4 + 3] == 255  # inside the body: mass
    assert data[(400 - 150) * stride + 60 * 4 + 3] == 0  # above it: desktop


@pytest.mark.parametrize("theme", THEMES)
def test_damaged_redraws_with_corner_panels_equal_a_full_redraw(make_config, theme):
    res = simulate(make_config(theme=theme).theme, (640, 400), MIXED, 80, check_every=7)
    assert res.checked == 12
    assert res.max_noisy <= 40 and res.max_diff <= 32, res
    assert res.full_draws == 1


def test_random_corner_depth_jumps_never_leave_stale_pixels(make_config):
    theme = make_config(theme=THEMES[-1]).theme
    w, h = 640, 400
    pending = []
    scene = Scene(w, h, theme.thickness, theme.radius)
    painter = CanvasPainter(scene, style_for(theme), pending.append)
    for key, shape in enumerate(MIXED):
        painter.add_panel(key, shape)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    painter.draw(cairo.Context(surface), None)
    pending.clear()
    rng = random.Random(11)
    for _ in range(40):
        for key in rng.sample(range(len(MIXED)), 2):
            painter.set_depth(key, rng.uniform(0, MIXED[key].depth))
        cr = cairo.Context(surface)
        for box in pending:
            cr.rectangle(*box_to_rect(box))
        cr.clip()
        extents = None
        for box in pending:
            extents = union_boxes(extents, box)
        painter.draw(cr, box_to_rect(extents))
        pending.clear()
    fresh = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    CanvasPainter(scene, painter.style, lambda _b: None).draw(cairo.Context(fresh), None)
    surface.flush()
    fresh.flush()
    worst, noisy = compare(bytes(surface.get_data()), bytes(fresh.get_data()))
    assert noisy <= 40 and worst <= 32, (worst, noisy)


def test_a_corner_panel_at_1080p_keeps_damage_small(make_config):
    theme = make_config(theme={"shadow": {"enabled": True}}).theme
    res = simulate(theme, (W, H), [BOX], 40)
    assert res.full_draws == 1
    assert max(res.damage_px[1:]) < 0.1 * W * H  # never a full-surface redraw while animating
