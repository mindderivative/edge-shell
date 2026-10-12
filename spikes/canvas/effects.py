"""Inner border and stacked-stroke shadow, both driven by the one union outline path."""

from __future__ import annotations

import functools
import math
from dataclasses import dataclass

import cairo

from spikes.canvas.outline import Panel, outline_path

RGB = tuple[float, float, float]


def _smoothstep(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def _per_layer(target: list[float]) -> list[float]:
    """Per-layer alphas whose cumulative 1 - prod(1 - a_i) gives target[k] at distance k."""
    return [1 - (1 - target[i - 1]) / (1 - target[i]) for i in range(1, len(target))]


def shadow_alphas(
    layers: int,
    opacity: float,
    profile: str = "gaussian",
    sigma: float | None = None,
    curve: str = "smoothstep",
) -> list[float]:
    """Per-layer alpha, index i-1 for the layer stroked at half-width i (covers distances < i).

    A pixel at distance k (0 <= k < layers) is covered by layers i > k, so the cumulative alpha
    there is C(k) = 1 - prod_{i>k}(1 - a_i). We pick the target C(k) and solve from the largest
    layer down: a_i = 1 - (1 - C(i-1)) / (1 - C(i)), with C(layers) = 0.

    "gaussian" (default): C(k) = opacity * 0.5 * erfc(k / (sigma * sqrt(2))), the shadow of a
    half-plane blurred with a Gaussian: HALF the peak at the edge (the other half lies under the
    shape), sigma defaults to layers / 2.5, cut to 0 at `layers`. `opacity` is the peak alpha.
    "legacy": C(k) = opacity * (1 - smoothstep(k / layers)), i.e. the FULL opacity at the edge
    (the tight dark halo that reads as an inner glow / bevel); kept only for comparison.
    """
    if profile == "legacy":
        if curve != "smoothstep":
            raise ValueError(f"unknown curve {curve!r}")
        target = [opacity * (1 - _smoothstep(k / layers)) for k in range(layers + 1)]
    elif profile == "gaussian":
        sg = sigma if sigma is not None else layers / 2.5
        target = [opacity * 0.5 * math.erfc(k / (sg * math.sqrt(2))) for k in range(layers + 1)]
        target[layers] = 0.0
    else:
        raise ValueError(f"unknown profile {profile!r}")
    return _per_layer(target)


def _mul_un8(a: int, b: int) -> int:
    t = a * b + 0x80
    return (t + (t >> 8)) >> 8


def _over(d: int, a: int) -> int:
    return a + _mul_un8(d, 255 - a)


def _dest_out(d: int, a: int) -> int:
    return _mul_un8(d, 255 - a)


@functools.lru_cache(maxsize=64)
def _levels(
    layers: int, opacity: float, profile: str, sigma: float | None, inside: bool
) -> tuple[float, ...]:
    """8-bit-aware per-layer alphas for the gaussian profile.

    A stack of 32-48 strokes whose float alphas are 0.1-1.5 levels each loses most of the tail to
    cairo's 8-bit rounding (measured: up to 15/255 low). So simulate pixman's UN8 compositing and
    pick the integer alpha of each layer (largest first) whose result lands nearest the target
    level; layers whose increment is below one level become 0 or 1, which dithers the tail.
    `inside`: DEST_OUT strokes over a solid `opacity` fill, targeting opacity - C(depth).
    """
    if profile != "gaussian":
        raise ValueError("8-bit levels are only defined for the gaussian profile")
    sg = sigma if sigma is not None else layers / 2.5
    cum = [opacity * 0.5 * math.erfc(k / (sg * math.sqrt(2))) for k in range(layers + 1)]
    cum[layers] = 0.0
    out = [0.0] * layers
    if inside:
        d = round(255 * opacity)
        for i in range(layers, 0, -1):
            t = round(255 * (opacity - cum[i - 1]))
            a = min(range(256), key=lambda a, d=d, t=t: (abs(_dest_out(d, a) - t), a))
            out[i - 1] = a / 255
            d = _dest_out(d, a)
    else:
        d = 0
        for i in range(layers, 0, -1):
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
    rgba: tuple[float, float, float, float],
) -> None:
    """Stroke the outline at 2*width, clipped to the mass side: `width` px inside, none outside."""
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


