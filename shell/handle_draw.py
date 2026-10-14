"""Draw a panel handle with cairo (spec 15). Pure: no GTK.

Shapes are drawn in a canonical frame centred on the handle: u along the edge, v across it,
+v pointing where the panel opens (towards the desktop). `handle_matrix` rotates that frame
onto the real edge. The chevron morphs with the panel's depth (`morph` = d / depth): at 0 it
points where the panel opens, at 0.5 it is a flat bar, at 1 it points back to the screen edge.

`python -m shell.handle_draw --sheet FILE.png [--thickness N]` renders every shape on every
edge at several morph values, enlarged, for a visual check without starting the shell: the
handle on its frame band and body, with the body's inner edge marked in red.
"""

from __future__ import annotations

import math
import sys

import cairo

from shell.config.models import Edge

RGBA = tuple[float, float, float, float]
SHAPES = ("dots", "bar", "chevron", "none")


def handle_matrix(edge: Edge, cx: float, cy: float) -> cairo.Matrix:
    """Canonical (u, v) -> device px, centred on (cx, cy)."""
    if edge == "top":
        return cairo.Matrix(1, 0, 0, 1, cx, cy)
    if edge == "bottom":
        return cairo.Matrix(1, 0, 0, -1, cx, cy)
    if edge == "left":
        return cairo.Matrix(0, 1, 1, 0, cx, cy)
    return cairo.Matrix(0, 1, -1, 0, cx, cy)  # right


def snap(value: float, extent: float) -> float:
    """Pixel-align a centre so a shape `extent` px wide covers whole pixels (crisp edges): a
    pixel centre for an odd extent, a pixel boundary for an even one. Halves round up
    (math.floor(v + 0.5); Python's round() would round half to even)."""
    if math.floor(extent + 0.5) % 2:
        return math.floor(value) + 0.5
    return float(math.floor(value + 0.5))


def snap_centre(
    edge: Edge, cx: float, cy: float, along: float, across: float
) -> tuple[float, float]:
    """Snap the centre of a shape `along` x `across` px. The across coordinate is snapped in
    the canonical frame (+v towards the desktop, so as a distance from the screen edge): every
    edge rounds the same way and the four edges mirror each other pixel for pixel."""
    sign = 1 if edge in ("top", "left") else -1  # device axis direction of +v
    if edge in ("top", "bottom"):
        return snap(cx, along), sign * snap(sign * cy, across)
    return sign * snap(sign * cx, across), snap(cy, along)


def draw_handle(
    cr: cairo.Context,
    shape: str,
    size: int,
    weight: int,
    rgba: RGBA,
    morph: float,
    edge: Edge,
    cx: float,
    cy: float,
    max_across: float,
) -> None:
    """Draw `shape` centred on (cx, cy): `size` px along the edge, `weight` px thick, never
    more than `max_across` px across, stroke included (callers pass shell.handle.shape_room,
    so the shape keeps 2 px of the band empty on each side, 1 px on a band under 8 px, and
    is no taller on a thick frame than on the default one). A
    weight above `max_across` is drawn `max_across` thick; a chevron gets flatter to fit."""
    if shape not in SHAPES:
        raise ValueError(f"unknown handle shape {shape!r}")
    if shape == "none" or rgba[3] <= 0 or max_across <= 0:
        return
    w = max(1.0, min(float(weight), float(max_across)))
    tip = 0.0  # dots and bar: across the edge the shape is just `w` px
    if shape == "chevron":
        height = max(0.0, min(size / 2, max_across - w))  # arm ends to tip, across
        tip = height / 2 * (1 - 2 * min(1.0, max(0.0, morph)))
    # Whole px the shape spans across the edge, stroke included (never more than max_across).
    # Its parity decides the snap, rounded up so a 5.4 px chevron snaps like a 6 px one and
    # stays inside max_across, clear of both band edges.
    across = math.ceil(round(abs(2 * tip) + w, 6))
    cr.save()
    cr.new_path()  # a path the caller left open must not be filled
    cr.transform(handle_matrix(edge, *snap_centre(edge, cx, cy, w, across)))
    cr.set_source_rgba(*rgba)
    if shape == "dots":
        r = w / 2
        reach = max(math.floor(size / 2 - r + 0.5), w)  # outer dot centres; the dots never overlap
        for u in (-reach, 0.0, reach):
            cr.new_sub_path()
            cr.arc(u, 0, r, 0, 2 * math.pi)
        cr.fill()
    else:
        half = max(0.0, (size - w) / 2)  # round caps add w / 2 at each end
        cr.move_to(-half, -tip)
        cr.line_to(0, tip)
        cr.line_to(half, -tip)
        cr.set_line_width(w)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.stroke()
    cr.restore()


