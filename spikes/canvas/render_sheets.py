"""Final parameter sheets (shadow, border, combo), written to spikes/out/ (headless).

Run: scripts/py -m spikes.canvas.render_sheets
"""

from __future__ import annotations

import pathlib

import cairo

from spikes.canvas import render_frames as rf
from spikes.canvas.effects import draw_shadow_reach, parse_rgba_hex, reach_px
from spikes.canvas.outline import fill_mass

OUT = rf.OUT
BACKGROUNDS = {"light": rf.background, "dark": rf.dark_background}
Cell = tuple[str, str, tuple[float, tuple] | None, tuple[float, tuple] | None]  # label, bg, B, S


def hex8(rgba) -> str:
    return "#" + "".join(f"{round(c * 255):02x}" for c in rgba)


def label(cr: cairo.Context, text: str, x: float = 8, y: float = 8) -> None:
    """Text label on a dark plate; `\\n` separates lines."""
    lines = text.split("\n")
    cr.save()
    cr.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(13)
    width = max(cr.text_extents(line).width for line in lines)
    cr.set_source_rgba(0, 0, 0, 0.75)
    cr.rectangle(x, y, width + 10, 6 + 16 * len(lines))
    cr.fill()
    cr.set_source_rgb(1, 1, 1)
    for n, line in enumerate(lines):
        cr.move_to(x + 5, y + 16 + 16 * n)
        cr.show_text(line)
    cr.restore()


def grid(cells: list[Cell], path: pathlib.Path, renderer=None) -> None:
    """2-column grid of 960x540 downscaled full frames, each with a label top-left."""
    cw, ch, pad = 960, 540, 6
    rows = (len(cells) + 1) // 2
    sheet = cairo.ImageSurface(cairo.FORMAT_RGB24, 2 * cw + 3 * pad, rows * (ch + pad) + pad)
    cr = cairo.Context(sheet)
    cr.set_source_rgb(1, 0, 1)
    cr.paint()
    bgs = {k: v() for k, v in BACKGROUNDS.items()}
    for n, (text, bg, border, shadow) in enumerate(cells):
        surf = (renderer or rf.render)(rf.FULL, border, shadow, bgs[bg])
        cr.save()
        cr.translate(pad + (n % 2) * (cw + pad), pad + (n // 2) * (ch + pad))
        cr.save()
        cr.scale(0.5, 0.5)
        cr.set_source_surface(surf, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_BEST)
        cr.paint()
        cr.restore()
        label(cr, text)
        cr.restore()
    sheet.write_to_png(str(path))
    print("wrote", path)


def shadow_label(pct: int, rgba) -> str:
    return f"elev {pct}% ({reach_px(pct)}px), {hex8(rgba)}"


REACHES = (8, 16, 24, 32, 40, 48, 64, 96)
CAL_RGBA = (0.0, 0.0, 0.0, 0.35)


def render_reach(depth: int, reach: int, _unused, bg: cairo.ImageSurface) -> cairo.ImageSurface:
    """Full scene with an ABSOLUTE shadow reach in px (no border), over `bg`."""
    layer = cairo.ImageSurface(cairo.FORMAT_ARGB32, rf.W, rf.H)
    lcr = cairo.Context(layer)
    panels = rf.panels_at(depth)
    draw_shadow_reach(lcr, rf.W, rf.H, rf.T, rf.R, panels, reach, CAL_RGBA)
    fill_mass(lcr, rf.W, rf.H, rf.T, rf.R, panels, rf.MASS)
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, rf.W, rf.H)
    cr = cairo.Context(s)
    cr.set_source_surface(bg, 0, 0)
    cr.paint()
    cr.set_source_surface(layer, 0, 0)
    cr.paint()
    return s


def reach_label(px: int) -> str:
    pcts = ", ".join(f"{round(100 * px / m)}% of {m}" for m in (48, 64, 96))
    return f"reach {px} px\n= {pcts}"


def calibration() -> None:
    for bg in ("light", "dark"):
        cells = [(reach_label(px), bg, px, None) for px in REACHES]
        grid(cells, OUT / f"sheet_reach_calibration_{bg}.png", render_reach)
    # zoomed crops: dock left join + bottom frame, light background, 2x, two rows of four
    bg = rf.background()
    zoom, cw, ch, pad = 2, 480, 330, 6
    sw, sh = cw // zoom, ch // zoom
    dock_x = (rf.W - 560) // 2
    sheet = cairo.ImageSurface(cairo.FORMAT_RGB24, 4 * (cw + pad) + pad, 2 * (ch + pad) + pad)
    cr = cairo.Context(sheet)
    cr.set_source_rgb(1, 0, 1)
    cr.paint()
    for n, px in enumerate(REACHES):
        surf = render_reach(rf.FULL, px, None, bg)
        cr.save()
        cr.translate(pad + (n % 4) * (cw + pad), pad + (n // 4) * (ch + pad))
        cr.rectangle(0, 0, cw, ch)
        cr.clip()
        cr.scale(zoom, zoom)
        cr.set_source_surface(surf, -(dock_x - sw // 2), -(rf.H - sh))
        cr.get_source().set_filter(cairo.FILTER_NEAREST)
        cr.paint()
        cr.restore()
        cr.save()
        cr.translate(pad + (n % 4) * (cw + pad), pad + (n // 4) * (ch + pad))
        label(cr, f"reach {px} px (2x)", 6, 6)
        cr.restore()
    path = OUT / "sheet_reach_calibration_crops.png"
    sheet.write_to_png(str(path))
    print("wrote", path)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    calibration()
    black = (0.0, 0.0, 0.0)
    for bg, name in (("light", "sheet_final_shadow.png"), ("dark", "sheet_final_shadow_dark.png")):
        cells = []
        for pct in (25, 50, 75, 100):
            for alpha in (0.25, 0.45):
                rgba = (*black, alpha)
                cells.append((shadow_label(pct, rgba), bg, None, (pct, rgba)))
        grid(cells, OUT / name)

    combos = [  # two (width, rgba) pairs per row; rows alternate light, dark
        [(1, "#8fd3b6ff"), (2, "#8fd3b680")],
        [(4, "#ffffff80"), (6, "#8fd3b659")],
    ]
    cells = []
    for pair in combos:
        for bg in ("light", "dark"):
            for wd, hx in pair:
                cells.append((f"border {wd}px {hx} ({bg})", bg, (wd, parse_rgba_hex(hx)), None))
    grid(cells, OUT / "sheet_final_border.png")

    cells = []
    for bg in ("light", "dark"):
        for pct, sh, wd, bh in (
            (50, "#00000066", 2, "#8fd3b6ff"),
            (70, "#00000073", 1, "#ffffff80"),
        ):
            text = f"elev {pct}% ({reach_px(pct)}px) {sh} + {wd}px {bh} ({bg})"
            cells.append((text, bg, (wd, parse_rgba_hex(bh)), (pct, parse_rgba_hex(sh))))
    grid(cells, OUT / "sheet_final_combo.png")


if __name__ == "__main__":
    main()
