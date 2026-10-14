"""Review sheet for corner panels (spec 19): the one union outline with a corner panel in each
corner, opening from each of the corner's two edges, at several collapse fractions, next to
edge panels placed by the layout resolver right beside it. Pure cairo; no shell, no GTK.

`python -m shell.canvas.corner_sheet --out FILE.png [--effects]` writes the sheet: one row per
(corner, opening edge) in the order of ROWS, one column per fraction in FRACTIONS (the corner
panel's depth / full depth; the edge panels stay extended), each cell a CELL-sized monitor
drawn by the real draw_scene on a grey desktop, enlarged ZOOM times without smoothing.
"""

from __future__ import annotations

import sys

import cairo

from shell.canvas.effects import draw_scene
from shell.canvas.scene import CornerShape, PanelShape, shape_for
from shell.panel_layout import AXIS_START, Layout, layout_monitor
from shell.panel_spec import CornerRequest, PanelRequest

ROWS = [
    (corner, edge)
    for corner in ("top-left", "top-right", "bottom-left", "bottom-right")
    for edge in corner.split("-")
]
FRACTIONS = (0.0, 0.05, 0.15, 0.3, 0.6, 1.0)
CELL = (360, 300)
THICKNESS, RADIUS, GAP = 10, 14, 8
ALONG, DEPTH = 120, 80  # the corner panel: px along its edge from the corner, px past the band
PAD, ZOOM = 6, 2
MASS = (0x0B / 255, 0x0C / 255, 0x0D / 255, 1.0)  # the default frame colour
BORDER = (2.0, (0x8F / 255, 0xD3 / 255, 0xB6 / 255, 1.0))  # the defaults once enabled
SHADOW = (50.0, (0.0, 0.0, 0.0, 0.5))


def _toward(corner: str, edge: str) -> str:
    """The align slot of `edge` nearest `corner`."""
    return "start" if AXIS_START[edge] == corner else "end"  # type: ignore[index]


def cell_layout(corner: str, edge: str) -> Layout:
    """The cell's corner panel plus one edge panel on each of its two edges, aligned towards
    it so they sit as close as the resolver allows."""
    side = next(e for e in corner.split("-") if e != edge)
    across = THICKNESS + DEPTH
    width, height = (ALONG, across) if edge in ("top", "bottom") else (across, ALONG)
    requests = [
        CornerRequest("corner", corner, edge, width, height, "extended", "corner"),
        _beside("next", edge, _toward(corner, edge), 80, 40),
        _beside("side", side, _toward(corner, side), 60, 30),
    ]
    return layout_monitor(requests, *CELL, THICKNESS, RADIUS, GAP, where=f"{corner}/{edge}")


def _beside(name: str, edge: str, align: str, length: int, depth: int) -> PanelRequest:
    return PanelRequest(
        widget=name,
        edge=edge,
        align=align,
        offset=0,
        pos=None,
        order=0,
        length=length,
        min_length=None,
        max_length=None,
        depth=depth,
        state="extended",
        label=name,
        fallback_length=length,
    )


def render_cell(corner: str, edge: str, fraction: float, effects: bool) -> cairo.ImageSurface:
    """One cell: the desktop grey, then the scene drawn by draw_scene."""
    w, h = CELL
    shapes = [shape_for(p) for p in cell_layout(corner, edge).panels if p is not None]
    panels = [
        (s.edge, s.pos, s.length, s.depth, s.depth) for s in shapes if isinstance(s, PanelShape)
    ]
    corners = [
        (s.corner, s.edge, s.along, s.depth, fraction * s.depth)
        for s in shapes
        if isinstance(s, CornerShape)
    ]
    scene = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    draw_scene(
        cairo.Context(scene),
        w,
        h,
        THICKNESS,
        RADIUS,
        panels,
        MASS,
        border=BORDER if effects else None,
        shadow=SHADOW if effects else None,
        corners=corners,
    )
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(out)
    cr.set_source_rgb(0.55, 0.6, 0.65)  # a mid-grey desktop
    cr.paint()
    cr.set_source_surface(scene, 0, 0)
    cr.paint()
    return out


def render_sheet(path: str, effects: bool = False) -> tuple[int, int]:
    w, h = CELL
    step_x, step_y = w + 2 * PAD, h + 2 * PAD
    small = cairo.ImageSurface(cairo.FORMAT_ARGB32, step_x * len(FRACTIONS), step_y * len(ROWS))
    cr = cairo.Context(small)
    cr.set_source_rgb(1, 1, 1)
    cr.paint()
    for row, (corner, edge) in enumerate(ROWS):
        for col, fraction in enumerate(FRACTIONS):
            cr.set_source_surface(
                render_cell(corner, edge, fraction, effects),
                col * step_x + PAD,
                row * step_y + PAD,
            )
            cr.paint()
    big = cairo.ImageSurface(
        cairo.FORMAT_ARGB32, small.get_width() * ZOOM, small.get_height() * ZOOM
    )
    out = cairo.Context(big)
    out.scale(ZOOM, ZOOM)
    out.set_source_surface(small, 0, 0)
    out.get_source().set_filter(cairo.FILTER_NEAREST)
    out.paint()
    big.write_to_png(path)
    return big.get_width(), big.get_height()


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        prog="python -m shell.canvas.corner_sheet",
        description="Render corner panels in every corner at several collapse fractions.",
    )
    p.add_argument("--out", required=True, help="output PNG path")
    p.add_argument("--effects", action="store_true", help="with the border and the shadow on")
    args = p.parse_args(argv)
    try:
        w, h = render_sheet(args.out, args.effects)
    except (OSError, cairo.Error) as exc:  # cairo raises its own error types
        print(f"corner_sheet: cannot write {args.out}: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {args.out} ({w}x{h})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
