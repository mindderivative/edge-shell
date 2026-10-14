"""Union outline of the desktop region: one closed path for frame + corners + all panels.

Pure cairo. Migrated from the shape-canvas spike (spikes/canvas/outline.py at 872eff9).
`tests/test_canvas_outline.py` pins it to the legacy per-window renderers (tests/legacy_draw.py).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import cairo

from shell import geometry

Panel = tuple[str, int, int, int, float]  # (edge, pos, length, depth_full, d_now)
# A corner panel (spec 19): (corner, edge it opens from, along, depth_full, d_now); `along` is px
# from the screen corner along that edge, the adjacent frame band included.
CornerSpan = tuple[str, str, int, int, float]

# Canonical frame -> device matrices. Canonical: u along the edge (clockwise), v from the
# screen edge towards the desktop. Pure rotations, so arc angles are unchanged.
_MATRICES = {
    "top": lambda w, h: cairo.Matrix(1, 0, 0, 1, 0, 0),
    "right": lambda w, h: cairo.Matrix(0, 1, -1, 0, w, 0),
    "bottom": lambda w, h: cairo.Matrix(-1, 0, 0, -1, w, h),
    "left": lambda w, h: cairo.Matrix(0, -1, 1, 0, 0, h),
}
_ORDER = ("top", "right", "bottom", "left")
# The screen corner each edge's clockwise walk starts and ends in.
_START = {"top": "top-left", "right": "top-right", "bottom": "bottom-right", "left": "bottom-left"}
_END = {"top": "top-right", "right": "bottom-right", "bottom": "bottom-left", "left": "top-left"}


def trace_edge(
    cr: cairo.Context,
    length: float,
    thickness: float,
    radius: float,
    spans: list[tuple[float, float, float]],
    first: bool,
    head: tuple[float, float] | None = None,
    tail: tuple[float, float] | None = None,
    lead: float = 0.0,
    trail: float = 0.0,
) -> None:
    """Trace one edge in the canonical frame (edge at v=0, desktop towards +v).

    Runs from the end of the previous corner arc, along the frame's inner line, over each
    panel bump `(u0, u1, d)` (sorted by u0), and through the following corner arc.

    Corner panels (spec 19) change only the two ends. `head = (u1, d)`: a corner panel on this
    edge in its start corner, body from the corner to `u1` at depth `d`; the walk starts on
    its body's inner edge and leaves it through a convex corner and a concave fillet (radius
    min(R, d/2)), like a bump's far side. `tail = (u0, d)`: the same in the end corner. The
    screen-corner arc keeps radius R and rides with the body: `tail` moves the end arc `d`
    across, `trail` (a corner panel in the end corner that opens from the NEXT edge) moves it
    back along by that panel's depth, and `lead` (one in the start corner that opens from the
    PREVIOUS edge) moves the start by its depth. With every depth 0 the walk is exactly the
    one without corner panels.
    """
    t, big_r = thickness, radius
    hd = max(0.0, head[1]) if head is not None else 0.0
    td = max(0.0, tail[1]) if tail is not None else 0.0
    start = (t + big_r + lead, t + hd)
    if first:
        cr.move_to(*start)
    else:
        cr.line_to(*start)
    if head is not None and hd > 0:
        u1, r = head[0], geometry.join_radius(hd, int(big_r))
        cr.line_to(u1 - r, t + hd)
        cr.arc_negative(u1 - r, t + hd - r, r, 0.5 * math.pi, 0)  # convex corner
        cr.line_to(u1, t + r)
        cr.arc(u1 + r, t + r, r, math.pi, 1.5 * math.pi)  # concave fillet
    for u0, u1, d in spans:
        if d <= 0:
            continue
        r = geometry.join_radius(d, int(big_r))
        cr.line_to(u0 - r, t)
        cr.arc(u0 - r, t + r, r, -0.5 * math.pi, 0)  # concave fillet
        cr.line_to(u0, t + d - r)
        cr.arc_negative(u0 + r, t + d - r, r, math.pi, 0.5 * math.pi)  # convex corner
        cr.line_to(u1 - r, t + d)
        cr.arc_negative(u1 - r, t + d - r, r, 0.5 * math.pi, 0)
        cr.line_to(u1, t + r)
        cr.arc(u1 + r, t + r, r, math.pi, 1.5 * math.pi)  # concave fillet
    if tail is not None and td > 0:
        u0, r = tail[0], geometry.join_radius(td, int(big_r))
        cr.line_to(u0 - r, t)
        cr.arc(u0 - r, t + r, r, -0.5 * math.pi, 0)  # concave fillet
        cr.line_to(u0, t + td - r)
        cr.arc_negative(u0 + r, t + td - r, r, math.pi, 0.5 * math.pi)  # convex corner
    cr.line_to(length - t - big_r - trail, t + td)
    cr.arc(length - t - big_r - trail, t + big_r + td, big_r, -0.5 * math.pi, 0)  # screen corner


def outline_path(
    cr: cairo.Context,
    w: int,
    h: int,
    T: int,
    R: int,
    panels: list[Panel],
    corners: Sequence[CornerSpan] = (),
) -> None:
    """Append the inner desktop boundary as ONE closed clockwise path (from the top-left).

    `corners` are corner panels (spec 19), at most one per screen corner; shell.panel_layout
    guarantees that and the minimum geometry that keeps the path simple."""
    first = True
    for edge in _ORDER:
        length = w if geometry.is_horizontal(edge) else h  # type: ignore[arg-type]
        spans = []
        for e, pos, plen, _depth, d in panels:
            if e != edge:
                continue
            if edge in ("bottom", "left"):  # screen pos grows against the clockwise walk
                spans.append((length - pos - plen, length - pos, d))
            else:
                spans.append((pos, pos + plen, d))
        spans.sort()
        head = tail = None
        lead = trail = 0.0
        for corner, opens, along, _depth, d in corners:
            if corner == _START[edge]:
                if opens == edge:
                    head = (along, d)
                else:
                    lead = max(0.0, d)
            elif corner == _END[edge]:
                if opens == edge:
                    tail = (length - along, d)
                else:
                    trail = max(0.0, d)
        cr.save()
        cr.transform(_MATRICES[edge](w, h))
        trace_edge(cr, length, T, R, spans, first, head, tail, lead, trail)
        cr.restore()
        first = False
    cr.close_path()


def fill_mass(
    cr: cairo.Context,
    w: int,
    h: int,
    T: int,
    R: int,
    panels: list[Panel],
    rgba: tuple[float, float, float, float],
    corners: Sequence[CornerSpan] = (),
) -> None:
    """Fill the dark mass: the whole screen minus the inner desktop region."""
    cr.save()
    cr.new_path()
    cr.rectangle(0, 0, w, h)
    outline_path(cr, w, h, T, R, panels, corners)
    cr.set_source_rgba(*rgba)
    cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    cr.fill()
    cr.restore()
