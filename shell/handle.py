"""Panel handle (spec 15): what it looks like, where it sits and what takes input. Pure: no GTK.

The handle is drawn by the panel's own window (shell.edge_panel) with shell.handle_draw. Its
hit target is a separate, larger box than the drawn shape: at least HIT_ALONG x HIT_ACROSS px
(today's 44 x 14 handle button), growing with the shape size and the frame thickness.

Across the edge the shape's centre sits `centre_inset(thickness)` px inside the body's inner
edge (the band's inner edge while collapsed): 5 px from the default 10 px frame up, so a
thick frame keeps the handle hugging the edge the panel opens from (Gate B, thickness 64);
on a thinner frame `thickness / 2`, the middle of its band. It rides the inner edge and never
leaves the mass (the border is drawn outside the mass, so it never covers the handle).
Across it never uses more than `shape_room(thickness)` px: `band_room` of the frame, but no
more than at the default thickness, so the shape keeps BAND_CLEAR px clear of both band
edges and does not grow with a thicker frame.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from shell import geometry
from shell.config.models import Edge, Theme
from shell.panel_spec import HandleSpec, Interaction
from shell.theme import hex_to_rgba

RGBA = tuple[float, float, float, float]
Rect = tuple[int, int, int, int]  # x, y, width, height in panel-surface px

HIT_ALONG = 44  # minimum hit target along the edge
HIT_ACROSS = 14  # minimum hit target across the edge
HIT_PAD = 8  # the hit target reaches this far past the drawn shape along the edge
BAND_CLEAR = 2  # empty band px kept on each side of the shape (1 on a band under 8 px)
DEFAULT_THICKNESS = 10  # the theme's default frame; the handle's look is tuned for it
SHAPE_INSET = DEFAULT_THICKNESS / 2  # px from the body's inner edge to the shape's centre


@dataclass(frozen=True)
class HandleLook:
    """A panel's handle with every theme default applied. `shape` is never "auto"."""

    shape: str  # "dots" | "bar" | "chevron" | "none"
    size: int
    weight: int
    offset: int
    rgba: RGBA
    hover_rgba: RGBA


def auto_shape(interaction: Interaction) -> str:
    """The shape "auto" stands for: dots while click and drag are both on (today's look), a
    bar for drag only, a chevron for click only, dots for hover only, nothing when all three
    are off (the handle would promise an interaction the panel does not answer)."""
    if interaction.click and interaction.drag:
        return "dots"
    if interaction.drag:
        return "bar"
    if interaction.click:
        return "chevron"
    return "dots" if interaction.hover else "none"


def resolve_handle(spec: HandleSpec, interaction: Interaction, theme: Theme) -> HandleLook:
    """Every key from the panel's spec (entry over widget default), else the theme. A panel
    with every interaction off never draws the theme's shape: only a shape set on the entry
    or by the widget is drawn there (as decoration)."""
    style = theme.handle_style
    all_off = not (interaction.click or interaction.hover or interaction.drag)
    shape = spec.shape or ("none" if all_off else style.shape)
    return HandleLook(
        shape=auto_shape(interaction) if shape == "auto" else shape,
        size=spec.size or style.size,
        weight=spec.weight or style.weight,
        offset=spec.offset,
        rgba=hex_to_rgba(spec.color or theme.handle),
        hover_rgba=hex_to_rgba(spec.hover_color or theme.handle_hover),
    )


def is_highlighted(
    prelight: bool, focused: bool, hovered: bool, extended: bool, interaction: Interaction
) -> bool:
    """Draw in the hover colour: pointer on (or keyboard focus in) the handle of a panel that
    answers a click or a drag, or the panel peeking (spec 4: the dots brighten on peek)."""
    if (interaction.click or interaction.drag) and (prelight or focused):
        return True
    return interaction.hover and hovered and not extended


def handle_label(label: str, extended: bool, interaction: Interaction) -> str | None:
    """Tooltip and accessible name; None when the handle answers neither click nor drag."""
    verb = "Collapse" if extended else "Expand"
    if interaction.click:
        return f"{verb} {label}"
    if interaction.drag:
        return f"Drag to {verb.lower()} {label}"
    return None


def morph(d: float, depth: int) -> float:
    """Chevron morph: 0 collapsed, 1 fully extended."""
    if depth <= 0:
        return 0.0
    return min(1.0, max(0.0, d / depth))


def band_room(thickness: int) -> int:
    """Px the drawn shape may use across the frame band (draw_handle's `max_across`): the band
    minus BAND_CLEAR px on each side, or minus 1 px on each side when the band is under 8 px
    (so a thin frame still shows a handle). A bigger `size` or `weight` is clamped to it."""
    clear = BAND_CLEAR if thickness >= 8 else 1
    return max(0, thickness - 2 * clear)