SHEET_DEPTH = 16  # the review sheet's panel depth: morph 1 draws the body this far out


def _strip(
    edge: Edge, x0: float, y0: float, cell: float, start: float, width: float
) -> tuple[float, float, float, float]:
    """The sheet cell's strip `start`..`start + width` px from its screen edge (x, y, w, h)."""
    return {
        "top": (x0, y0 + start, cell, width),
        "bottom": (x0, y0 + cell - start - width, cell, width),
        "left": (x0 + start, y0, width, cell),
        "right": (x0 + cell - start - width, y0, width, cell),
    }[edge]


def render_sheet(path: str, thickness: int = 10, zoom: int = 6) -> tuple[int, int]:
    """Write a PNG: one row per shape and edge, columns at morph 0, 0.25, 0.5, 0.75, 1. Each
    cell is the panel's mass in the frame colour (the `thickness` px band plus the body out
    to depth morph x SHEET_DEPTH), a 1 px red line just past the body's inner edge, and the
    handle where the shell puts it (shell.handle.shape_offset, at most shape_room across) in
    the theme's rest colour, then the same in the hover colour; enlarged `zoom` times without
    smoothing."""
    from shell.handle import shape_offset, shape_room
    from shell.theme import hex_to_rgba

    frame, rest, hover = (hex_to_rgba(c) for c in ("#0b0c0d", "#7b7f84", "#e6e8ea"))
    morphs = (0.0, 0.25, 0.5, 0.75, 1.0)
    cell, pad = max(48, thickness + SHEET_DEPTH + 8), 4  # px per cell at 1x, white gap
    rows = [(s, e) for s in SHAPES[:3] for e in ("top", "bottom", "left", "right")]
    step = cell + 2 * pad
    width, height = step * len(morphs) * 2, step * len(rows)
    small = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(small)
    cr.set_source_rgb(1, 1, 1)
    cr.paint()
    for row, (shape, edge) in enumerate(rows):
        for col in range(len(morphs) * 2):
            x0, y0 = col * step + pad, row * step + pad
            cr.set_source_rgb(0.55, 0.6, 0.65)  # a mid-grey "desktop"
            cr.rectangle(x0, y0, cell, cell)
            cr.fill()
            colour = rest if col < len(morphs) else hover
            m = morphs[col % len(morphs)]
            d = m * SHEET_DEPTH
            cr.set_source_rgba(*frame)  # the mass: frame band plus the body out to depth d
            cr.rectangle(*_strip(edge, x0, y0, cell, 0, thickness + d))
            cr.fill()
            cr.set_source_rgb(0.9, 0.1, 0.1)  # the body's inner edge, on the desktop side
            cr.rectangle(*_strip(edge, x0, y0, cell, thickness + d, 1))
            cr.fill()
            v = shape_offset(thickness, d)  # handle centre, px from the screen edge
            cx, cy = {
                "top": (x0 + cell / 2, y0 + v),
                "bottom": (x0 + cell / 2, y0 + cell - v),
                "left": (x0 + v, y0 + cell / 2),
                "right": (x0 + cell - v, y0 + cell / 2),
            }[edge]
            draw_handle(cr, shape, 15, 3, colour, m, edge, cx, cy, shape_room(thickness))
    big = cairo.ImageSurface(cairo.FORMAT_ARGB32, width * zoom, height * zoom)
    out = cairo.Context(big)
    out.scale(zoom, zoom)
    out.set_source_surface(small, 0, 0)
    out.get_source().set_filter(cairo.FILTER_NEAREST)
    out.paint()
    big.write_to_png(path)
    return big.get_width(), big.get_height()


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Render every handle shape to a PNG sheet.")
    p.add_argument("--sheet", required=True, help="output PNG path")
    p.add_argument("--thickness", type=int, default=10, help="frame thickness (default 10)")
    args = p.parse_args(argv)
    try:
        w, h = render_sheet(args.sheet, args.thickness)
    except (OSError, cairo.Error) as exc:  # cairo raises its own error types
        print(f"handle_draw: cannot write {args.sheet}: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {args.sheet} ({w}x{h})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
