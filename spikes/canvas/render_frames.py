"""Headless renders of the full monitor with the final effects, written to spikes/out/."""

from __future__ import annotations

import pathlib

import cairo

from shell.theme import hex_to_rgba
from spikes.canvas.effects import draw_scene

W, H, T, R = 1920, 1080, 10, 14
MASS = (0.04, 0.05, 0.05, 1.0)
ACCENT = hex_to_rgba("#8fd3b6")
OUT = pathlib.Path(__file__).resolve().parents[1] / "out"
DEPTHS = (0, 14, 32, 64)
FULL = 64  # depth that counts as fraction 1.0 (dock full depth)

# (edge, pos, length, depth_full)
PANELS = [
    ("bottom", (W - 560) // 2, 560, 64),
    ("top", (W - 168) // 2, 168, 46),
    ("right", 600, 300, 56),
]


def panels_at(depth: int) -> list[tuple[str, int, int, int, float]]:
    f = depth / FULL
    return [(e, p, ln, d, d * f) for e, p, ln, d in PANELS]


def background() -> cairo.ImageSurface:
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(s)
    g = cairo.LinearGradient(0, 0, 0, H)
    g.add_color_stop_rgb(0, 0.88, 0.88, 0.88)
    g.add_color_stop_rgb(1, 0.5, 0.5, 0.52)
    cr.set_source(g)
    cr.paint()
    for x, y, bw, bh, c in [
        (200, 150, 420, 260, (0.85, 0.35, 0.30)),
        (900, 300, 500, 300, (0.25, 0.50, 0.85)),
        (1450, 700, 300, 200, (0.95, 0.80, 0.30)),
        (300, 700, 600, 250, (0.95, 0.95, 0.95)),
    ]:
        cr.set_source_rgb(*c)
        cr.rectangle(x, y, bw, bh)
        cr.fill()
    return s


def dark_background() -> cairo.ImageSurface:
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(s)
    g = cairo.LinearGradient(0, 0, 0, H)
    g.add_color_stop_rgb(0, 0x1B / 255, 0x1F / 255, 0x24 / 255)
    g.add_color_stop_rgb(1, 0x2B / 255, 0x31 / 255, 0x39 / 255)
    cr.set_source(g)
    cr.paint()
    for x, y, bw, bh, c in [
        (200, 150, 420, 260, (0.62, 0.30, 0.28)),
        (1450, 700, 300, 200, (0.75, 0.65, 0.30)),
        (300, 700, 600, 250, (0.72, 0.74, 0.76)),
        (700, 120, 520, 360, (0.40, 0.42, 0.45)),  # mid-grey window-like rectangle
        (1350, 250, 380, 260, (0.28, 0.45, 0.70)),
    ]:
        cr.set_source_rgb(*c)
        cr.rectangle(x, y, bw, bh)
        cr.fill()
    cr.set_source_rgb(0.30, 0.32, 0.35)  # window title bar
    cr.rectangle(700, 120, 520, 26)
    cr.fill()
    return s


def render(depth: int, border, shadow, bg: cairo.ImageSurface) -> cairo.ImageSurface:
    """Scene over `bg`; `border` = (width, rgba) | None, `shadow` = (elevation_pct, rgba) | None."""
    layer = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    draw_scene(cairo.Context(layer), W, H, T, R, panels_at(depth), MASS, border, shadow)
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(s)
    cr.set_source_surface(bg, 0, 0)
    cr.paint()
    cr.set_source_surface(layer, 0, 0)
    cr.paint()
    return s


def main() -> None:
    OUT.mkdir(exist_ok=True)
    bg = background()
    for depth in DEPTHS:
        render(depth, (2, ACCENT), (50, (0, 0, 0, 0.45)), bg).write_to_png(
            str(OUT / f"frame_d{depth:02d}_default.png")
        )
    print(f"wrote {len(DEPTHS)} PNGs to {OUT}")


if __name__ == "__main__":
    main()
