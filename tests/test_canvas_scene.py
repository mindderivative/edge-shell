"""Scene model, damage boxes, CanvasPainter and the headless tick/draw simulation."""

import random

import cairo
import pytest

from shell.canvas.painter import CanvasPainter
from shell.canvas.scene import PanelShape, Scene, box_to_rect, panel_box, union_boxes
from shell.canvas.simulate import FRAME_US, FakeClock, FakeTicker, compare, simulate
from shell.canvas.style import style_for

W, H, T, R = 1920, 1080, 10, 14
DOCK = PanelShape("bottom", 680, 560, 64)


def contains(outer, inner):
    return (
        outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and outer[2] >= inner[2]
        and outer[3] >= inner[3]
    )


# ---- boxes --------------------------------------------------------------------------


def test_union_is_none_safe_and_commutative():
    a, b = (10, 20, 30, 40), (5, 25, 50, 35)
    assert union_boxes(None, None) is None
    assert union_boxes(a, None) == union_boxes(None, a) == a
    assert union_boxes(a, b) == union_boxes(b, a) == (5, 20, 50, 40)


def test_box_to_rect():
    assert box_to_rect((5, 6, 15, 26)) == (5, 6, 10, 20)


@pytest.mark.parametrize(
    ("edge", "expected"),
    [
        ("bottom", (680 - 14 - 3, 1080 - 10 - 64 - 3, 680 + 560 + 14 + 3, 1080)),
        ("top", (680 - 14 - 3, 0, 680 + 560 + 14 + 3, 10 + 64 + 3)),
        ("left", (0, 680 - 14 - 3, 10 + 64 + 3, 680 + 560 + 14 + 3)),
        ("right", (1920 - 10 - 64 - 3, 680 - 14 - 3, 1920, 680 + 560 + 14 + 3)),
    ],
)
def test_panel_box_on_every_edge(edge, expected):
    shape = PanelShape(edge, 680, 560, 64)
    got = panel_box(shape, 64.0, W, H, T, R, 3)
    assert got == (expected[0], expected[1], min(W, expected[2]), min(H, expected[3]))


def test_panel_box_rounds_fractional_depth_outward_and_clamps():
    assert panel_box(DOCK, 3.2, W, H, T, R, 0)[1] == 1080 - 10 - 4
    near = PanelShape("top", 5, 100, 40)
    x0, y0, x1, y1 = panel_box(near, 40, W, H, T, R, 48)
    assert (x0, y0) == (0, 0) and x1 == 5 + 100 + 14 + 48 and y1 == 10 + 40 + 48


# ---- scene --------------------------------------------------------------------------


def test_set_depth_damages_old_and_new_footprint():
    scene = Scene(W, H, T, R, pad=26)
    scene.add_panel("dock", DOCK)
    prev = panel_box(DOCK, 0.0, W, H, T, R, 26)
    for d in (5.0, 30.5, 64.0, 12.0, 0.0):
        box = scene.set_depth("dock", d)
        now = panel_box(DOCK, d, W, H, T, R, 26)
        assert contains(box, prev) and contains(box, now)
        prev = now


def test_set_depth_unchanged_or_unknown_is_none():
    scene = Scene(W, H, T, R)
    scene.add_panel(1, DOCK, depth=10.0)
    assert scene.set_depth(1, 10.0) is None
    assert scene.set_depth("nope", 5.0) is None


def test_add_and_remove_return_the_footprint():
    scene = Scene(W, H, T, R, pad=4)
    box = scene.add_panel(1, DOCK, depth=64.0)
    assert box == panel_box(DOCK, 64.0, W, H, T, R, 4)
    assert scene.remove_panel(1) == box
    assert scene.remove_panel(1) is None
    assert scene.outline_panels() == []


def test_outline_panels_carry_current_depth():
    scene = Scene(W, H, T, R)
    scene.add_panel("a", DOCK)
    scene.add_panel("b", PanelShape("top", 876, 168, 46), depth=46.0)
    scene.set_depth("a", 12.5)
    assert sorted(scene.outline_panels()) == [
        ("bottom", 680, 560, 64, 12.5),
        ("top", 876, 168, 46, 46.0),
    ]
    assert scene.depths() == {"a": 12.5, "b": 46.0}


# ---- painter ------------------------------------------------------------------------


def make_painter(make_config, theme=None):
    seen = []
    scene = Scene(W, H, T, R)
    painter = CanvasPainter(scene, style_for(make_config(theme=theme).theme), seen.append)
    return painter, scene, seen


