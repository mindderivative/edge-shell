"""Panel layout (spec 16-17): every panel of one monitor resolved to an exact body start and
length, from align / offset / order / gap, keeping the minimum geometry the single-outline
canvas needs. Pure: no GTK.

Per edge (`layout_edge`):

1. Free span. A body must stay `T + R + r` from each end of the edge (`r` = its join radius
   at full depth), so its fillet never reaches into a screen-corner arc. A free span shorter
   than MIN_LENGTH hides the panel.
2. Lengths. px as given; "NN%" of the panel's own free span; "content" = the measured natural
   length (`natural[index]`, the widget's default px until measured); then min_length /
   max_length and the MIN_LENGTH floor. "fill" panels share what the slotted neighbours, the
   offsets and the spacing leave, equally (the first fill gets the odd pixels). A length
   longer than the free span is shrunk to it (warning).
3. Slots. start / center / end, each sorted by (order, config index). Neighbours in the
   sequence start -> center -> end are `r1 + r2 + gap` apart. The start slot packs from the
   start of the free span, the end slot from its end (its first panel nearest the end); each
   panel's `offset` is extra space before it, counted from the end (first panel) or from its
   neighbour. The center slot is centred on the edge as one group and pushed clear of the
   start and end groups; its first panel's offset then shifts the group from there (a
   negative offset on a later center panel counts as 0).
4. `pos` (deprecated alias): the panel is placed alone at `pos` px from the start of the
   edge, clamped into its free span (warning); it takes no part in the slots or the fill
   (a `pos` panel with length "fill" runs to the end of its free span).

Across the monitor (`layout_monitor`): corner panels are checked first, then edge panels in
config order; a panel whose body box (full depth, from the screen edge, grown by its `r`)
overlaps an earlier panel's is not shown (warning). On one edge that is the minimum gap
`r1 + r2`; it also catches deep panels on neighbouring edges (two panels meeting at a shared
screen corner at offset 0 always collide:
one needs an offset of at least the other's depth + r - R), and `pos` panels dropped onto
slotted ones. Touching is allowed. A hidden panel keeps the slot space it was given: its
neighbours do not close up.

Gaps between slot groups: the `gap` is honoured between neighbours inside one slot, but
between different groups (start / center / end) only the minimum `r1 + r2` is guaranteed,
not `r1 + r2 + gap` (the center group is pushed clear of the start and end groups by the
minimum, and a fill sizes against the full spacing). Raised for a decision.

Corner panels (spec 19, `layout_corners`) are placed first, in config order: at most one per
screen corner (a later one in a taken corner is not shown); each is shrunk to fit beside the
corner panels already placed (along its edge: their free ends plus `r1 + r2 + gap`, or their
lifted screen-corner arc; across: the far corner's occupant), and not shown when `along` falls
below max(T + MIN_LENGTH, T + R + r) (so the outline never folds, whatever the theme radius)
or less than MIN_DEPTH px of depth remains; a hidden panel gets only its "not shown" warning.
A corner panel that overlaps one placed before it is hidden there too, so only the corner
panels that are shown are held. They then move the free span of their two edges: on the edge
a corner panel opens from, the span starts `along + r_c + gap` from that corner (plus the
panel's own `r`, as between neighbours); on the other edge the screen-corner arc rides up by
its depth, so the span starts `T + R + depth` from the corner (plus `r`). The overlap check
then runs over the shown corner panels first, then the edge panels.

Every warning names the key path (`where`.panels.N (widget)).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise

from shell import geometry
from shell.config.models import Corner, Edge
from shell.corner import pq_box
from shell.panel_spec import CornerGeometry, CornerRequest, PanelGeometry, PanelRequest

MIN_LENGTH = 60  # same floor as the config model's px lengths
MIN_DEPTH = 16  # a corner panel's smallest depth past the band (the model's Depth minimum)
CONTENT_PAD = 12  # body px on each side of a "content" panel's natural size
EDGES: tuple[Edge, ...] = ("top", "right", "bottom", "left")

Box = tuple[float, float, float, float]  # x0, y0, x1, y1
Note = tuple[int, str]  # (config index, warning)


# The screen corner at the start (left / top) and at the end (right / bottom) of each edge, in
# the layout's screen-axis terms (`pos` grows left to right, top to bottom).
AXIS_START: dict[Edge, Corner] = {
    "top": "top-left",
    "bottom": "bottom-left",
    "left": "top-left",
    "right": "top-right",
}
AXIS_END: dict[Edge, Corner] = {
    "top": "top-right",
    "bottom": "bottom-right",
    "left": "bottom-left",
    "right": "bottom-right",
}


@dataclass(frozen=True)
class Layout:
    panels: list[PanelGeometry | CornerGeometry | None]  # config order; None = not shown
    warnings: list[str]


def content_length(natural: int) -> int:
    """Body length for a widget whose content is `natural` px long along the edge."""
    return max(MIN_LENGTH, natural + 2 * CONTENT_PAD)


def free_span(
    extent: int,
    thickness: int,
    radius: int,
    depth: int,
    start: float | None = None,
    end: float | None = None,
) -> tuple[int, int]:
    """(first, last) px along the edge a body of this depth may occupy: `start` / `end` px of
    each corner are taken (`T + R` without a corner panel, `corner_clearance`), plus the
    body's own join radius."""
    r = geometry.join_radius(depth, radius)
    lo = (thickness + radius if start is None else start) + r
    hi = extent - (thickness + radius if end is None else end) - r
    return math.ceil(lo), math.floor(hi)


