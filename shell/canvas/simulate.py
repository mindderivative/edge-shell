"""Headless run of the real animation/draw loop: shell.anim.Tween on a fake frame clock drives
CanvasPainter.set_depth exactly as EdgePanel does, and the canvas "draw" happens once per frame
with the cairo clip set to the union of the invalidated boxes, the way GTK clips a draw handler.
Pure (cairo image surfaces)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import cairo

from shell.anim import Tween
from shell.canvas.painter import CanvasPainter
from shell.canvas.scene import (
    Box,
    PanelShape,
    Scene,
    Shape,
    box_to_rect,
    shape_for,
    union_boxes,
)
from shell.canvas.style import style_for
from shell.config.models import Config, Theme
from shell.panel_layout import layout_monitor
from shell.registry import requests_for, validate_widgets

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
    shapes: list[Shape],
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
    tweens: list[tuple[Tween, Shape]] = []
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


# ---- command line: the headless twin of `main.py --stats` -------------------------------


def default_shapes(width: int, height: int) -> list[PanelShape]:
    """The built-in panels (widgets/: dock, clock, system_bar): their registered defaults at
    1920x1080 (the system bar aligned to the end, 142 px from the corner), shrunk and moved on
    smaller sizes so that no layout rule (shell.panel_layout) would move, shrink or hide one on
    the simulated surface. Pure: it does not import the widgets."""
    dock = min(560, width - 160)
    bar = min(300, height // 3)
    return [
        PanelShape("bottom", (width - dock) // 2, dock, 64),
        PanelShape("top", (width - 168) // 2, 168, 46),
        # end-aligned: the free span ends 38 px (T + R + r) short of the screen edge, then 142 px
        PanelShape("right", height - 38 - 142 - bar, bar, 56),
    ]


def config_shapes(
    config: Config, monitor: str, width: int, height: int
) -> tuple[list[Shape], list[str]]:
    """The shown panels of `monitor` in `config` (edge and corner panels), laid out by
    shell.panel_layout at width x height, plus the layout warnings. The widgets must be
    registered (import widgets)."""
    theme = config.theme_for(monitor)
    layout = layout_monitor(
        requests_for(config, monitor),
        width,
        height,
        theme.thickness,
        theme.radius,
        config.layout_for(monitor).gap,
        where=f"monitors.{monitor}",
    )
    shapes = [shape_for(p) for p in layout.panels if p]
    return shapes, layout.warnings


def main(argv: list[str] | None = None) -> int:
    import argparse
    import time

    from pydantic import ValidationError

    from shell.canvas.stats import StatsRecorder
    from shell.config.loader import load_config
    from shell.config.models import ConfigError, deep_merge

    p = argparse.ArgumentParser(
        prog="python -m shell.canvas.simulate",
        description="Headless run of the canvas animation loop with the default theme.",
    )
    p.add_argument("--frames", type=int, default=600, help="frames at 60 Hz (default 600)")
    p.add_argument("--size", default="1920x1080", help="WxH (default 1920x1080)")
    p.add_argument("--elevation", type=int, default=None, help="enable the shadow at 0-100 %%")
    p.add_argument("--border", type=int, default=None, help="enable the border, width in px")
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="lay out this config's panels and use its theme (needs Fabric for the widgets)",
    )
    p.add_argument("--monitor", default="HDMI-A-1", help="monitor of --config (default HDMI-A-1)")
    args = p.parse_args(argv)
    try:
        width, height = (int(v) for v in args.size.lower().split("x"))
    except ValueError:
        p.error(f"--size must be WxH, got {args.size!r}")
    shapes = default_shapes(width, height)
    if args.config is None:
        theme = load_config(None).theme
    else:
        import widgets  # noqa: F401  (registers the built-in panels: their default geometry)

        try:
            config = load_config(args.config, required=True)
            validate_widgets(config)  # an unknown widget is a usage error (exit 2), as in main.py
        except ConfigError as exc:
            p.error(str(exc))
        theme = config.theme_for(args.monitor)
        shapes, warnings = config_shapes(config, args.monitor, width, height)
        for warning in warnings:
            print(f"layout: {warning}")
    over: dict = {}
    if args.elevation is not None:
        over["shadow"] = {"enabled": True, "elevation": args.elevation}
    if args.border is not None:
        over["border"] = {"enabled": True, "width": args.border}
    try:
        theme = Theme.model_validate(deep_merge(theme.model_dump(), over))
    except ValidationError as exc:
        p.error(str(exc))
    clock = FakeClock()
    recorder = StatsRecorder(clock.get_frame_time)
    wall0, cpu0 = time.perf_counter(), time.process_time()
    res = simulate(
        theme,
        (width, height),
        shapes,
        args.frames,
        recorder=recorder,
        clock=clock,
    )
    print("\n".join(recorder.report(time.perf_counter() - wall0, time.process_time() - cpu0)))
    print(
        f"simulated {res.frames} frames at {width}x{height}: "
        f"{res.draws} draws, {res.full_draws} full"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
