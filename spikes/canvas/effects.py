"""Final effects driven by the one union outline path: RGBA border and uniform shadow.

Controls (the user's decision): border = (width px, RGBA); shadow = (elevation %, RGBA) where
the colour's alpha is the strength. No offset, no top/bottom bias, no second layer.
"""

from __future__ import annotations

import functools
import math
import re

import cairo

from spikes.canvas.outline import Panel, fill_mass, outline_path

RGBA = tuple[float, float, float, float]

MAX_REACH_PX = 48  # shadow reach at elevation 100 % (logical px); placeholder, user to calibrate


def reach_px(elevation_pct: float) -> int:
    """Shadow reach in px for an elevation percentage; out-of-range values are clamped to 0..100."""
    pct = min(100.0, max(0.0, float(elevation_pct)))
    return round(MAX_REACH_PX * pct / 100)


_HEX_RE = re.compile(r"#([0-9a-fA-F]{6})([0-9a-fA-F]{2})?")


def parse_rgba_hex(text: str) -> RGBA:
    """'#rrggbbaa' or '#rrggbb' (alpha 1.0) -> (r, g, b, a) floats in 0..1. Else ValueError."""
    m = _HEX_RE.fullmatch(text) if isinstance(text, str) else None
    if m is None:
        raise ValueError(f"invalid colour {text!r}: expected #rrggbb or #rrggbbaa")
    digits = m.group(1) + (m.group(2) or "ff")
    r, g, b, a = (int(digits[i : i + 2], 16) / 255 for i in range(0, 8, 2))
    return r, g, b, a


def _mul_un8(a: int, b: int) -> int:
    t = a * b + 0x80
    return (t + (t >> 8)) >> 8


def _over(d: int, a: int) -> int:
    return a + _mul_un8(d, 255 - a)


@functools.lru_cache(maxsize=64)
def shadow_levels(elevation: int, alpha: float) -> tuple[float, ...]:
    """Per-layer alphas for the uniform shadow; index i-1 is the layer stroked at half-width i.

    A pixel at distance k is covered by layers i > k, so the cumulative alpha there is
    C(k) = 1 - prod_{i>k}(1 - a_i). The target is the half-Gaussian tail
    C(k) = alpha * 0.5 * erfc(k / (sigma * sqrt(2))), sigma = elevation / 2.5, cut to 0 at
    k = elevation (half the strength at the edge: the other half lies under the mass).

    A stack of 32-48 strokes whose float alphas are 0.1-1.5 levels each loses most of the tail to
    cairo's 8-bit rounding (measured: up to 15/255 low). So simulate pixman's UN8 compositing and
    pick the integer alpha of each layer (largest first) whose result lands nearest the target
    level; layers whose increment is below one level become 0 or 1, which dithers the tail.
    """
    if elevation < 1:
        raise ValueError("elevation must be >= 1")
    sigma = elevation / 2.5
    cum = [alpha * 0.5 * math.erfc(k / (sigma * math.sqrt(2))) for k in range(elevation + 1)]
    cum[elevation] = 0.0
    out = [0.0] * elevation
    d = 0
    for i in range(elevation, 0, -1):
        t = round(255 * cum[i - 1])
        a = min(range(256), key=lambda a, d=d, t=t: (abs(_over(d, a) - t), a))
        out[i - 1] = a / 255
        d = _over(d, a)
    return tuple(out)


def draw_border(
    cr: cairo.Context,
    w: int,
    h: int,
    T: int,
    R: int,
    panels: list[Panel],
    width: float,
    rgba: RGBA,
) -> None:
    """RGBA border `width` px thick on the mass side of the outline; nothing on the desktop side.

    The outline is stroked at 2*width and clipped to the mass side (even-odd with the screen
    rectangle), so a translucent colour blends once over the mass and never reaches the desktop.
    """
    cr.save()
    cr.new_path()
    cr.rectangle(0, 0, w, h)
    outline_path(cr, w, h, T, R, panels)
    cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    cr.clip()
    cr.new_path()
    outline_path(cr, w, h, T, R, panels)
    cr.set_line_width(2 * width)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.set_source_rgba(*rgba)
    cr.stroke()
    cr.restore()


def draw_shadow_uniform(
    cr: cairo.Context,
    w: int,
    h: int,
    T: int,
    R: int,
    panels: list[Panel],
    elevation_pct: float,
    rgba: RGBA,
) -> None:
    """Uniform shadow of the mass: reach = reach_px(elevation_pct), strength = rgba alpha."""
    draw_shadow_reach(cr, w, h, T, R, panels, reach_px(elevation_pct), rgba)


def draw_shadow_reach(
    cr: cairo.Context,
    w: int,
    h: int,
    T: int,
    R: int,
    panels: list[Panel],
    reach: int,
    rgba: RGBA,
) -> None:
    """Uniform shadow with an absolute `reach` in px (the primitive under draw_shadow_uniform).

    Drawn on the desktop side only: one 1 px-step stroke per layer of the outline, widest first,
    clipped to the desktop region (so nothing is drawn under the mass). The caller draws the
    mass over it.
    """
    r, g, b, a = rgba
    if reach < 1 or a <= 0:
        return
    levels = shadow_levels(reach, a)
    cr.save()
    cr.new_path()
    outline_path(cr, w, h, T, R, panels)
    cr.clip()
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    for i in range(reach, 0, -1):
        cr.new_path()
        outline_path(cr, w, h, T, R, panels)
        cr.set_line_width(2 * i)
        cr.set_source_rgba(r, g, b, levels[i - 1])
        cr.stroke()
    cr.restore()


def draw_scene(
    cr: cairo.Context,
    w: int,
    h: int,
    T: int,
    R: int,
    panels: list[Panel],
    mass_rgba: RGBA,
    border: tuple[float, RGBA] | None = None,
    shadow: tuple[float, RGBA] | None = None,
    clip: tuple[int, int, int, int] | None = None,
) -> None:
    """Clear, then draw shadow (under), mass, border (over).

    `border` = (width, rgba), `shadow` = (elevation_pct, rgba). With `clip` = (x, y, w, h) only that
    rectangle is cleared and redrawn (damaged-region redraw on a retained transparent surface);
    pixels outside it are untouched. Without it the whole surface is cleared first.
    """
    # Draw into a group sized to the rectangle and SOURCE-paint it back: clipping the strokes
    # directly would round edge pixels differently from a full redraw (off by 1/255).
    cr.save()
    cr.rectangle(*(clip if clip is not None else (0, 0, w, h)))
    cr.clip()
    cr.push_group()
    if shadow is not None:
        draw_shadow_uniform(cr, w, h, T, R, panels, shadow[0], shadow[1])
    fill_mass(cr, w, h, T, R, panels, mass_rgba)
    if border is not None:
        draw_border(cr, w, h, T, R, panels, border[0], border[1])
    cr.pop_group_to_source()
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.paint()
    cr.restore()