def test_painter_invalidates_damage_and_full_on_style(make_config):
    painter, scene, seen = make_painter(make_config)
    painter.add_panel(1, DOCK)
    painter.set_depth(1, 20.0)
    painter.set_depth(1, 20.0)  # unchanged: nothing
    assert len(seen) == 2 and all(box is not None for box in seen)
    painter.set_style(style_for(make_config(theme={"shadow": {"enabled": True}}).theme))
    assert seen[-1] is None and scene.pad == 24 and painter.needs_full


def test_painter_resize_only_when_different(make_config):
    painter, scene, seen = make_painter(make_config)
    assert painter.resize(W, H) is False and seen == []
    assert painter.resize(1280, 720) is True and seen == [None]
    assert (scene.width, scene.height) == (1280, 720)


def test_first_draw_is_full_even_with_a_clip(make_config):
    painter, _, _ = make_painter(make_config)
    calls = []

    class Rec:
        def on_tick(self, key, depth):
            calls.append(("tick", key, depth))

        def on_draw(self, ms, full):
            calls.append(("draw", full))

    painter.recorder = Rec()
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    painter.draw(cairo.Context(surface), (0, 0, 10, 10))
    painter.add_panel(1, DOCK)
    painter.set_depth(1, 3.0)
    painter.draw(cairo.Context(surface), (600, 1000, 700, 80))
    assert calls == [("draw", True), ("tick", 1, 3.0), ("draw", False)]


# ---- simulation: the real Tween -> painter -> clipped draw loop ---------------------


def test_fake_ticker_runs_and_drops_finished_callbacks():
    ticker, clock = FakeTicker(), FakeClock()
    seen = []
    ticker.add_tick_callback(lambda w, c: seen.append(c.get_frame_time()) or len(seen) < 2)
    for t in (0, FRAME_US, 2 * FRAME_US):
        clock.now_us = t
        ticker.run(clock)
    assert seen == [0, FRAME_US]


THEMES = [
    {},
    {"border": {"enabled": True, "width": 3, "color": "#ffffff80"}},
    {"shadow": {"enabled": True, "elevation": 50}},
    {"shadow": {"enabled": True, "elevation": 100}, "border": {"enabled": True}},
]


@pytest.mark.parametrize("theme", THEMES)
def test_damaged_redraws_equal_a_full_redraw(make_config, theme):
    """The core damage contract: after many clipped redraws of an animating scene the retained
    surface matches a fresh full redraw, up to cairo's arc tessellation noise (a few pixels)."""
    shapes = [
        PanelShape("bottom", 170, 260, 64),
        PanelShape("top", 300, 120, 46),
        PanelShape("right", 100, 120, 56),
        PanelShape("left", 140, 90, 40),
    ]
    res = simulate(make_config(theme=theme).theme, (640, 400), shapes, 80, check_every=7)
    assert res.checked == 12
    assert res.max_noisy <= 40 and res.max_diff <= 32, res
    assert res.full_draws == 1  # only the first draw
    assert res.draws > 60


def test_random_depth_jumps_never_leave_stale_pixels(make_config):
    """Drag-like arbitrary depth changes on several panels, several per frame."""
    theme = make_config(theme={"shadow": {"enabled": True}, "border": {"enabled": True}}).theme
    w, h = 500, 360
    shapes = {
        0: PanelShape("bottom", 140, 200, 60),
        1: PanelShape("bottom", 400, 50, 30),  # gap 60 >= 14 + 14
        2: PanelShape("top", 200, 100, 50),
        3: PanelShape("left", 120, 80, 70),
    }
    pending = []
    scene = Scene(w, h, theme.thickness, theme.radius)
    painter = CanvasPainter(scene, style_for(theme), pending.append)
    for key, shape in shapes.items():
        painter.add_panel(key, shape)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    painter.draw(cairo.Context(surface), None)
    pending.clear()
    rng = random.Random(7)
    for _ in range(40):
        for key in rng.sample(sorted(shapes), 2):
            painter.set_depth(key, rng.uniform(0, shapes[key].depth))
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


def test_simulation_at_1080p_keeps_damage_small(make_config):
    theme = make_config(theme={"shadow": {"enabled": True}}).theme
    res = simulate(theme, (W, H), [DOCK], 40)
    assert res.full_draws == 1
    assert max(res.damage_px[1:]) < 0.05 * W * H  # never a full-surface redraw while animating
