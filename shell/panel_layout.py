"""Resolve every panel of one monitor to an exact position, enforcing the minimum geometry the
single-outline canvas needs (spec 17, "Minimum geometry rules"). Pure: no GTK.

The full align/offset/gap layout resolver is a later plan; this is the smallest safe rule set:

1. Corner clearance: a panel's fillet must not reach into a screen-corner arc, so
   `pos - r >= T + R` at both ends of the edge, with `r = join_radius(depth, R)` (the join
   radius at full depth, the widest it gets). Positions are clamped into that free span; a
   panel longer than the span is shrunk to fit; one that cannot keep MIN_LENGTH is not shown.
2. Separation: the body boxes (full depth, from the screen edge), each grown by its own `r`,
   must not overlap. On one edge that is the minimum gap `r1 + r2`; it also catches deep panels
   on neighbouring or opposite edges that would cross. A later panel (config order) that
   breaks it is not shown.

Every adjustment produces a warning naming the key path. Touching (gap exactly `r1 + r2`,
pos exactly at the clearance) is allowed: the outline renders it correctly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from shell import geometry
from shell.panel_spec import PanelGeometry

MIN_LENGTH = 60  # same floor as the config model's Length

Box = tuple[float, float, float, float]  # x0, y0, x1, y1


@dataclass(frozen=True)
class Layout:
    panels: list[PanelGeometry | None]  # input order; pos is always an int; None = not shown
    warnings: list[str]


def _grown_body(geo: PanelGeometry, width: int, height: int, thickness: int, r: float) -> Box:
    a0, a1 = geo.pos - r, geo.pos + geo.length + r
    across = thickness + geo.depth + r
    if geo.edge == "top":
        return (a0, -r, a1, across)
    if geo.edge == "bottom":
        return (a0, height - across, a1, height + r)
    if geo.edge == "left":
        return (-r, a0, across, a1)
    return (width - across, a0, width + r, a1)


def _overlap(a: Box, b: Box) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def resolve_layout(
    geos: list[PanelGeometry],
    width: int,
    height: int,
    thickness: int,
    radius: int,
    where: str = "monitor",
) -> Layout:
    """`where` prefixes warnings, e.g. "monitors.HDMI-A-1"."""
    out: list[PanelGeometry | None] = []
    warnings: list[str] = []
    placed: list[tuple[int, PanelGeometry, Box]] = []
    for i, geo in enumerate(geos):
        name = f"{where}.panels.{i} ({geo.widget})"
        extent = width if geometry.is_horizontal(geo.edge) else height
        r = geometry.join_radius(geo.depth, radius)
        clearance = thickness + radius + r  # corner clearance at each end of the edge
        lo, hi = math.ceil(clearance), math.floor(extent - clearance)  # body start / end limits
        span = hi - lo
        length = geo.length
        if length > span:
            if span < MIN_LENGTH:
                warnings.append(
                    f"{name}: the {geo.edge} edge ({extent} px) has no room for it; not shown"
                )
                out.append(None)
                continue
            warnings.append(
                f"{name}: length {length} px does not fit the {geo.edge} edge; shrunk to {span}"
            )
            length = span
        wanted = (extent - length) // 2 if geo.pos is None else geo.pos
        pos = min(max(wanted, lo), hi - length)
        if geo.pos is not None and pos != geo.pos:
            warnings.append(f"{name}: pos {geo.pos} would run into a screen corner; moved to {pos}")
        resolved = replace(geo, pos=pos, length=length)
        box = _grown_body(resolved, width, height, thickness, r)
        clash = next((j for j, _g, other in placed if _overlap(box, other)), None)
        if clash is not None:
            other = next(g for j, g, _b in placed if j == clash)
            warnings.append(
                f"{name}: overlaps {where}.panels.{clash} ({other.widget}) or leaves less than "
                f"the minimum gap between their joins; not shown"
            )
            out.append(None)
            continue
        placed.append((i, resolved, box))
        out.append(resolved)
    return Layout(out, warnings)
