"""Panel layout (spec 16-17): every panel of one monitor resolved to an exact body start and
length, from align / offset / order / gap, keeping the minimum geometry the single-outline
canvas needs. Pure: no GTK.

Per edge (`layout_edge`):

1. Free span. A body must stay `T + R + r` from each end of the edge (`r` = its join radius
   at full depth), so its fillet never reaches into a screen-corner arc. A free span shorter
   than MIN_LENGTH hides the panel.
2. Lengths. px as given (other length modes: the widget's default px for now). A length
   longer than the free span is shrunk to it (warning).
3. Slots. start / center / end, each sorted by (order, config index). Neighbours in the
   sequence start -> center -> end are `r1 + r2 + gap` apart. The start slot packs from the
   start of the free span, the end slot from its end (its first panel nearest the end); each
   panel's `offset` is extra space before it, counted from the end (first panel) or from its
   neighbour. The center slot is centred on the edge as one group and pushed clear of the
   start and end groups; its first panel's offset then shifts the group from there (a
   negative offset on a later center panel counts as 0).
4. `pos` (deprecated alias): the panel is placed alone at `pos` px from the start of the
   edge, clamped into its free span (warning); it takes no part in the slots.

Across the monitor (`layout_monitor`): panels are checked in config order; a panel whose body
box (full depth, from the screen edge, grown by its `r`) overlaps an earlier panel's is not
shown (warning). On one edge that is the minimum gap `r1 + r2`; it also catches deep panels on
neighbouring edges (two panels meeting at a shared screen corner at offset 0 always collide:
one needs an offset of at least the other's depth + r - R), and `pos` panels dropped onto
slotted ones. Touching is allowed. A hidden panel keeps the slot space it was given: its
neighbours do not close up.

Every warning names the key path (`where`.panels.N (widget)).

`resolve_layout` is the interim rule set (pos only) that MonitorShell still uses; it goes when
MonitorShell switches to `layout_monitor`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from itertools import pairwise

from shell import geometry
from shell.config.models import Edge
from shell.panel_spec import PanelGeometry, PanelRequest

MIN_LENGTH = 60  # same floor as the config model's px lengths
EDGES: tuple[Edge, ...] = ("top", "right", "bottom", "left")

Box = tuple[float, float, float, float]  # x0, y0, x1, y1
Note = tuple[int, str]  # (config index, warning)


@dataclass(frozen=True)
class Layout:
    panels: list[PanelGeometry | None]  # config order; None = not shown
    warnings: list[str]


def free_span(extent: int, thickness: int, radius: int, depth: int) -> tuple[int, int]:
    """(first, last) px along the edge a body of this depth may occupy (corner clearance)."""
    clearance = thickness + radius + geometry.join_radius(depth, radius)
    return math.ceil(clearance), math.floor(extent - clearance)


@dataclass
class _Item:
    index: int
    req: PanelRequest
    name: str
    lo: int
    hi: int
    r: float
    length: int = 0
    pos: int = 0


def _wanted(it: _Item, natural: Mapping[int, int]) -> int:
    spec = it.req.length
    return spec if isinstance(spec, int) else it.req.fallback_length


def _fit(it: _Item, length: int, notes: list[Note]) -> int:
    length = max(length, MIN_LENGTH)
    span = it.hi - it.lo
    if length > span:
        notes.append(
            (
                it.index,
                f"{it.name}: length {length} px does not fit the {it.req.edge} edge; "
                f"shrunk to {span}",
            )
        )
        length = span
    return length


def _clamp(it: _Item, wanted: int, what: str | None, notes: list[Note]) -> int:
    """Keep the body inside its free span; `what` names the user value for the warning."""
    pos = min(max(wanted, it.lo), it.hi - it.length)
    if what is not None and pos != wanted:
        notes.append(
            (it.index, f"{it.name}: {what} would run into a screen corner; moved to {pos}")
        )
    return pos


def layout_edge(
    entries: Sequence[tuple[int, PanelRequest]],
    extent: int,
    thickness: int,
    radius: int,
    gap: int,
    natural: Mapping[int, int] | None = None,
    where: str = "monitor",
) -> tuple[dict[int, tuple[int, int] | None], list[Note]]:
    """Resolve the panels of ONE edge. `entries` are (config index, request) pairs; returns
    {index: (pos, length) or None when the edge has no room} and (index, warning) notes."""
    natural = natural or {}
    out: dict[int, tuple[int, int] | None] = {}
    notes: list[Note] = []
    items: list[_Item] = []
    for index, req in entries:
        name = f"{where}.panels.{index} ({req.widget})"
        lo, hi = free_span(extent, thickness, radius, req.depth)
        if hi - lo < MIN_LENGTH:
            notes.append(
                (index, f"{name}: the {req.edge} edge ({extent} px) has no room for it; not shown")
            )
            out[index] = None
            continue
        items.append(_Item(index, req, name, lo, hi, geometry.join_radius(req.depth, radius)))

    def space(a: _Item, b: _Item) -> float:
        return a.r + b.r + gap

    def slot(align: str) -> list[_Item]:
        chosen = [it for it in items if it.req.pos is None and it.req.align == align]
        return sorted(chosen, key=lambda it: (it.req.order, it.index))

    start, center, end = slot("start"), slot("center"), slot("end")
    for it in items:
        if it.req.length != "fill":
            it.length = _fit(it, _wanted(it, natural), notes)

    cursor: float = start[0].lo if start else 0
    for k, it in enumerate(start):
        wanted = math.ceil(cursor + it.req.offset)
        it.pos = _clamp(it, wanted, f"offset {it.req.offset}" if it.req.offset else None, notes)
        if k + 1 < len(start):
            cursor = it.pos + it.length + space(it, start[k + 1])
    cursor = end[0].hi if end else 0
    for k, it in enumerate(end):
        wanted = math.floor(cursor - it.req.offset - it.length)
        it.pos = _clamp(it, wanted, f"offset {it.req.offset}" if it.req.offset else None, notes)
        if k + 1 < len(end):
            cursor = it.pos - space(it, end[k + 1])
    if center:
        head, shift = center[0], center[0].req.offset
        inner = sum(space(a, b) for a, b in pairwise(center))
        total = math.ceil(
            sum(it.length for it in center)
            + inner
            + sum(max(0, it.req.offset) for it in center[1:])
        )
        left = (
            math.ceil(start[-1].pos + start[-1].length + space(start[-1], head))
            if start
            else head.lo
        )
        right = math.floor(end[-1].pos - space(center[-1], end[-1])) if end else center[-1].hi
        base = max(left, min((extent - total) // 2, right - total))  # without the offset
        first = max(left, min(base + shift, right - total))
        if shift and first != base + shift:
            notes.append(
                (
                    head.index,
                    f"{head.name}: offset {shift} would run into a screen corner or a "
                    f"neighbour; moved to {first}",
                )
            )
        cursor = first
        for k, it in enumerate(center):
            if k:
                cursor = math.ceil(cursor + space(center[k - 1], it) + max(0, it.req.offset))
            it.pos = min(max(int(cursor), it.lo), it.hi - it.length)
            cursor = it.pos + it.length
    for it in items:
        if it.req.pos is not None:
            it.pos = _clamp(it, it.req.pos, f"pos {it.req.pos}", notes)
    for it in items:
        out[it.index] = (it.pos, it.length)
    return out, notes


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


def layout_monitor(
    requests: Sequence[PanelRequest],
    width: int,
    height: int,
    thickness: int,
    radius: int,
    gap: int,
    natural: Mapping[int, int] | None = None,
    where: str = "monitor",
) -> Layout:
    """Resolve every panel of one monitor. `natural` maps a config index to the measured
    length of a "content" panel; `where` prefixes warnings, e.g. "monitors.HDMI-A-1"."""
    resolved: dict[int, tuple[int, int] | None] = {}
    notes: list[Note] = []
    for edge in EDGES:
        entries = [(i, req) for i, req in enumerate(requests) if req.edge == edge]
        if entries:
            extent = width if geometry.is_horizontal(edge) else height
            got, edge_notes = layout_edge(entries, extent, thickness, radius, gap, natural, where)
            resolved.update(got)
            notes.extend(edge_notes)
    out: list[PanelGeometry | None] = []
    placed: list[tuple[int, PanelGeometry, Box]] = []
    for i, req in enumerate(requests):
        got = resolved[i]
        if got is None:
            out.append(None)
            continue
        geo = PanelGeometry(req.widget, req.edge, got[0], got[1], req.depth, req.state, req.label)
        box = _grown_body(geo, width, height, thickness, geometry.join_radius(req.depth, radius))
        clash = next(((j, other) for j, other, b in placed if _overlap(box, b)), None)
        if clash is not None:
            notes.append(
                (
                    i,
                    f"{where}.panels.{i} ({req.widget}): overlaps {where}.panels.{clash[0]} "
                    f"({clash[1].widget}) or leaves less than the minimum gap between their "
                    "joins; not shown",
                )
            )
            out.append(None)
            continue
        placed.append((i, geo, box))
        out.append(geo)
    notes.sort(key=lambda note: note[0])  # stable: per panel, in the order they arose
    return Layout(out, [message for _, message in notes])


def resolve_layout(
    geos: list[PanelGeometry],
    width: int,
    height: int,
    thickness: int,
    radius: int,
    where: str = "monitor",
) -> Layout:
    """Interim rules (pos only). `where` prefixes warnings, e.g. "monitors.HDMI-A-1"."""
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
