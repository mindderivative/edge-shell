"""Frame strips and rounded screen corners (GTK / Fabric windows)."""

from __future__ import annotations

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from fabric.widgets.box import Box
from fabric.widgets.wayland import WaylandWindow
from gi.repository import Gtk, GtkLayerShell

from shell.config.models import Theme
from shell.draw import draw_screen_corner
from shell.theme import hex_to_rgba

EDGES = ("top", "bottom", "left", "right")
CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")

_STRIP_ANCHOR = {
    "top": "top left right",
    "bottom": "bottom left right",
    "left": "left top bottom",
    "right": "right top bottom",
}


class FrameEdge(WaylandWindow):
    """One side of the frame. The only surface that reserves screen space."""

    def __init__(self, edge: str, monitor, theme: Theme, scope: str):
        horizontal = edge in ("top", "bottom")
        t = theme.thickness
        super().__init__(
            layer="top",
            anchor=_STRIP_ANCHOR[edge],
            exclusivity="auto",  # NOT "normal": that reserves 1 px
            keyboard_mode="none",
            monitor=monitor,
            title=f"edge-shell-frame-{edge}",
            style_classes=[scope],
            child=Box(name="frame-strip", size=(-1, t) if horizontal else (t, -1)),
            all_visible=True,
        )


class ScreenCorner(WaylandWindow):
    """The rounded desktop corner: click-through, placed just inside the frame."""

    def __init__(self, corner: str, monitor, theme: Theme, scope: str):
        vertical, horizontal = corner.split("-")
        t, r = theme.thickness, theme.radius
        area = Gtk.DrawingArea()
        area.set_size_request(r, r)
        super().__init__(
            layer="top",
            anchor=f"{vertical} {horizontal}",
            margin=f"{t}px {t}px {t}px {t}px",
            exclusivity="none",
            pass_through=True,
            monitor=monitor,
            title=f"edge-shell-corner-{corner}",
            style_classes=[scope],
            child=area,
            all_visible=True,
        )
        GtkLayerShell.set_exclusive_zone(self, -1)  # place by margin, not by other zones
        self._corner = corner
        self._radius = r
        self._rgba = hex_to_rgba(theme.frame)
        self._area = area
        area.connect("draw", self._on_draw)

    def set_theme(self, theme: Theme) -> None:
        self._rgba = hex_to_rgba(theme.frame)
        self._area.queue_draw()

    def _on_draw(self, _area, cr) -> bool:
        cr.save()
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.restore()
        draw_screen_corner(cr, self._corner, self._radius, self._rgba)
        return False
