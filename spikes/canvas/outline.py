"""Union outline of the desktop region: one closed path for frame + corners + all panels."""

from __future__ import annotations

import math

import cairo

from shell import geometry

Panel = tuple[str, int, int, int, float]  # (edge, pos, length, depth_full, d_now)

# Canonical frame -> device matrices. Canonical: u along the edge (clockwise), v from the
# screen edge towards the desktop. Pure rotations, so arc angles are unchanged.
_MATRICES = {
    "top": lambda w, h: cairo.Matrix(1, 0, 0, 1, 0, 0),
    "right": lambda w, h: cairo.Matrix(0, 1, -1, 0, w, 0),
    "bottom": lambda w, h: cairo.Matrix(-1, 0, 0, -1, w, h),
    "left": lambda w, h: cairo.Matrix(0, -1, 1, 0, 0, h),
}
_ORDER = ("top", "right", "bottom", "left")


def trace_edge(
    cr: cairo.Context,
    length: float,
    thickness: float,
    radius: float,
    spans: list[tuple[float, float, float]],
    first: bool,
) -> None:
    """Trace one edge in the canonical frame (edge at v=0, desktop towards +v).

    Runs from the end of the previous corner arc, along the frame's inner line, over each
    panel bump `(u0, u1, d)` (sorted by u0), and through the following corner arc.
    """
    t, big_r = thickness, radius
    start = (t + big_r, t)
    if first:
        cr.move_to(*start)
    else:
        cr.line_to(*start)
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
    cr.line_to(length - t - big_r, t)
    cr.arc(length - t - big_r, t + big_r, big_r, -0.5 * math.pi, 0)  # inner screen corner


def outline_path(cr: cairo.Context, w: int, h: int, T: int, R: int, panels: list[Panel]) -> None:
    """Append the inner desktop boundary as ONE closed clockwise path (from the top-left)."""
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
        cr.save()
        cr.transform(_MATRICES[edge](w, h))
        trace_edge(cr, length, T, R, spans, first)
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
) -> None:
    """Fill the dark mass: the whole screen minus the inner desktop region."""
    cr.save()
    cr.new_path()
    cr.rectangle(0, 0, w, h)
    outline_path(cr, w, h, T, R, panels)
    cr.set_source_rgba(*rgba)
    cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    cr.fill()
    cr.restore()
