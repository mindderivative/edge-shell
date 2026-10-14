"""Everything the shape canvas window does except being a window. Pure: the GTK window passes
an `invalidate` callback (queue_draw_area / queue_draw) and calls draw() from its draw handler,
and shell.canvas.simulate drives the same object headlessly."""

from __future__ import annotations

import time
from collections.abc import Callable, Hashable
from typing import Protocol

import cairo

from shell.canvas.effects import draw_scene
from shell.canvas.scene import Box, Scene, Shape
from shell.canvas.style import CanvasStyle

Rect = tuple[int, int, int, int]  # (x, y, width, height)


class Recorder(Protocol):
    """Optional measurement hook (shell.canvas.stats.StatsRecorder implements it)."""

    def on_tick(self, key: Hashable, depth: float) -> None: ...

    def on_draw(self, duration_ms: float, full: bool) -> None: ...


class CanvasPainter:
    def __init__(self, scene: Scene, style: CanvasStyle, invalidate: Callable[[Box | None], None]):
        """`invalidate(box)` schedules a redraw of `box`; `invalidate(None)` of everything."""
        self.scene = scene
        self.style = style
        self.recorder: Recorder | None = None
        self._invalidate = invalidate
        self._needs_full = True  # the first draw is always a full redraw
        scene.set_pad(style.pad)

    @property
    def needs_full(self) -> bool:
        """True until the next draw() when a full redraw is pending (start, theme, resize)."""
        return self._needs_full

    # ---- changes ------------------------------------------------------------------------
    def set_style(self, style: CanvasStyle) -> None:
        """Theme change (colour, border, shadow): new pad, full redraw."""
        self.style = style
        self.scene.set_pad(style.pad)
        self._full()

    def resize(self, width: int, height: int) -> bool:
        """Adopt the real surface size; True (and a full redraw) when it changed."""
        if (width, height) == (self.scene.width, self.scene.height):
            return False
        self.scene.resize(width, height)
        self._full()
        return True

    def add_panel(self, key: Hashable, shape: Shape) -> None:
        self._damage(self.scene.add_panel(key, shape))

    def remove_panel(self, key: Hashable) -> None:
        self._damage(self.scene.remove_panel(key))

    def set_depth(self, key: Hashable, d: float) -> None:
        """Called from a panel's Tween on every frame; redraws only the damaged box."""
        box = self.scene.set_depth(key, d)
        if box is not None and self.recorder is not None:  # count only real depth changes
            self.recorder.on_tick(key, d)
        self._damage(box)

    # ---- drawing ------------------------------------------------------------------------
    def draw(self, cr: cairo.Context, clip: Rect | None) -> None:
        """Paint into `cr`. `clip` is the bounding rectangle of the region being redrawn (GTK:
        Gdk.cairo_get_clip_rectangle); None, or a pending full redraw, repaints everything."""
        full = self._needs_full or clip is None
        self._needs_full = False
        start = time.perf_counter()
        s, st = self.scene, self.style
        draw_scene(
            cr,
            s.width,
            s.height,
            s.thickness,
            s.radius,
            s.outline_panels(),
            st.mass,
            border=st.border,
            shadow=st.shadow,
            clip=None if full else clip,
            corners=s.outline_corners(),
        )
        if self.recorder is not None:
            self.recorder.on_draw((time.perf_counter() - start) * 1000, full)

    def _full(self) -> None:
        self._needs_full = True
        self._invalidate(None)

    def _damage(self, box: Box | None) -> None:
        if box is not None and box[2] > box[0] and box[3] > box[1]:
            self._invalidate(box)
