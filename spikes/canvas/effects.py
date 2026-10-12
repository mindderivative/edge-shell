"""Inner border and stacked-stroke shadow, both driven by the one union outline path."""

from __future__ import annotations

import cairo

from spikes.canvas.outline import Panel, outline_path

RGB = tuple[float, float, float]


def _smoothstep(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def shadow_alphas(layers: int, opacity: float, curve: str = "smoothstep") -> list[float]:
    """Per-layer alpha, index i-1 for the layer stroked at half-width i (covers distances < i).

    A pixel at distance k (0 <= k < layers) is covered by layers i > k, so the cumulative alpha
    there is C(k) = 1 - prod_{i>k}(1 - a_i). We want C(k) = opacity * (1 - smoothstep(k / layers)),
    which gives C(0) = opacity exactly and C(layers) = 0. Solving from the largest layer down:
    a_i = 1 - (1 - C(i-1)) / (1 - C(i)), with C(layers) = 0.
    """
    if curve != "smoothstep":
        raise ValueError(f"unknown curve {curve!r}")
    target = [opacity * (1 - _smoothstep(k / layers)) for k in range(layers + 1)]
    return [1 - (1 - target[i - 1]) / (1 - target[i]) for i in range(1, layers + 1)]


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
) -> None:
    """Stroke the outline under the shapes, largest first, clipped to the desktop region.

    `step` is the line-width increment in px per layer (1.0 normally; 0.5 for finer bands).
    The layer count stays `layers`; with step != 1 the covered distance is layers * step.
    """
    alphas = shadow_alphas(layers, opacity)
    cr.save()
    cr.new_path()
    outline_path(cr, w, h, T, R, panels)
    cr.clip()  # clip before the translate: only the stroke moves with the light offset
    cr.translate(*offset)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    for i in range(layers, 0, -1):
        cr.new_path()
        outline_path(cr, w, h, T, R, panels)
        cr.set_line_width(2 * i * step)
        cr.set_source_rgba(*rgb, alphas[i - 1])
        cr.stroke()
    cr.restore()
