"""Comparison sheets for the shadow and border look, written to spikes/out/ (headless).

Run: scripts/py -m spikes.canvas.render_sheets
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable

import cairo

from spikes.canvas import render_frames as rf
from spikes.canvas.effects import (
    ShadowLayer,
    draw_border,
    draw_border_stack,
    draw_shadow,
    draw_shadow_stack,
)
from spikes.canvas.outline import fill_mass

OUT = rf.OUT
W, H, T, R = rf.W, rf.H, rf.T, rf.R
BLACK = (0.0, 0.0, 0.0)
CELL = (300, 220)
PANELS = rf.panels_at(rf.FULL)
DOCK_X = (W - 560) // 2  # left join of the dock with the bottom frame
CLOCK_X1 = (W - 168) // 2 + 168  # right join of the clock with the top frame
CROP_ROWS = ("dock-join", "top-left-corner", "clock-join")

DrawFn = Callable[[cairo.Context], None]


def _gauss(opacity: float, reach: int, offset=(0, 0)) -> DrawFn:
    return lambda cr: draw_shadow(cr, W, H, T, R, PANELS, reach, opacity, BLACK, offset)


def _s3(cr: cairo.Context) -> None:
    layers = [ShadowLayer(0.30, 8, (0, 2)), ShadowLayer(0.22, 40, (0, 10))]
    draw_shadow_stack(cr, W, H, T, R, PANELS, layers, BLACK)


SHADOWS: list[tuple[str, DrawFn]] = [
    (
        "S0 legacy (peak at edge, 0.55, 16, no offset)",
        lambda cr: draw_shadow(cr, W, H, T, R, PANELS, 16, 0.55, BLACK, profile="legacy"),
    ),
    ("S1 soft uniform (gauss 0.30, reach 32)", _gauss(0.30, 32)),
    ("S2 top-lit (gauss 0.35, reach 32, off 0,8)", _gauss(0.35, 32, (0, 8))),
    ("S3 two-layer (0.30/8/0,2 + 0.22/40/0,10)", _s3),
    ("S4 high elevation (gauss 0.40, reach 48, off 0,16)", _gauss(0.40, 48, (0, 16))),
]

ACC = rf.ACCENT


def _single(width: float, rgba) -> DrawFn:
    return lambda cr: draw_border(cr, W, H, T, R, PANELS, width, rgba)


def _b2(cr: cairo.Context) -> None:
    lines = [(1, (1, 1, 1, 0.28)), (1, (0, 0, 0, 0.55))]  # inner light line, outer dark line
    draw_border_stack(cr, W, H, T, R, PANELS, lines)


BORDERS: list[tuple[str, DrawFn]] = [
    ("B0 thin accent #8fd3b6, 2px", _single(2, ACC)),
    ("B1 glass edge white 35%, 1px", _single(1, (1, 1, 1, 0.35))),
    ("B2 dual: inner white 28% + outer black 55%, 1px each", _b2),
    ("B3 soft accent 60%, 3px", _single(3, (ACC[0], ACC[1], ACC[2], 0.6))),
    ("B4 hairline #e6e8ea 80%, 1px", _single(1, (0.902, 0.910, 0.918, 0.8))),
]


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


BACKGROUNDS = {"light": rf.background, "dark": dark_background}


def frame(
    bg: cairo.ImageSurface, shadow: DrawFn | None = None, border: DrawFn | None = None
) -> cairo.ImageSurface:
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(s)
    cr.set_source_surface(bg, 0, 0)
    cr.paint()
    if shadow:
        shadow(cr)
    fill_mass(cr, W, H, T, R, PANELS, rf.MASS)
    if border:
        border(cr)
    return s


def label(cr: cairo.Context, text: str, x: float = 6, y: float = 6) -> None:
    cr.save()
    cr.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(13)
    ext = cr.text_extents(text)
    cr.set_source_rgba(0, 0, 0, 0.75)
    cr.rectangle(x, y, ext.width + 10, 21)
    cr.fill()
    cr.set_source_rgb(1, 1, 1)
    cr.move_to(x + 5, y + 15)
    cr.show_text(text)
    cr.restore()


def grid(frames: list[tuple[str, cairo.ImageSurface]], path: pathlib.Path) -> None:
    """2-column grid of 960x540 downscaled frames with a label in the top-left corner."""
    cw, ch, pad = 960, 540, 6
    rows = (len(frames) + 1) // 2
    sheet = cairo.ImageSurface(cairo.FORMAT_RGB24, 2 * cw + 3 * pad, rows * ch + (rows + 1) * pad)
    cr = cairo.Context(sheet)
    cr.set_source_rgb(1, 0, 1)
    cr.paint()
    for n, (name, surf) in enumerate(frames):
        cr.save()
        cr.translate(pad + (n % 2) * (cw + pad), pad + (n // 2) * (ch + pad))
        cr.save()
        cr.scale(0.5, 0.5)
        cr.set_source_surface(surf, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_BEST)
        cr.paint()
        cr.restore()
        label(cr, name, 8, 8)
        cr.restore()
    sheet.write_to_png(str(path))


def crop_origin(row: str, sw: int, sh: int) -> tuple[int, int]:
    """Top-left of the source window for a crop row (join centred horizontally)."""
    if row == "dock-join":
        return DOCK_X - sw // 2, H - sh
    if row == "clock-join":
        return CLOCK_X1 - sw // 2, 0
    return 0, 0  # top-left-corner


def crops(
    columns: list[tuple[str, dict[str, cairo.ImageSurface]]],
    rows: list[tuple[str, str]],
    zoom: int,
    path: pathlib.Path,
) -> None:
    """One column per variant; `rows` = [(crop row, background key)]; cells CELL px at `zoom`x."""
    cw, ch = CELL
    pad = 4
    sw, sh = cw // zoom, ch // zoom
    sheet = cairo.ImageSurface(
        cairo.FORMAT_RGB24, len(columns) * (cw + pad) + pad, len(rows) * (ch + pad) + pad
    )
    cr = cairo.Context(sheet)
    cr.set_source_rgb(1, 0, 1)
    cr.paint()
    for r, (row, bgkey) in enumerate(rows):
        x0, y0 = crop_origin(row, sw, sh)
        for c, (name, surfs) in enumerate(columns):
            cr.save()
            cr.translate(pad + c * (cw + pad), pad + r * (ch + pad))
            cr.rectangle(0, 0, cw, ch)
            cr.clip()
            cr.save()
            cr.scale(zoom, zoom)
            cr.set_source_surface(surfs[bgkey], -x0, -y0)
            cr.get_source().set_filter(cairo.FILTER_NEAREST)
            cr.paint()
            cr.restore()
            label(cr, f"{name.split()[0]} {row} ({bgkey}) {zoom}x", 4, 4)
            cr.restore()
    sheet.write_to_png(str(path))


def main() -> None:
    OUT.mkdir(exist_ok=True)
    bgs = {k: v() for k, v in BACKGROUNDS.items()}
    for kind, variants, shadow in (("shadow", SHADOWS, True), ("border", BORDERS, False)):
        frames = {
            (name, k): frame(bg, fn, None) if shadow else frame(bg, None, fn)
            for name, fn in variants
            for k, bg in bgs.items()
        }
        for k in bgs:
            grid([(n, frames[(n, k)]) for n, _ in variants], OUT / f"sheet_{kind}_{k}.png")
        cols = [(n, {k: frames[(n, k)] for k in bgs}) for n, _ in variants]
        if shadow:
            rows = [(r, "light") for r in CROP_ROWS]
        else:
            rows = [(r, k) for k in ("light", "dark") for r in CROP_ROWS]
        crops(cols, rows, 2 if shadow else 3, OUT / f"sheet_{kind}_crops.png")
    print("wrote sheets to", OUT)


if __name__ == "__main__":
    main()
