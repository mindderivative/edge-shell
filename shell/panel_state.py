"""Click / drag / hover maths for panels. Pure."""

from __future__ import annotations

CLICK_THRESHOLD_PX = 4

# +1 when moving the pointer in the +x / +y direction deepens the panel.
_SIGN = {"bottom": -1, "top": 1, "right": -1, "left": 1}


def target_depth(extended: bool, hovered: bool, depth: int, peek: int) -> float:
    if extended:
        return float(depth)
    if hovered:
        return float(min(peek, depth))
    return 0.0


def drag_depth(start: float, delta: float, depth: int, edge: str) -> float:
    """Depth after dragging `delta` px along the depth axis, clamped to [0, depth]."""
    return max(0.0, min(float(depth), start + _SIGN[edge] * delta))


def snap_extended(d: float, depth: int) -> bool:
    return d >= depth / 2


def is_click(moved_px: float) -> bool:
    return moved_px < CLICK_THRESHOLD_PX
