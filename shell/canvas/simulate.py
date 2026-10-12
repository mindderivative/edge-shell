"""Headless run of the real animation/draw loop: shell.anim.Tween on a fake frame clock drives
CanvasPainter.set_depth exactly as EdgePanel does, and the canvas "draw" happens once per frame
with the cairo clip set to the union of the invalidated boxes, the way GTK clips a draw handler.
Pure (cairo image surfaces)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import cairo

from shell.anim import Tween
from shell.canvas.painter import CanvasPainter
from shell.canvas.scene import Box, PanelShape, Scene, box_to_rect, union_boxes
from shell.canvas.style import style_for
from shell.config.models import Theme

FRAME_US = 16_667  # 60 Hz
# cairo's arc tessellation differs by a few levels between a clipped and a full redraw on a
# handful of anti-aliased pixels (measured: <= 15/255 on <= 10 channels at 640x400). A missed
# damaged region shows as hundreds of channels off by tens of levels.
NOISE = 3


class FakeClock:
    def __init__(self) -> None:
        self.now_us = 0

    def get_frame_time(self) -> int:
        return self.now_us


class FakeTicker:
    """The two methods of a Gtk.Widget that shell.anim.Tween uses, run by hand per frame."""

    def __init__(self) -> None:
        self._callbacks: dict[int, Callable] = {}
        self._next_id = 1

    def add_tick_callback(self, fn: Callable) -> int:
        tick_id, self._next_id = self._next_id, self._next_id + 1
        self._callbacks[tick_id] = fn
        return tick_id

    def remove_tick_callback(self, tick_id: int) -> None:
        self._callbacks.pop(tick_id, None)

    def run(self, clock: FakeClock) -> None:
        for tick_id, fn in list(self._callbacks.items()):
            if tick_id in self._callbacks and not fn(self, clock):
                self._callbacks.pop(tick_id, None)


@dataclass
class SimResult:
    frames: int = 0
    draws: int = 0
    full_draws: int = 0
    max_diff: int = 0  # worst channel difference vs a fresh full redraw, over checked frames
    max_noisy: int = 0  # most channels differing by more than NOISE in one checked frame
    checked: int = 0
    damage_px: list[int] = field(default_factory=list)  # summed box area per draw (approx.)


def _snapshot(surface: cairo.ImageSurface) -> bytes:
    surface.flush()
    return bytes(surface.get_data())


def compare(a: bytes, b: bytes) -> tuple[int, int]:
    """(largest channel difference, number of channels differing by more than NOISE)."""
    diffs = [abs(x - y) for x, y in zip(a, b, strict=True)]
    return max(diffs, default=0), sum(d > NOISE for d in diffs)


def simulate(
    theme: Theme,
    size: tuple[int, int],
    shapes: list[PanelShape],
    frames: int,
    toggle_every: int = 18,
    check_every: int = 0,
    recorder=None,
    clock: FakeClock | None = None,
) -> SimResult:
    """Run `frames` frames. Every `toggle_every` frames every panel flips between collapsed and
    extended (280 ms tweens at 60 Hz take 17 frames, so 18 keeps them moving). With
    `check_every` > 0, every n-th frame the retained surface is compared with a fresh full
    redraw (max channel difference recorded in `max_diff`)."""
    w, h = size
    clock = clock or FakeClock()
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    pending: list[Box | None] = [None]  # the window's first expose covers everything
    scene = Scene(w, h, theme.thickness, theme.radius)
    painter = CanvasPainter(scene, style_for(theme), pending.append)
    painter.recorder = recorder
    ticker = FakeTicker()
    tweens: list[tuple[Tween, PanelShape]] = []
    for key, shape in enumerate(shapes):
        painter.add_panel(key, shape)
        tween = Tween(ticker, lambda d, k=key: painter.set_depth(k, d), theme.duration_ms)
        tween.jump_to(0.0)
        tweens.append((tween, shape))
    result = SimResult()
    extended = False
    for i in range(frames):
        clock.now_us = i * FRAME_US
        if toggle_every and i % toggle_every == 0:
            extended = not extended
            for tween, shape in tweens:
                tween.animate_to(shape.depth if extended else 0.0)
        ticker.run(clock)
        result.frames += 1
        if pending:
            _draw_like_gtk(surface, painter, pending, result)
            pending.clear()
        if check_every and i % check_every == 0:
            fresh = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
            check = CanvasPainter(scene, painter.style, lambda _box: None)
            check.draw(cairo.Context(fresh), None)
            worst, noisy = compare(_snapshot(surface), _snapshot(fresh))
            result.max_diff = max(result.max_diff, worst)
            result.max_noisy = max(result.max_noisy, noisy)
            result.checked += 1
    return result


def _draw_like_gtk(
    surface: cairo.ImageSurface,
    painter: CanvasPainter,
    pending: list[Box | None],
    result: SimResult,
) -> None:
    """One draw handler call: cr clipped to the invalid region, clip rect = its extents."""
    cr = cairo.Context(surface)
    scene = painter.scene
    if any(box is None for box in pending):
        boxes = [scene.full_box()]
    else:
        boxes = [box for box in pending if box is not None]
    for box in boxes:
        cr.rectangle(*box_to_rect(box))
    cr.clip()
    extents = None
    for box in boxes:
        extents = union_boxes(extents, box)
    result.full_draws += painter.needs_full
    painter.draw(cr, box_to_rect(extents))
    result.draws += 1
    result.damage_px.append(sum((b[2] - b[0]) * (b[3] - b[1]) for b in boxes))