def shape_room(thickness: int) -> int:
    """Px the drawn shape may use across (draw_handle's `max_across`): `band_room`, but never
    more than on the default frame (6 px), so a thicker frame does not make the shape taller.
    A thinner frame still shrinks it (4 px at 8 and 6, 3 at 5, the thinnest frame)."""
    return band_room(min(thickness, DEFAULT_THICKNESS))


def centre_inset(thickness: int) -> float:
    """Px from the body's inner edge to the shape's centre: SHAPE_INSET (5) from the default
    frame up, the middle of the band (`thickness / 2`) on a thinner one."""
    return min(thickness / 2, SHAPE_INSET)


def shape_offset(thickness: int, d: float) -> float:
    """Distance of the shape's centre from the screen edge at depth `d`: `centre_inset` px
    inside the body's inner edge, which is `thickness + d` px from the screen edge."""
    return thickness + d - centre_inset(thickness)


def hit_size(thickness: int, size: int, length: int) -> tuple[int, int]:
    """(along, across) px of the hit target; never longer than the body. Across it is today's
    14 px on any frame: the shape's room (at most 5 + 3 px from the body's inner edge) always
    fits in it, so a thick frame does not turn the whole band into the target; extended it
    never reaches further into the content than that."""
    along = min(length, max(HIT_ALONG, size + 2 * HIT_PAD))
    return along, HIT_ACROSS


def clamp_offset(offset: int, length: int, hit_along: int) -> int:
    """Keep the hit target (and so the shape) inside the body."""
    room = max(0, (length - hit_along) // 2)
    return max(-room, min(room, offset))


def along_margins(offset: int) -> tuple[int, int]:
    """(start, end) margins that move a centred widget by `offset` px along the edge. The
    caller passes an offset already clamped (Task 6's _place_handle clamps first)."""
    return max(0, 2 * offset), max(0, -2 * offset)


def hit_inset(thickness: int, d: float, hit_across: int) -> int:
    """Distance of the hit target from the screen edge: it rides the body's inner edge."""
    return max(0, int(thickness + d - hit_across))


def shape_centre(
    edge: Edge, width: float, height: float, thickness: int, d: float
) -> tuple[float, float]:
    """Centre of the drawn shape in the hit target's own coordinates (`width` x `height` is its
    allocation). Along the edge: the middle. Across: `shape_offset(thickness, d)` px from the
    screen edge (`centre_inset` px inside the body's inner edge)."""
    across = height if geometry.is_horizontal(edge) else width
    local = shape_offset(thickness, d) - hit_inset(thickness, d, round(across))
    if edge == "bottom":
        return width / 2, height - local
    if edge == "top":
        return width / 2, local
    if edge == "left":
        return local, height / 2
    return width - local, height / 2  # right


def hit_rect(
    edge: Edge,
    length: int,
    depth: int,
    d: float,
    thickness: int,
    radius: int,
    hit: tuple[int, int],
    offset: int,
) -> Rect:
    """The hit target in panel-surface px (the input region needs it when hover is off)."""
    # may be 1 px wider than the button when length - along is odd (conservative)
    along, across = length + 2 * radius, thickness + depth
    hit_along, hit_across = hit
    centre = radius + length / 2 + clamp_offset(offset, length, hit_along)
    u0, u1 = centre - hit_along / 2, centre + hit_along / 2
    inset = hit_inset(thickness, d, hit_across)
    v0, v1 = across - inset - hit_across, across - inset  # v: far side 0, screen edge `across`
    x1, y1 = geometry.to_canvas(edge, u0, v0, along, across)
    x2, y2 = geometry.to_canvas(edge, u1, v1, along, across)
    x, y = math.floor(min(x1, x2)), math.floor(min(y1, y2))
    return x, y, math.ceil(max(x1, x2)) - x, math.ceil(max(y1, y2)) - y


def input_rects(
    edge: Edge,
    length: int,
    depth: int,
    d: float,
    thickness: int,
    radius: int,
    hover_zone: int,
    interaction: Interaction,
    hit: tuple[int, int],
    offset: int,
) -> list[Rect]:
    """Where the panel takes input at depth `d`. With hover on: the body plus the invisible
    hover zone, as before (it holds the whole hit target while hover_zone >= hit across -
    thickness, 4 px at the defaults; a smaller zone leaves the target's inner part without
    input, as with today's 14 px button). With hover off: the body while it is
    out, plus the hit target when click or drag is on; nothing at all while collapsed with
    every interaction off (the strip is click-through)."""
    if interaction.hover:
        return [geometry.input_rect(edge, length, depth, d, thickness, radius, hover_zone)]
    rects = []
    if d > 0:
        rects.append(geometry.body_rect(edge, length, depth, d, thickness, radius))
    if interaction.click or interaction.drag:
        rects.append(hit_rect(edge, length, depth, d, thickness, radius, hit, offset))
    return rects