def corner_clearance(
    edge: Edge,
    held: CornerGeometry | None,
    thickness: int,
    radius: int,
    gap: int,
) -> float:
    """Px of `edge` taken from the corner that holds `held` (None: a plain screen corner,
    T + R). A corner panel opening from `edge` takes its body, its free-end join and the gap
    (edge panels keep `r1 + r2 + gap` from it, as from a neighbour); one opening from the
    other edge lifts the screen-corner arc by its depth (no gap, as at a plain corner)."""
    spare = gap if held is not None and held.edge == edge else 0
    return _reach(edge, held, thickness, radius) + spare


def _reach(edge: Edge, held: CornerGeometry | None, thickness: int, radius: int) -> float:
    """Px of `edge` a corner's occupant reaches from its corner: its free end (body plus join)
    when it opens from `edge`, else the screen-corner arc it lifts (T + R + depth)."""
    if held is None:
        return thickness + radius
    if held.edge == edge:
        return held.along + geometry.join_radius(held.depth, radius)
    return thickness + radius + held.depth


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
    if spec == "content":
        return natural.get(it.index, it.req.fallback_length)
    if isinstance(spec, str):  # "NN%" (the model only lets through px, fill, content, NN%)
        return round((it.hi - it.lo) * float(spec[:-1]) / 100)
    return spec


