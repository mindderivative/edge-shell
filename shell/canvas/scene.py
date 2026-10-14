"""Per-monitor scene model for the shape canvas: monitor size, T, R, every panel's shape and
current depth, and the damaged box a depth change invalidates. Pure: no GTK, no cairo."""

from __future__ import annotations

import math
from collections.abc import Hashable
from dataclasses import dataclass

from shell.canvas.outline import CornerSpan, Panel
from shell.config.models import Corner, Edge
from shell.corner import corner_box
from shell.panel_spec import CornerGeometry, PanelGeometry

Box = tuple[int, int, int, int]  # (x0, y0, x1, y1) in surface px; x1 / y1 exclusive


@dataclass(frozen=True)
class PanelShape:
    """A panel as the canvas draws it. `pos` is where the body starts along the edge, in px
    from the left (top/bottom edges) or from the top (left/right edges)."""

    edge: Edge
    pos: int
    length: int
    depth: int  # full depth past the frame


@dataclass(frozen=True)
class CornerShape:
    """A corner panel as the canvas draws it (spec 19): a rectangle in `corner`, `along` px
    along `edge` (the edge it opens from) from the screen corner, the adjacent frame band
    included, `depth` px past the band of `edge` when extended."""

    corner: Corner
    edge: Edge
    along: int
    depth: int


Shape = PanelShape | CornerShape


def shape_for(geo: PanelGeometry | CornerGeometry) -> Shape:
    """The canvas shape of a panel resolved by shell.panel_layout (PanelGeometry or
    CornerGeometry)."""
    if isinstance(geo, CornerGeometry):
        return CornerShape(geo.corner, geo.edge, geo.along, geo.depth)
    return PanelShape(geo.edge, geo.pos, geo.length, geo.depth)


def union_boxes(a: Box | None, b: Box | None) -> Box | None:
    """Bounding union; None means 'no box' and is neutral."""
    if a is None:
        return b
    if b is None:
        return a
    return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])


def box_to_rect(box: Box) -> tuple[int, int, int, int]:
    """(x0, y0, x1, y1) -> (x, y, width, height), as queue_draw_area and draw_scene take it."""
    return box[0], box[1], box[2] - box[0], box[3] - box[1]


def panel_box(
    shape: PanelShape, d: float, width: int, height: int, thickness: int, radius: int, pad: int
) -> Box:
    """Every pixel the panel can affect at depth `d`: the body plus both fillets (radius <= R),
    from the screen edge to the body's inner edge, grown by `pad`, clamped to the surface."""
    a0 = shape.pos - radius - pad
    a1 = shape.pos + shape.length + radius + pad
    across = thickness + math.ceil(max(0.0, d)) + pad
    if shape.edge == "top":
        box = (a0, 0, a1, across)
    elif shape.edge == "bottom":
        box = (a0, height - across, a1, height)
    elif shape.edge == "left":
        box = (0, a0, across, a1)
    else:  # right
        box = (width - across, a0, width, a1)
    return max(0, box[0]), max(0, box[1]), min(width, box[2]), min(height, box[3])


class Scene:
    """What one monitor's canvas draws. Panels are keyed by any hashable (MonitorShell uses ints).

    `pad` is how far the effects reach past the outline (CanvasStyle.pad); damage boxes grow by it.
    """

    def __init__(self, width: int, height: int, thickness: int, radius: int, pad: int = 0):
        self.width, self.height = width, height
        self.thickness, self.radius = thickness, radius
        self.pad = pad
        self._shapes: dict[Hashable, Shape] = {}
        self._depths: dict[Hashable, float] = {}

    # ---- whole-surface changes (callers redraw everything) ----------------------------
    def resize(self, width: int, height: int) -> None:
        self.width, self.height = width, height

    def set_pad(self, pad: int) -> None:
        self.pad = pad

    def full_box(self) -> Box:
        return 0, 0, self.width, self.height

    # ---- panels -------------------------------------------------------------------------
    def add_panel(self, key: Hashable, shape: Shape, depth: float = 0.0) -> Box:
        """Add (or replace) an edge or corner panel; returns the box to redraw."""
        old = self._box(key)
        self._shapes[key] = shape
        self._depths[key] = float(depth)
        return union_boxes(old, self._box(key))

    def remove_panel(self, key: Hashable) -> Box | None:
        """Forget a panel; returns the box it covered (None if it was unknown)."""
        box = self._box(key)
        self._shapes.pop(key, None)
        self._depths.pop(key, None)
        return box

    def set_depth(self, key: Hashable, d: float) -> Box | None:
        """Move a panel to depth `d`. Returns the damaged box (old and new footprint, grown by
        pad), or None when the key is unknown or the depth did not change."""
        if key not in self._shapes:
            return None
        d = float(d)
        if d == self._depths[key]:
            return None
        old = self._box(key)
        self._depths[key] = d
        return union_boxes(old, self._box(key))

    def depth(self, key: Hashable) -> float:
        return self._depths[key]

    def depths(self) -> dict[Hashable, float]:
        return dict(self._depths)

    def keys(self) -> list[Hashable]:
        return list(self._shapes)

    def outline_panels(self) -> list[Panel]:
        """Edge panels in the form shell.canvas.outline expects: (edge, pos, length, depth, d)."""
        return [
            (s.edge, s.pos, s.length, s.depth, self._depths[k])
            for k, s in self._shapes.items()
            if isinstance(s, PanelShape)
        ]

    def outline_corners(self) -> list[CornerSpan]:
        """Corner panels as shell.canvas.outline expects: (corner, edge, along, depth, d)."""
        return [
            (s.corner, s.edge, s.along, s.depth, self._depths[k])
            for k, s in self._shapes.items()
            if isinstance(s, CornerShape)
        ]

    def _box(self, key: Hashable) -> Box | None:
        shape = self._shapes.get(key)
        if shape is None:
            return None
        if isinstance(shape, CornerShape):
            return corner_box(
                shape.corner,
                shape.edge,
                shape.along,
                self._depths[key],
                self.width,
                self.height,
                self.thickness,
                self.radius,
                self.pad,
            )
        return panel_box(
            shape,
            self._depths[key],
            self.width,
            self.height,
            self.thickness,
            self.radius,
            self.pad,
        )
