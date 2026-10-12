"""Headless renders of the full monitor with the canvas effects, written to spikes/out/."""

from __future__ import annotations

import pathlib

import cairo

from shell.theme import hex_to_rgba
from spikes.canvas.effects import draw_border, draw_shadow
from spikes.canvas.outline import fill_mass

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
CROPS = [  # (label, x, y, w, h) in screen px, shown at 2x
    ("dock-join", 600, 950, 160, 130),
    ("top-left-corner", 0, 0, 160, 130),
    ("clock-join", 800, 0, 160, 130),
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


def render(depth: int, border: bool, shadow: bool, bg: cairo.ImageSurface) -> cairo.ImageSurface:
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(s)
    cr.set_source_surface(bg, 0, 0)
    cr.paint()
    panels = panels_at(depth)
    if shadow:
        draw_shadow(cr, W, H, T, R, panels, 16, 0.55, (0, 0, 0))
    fill_mass(cr, W, H, T, R, panels, MASS)
    if border:
        draw_border(cr, W, H, T, R, panels, 2, ACCENT)
    return s


def crop_sheet(frames: dict[str, cairo.ImageSurface], path: pathlib.Path) -> None:
    scale, pad = 2, 6
    cw, ch = CROPS[0][3] * scale, CROPS[0][4] * scale
    rows = list(frames.items())
    sheet = cairo.ImageSurface(
        cairo.FORMAT_RGB24, len(CROPS) * (cw + pad) + pad, len(rows) * (ch + pad) + pad
    )
    cr = cairo.Context(sheet)
    cr.set_source_rgb(1, 0, 1)
    cr.paint()
    for r, (_name, surf) in enumerate(rows):
        for c, (_label, x, y, _w, _h) in enumerate(CROPS):
            cr.save()
            cr.translate(pad + c * (cw + pad), pad + r * (ch + pad))
            cr.rectangle(0, 0, cw, ch)
            cr.clip()
            cr.scale(scale, scale)
            cr.set_source_surface(surf, -x, -y)
            cr.get_source().set_filter(cairo.FILTER_NEAREST)
            cr.paint()
            cr.restore()
    sheet.write_to_png(str(path))


def main() -> None:
    OUT.mkdir(exist_ok=True)
    bg = background()
    variants = {
        "none": (False, False),
        "border": (True, False),
        "shadow": (False, True),
        "both": (True, True),
    }
    last: dict[str, cairo.ImageSurface] = {}
    for depth in DEPTHS:
        for name, (b, sh) in variants.items():
            surf = render(depth, b, sh, bg)
            surf.write_to_png(str(OUT / f"frame_d{depth:02d}_{name}.png"))
            if depth == FULL:
                last[name] = surf
    crop_sheet({"shadow": last["shadow"], "both": last["both"]}, OUT / "crops_joins_2x.png")
    print(f"wrote {len(DEPTHS) * len(variants) + 1} PNGs to {OUT}")


if __name__ == "__main__":
    main()
