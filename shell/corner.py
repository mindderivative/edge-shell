"""Corner panel geometry (spec 19). Pure: no GTK.

A corner panel is a RECTANGLE in a screen corner (never an L): `along` px along the edge it
opens from (`edge`), the adjacent frame band included, and `thickness + depth` px across that
edge. Two of its sides lie on the screen edges; its two free sides meet the two frame bands.
Only its depth animates (0 = collapsed into the band of `edge`), exactly like an edge panel.

Coordinates: `p` runs along `edge` away from the corner, `q` away from `edge`'s screen edge
(towards the desktop), both from the screen corner. `to_xy` maps (p, q) onto a `width` x
`height` box anchored in that corner: the screen (canvas, layout) or the panel's own surface.
"""

from __future__ import annotations

import math

from shell import geometry
from shell import handle as hd
from shell.config.models import Corner, Edge
from shell.panel_spec import Interaction

Rect = tuple[int, int, int, int]  # x, y, width, height
Box = tuple[int, int, int, int]  # x0, y0, x1, y1 (x1 / y1 exclusive)


def to_xy(
    corner: Corner, edge: Edge, p: float, q: float, width: float, height: float
) -> tuple[float, float]:
    """(p, q) from the corner -> (x, y) in a `width` x `height` box anchored in that corner."""
    dx, dy = (p, q) if geometry.is_horizontal(edge) else (q, p)
    x = dx if corner.endswith("left") else width - dx
    y = dy if corner.startswith("top") else height - dy
    return x, y


def pq_box(
    corner: Corner,
    edge: Edge,
    p0: float,
    p1: float,
    q0: float,
    q1: float,
    width: float,
    height: float,
) -> tuple[float, float, float, float]:
    """The (p0..p1) x (q0..q1) rectangle as (x0, y0, x1, y1) in the box, sorted."""
    xa, ya = to_xy(corner, edge, p0, q0, width, height)
    xb, yb = to_xy(corner, edge, p1, q1, width, height)
    return min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb)


def _rect(box: tuple[float, float, float, float]) -> Rect:
    x, y = math.floor(box[0]), math.floor(box[1])
    return x, y, math.ceil(box[2]) - x, math.ceil(box[3]) - y


def surface_size(edge: Edge, along: int, depth: int, thickness: int) -> tuple[int, int]:
    """The panel window: exactly the extended body, `along` x (thickness + depth)."""
    across = thickness + depth
    return (along, across) if geometry.is_horizontal(edge) else (across, along)


def anchor(corner: Corner) -> str:
    """Layer-shell anchor: the two screen edges of the corner (margins stay 0)."""
    return " ".join(corner.split("-"))


def corner_box(
    corner: Corner,
    edge: Edge,
    along: int,
    d: float,
    width: int,
    height: int,
    thickness: int,
    radius: int,
    pad: int = 0,
) -> Box:
    """Every canvas pixel the panel can change at depth `d`: the body, its free-end fillet
    (radius <= R) along `edge`, and the screen-corner arc it lifts `d` px up the other edge
    (radius R), grown by `pad` (border + shadow), clamped to the screen."""
    x0, y0, x1, y1 = pq_box(
        corner,
        edge,
        0,
        along + radius + pad,
        0,
        thickness + math.ceil(max(0.0, d)) + radius + pad,
        width,
        height,
    )
    return max(0, int(x0)), max(0, int(y0)), min(width, int(x1)), min(height, int(y1))


def body_rect(corner: Corner, edge: Edge, along: int, depth: int, d: float, thickness: int) -> Rect:
    """The body at depth `d` in surface px: the whole `along`, from the screen edge to the
    body's inner edge (the frame band under it included, like an edge panel's body)."""
    w, h = surface_size(edge, along, depth, thickness)
    return _rect(pq_box(corner, edge, 0, along, 0, thickness + max(0.0, d), w, h))


def content_rect(corner: Corner, edge: Edge, along: int, depth: int, thickness: int) -> Rect:
    """Where the content box sits in the surface: past both frame bands, `along - thickness`
    by `depth` px."""
    w, h = surface_size(edge, along, depth, thickness)
    return _rect(pq_box(corner, edge, thickness, along, thickness, thickness + depth, w, h))


def _along_sign(corner: Corner, edge: Edge) -> int:
    """+1 when p grows towards the end of the screen axis (right, down): handle.offset keeps
    its edge-panel meaning (negative = towards the left or the top) in every corner."""
    if geometry.is_horizontal(edge):
        return 1 if corner.endswith("left") else -1
    return 1 if corner.startswith("top") else -1


def hit_rect(
    corner: Corner,
    edge: Edge,
    along: int,
    depth: int,
    d: float,
    thickness: int,
    hit: tuple[int, int],
    offset: int,
) -> Rect:
    """The handle's hit target in surface px: centred on the body past the adjacent band
    (`along - thickness` px), moved by `offset` (clamped to that body), riding the body's inner
    edge across (shell.handle.hit_inset) exactly as on an edge panel. Whole pixels."""
    length = along - thickness
    hit_along, hit_across = hit
    shift = _along_sign(corner, edge) * hd.clamp_offset(offset, length, hit_along)
    p0 = thickness + (length - hit_along) // 2 + shift
    q0 = hd.hit_inset(thickness, d, hit_across)
    w, h = surface_size(edge, along, depth, thickness)
    return _rect(pq_box(corner, edge, p0, p0 + hit_along, q0, q0 + hit_across, w, h))


def input_rects(
    corner: Corner,
    edge: Edge,
    along: int,
    depth: int,
    d: float,
    thickness: int,
    hover_zone: int,
    interaction: Interaction,
    hit: tuple[int, int],
    offset: int,
) -> list[Rect]:
    """Where the panel takes input at depth `d` (shell.handle.input_rects' rules): with hover
    on, the body plus the invisible hover zone while collapsed; with hover off, the body while
    it is out plus the hit target when click or drag is on; nothing at all while collapsed
    with every interaction off. Every rect is a plain rectangle."""
    if interaction.hover:
        effective = max(d, min(hover_zone, depth))
        return [body_rect(corner, edge, along, depth, effective, thickness)]
    rects = []
    if d > 0:
        rects.append(body_rect(corner, edge, along, depth, d, thickness))
    if interaction.click or interaction.drag:
        rects.append(hit_rect(corner, edge, along, depth, d, thickness, hit, offset))
    return rects
