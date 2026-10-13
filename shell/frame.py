"""Zone-reserving frame strips (GTK / Fabric windows). The frame itself is drawn by the shape
canvas (shell/canvas/canvas.py); these strips are invisible and take no input."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from fabric.widgets.box import Box
from fabric.widgets.wayland import WaylandWindow

from shell.canvas.style import reserved_px
from shell.config.models import Theme
from shell.gdk_util import monitor_index

EDGES = ("top", "bottom", "left", "right")

# Below the canvas and the panels (both on "top"): an invisible strip can then never cover a
# panel, whatever order KWin stacks same-layer surfaces in. Exclusive zones count on every
# layer (verified at Gate 1; the fallback, plan Task 11 A, moves them back to "top").
STRIP_LAYER = "bottom"

_STRIP_ANCHOR = {
    "top": "top left right",
    "bottom": "bottom left right",
    "left": "left top bottom",
    "right": "right top bottom",
}


def strip_window(edge: str) -> dict:
    """Layer-shell setup of one strip: reserves its size ("auto"; NOT "normal", which reserves
    1 px) and takes no input (pass_through: Fabric re-applies it after every allocate)."""
    return {
        "layer": STRIP_LAYER,
        "anchor": _STRIP_ANCHOR[edge],
        "exclusivity": "auto",
        "keyboard_mode": "none",
        "pass_through": True,
    }


def strip_size(edge: str, theme: Theme) -> tuple[int, int]:
    """Size request of one strip: the reserved width across, unconstrained along the edge."""
    t = reserved_px(theme)
    return (-1, t) if edge in ("top", "bottom") else (t, -1)


class FrameEdge(WaylandWindow):
    """One side of the frame: reserves thickness (+ the outer border) px so maximized windows
    stop at the outer edge of the frame."""

    def __init__(self, edge: str, monitor, theme: Theme, scope: str):
        self._edge = edge
        self._strip = Box(name="frame-strip", size=strip_size(edge, theme))
        # Fabric's `monitor` property is an int; a Gdk.Monitor object is silently ignored.
        super().__init__(
            **strip_window(edge),
            monitor=monitor_index(monitor),
            title=f"edge-shell-frame-{edge}",
            style_classes=[scope],
            child=self._strip,
            all_visible=True,
        )

    def apply_theme(self, theme: Theme) -> None:
        """Restyle in place: resize the strip (and so the exclusive zone) without a rebuild."""
        self._strip.set_size_request(*strip_size(self._edge, theme))
