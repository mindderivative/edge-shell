"""CornerPanel: the content, handle and input window of one corner panel (spec 19).

The window is a plain RECTANGLE anchored in a screen corner (two layer-shell anchors, zero
margins), exactly the extended body: `along` x (T + depth) px. It is not an L: its surface,
body, content box and input region are rectangles; only the shape canvas's outline curves
where the body's free sides meet the two frame bands. Everything else (handle look,
interactions, hover peek, click, drag, fade, input-region upkeep, the delayed re-raise) is
EdgePanel's, running on the edge the panel opens from (`spec.edge`). The geometry comes from
the pure shell.corner."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from shell import corner as cn
from shell.config.models import Theme
from shell.edge_panel import EdgePanel
from shell.panel_spec import CornerGeometry


def place_at(widget: Gtk.Widget, x: int, y: int) -> None:
    """Put an overlay child at (x, y) of the surface: start-aligned, offset by its margins."""
    widget.set_halign(Gtk.Align.START)
    widget.set_valign(Gtk.Align.START)
    widget.set_margin_start(x)
    widget.set_margin_top(y)
    widget.set_margin_end(0)
    widget.set_margin_bottom(0)


class CornerPanel(EdgePanel):
    """Base class for corner widgets: register them with CornerDefaults (shell.registry)."""

    spec: CornerGeometry

    @classmethod
    def surface_layout(
        cls, spec: CornerGeometry, theme: Theme, monitor
    ) -> tuple[str, str, tuple[int, int]]:
        """Anchored to the corner's two screen edges, no margins, the extended body's size."""
        size = cn.surface_size(spec.edge, spec.along, spec.depth, theme.thickness)
        return cn.anchor(spec.corner), "0px 0px 0px 0px", size

    def natural_length(self) -> int:
        """Corner panels have no "content" length; MonitorShell never measures them."""
        return self.spec.length

    def _input_rects(self, d: float) -> list[tuple[int, int, int, int]]:
        t, s = self._theme, self.spec
        return cn.input_rects(
            s.corner,
            s.edge,
            s.along,
            s.depth,
            d,
            t.thickness,
            t.hover_zone,
            self._interaction,
            self._hit(),
            self._look.offset,
        )

    def _place_content(self) -> None:
        s = self.spec
        x, y, w, h = cn.content_rect(s.corner, s.edge, s.along, s.depth, self._theme.thickness)
        self._content.set_size_request(w, h)
        place_at(self._content, x, y)

    def _place_handle(self, d: float) -> None:
        s = self.spec
        x, y, _w, _h = cn.hit_rect(
            s.corner,
            s.edge,
            s.along,
            s.depth,
            d,
            self._theme.thickness,
            self._hit(),
            self._look.offset,
        )
        place_at(self._handle, x, y)
        self._handle_area.queue_draw()  # the shape moves with the body's inner edge
