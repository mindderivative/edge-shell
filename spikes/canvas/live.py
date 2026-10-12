"""LIVE canvas probe (throwaway spike, run by hand on one output for at most 10 seconds).

One click-through layer-shell canvas covers the output and draws the whole scene (frame, corners,
dock, clock, system bar) with the final shadow/border API. The dock's depth animates 0 -> 64 -> 0
on the widget frame clock with damaged-region redraws. Dummy opaque content windows (one per
panel) test stacking above the canvas. Frame/draw timings and a tester checklist print at exit.

Run: scripts/py -m spikes.canvas.live [flags]      (see --help; --selftest opens no window)
Refuses every output but HDMI-A-1; the run is hard-capped at 10 s by a GLib timeout.
"""

from __future__ import annotations

import argparse
import math
import statistics
import time
from dataclasses import dataclass

from spikes.canvas.effects import RGBA, draw_scene, parse_rgba_hex, reach_px
from spikes.canvas.outline import Panel

ALLOWED_OUTPUT = "HDMI-A-1"
MAX_SECONDS = 10
APP_NAME = "edge-canvas-probe"
T, R = 10, 14
MASS = parse_rgba_hex("#0b0c0d")
DOCK_LEN, DOCK_FULL = 560, 64
CLOCK_LEN, CLOCK_FULL = 168, 46
BAR_POS, BAR_LEN, BAR_FULL = 600, 300, 56
PERIOD_S = 2.0

CSS = """\
window#probe-canvas { background-color: transparent; }
window#probe-content { background-color: #202428; }
window#probe-content label { color: #f2f2f2; font-weight: bold; }
"""


@dataclass(frozen=True)
class Settings:
    output: str
    elevation: float
    shadow_rgba: RGBA
    border_width: int
    border_rgba: RGBA
    content_layer: str
    raise_ms: int
    seconds: float
    selftest: bool
    simulate: int = 0
    sim_size: tuple[int, int] = (1920, 1080)

    @property
    def reach_px(self) -> int:
        return reach_px(self.elevation)


def _colour(text: str) -> RGBA:
    try:
        return parse_rgba_hex(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _bounded(lo: float, hi: float | None, kind=float):
    def conv(text: str):
        try:
            v = kind(text)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"not a number: {text!r}") from exc
        if v < lo or (hi is not None and v > hi):
            raise argparse.ArgumentTypeError(f"{v} outside {lo}..{hi if hi is not None else 'inf'}")
        return v

    return conv


def _output(text: str) -> str:
    if text != ALLOWED_OUTPUT:
        raise argparse.ArgumentTypeError(f"refusing output {text!r}: only {ALLOWED_OUTPUT} allowed")
    return text


def _seconds(text: str) -> float:
    try:
        v = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from exc
    if not 0 < v <= MAX_SECONDS:
        raise argparse.ArgumentTypeError(f"--seconds must be in (0, {MAX_SECONDS}]")
    return v