def _fit(it: _Item, length: int, notes: list[Note]) -> int:
    length = max(length, MIN_LENGTH, it.req.min_length or 0)
    if it.req.max_length is not None:
        length = max(MIN_LENGTH, min(length, it.req.max_length))
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
    clear: tuple[float | None, float | None] = (None, None),
) -> tuple[dict[int, tuple[int, int] | None], list[Note]]:
    """Resolve the panels of ONE edge. `entries` are (config index, request) pairs; `clear`
    is what corner panels take at the start and the end of the edge (corner_clearance; None:
    a plain corner). Returns {index: (pos, length) or None when the edge has no room} and
    (index, warning) notes."""
    natural = natural or {}
    out: dict[int, tuple[int, int] | None] = {}
    notes: list[Note] = []
    items: list[_Item] = []
    for index, req in entries:
        name = f"{where}.panels.{index} ({req.widget})"
        lo, hi = free_span(extent, thickness, radius, req.depth, *clear)
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
    seq = start + center + end[::-1]  # left to right (top to bottom)
    for it in items:
        if it.req.length != "fill":
            it.length = _fit(it, _wanted(it, natural), notes)
    fills = [it for it in seq if it.req.length == "fill"]
    if fills:
        fixed = sum(it.length for it in seq if it.req.length != "fill")
        gaps = sum(math.ceil(space(a, b)) for a, b in pairwise(seq))
        offsets = sum(it.req.offset for it in start + end) + sum(
            max(0, it.req.offset) for it in center[1:]
        )
        if center and center[0].req.length == "fill":  # it gives up its offset (see below)
            offsets += abs(center[0].req.offset)
        room = math.floor(seq[-1].hi - seq[0].lo - fixed - gaps - offsets)
        share, extra = divmod(max(0, room), len(fills))
        for k, it in enumerate(fills):
            part = share + (extra if k == 0 else 0)
            if part < MIN_LENGTH:
                notes.append((it.index, f"{it.name}: no room to fill; shown at {MIN_LENGTH} px"))
            it.length = _fit(it, part, notes)

    def place(it: _Item, wanted: int, alone: int, align: str) -> int:
        """Clamp a slotted panel; a move is always reported, as the user's own offset running
        into a corner when it would have done so alone, else as the neighbours' doing."""
        pos = _clamp(it, wanted, None, notes)
        if pos != wanted:
            if it.req.offset and not it.lo <= alone <= it.hi - it.length:
                text = f"offset {it.req.offset} would run into a screen corner; moved to {pos}"
            else:
                text = f"no room after its neighbours in the {align} slot; moved to {pos}"
            notes.append((it.index, f"{it.name}: {text}"))
        return pos

    cursor: float = start[0].lo if start else 0
    for k, it in enumerate(start):
        it.pos = place(
            it, math.ceil(cursor + it.req.offset), math.ceil(it.lo + it.req.offset), "start"
        )
        if k + 1 < len(start):
            cursor = it.pos + it.length + space(it, start[k + 1])
    cursor = end[0].hi if end else 0
    for k, it in enumerate(end):
        it.pos = place(
            it,
            math.floor(cursor - it.req.offset - it.length),
            math.floor(it.hi - it.req.offset - it.length),
            "end",
        )
        if k + 1 < len(end):
            cursor = it.pos - space(it, end[k + 1])
    if center:
        head, shift = center[0], center[0].req.offset
        inner = sum(math.ceil(space(a, b)) for a, b in pairwise(center))
        total = (
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
        cursor = first
        for k, it in enumerate(center):
            if k:
                cursor = math.ceil(cursor + space(center[k - 1], it) + max(0, it.req.offset))
            wanted = int(cursor)
            it.pos = min(max(wanted, it.lo), it.hi - it.length)
            cursor = it.pos + it.length
            if k == 0 and shift and head.req.length != "fill":
                # reported last, with the final position (a fill took its offset as room: the
                # clamp only decides which side the free space is on, so it is no warning)
                if it.pos != base + shift:
                    notes.append(
                        (
                            it.index,
                            f"{it.name}: offset {shift} would run into a screen corner or a "
                            f"neighbour; moved to {it.pos}",
                        )
                    )
            elif it.pos != wanted:
                notes.append(
                    (
                        it.index,
                        f"{it.name}: no room after its neighbours in the center slot; "
                        f"moved to {it.pos}",
                    )
                )
    for it in items:
        if it.req.pos is not None:
            if it.req.length == "fill":
                it.length = _fit(it, it.hi - max(it.req.pos, it.lo), notes)
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


def _corner_grown(geo: CornerGeometry, width: int, height: int, thickness: int, radius: int) -> Box:
    """The corner panel's box for the overlap check: its body, its free-end join along its
    edge and the lifted screen-corner arc (radius R) across, from beyond the screen corner."""
    r = geometry.join_radius(geo.depth, radius)
    return pq_box(
        geo.corner,
        geo.edge,
        -radius,
        geo.along + r,
        -radius,
        thickness + geo.depth + radius,
        width,
        height,
    )


def _other(corner: Corner, edge: Edge) -> Edge:
    first, second = corner.split("-")
    return second if edge == first else first  # type: ignore[return-value]


def _far(corner: Corner, edge: Edge) -> Corner:
    """The other screen corner on `edge`."""
    return AXIS_END[edge] if AXIS_START[edge] == corner else AXIS_START[edge]


def layout_corners(
    entries: Sequence[tuple[int, CornerRequest]],
    width: int,
    height: int,
    thickness: int,
    radius: int,
    gap: int,
    where: str = "monitor",
) -> tuple[dict[int, CornerGeometry | None], list[Note]]:
    """Resolve the corner panels (spec 19), in config order (see the module docstring). Only
    corner panels that are shown are held: a hidden one takes no clearance from anything."""
    out: dict[int, CornerGeometry | None] = {}
    notes: list[Note] = []
    held: dict[Corner, tuple[int, CornerGeometry]] = {}
    boxes: list[tuple[int, CornerGeometry, Box]] = []
    for index, req in entries:
        name = f"{where}.panels.{index} ({req.widget})"
        if req.corner in held:
            j, other = held[req.corner]
            notes.append(
                (
                    index,
                    f"{name}: the {req.corner} corner already holds {where}.panels.{j} "
                    f"({other.widget}); not shown",
                )
            )
            out[index] = None
            continue
        edge, side = req.edge, _other(req.corner, req.edge)
        horizontal = geometry.is_horizontal(edge)
        along_key, across_key = ("width", "height") if horizontal else ("height", "width")
        extent_e, extent_f = (width, height) if horizontal else (height, width)
        depth = getattr(req, across_key) - thickness
        shrunk: list[Note] = []  # reported only when the panel is shown
        # across: the screen-corner arc it lifts must stay clear of the far corner of `side`
        far_f = held.get(_far(req.corner, side), (None, None))[1]
        room = extent_f - thickness - radius - math.ceil(_reach(side, far_f, thickness, radius))
        if depth > room:
            shrunk.append(
                (
                    index,
                    f"{name}: {across_key} {depth + thickness} px does not fit the {side} edge; "
                    f"shrunk to {room + thickness}",
                )
            )
            depth = room
        r = geometry.join_radius(depth, radius)
        # the side from the lifted arc (T + R) to the free corner (along - r) never runs
        # backwards, and the body keeps MIN_LENGTH px past the band, whatever the theme radius
        need = max(thickness + MIN_LENGTH, thickness + radius + math.ceil(r))
        along = max(getattr(req, along_key), need)
        # along: its free end must stay clear of the far corner of `edge`
        far_e = held.get(_far(req.corner, edge), (None, None))[1]
        room = math.floor(extent_e - corner_clearance(edge, far_e, thickness, radius, gap) - r)
        if along > room:
            shrunk.append(
                (
                    index,
                    f"{name}: {along_key} {along} px does not fit the {edge} edge; "
                    f"shrunk to {room}",
                )
            )
            along = room
        if depth < MIN_DEPTH or along < need:
            notes.append((index, f"{name}: the {req.corner} corner has no room for it; not shown"))
            out[index] = None
            continue
        geo = CornerGeometry(
            req.widget,
            req.corner,
            edge,
            along,
            along - thickness,
            depth,
            req.state,
            req.label,
        )
        # a corner panel across the screen may still overlap one placed before it: hidden,
        # and never held, so it takes no clearance from any edge panel
        box = _corner_grown(geo, width, height, thickness, radius)
        clash = next(((j, other) for j, other, b in boxes if _overlap(box, b)), None)
        if clash is not None:
            notes.append(
                (
                    index,
                    f"{name}: overlaps {where}.panels.{clash[0]} ({clash[1].widget}) or leaves "
                    "less than the minimum gap between their joins; not shown",
                )
            )
            out[index] = None
            continue
        notes.extend(shrunk)
        held[req.corner] = (index, geo)
        boxes.append((index, geo, box))
        out[index] = geo
    return out, notes


def _overlap(a: Box, b: Box) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def layout_monitor(
    requests: Sequence[PanelRequest | CornerRequest],
    width: int,
    height: int,
    thickness: int,
    radius: int,
    gap: int,
    natural: Mapping[int, int] | None = None,
    where: str = "monitor",
) -> Layout:
    """Resolve every panel of one monitor, edge (PanelRequest) and corner (CornerRequest).
    `natural` maps a config index to the measured length of a "content" panel; `where`
    prefixes warnings, e.g. "monitors.HDMI-A-1"."""
    corner_entries = [(i, r) for i, r in enumerate(requests) if isinstance(r, CornerRequest)]
    corners, notes = layout_corners(corner_entries, width, height, thickness, radius, gap, where)
    held = {geo.corner: geo for geo in corners.values() if geo is not None}
    resolved: dict[int, tuple[int, int] | None] = {}
    for edge in EDGES:
        entries = [
            (i, req)
            for i, req in enumerate(requests)
            if isinstance(req, PanelRequest) and req.edge == edge
        ]
        if entries:
            extent = width if geometry.is_horizontal(edge) else height
            clear = (
                corner_clearance(edge, held.get(AXIS_START[edge]), thickness, radius, gap),
                corner_clearance(edge, held.get(AXIS_END[edge]), thickness, radius, gap),
            )
            got, edge_notes = layout_edge(
                entries, extent, thickness, radius, gap, natural, where, clear
            )
            resolved.update(got)
            notes.extend(edge_notes)
    geos: dict[int, PanelGeometry | CornerGeometry | None] = dict(corners)
    for i, got in resolved.items():
        req = requests[i]
        if got is None:
            geos[i] = None
            continue
        pos, length = got
        geos[i] = PanelGeometry(req.widget, req.edge, pos, length, req.depth, req.state, req.label)
    out: list[PanelGeometry | CornerGeometry | None] = [geos[i] for i in range(len(requests))]
    placed: list[tuple[int, PanelGeometry | CornerGeometry, Box]] = []
    order = [i for i, _ in corner_entries] + [i for i in range(len(requests)) if i in resolved]
    for i in order:
        geo = out[i]
        if geo is None:
            continue
        if isinstance(geo, CornerGeometry):
            box = _corner_grown(geo, width, height, thickness, radius)
        else:
            r = geometry.join_radius(geo.depth, radius)
            box = _grown_body(geo, width, height, thickness, r)
        clash = next(((j, other) for j, other, b in placed if _overlap(box, b)), None)
        if clash is not None:
            notes.append(
                (
                    i,
                    f"{where}.panels.{i} ({geo.widget}): overlaps {where}.panels.{clash[0]} "
                    f"({clash[1].widget}) or leaves less than the minimum gap between their "
                    "joins; not shown",
                )
            )
            out[i] = None
            continue
        placed.append((i, geo, box))
    notes.sort(key=lambda note: note[0])  # stable: per panel, in the order they arose
    return Layout(out, [message for _, message in notes])