def draw_shadow(
    cr: cairo.Context,
    w: int,
    h: int,
    T: int,
    R: int,
    panels: list[Panel],
    layers: int,
    opacity: float,
    rgb: RGB,
    offset: tuple[float, float] = (0, 0),
    step: float = 1.0,
    profile: str = "gaussian",
    sigma: float | None = None,
) -> None:
    """Shadow of the mass (the shape the outline bounds), drawn under it, on the desktop only.

    `layers` is the reach in px (one 1 px stroke per layer). `step` is the line-width increment
    per layer (1.0 normally; 0.5 for finer bands): the covered distance is layers * step.
    The shadow shape is the outline translated by `offset`; everything is clipped to the
    UNtranslated desktop region, so what the offset pushes under the mass stays hidden.

    gaussian: outside the shifted shape the strokes give 0.5 * opacity * erfc(...) at distance k.
    The part of the desktop that the shift puts INSIDE the shifted shape (e.g. the strip under
    the top bar when offset has dy > 0) gets the mirrored ramp opacity - C(depth), built from a
    solid fill and DEST_OUT strokes in a group, so the two sides join continuously at 0.5 * opacity.
    """
    if profile == "gaussian":
        alphas = list(_levels(layers, opacity, profile, sigma, False))
    else:
        alphas = shadow_alphas(layers, opacity, profile, sigma)
    dx, dy = offset
    cr.save()
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    if profile == "legacy" or (dx == 0 and dy == 0):
        cr.new_path()
        outline_path(cr, w, h, T, R, panels)
        cr.clip()  # clip before the translate: only the stroke moves with the light offset
        cr.translate(dx, dy)
        _stroke_layers(cr, w, h, T, R, panels, layers, step, alphas, rgb)
        cr.restore()
        return
    big = (-w, -h, 3 * w, 3 * h)
    # outside the shifted shape = desktop side of the shifted line, inside the desktop region
    cr.save()
    cr.new_path()
    outline_path(cr, w, h, T, R, panels)
    cr.clip()
    cr.translate(dx, dy)
    cr.new_path()
    outline_path(cr, w, h, T, R, panels)
    cr.set_antialias(cairo.ANTIALIAS_NONE)  # hard seam: both sides equal 0.5 * opacity there, and
    cr.clip()  # an antialiased seam would not sum to 1 along curves (faint dotted arc)
    cr.set_antialias(cairo.ANTIALIAS_DEFAULT)
    _stroke_layers(cr, w, h, T, R, panels, layers, step, alphas, rgb)
    cr.restore()
    # inside the shifted shape = mass side of the shifted line, inside the desktop region
    cr.save()
    cr.new_path()
    outline_path(cr, w, h, T, R, panels)
    cr.clip()
    cr.translate(dx, dy)
    cr.new_path()
    cr.rectangle(*big)
    outline_path(cr, w, h, T, R, panels)
    cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    cr.set_antialias(cairo.ANTIALIAS_NONE)
    cr.clip()
    cr.set_antialias(cairo.ANTIALIAS_DEFAULT)
    cr.push_group()
    cr.set_source_rgba(*rgb, opacity)
    cr.paint()
    cr.set_operator(cairo.OPERATOR_DEST_OUT)
    unit = list(_levels(layers, opacity, profile, sigma, True))
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    _stroke_layers(cr, w, h, T, R, panels, layers, step, unit, rgb)
    cr.pop_group_to_source()
    cr.paint()
    cr.restore()
    cr.restore()


def _stroke_layers(
    cr: cairo.Context,
    w: int,
    h: int,
    T: int,
    R: int,
    panels: list[Panel],
    layers: int,
    step: float,
    alphas: list[float],
    rgb: RGB,
) -> None:
    for i in range(layers, 0, -1):
        cr.new_path()
        outline_path(cr, w, h, T, R, panels)
        cr.set_line_width(2 * i * step)
        cr.set_source_rgba(*rgb, alphas[i - 1])
        cr.stroke()


@dataclass(frozen=True)
class ShadowLayer:
    opacity: float
    reach: int
    offset: tuple[float, float] = (0, 0)
    sigma: float | None = None


def draw_shadow_stack(
    cr: cairo.Context,
    w: int,
    h: int,
    T: int,
    R: int,
    panels: list[Panel],
    layers: list[ShadowLayer],
    rgb: RGB = (0.0, 0.0, 0.0),
) -> None:
    """Draw several gaussian shadow layers in order (e.g. contact then ambient)."""
    for sl in layers:
        draw_shadow(cr, w, h, T, R, panels, sl.reach, sl.opacity, rgb, sl.offset, sigma=sl.sigma)


def draw_border_stack(
    cr: cairo.Context,
    w: int,
    h: int,
    T: int,
    R: int,
    panels: list[Panel],
    lines: list[tuple[float, tuple[float, float, float, float]]],
) -> None:
    """Several mass-side border lines, outermost (farthest from the desktop) first.

    `lines` = [(width, rgba), ...] listed from the INNER line (touching the desktop) outwards;
    each line is drawn as the ring between the accumulated widths, so a dual line is
    [(1, light), (1, dark)]: the light line adjacent to the desktop, the dark one outside it.
    """
    total = sum(wd for wd, _ in lines)
    acc = total
    for wd, rgba in reversed(lines):
        _ring(cr, w, h, T, R, panels, acc - wd, acc, rgba)
        acc -= wd


def _ring(cr, w, h, T, R, panels, inner, outer, rgba) -> None:
    """Fill the band between `inner` and `outer` px inside the mass edge."""
    cr.save()
    cr.new_path()
    cr.rectangle(0, 0, w, h)
    outline_path(cr, w, h, T, R, panels)
    cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    cr.clip()
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    if inner > 0:  # carve out the inner part so translucent colours do not overlap
        cr.push_group()
        cr.set_source_rgba(0, 0, 0, 1)
        cr.new_path()
        outline_path(cr, w, h, T, R, panels)
        cr.set_line_width(2 * outer)
        cr.stroke()
        cr.set_operator(cairo.OPERATOR_DEST_OUT)
        cr.new_path()
        outline_path(cr, w, h, T, R, panels)
        cr.set_line_width(2 * inner)
        cr.stroke()
        mask = cr.pop_group()
        cr.set_source_rgba(*rgba)
        cr.mask(mask)
    else:
        cr.set_source_rgba(*rgba)
        cr.new_path()
        outline_path(cr, w, h, T, R, panels)
        cr.set_line_width(2 * outer)
        cr.stroke()
    cr.restore()
