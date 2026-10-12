"""Edge geometry. Panels are drawn in a canonical *bottom-edge* space: u runs along the
edge, v runs from the far (screen-interior) side at 0 to the screen edge at `across`.
`to_canvas` / `cairo_matrix` rotate that space onto the real edge. Pure: no GTK."""

from __future__ import annotations

import math

import cairo

from shell.config.models import Edge

Rect = tuple[int, int, int, int]


def is_horizontal(edge: Edge) -> bool:
    return edge in ("top", "bottom")


def surface_size(
    edge: Edge, length: int, depth: int, thickness: int, radius: int
) -> tuple[int, int]:
    along = length + 2 * radius
    across = thickness + depth
    return (along, across) if is_horizontal(edge) else (across, along)


def join_radius(d: float, radius: int) -> float:
    """Radius of the body's convex corners and the concave joins: min(R, d/2).

    Half the depth, so the convex corner and the concave join stack into a smooth
    S-curve (they need 2r of height) instead of overlapping while the panel is shallow.
    """
    return min(float(radius), max(0.0, float(d)) / 2)


def to_canvas(edge: Edge, u: float, v: float, along: float, across: float) -> tuple[float, float]:
    if edge == "bottom":
        return (u, v)
    if edge == "top":
        return (u, across - v)
    if edge == "left":
        return (across - v, u)
    return (v, u)  # right


def cairo_matrix(edge: Edge, across: float) -> cairo.Matrix:
    if edge == "bottom":
        return cairo.Matrix(1, 0, 0, 1, 0, 0)
    if edge == "top":
        return cairo.Matrix(1, 0, 0, -1, 0, across)
    if edge == "left":
        return cairo.Matrix(0, 1, -1, 0, across, 0)
    return cairo.Matrix(0, 1, 1, 0, 0, 0)  # right


def _bounds(edge: Edge, u1, v1, u2, v2, along, across) -> Rect:
    x1, y1 = to_canvas(edge, u1, v1, along, across)
    x2, y2 = to_canvas(edge, u2, v2, along, across)
    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))
    x, y = math.floor(left), math.floor(top)
    return (x, y, max(1, math.ceil(right) - x), max(1, math.ceil(bottom) - y))


def body_rect(edge: Edge, length: int, depth: int, d: float, thickness: int, radius: int) -> Rect:
    along = length + 2 * radius
    across = thickness + depth
    return _bounds(edge, radius, across - thickness - d, radius + length, across, along, across)


def input_rect(
    edge: Edge, length: int, depth: int, d: float, thickness: int, radius: int, hover_zone: int
) -> Rect:
    """Where the panel takes input. A collapsed panel keeps an invisible hover zone."""
    effective = max(d, min(hover_zone, depth))
    return body_rect(edge, length, depth, effective, thickness, radius)


def anchor_and_margin(
    edge: Edge, pos: int | None, along: int, radius: int, extent: int
) -> tuple[str, str]:
    """Layer-shell anchor string and margin string. `pos=None` centers along the edge."""
    if pos is None:
        return edge, "0px 0px 0px 0px"
    offset = max(0, pos - radius)  # the body starts `radius` into the surface
    offset = min(offset, max(0, extent - along))  # keep the surface on screen
    if is_horizontal(edge):
        return f"{edge} left", f"0px 0px 0px {offset}px"
    return f"{edge} top", f"{offset}px 0px 0px 0px"
