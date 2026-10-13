"""Theme -> what the shape canvas paints (mass colour, border, shadow). Pure."""

from __future__ import annotations

import math
from dataclasses import dataclass

from shell.canvas.effects import RGBA, reach_px
from shell.config.models import Theme
from shell.theme import hex_to_rgba


@dataclass(frozen=True)
class CanvasStyle:
    mass: RGBA
    border: tuple[float, RGBA] | None  # (width px, rgba) or None when disabled
    shadow: tuple[float, RGBA] | None  # (elevation %, rgba) or None when disabled / 0 %

    @property
    def pad(self) -> int:
        """How far past a panel's box a depth change can alter pixels: reach + border width.

        The border is drawn outside the mass and the shadow is measured from its outer edge.
        """
        reach = reach_px(self.shadow[0]) if self.shadow is not None else 0
        width = math.ceil(self.border[0]) if self.border is not None else 0
        return reach + width


def reserved_px(theme: Theme) -> int:
    """Width of the zone each frame strip reserves: the frame thickness plus the border drawn
    outside it (so maximized windows stop at the outer border edge)."""
    border = theme.border
    return theme.thickness + (math.ceil(border.width) if border.enabled else 0)


def style_for(theme: Theme) -> CanvasStyle:
    border, shadow = theme.border, theme.shadow
    return CanvasStyle(
        mass=hex_to_rgba(theme.frame),
        border=(border.width, hex_to_rgba(border.color)) if border.enabled else None,
        shadow=(
            (shadow.elevation, hex_to_rgba(shadow.color))
            if shadow.enabled and shadow.elevation > 0
            else None
        ),
    )
