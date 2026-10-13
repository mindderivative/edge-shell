"""TEST-ONLY reference: the per-window renderers the core shell used before the shape canvas.

Kept verbatim from shell/draw.py so tests/test_canvas_outline.py can prove the union outline
draws the same shapes. Not imported by shell code."""

from __future__ import annotations

import math

import cairo

from shell import geometry

RGBA = tuple[float, float, float, float]


def draw_panel(
    cr: cairo.Context,
    edge: str,
    length: int,
    depth: int,
    d: float,
    thickness: int,
    radius: int,
    rgba: RGBA,
) -> None:
    """Draw the panel body plus both curved joins with one radius, at current depth `d`."""
    across = thickness + depth
    r = geometry.join_radius(d, radius)
    height = float(across)
    x0, y0 = float(radius), height - thickness - d  # body top-left (canonical)
    right = x0 + length

    cr.save()
    cr.transform(geometry.cairo_matrix(edge, across))
    cr.set_source_rgba(*rgba)

    # body: a rectangle whose two inner corners are rounded by r
    cr.new_path()
    cr.move_to(x0, height)
    cr.line_to(x0, y0 + r)
    if r > 0:
        cr.arc(x0 + r, y0 + r, r, math.pi, 1.5 * math.pi)
    cr.line_to(right - r, y0)
    if r > 0:
        cr.arc(right - r, y0 + r, r, 1.5 * math.pi, 2 * math.pi)
    cr.line_to(right, height)
    cr.close_path()
    cr.fill()

    if r >= 0.5:
        # joins: frame color outside a quarter circle, sitting on the frame's inner edge
        jy = height - thickness
        cr.new_path()
        cr.move_to(x0, jy)
        cr.line_to(x0, jy - r)
        cr.arc(x0 - r, jy - r, r, 0, 0.5 * math.pi)
        cr.close_path()
        cr.move_to(right, jy)
        cr.line_to(right, jy - r)
        cr.arc_negative(right + r, jy - r, r, math.pi, 0.5 * math.pi)
        cr.close_path()
        cr.fill()
    cr.restore()


def draw_screen_corner(cr: cairo.Context, corner: str, radius: int, rgba: RGBA) -> None:
    """Fill the radius x radius square outside a quarter circle (the rounded desktop corner)."""
    vertical, horizontal = corner.split("-")
    cx = radius if horizontal == "left" else 0
    cy = radius if vertical == "top" else 0
    cr.save()
    cr.set_source_rgba(*rgba)
    cr.rectangle(0, 0, radius, radius)
    cr.clip()
    cr.new_path()
    cr.rectangle(0, 0, radius, radius)
    cr.new_sub_path()
    cr.arc(cx, cy, radius, 0, 2 * math.pi)
    cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    cr.fill()
    cr.restore()