def _size(text: str) -> tuple[int, int]:
    try:
        w, h = (int(x) for x in text.lower().split("x"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected WxH, got {text!r}") from exc
    if w < 1 or h < 1:
        raise argparse.ArgumentTypeError("size must be positive")
    return w, h


def parse_args(argv: list[str] | None = None) -> Settings:
    """Parse and validate the flags. No GTK import; invalid input exits via argparse (code 2)."""
    p = argparse.ArgumentParser(prog="spikes.canvas.live", description=__doc__.split("\n\n")[0])
    p.add_argument(
        "--output", type=_output, default=ALLOWED_OUTPUT, help="connector (HDMI-A-1 only)"
    )
    p.add_argument(
        "--elevation", type=_bounded(0, 100), default=50, help="shadow elevation, 0..100 %%"
    )
    p.add_argument("--shadow-color", type=_colour, default=_colour("#00000080"), help="#rrggbb[aa]")
    p.add_argument("--border-width", type=_bounded(0, None, int), default=2, help="border px")
    p.add_argument("--border-color", type=_colour, default=_colour("#8fd3b6ff"), help="#rrggbb[aa]")
    p.add_argument("--content-layer", choices=("top", "overlay"), default="top")
    p.add_argument("--raise-ms", type=_bounded(0, None, int), default=500, help="0 disables raise")
    p.add_argument(
        "--seconds", type=_seconds, default=MAX_SECONDS, help=f"run time, max {MAX_SECONDS}"
    )
    p.add_argument(
        "--selftest", action="store_true", help="parse flags, print them, open no window"
    )
    p.add_argument(
        "--simulate",
        type=_bounded(1, None, int),
        default=0,
        metavar="N",
        help="headless: run N frames of the same tick/draw code, no window",
    )
    p.add_argument("--sim-size", type=_size, default=(1920, 1080), metavar="WxH")
    a = p.parse_args(argv)
    return Settings(
        output=a.output,
        elevation=a.elevation,
        shadow_rgba=a.shadow_color,
        border_width=a.border_width,
        border_rgba=a.border_color,
        content_layer=a.content_layer,
        raise_ms=a.raise_ms,
        seconds=a.seconds,
        selftest=a.selftest,
        simulate=a.simulate,
        sim_size=a.sim_size,
    )


# ---- scene / animation / damage maths (no GTK) ---------------------------------------------

Box = tuple[int, int, int, int]  # (x0, y0, x1, y1), x1/y1 exclusive
FAKE_FRAME_US = 1_000_000 / 60  # simulated frame clock: 16.667 ms per frame


def scene_panels(w: int, h: int, dock_depth: float) -> list[Panel]:
    return [
        ("bottom", (w - DOCK_LEN) // 2, DOCK_LEN, DOCK_FULL, dock_depth),
        ("top", (w - CLOCK_LEN) // 2, CLOCK_LEN, CLOCK_FULL, float(CLOCK_FULL)),
        ("right", BAR_POS, BAR_LEN, BAR_FULL, float(BAR_FULL)),
    ]


def dock_depth_at(t_s: float) -> float:
    """0 -> 64 -> 0 sine ease, one cycle per PERIOD_S."""
    return DOCK_FULL * (1 - math.cos(2 * math.pi * t_s / PERIOD_S)) / 2


def dock_box(w: int, h: int, depth: float, pad: int) -> Box:
    """Dock bounding box at `depth`: fillets included, down to the screen edge, expanded by `pad`
    (= shadow reach + border width), clamped to the surface."""
    x0 = (w - DOCK_LEN) // 2 - R - pad
    x1 = (w - DOCK_LEN) // 2 + DOCK_LEN + R + pad
    y0 = h - T - math.ceil(depth) - pad
    return max(0, x0), max(0, y0), min(w, x1), h


def union_boxes(a: Box | None, b: Box | None) -> Box | None:
    """Bounding union; None means 'no box yet' and is neutral. Commutative."""
    if a is None:
        return b
    if b is None:
        return a
    return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])


@dataclass(frozen=True)
class Step:
    depth: float
    box: Box  # dock box now
    invalidate: Box  # box to hand to queue_draw_area: now, plus the previous frame's box


class AnimationState:
    """Per-frame dock depth and damage. The first step invalidates the whole current box."""

    def __init__(self, w: int, h: int, pad: int):
        self.w, self.h, self.pad = w, h, pad
        self._prev: Box | None = None

    def step(self, t_s: float) -> Step:
        depth = dock_depth_at(t_s)
        box = dock_box(self.w, self.h, depth, self.pad)
        inv = union_boxes(box, self._prev)
        self._prev = box
        return Step(depth, box, inv)


def pct(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(q * (len(s) - 1) + 0.5))] if s else float("nan")


def interval_stats(timestamps_us: list[int]) -> dict:
    """Frame-interval stats from frame-clock timestamps (us); None values when < 2 frames."""
    n = len(timestamps_us)
    out = {"frames": n, "mean_ms": None, "median_ms": None, "p95_ms": None, "fps": None}
    if n < 2:
        return out
    iv = [(b - a) / 1000 for a, b in zip(timestamps_us, timestamps_us[1:], strict=False)]
    out["mean_ms"] = statistics.fmean(iv)
    out["median_ms"] = statistics.median(iv)
    out["p95_ms"] = pct(iv, 0.95)
    span_s = (timestamps_us[-1] - timestamps_us[0]) / 1e6
    out["fps"] = (n - 1) / span_s if span_s > 0 else None
    return out


def make_painter(cfg: Settings, w: int, h: int):
    """The one draw function used by the live draw handler and by --simulate."""
    border = (cfg.border_width, cfg.border_rgba) if cfg.border_width > 0 else None
    shadow = (cfg.elevation, cfg.shadow_rgba)

    def paint(cr, depth: float, clip: tuple[int, int, int, int] | None) -> None:
        draw_scene(
            cr,
            w,
            h,
            T,
            R,
            scene_panels(w, h, depth),
            MASS,
            border=border,
            shadow=shadow,
            clip=clip,
        )

    return paint


def box_to_rect(b: Box) -> tuple[int, int, int, int]:
    return b[0], b[1], b[2] - b[0], b[3] - b[1]


@dataclass
class ProbeResult:
    timestamps_us: list[int]
    draws_ms: list[float]
    error: str | None = None
    wall: float = 0.0
    cpu: float = 0.0
    geometry: str = ""


def simulate(cfg: Settings, frames: int, size: tuple[int, int]) -> ProbeResult:
    """Headless run of the live tick/draw loop: no window, fake 60 Hz clock, image surface."""
    import cairo

    w, h = size
    res = ProbeResult([], [])
    wall0, cpu0 = time.perf_counter(), time.process_time()
    try:
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        cr = cairo.Context(surface)
        paint = make_painter(cfg, w, h)
        state = AnimationState(w, h, cfg.reach_px + cfg.border_width)
        t0 = None
        for i in range(frames):
            ft = round(i * FAKE_FRAME_US)
            if t0 is None:
                t0 = ft
            res.timestamps_us.append(ft)
            step = state.step((ft - t0) / 1e6)
            clip = None if i == 0 else box_to_rect(step.invalidate)  # first draw is full
            t_start = time.perf_counter()
            cr.save()
            paint(cr, step.depth, clip)
            cr.restore()
            surface.flush()
            res.draws_ms.append((time.perf_counter() - t_start) * 1000)
    except Exception:
        import traceback

        traceback.print_exc()
        res.error = traceback.format_exc().strip().splitlines()[-1]
    res.wall = time.perf_counter() - wall0
    res.cpu = time.process_time() - cpu0
    return res


# ---- live part (GTK imported lazily) -------------------------------------------------------


def run(cfg: Settings) -> ProbeResult:
    import traceback

    import cairo
    import gi

    gi.require_version("Gdk", "3.0")
    gi.require_version("Gtk", "3.0")
    gi.require_version("GtkLayerShell", "0.1")
    from fabric import Application
    from fabric.widgets.wayland import WaylandWindow
    from gi.repository import Gdk, GLib, Gtk, GtkLayerShell

    from shell.gdk_util import monitor_index
    from shell.monitors import monitors_by_name

    res = ProbeResult([], [])
    mon = monitors_by_name().get(cfg.output)
    if mon is None:
        res.error = f"output {cfg.output} not found (kscreen-doctor mapping failed?)"
        return res
    geo = mon.get_geometry()
    w, h = geo.width, geo.height
    res.geometry = f"{cfg.output}: {w}x{h} at +{geo.x}+{geo.y}"
    idx = monitor_index(mon)
    paint = make_painter(cfg, w, h)
    state = AnimationState(w, h, cfg.reach_px + cfg.border_width)

    class Canvas(WaylandWindow):
        def __init__(self):
            super().__init__(
                layer="top",
                anchor="top left bottom right",
                exclusivity="none",
                keyboard_mode="none",
                monitor=idx,
                title="edge-canvas-probe-canvas",
                name="probe-canvas",
                visible=False,
            )
            GtkLayerShell.set_exclusive_zone(self, -1)  # "none" alone is zone 0: KWin shifts us
            self.area = Gtk.DrawingArea()
            self.add(self.area)

        def make_click_through(self) -> None:
            self.input_shape_combine_region(cairo.Region(cairo.RectangleInt()))

        def do_size_allocate(self, alloc) -> None:
            # Fabric's allocate resets the input shape to the whole surface; re-apply EMPTY.
            WaylandWindow.do_size_allocate(self, alloc)
            self.make_click_through()

    class Content(WaylandWindow):
        def __init__(self, text, anchor, margin, size):
            super().__init__(
                layer=cfg.content_layer,
                anchor=anchor,
                margin=margin,
                exclusivity="none",
                keyboard_mode="none",
                monitor=idx,
                title=f"edge-canvas-probe-{text}",
                name="probe-content",
                visible=False,
            )
            GtkLayerShell.set_exclusive_zone(self, -1)
            label = Gtk.Label(label=text)
            label.set_size_request(*size)
            self.add(label)

    st = {"depth": 0.0, "first": True, "t0": None, "app": None}

    def fail() -> None:
        """Loud failure: traceback to stderr, record the reason, quit."""
        traceback.print_exc()
        if res.error is None:
            res.error = traceback.format_exc().strip().splitlines()[-1]
        if st["app"] is not None:
            st["app"].quit()

    def on_draw(_area, cr) -> bool:
        try:
            t_start = time.perf_counter()
            if st["first"]:
                st["first"] = False
                clip = None  # first draw is a full redraw
            else:
                ok, rect = Gdk.cairo_get_clip_rectangle(cr)
                clip = (rect.x, rect.y, rect.width, rect.height) if ok else None
            paint(cr, st["depth"], clip)
            res.draws_ms.append((time.perf_counter() - t_start) * 1000)
        except Exception:
            fail()
        return False

    canvas = Canvas()
    canvas.area.connect("draw", on_draw)

    def on_tick(widget, frame_clock) -> bool:
        try:
            ft = frame_clock.get_frame_time()  # microseconds
            if st["t0"] is None:
                st["t0"] = ft
            res.timestamps_us.append(ft)
            step = state.step((ft - st["t0"]) / 1e6)
            st["depth"] = step.depth
            widget.queue_draw_area(*box_to_rect(step.invalidate))
        except Exception:
            fail()
            return False
        return True

    canvas.area.add_tick_callback(on_tick)
    canvas.show_all()
    canvas.make_click_through()

    # Content windows are created AFTER the canvas. Bodies at full depth (monitor-relative).
    dock_x = (w - DOCK_LEN) // 2
    clock_x = (w - CLOCK_LEN) // 2
    contents = [
        Content("dock", "bottom left", f"0px 0px {T}px {dock_x}px", (DOCK_LEN, DOCK_FULL)),
        Content("clock", "top left", f"{T}px 0px 0px {clock_x}px", (CLOCK_LEN, CLOCK_FULL)),
        Content("bar", "right top", f"{BAR_POS}px {T}px 0px 0px", (BAR_FULL, BAR_LEN)),
    ]
    for c in contents:
        c.show_all()

    def raise_all() -> bool:
        for c in contents:  # same trick as EdgePanel.raise_to_top: remap puts us on top
            c.hide()
            c.show_all()
        return False

    if cfg.raise_ms > 0:
        GLib.timeout_add(cfg.raise_ms, raise_all)

    app = Application(APP_NAME, canvas, *contents, open_client=False)
    st["app"] = app
    app.set_stylesheet_from_string(CSS, compile=False)

    def stop() -> bool:
        app.quit()
        return False

    GLib.timeout_add(int(cfg.seconds * 1000), stop)  # hard cap: always quits
    wall0, cpu0 = time.perf_counter(), time.process_time()
    try:
        app.run()
    except Exception:
        traceback.print_exc()
        res.error = res.error or traceback.format_exc().strip().splitlines()[-1]
    res.wall = time.perf_counter() - wall0
    res.cpu = time.process_time() - cpu0
    return res


def _fmt(v, spec: str = ".2f") -> str:
    return "n/a" if v is None else format(v, spec)


def report(cfg: Settings, res: ProbeResult, where: str) -> bool:
    """Print the report; returns True when the probe counts as failed."""
    stats = interval_stats(res.timestamps_us)
    reason = res.error
    if reason is None and stats["frames"] == 0:
        reason = "no animation frames were produced"
    if reason is not None:
        print(f"PROBE FAILED: {reason}")
    print("=== canvas probe results ===")
    print(f"flags: {cfg}")
    print(f"monitor {where}; reach_px={cfg.reach_px}")
    print(f"frames (ticks): {stats['frames']}")
    print(
        f"frame interval ms: mean {_fmt(stats['mean_ms'])} median {_fmt(stats['median_ms'])} "
        f"p95 {_fmt(stats['p95_ms'])}"
    )
    print(f"achieved fps over animation: {_fmt(stats['fps'], '.1f')}")
    d = res.draws_ms
    if d:
        print(
            f"draw ms/frame: median {statistics.median(d):.2f} p95 {pct(d, 0.95):.2f} "
            f"max {max(d):.2f} ({len(d)} draws)"
        )
    else:
        print("draw ms/frame: n/a (0 draws)")
    load = res.cpu / res.wall if res.wall > 0 else None
    print(f"CPU: {res.cpu:.2f} s over {res.wall:.2f} s wall = {_fmt(load)} of one core")
    if not cfg.simulate:
        print(CHECKLIST)
    return reason is not None


CHECKLIST = """
CHECKLIST for the tester (answer each):
 (a) Smooth: no flicker, no tearing while the dock grows and shrinks?
 (b) Shadow and border follow the animating dock with no seams at the joins
     (dock/frame fillets, clock, bar)?
 (c) The three labels (dock, clock, bar) are visible ABOVE the canvas? If one is hidden,
     stacking failed: did --raise-ms (default 500) or --content-layer overlay help?
     (compare with: --raise-ms 0   and   --content-layer overlay --raise-ms 0)
 (d) Click-through: clicks on windows or desktop icons everywhere (over the shadow and the
     dock region too, except on the three label windows) reach them?
 (e) Optional: a fullscreen window should cover the canvas (top layer). What happened?
"""


def main(argv: list[str] | None = None) -> int:
    cfg = parse_args(argv)
    if cfg.selftest:
        print(f"settings: {cfg}")
        print(f"reach_px for elevation {cfg.elevation}%: {cfg.reach_px}")
        return 0
    if cfg.simulate:
        res = simulate(cfg, cfg.simulate, cfg.sim_size)
        where = f"simulated {cfg.sim_size[0]}x{cfg.sim_size[1]} (no window, fake 60 Hz clock)"
    else:
        res = run(cfg)
        where = res.geometry or cfg.output
    return 1 if report(cfg, res, where) else 0


if __name__ == "__main__":
    raise SystemExit(main())
