"""The shape canvas window: one click-through, monitor-sized layer surface per monitor that
draws the frame, the screen corners and every panel shape as one outline, plus the border and
the shadow (spec 18, option B). A thin GTK shell over shell.canvas.painter.CanvasPainter."""

from __future__ import annotations

import logging
from collections.abc import Hashable

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from fabric.widgets.wayland import WaylandWindow
from gi.repository import Gdk, Gtk, GtkLayerShell

from shell.canvas.painter import CanvasPainter
from shell.canvas.scene import Box, Scene, Shape, box_to_rect
from shell.canvas.style import style_for
from shell.config.models import Theme
from shell.gdk_util import monitor_index

log = logging.getLogger(__name__)

# Layer-shell setup of the canvas. pass_through=True: Fabric's Window.do_size_allocate
# re-applies the EMPTY input region after every allocate (fabric/widgets/window.py), so the
# canvas never takes input. Same layer as the panels, created before them (MonitorShell).
CANVAS_WINDOW = {
    "layer": "top",
    "anchor": "top left bottom right",
    "exclusivity": "none",
    "keyboard_mode": "none",
    "pass_through": True,
}


class ShapeCanvas(WaylandWindow):
    def __init__(self, monitor, theme: Theme, scope: str):
        geo = monitor.get_geometry()
        if monitor.get_scale_factor() != 1:  # HiDPI is a later plan (reach x scale, clip area)
            log.warning(
                "scale %d is not supported yet: drawing at scale 1", monitor.get_scale_factor()
            )
        # Fabric's monitor property is an int: a Gdk.Monitor object is silently ignored.
        super().__init__(
            **CANVAS_WINDOW,
            monitor=monitor_index(monitor),
            title="edge-shell-canvas",
            name="shape-canvas",
            style_classes=[scope],
            visible=False,
        )
        # "none" alone is zone 0, which makes KWin shift us clear of other zones; -1 = cover all.
        GtkLayerShell.set_exclusive_zone(self, -1)
        self._monitor = monitor  # read live by _check_size
        self._size_warned = False
        self.area = Gtk.DrawingArea()
        self.add(self.area)
        scene = Scene(geo.width, geo.height, theme.thickness, theme.radius)
        self.painter = CanvasPainter(scene, style_for(theme), self._invalidate)
        self.area.connect("size-allocate", self._on_allocate)
        self.area.connect("draw", self._on_draw)
        self.show_all()

    # ---- used by MonitorShell -----------------------------------------------------------
    def set_theme(self, theme: Theme) -> None:
        """Colour / border / shadow change (a restyle): full redraw, no rebuild."""
        self.painter.set_style(style_for(theme))

    def add_panel(self, key: Hashable, shape: Shape) -> None:
        self.painter.add_panel(key, shape)

    def remove_panel(self, key: Hashable) -> None:
        self.painter.remove_panel(key)

    def set_depth(self, key: Hashable, d: float) -> None:
        self.painter.set_depth(key, d)

    # ---- GTK ----------------------------------------------------------------------------
    def _invalidate(self, box: Box | None) -> None:
        if box is None:
            self.area.queue_draw()
        else:
            self.area.queue_draw_area(*box_to_rect(box))

    def _on_allocate(self, _area, alloc) -> None:
        scene = self.painter.scene
        if (alloc.width, alloc.height) != (scene.width, scene.height):
            self._size_warned = False  # a new size: check it against the monitor again
        self.painter.resize(alloc.width, alloc.height)

    def _on_draw(self, _area, cr) -> bool:
        try:
            self._check_size()
            ok, rect = Gdk.cairo_get_clip_rectangle(cr)
            self.painter.draw(cr, (rect.x, rect.y, rect.width, rect.height) if ok else None)
        except Exception:  # never let a draw error escape into GTK's main loop
            log.exception("shape canvas draw failed")
        return False

    def _check_size(self) -> None:
        size = (self.painter.scene.width, self.painter.scene.height)
        g = self._monitor.get_geometry()  # live: the stored size would lag a resolution change
        if size != (g.width, g.height) and not self._size_warned:
            self._size_warned = True
            log.warning(
                "shape canvas is %dx%d but the monitor is %dx%d: panels may be misaligned",
                *size,
                g.width,
                g.height,
            )
