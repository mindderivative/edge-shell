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
    )


# ---- scene / damage maths (no GTK) ---------------------------------------------------------


def scene_panels(w: int, h: int, dock_depth: float) -> list[Panel]:
    return [
        ("bottom", (w - DOCK_LEN) // 2, DOCK_LEN, DOCK_FULL, dock_depth),
        ("top", (w - CLOCK_LEN) // 2, CLOCK_LEN, CLOCK_FULL, float(CLOCK_FULL)),
        ("right", BAR_POS, BAR_LEN, BAR_FULL, float(BAR_FULL)),
    ]


def dock_depth_at(t_s: float) -> float:
    """0 -> 64 -> 0 sine ease, one cycle per PERIOD_S."""
    return DOCK_FULL * (1 - math.cos(2 * math.pi * t_s / PERIOD_S)) / 2


def dock_box(w: int, h: int, depth: float, pad: int) -> tuple[int, int, int, int]:
    """Dock bounding box (x0, y0, x1, y1) at `depth`: fillets included, down to the screen edge,
    expanded by `pad` (= shadow reach + border width), clamped to the surface."""
    x0 = (w - DOCK_LEN) // 2 - R - pad
    x1 = (w - DOCK_LEN) // 2 + DOCK_LEN + R + pad
    y0 = h - T - math.ceil(depth) - pad
    return max(0, x0), max(0, y0), min(w, x1), h


def union(a, b):
    if a is None:
        return b
    return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])


def pct(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(q * (len(s) - 1) + 0.5))] if s else float("nan")


# ---- live part (GTK imported lazily) -------------------------------------------------------


def run(cfg: Settings) -> int:
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

    mon = monitors_by_name().get(cfg.output)
    if mon is None:
        print(f"output {cfg.output} not found (kscreen-doctor mapping failed?); nothing started")
        return 1
    geo = mon.get_geometry()
    w, h = geo.width, geo.height
    idx = monitor_index(mon)
    pad = cfg.reach_px + cfg.border_width
    border = (cfg.border_width, cfg.border_rgba) if cfg.border_width > 0 else None
    shadow = (cfg.elevation, cfg.shadow_rgba)

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

    st = {"depth": 0.0, "box": None, "first": True, "t0": None, "last_ft": None}
    intervals: list[float] = []
    draws_ms: list[float] = []

    def on_draw(_area, cr) -> bool:
        t_start = time.perf_counter()
        if st["first"]:
            st["first"] = False
            clip = None  # first draw is a full redraw
        else:
            ok, rect = Gdk.cairo_get_clip_rectangle(cr)
            clip = (rect.x, rect.y, rect.width, rect.height) if ok else None
        draw_scene(
            cr,
            w,
            h,
            T,
            R,
            scene_panels(w, h, st["depth"]),
            MASS,
            border=border,
            shadow=shadow,
            clip=clip,
        )
        draws_ms.append((time.perf_counter() - t_start) * 1000)
        return False

    canvas = Canvas()
    canvas.area.connect("draw", on_draw)

    def on_tick(widget, frame_clock) -> bool:
        ft = frame_clock.get_frame_time()  # microseconds
        if st["t0"] is None:
            st["t0"] = ft
        if st["last_ft"] is not None:
            intervals.append((ft - st["last_ft"]) / 1000)
        st["last_ft"] = ft
        st["depth"] = dock_depth_at((ft - st["t0"]) / 1e6)
        new = dock_box(w, h, st["depth"], pad)
        x0, y0, x1, y1 = union(new, st["box"])
        st["box"] = new
        widget.queue_draw_area(x0, y0, x1 - x0, y1 - y0)
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
    app.set_stylesheet_from_string(CSS, compile=False)

    wall0, cpu0 = time.perf_counter(), time.process_time()

    def stop() -> bool:
        app.quit()
        return False

    GLib.timeout_add(int(cfg.seconds * 1000), stop)  # hard cap: always quits
    try:
        app.run()
    finally:
        report(
            cfg, geo, intervals, draws_ms, time.perf_counter() - wall0, time.process_time() - cpu0
        )
    return 0


def report(cfg: Settings, geo, intervals, draws_ms, wall: float, cpu: float) -> None:
    print("=== canvas probe results ===")
    print(f"flags: {cfg}")
    print(
        f"monitor {cfg.output}: {geo.width}x{geo.height} at +{geo.x}+{geo.y}; "
        f"reach_px={cfg.reach_px}"
    )
    print(f"frames (ticks): {len(intervals) + 1 if intervals else 0}")
    if intervals:
        span = sum(intervals) / 1000
        print(
            f"frame interval ms: mean {statistics.fmean(intervals):.2f} "
            f"median {statistics.median(intervals):.2f} p95 {pct(intervals, 0.95):.2f}"
        )
        print(f"achieved fps over animation: {len(intervals) / span:.1f}")
    if draws_ms:
        print(
            f"draw handler ms/frame: median {statistics.median(draws_ms):.2f} "
            f"p95 {pct(draws_ms, 0.95):.2f} max {max(draws_ms):.2f} ({len(draws_ms)} draws)"
        )
    print(f"CPU: {cpu:.2f} s over {wall:.2f} s wall = {cpu / wall:.2f} of one core")
    print(CHECKLIST)


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
    return run(cfg)


if __name__ == "__main__":
    raise SystemExit(main())
