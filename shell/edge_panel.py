"""EdgePanel: a layer-shell window that grows out of the frame and fuses with it."""

from __future__ import annotations

import cairo
import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.overlay import Overlay
from fabric.widgets.wayland import WaylandWindow
from gi.repository import Gdk, Gtk, GtkLayerShell

from shell import geometry, panel_state
from shell.anim import Tween
from shell.config.models import Theme
from shell.draw import draw_panel
from shell.gdk_util import monitor_index
from shell.panel_spec import PanelGeometry
from shell.theme import hex_to_rgba

HANDLE_DEPTH = 14  # handle size across the depth axis
HANDLE_LENGTH = 44  # handle size along the edge


class EdgePanel(WaylandWindow):
    """Base class for panels. Subclasses implement build_content()."""

    wants_keyboard = False

    def __init__(self, spec: PanelGeometry, theme: Theme, monitor, index: int, scope: str):
        t, r = theme.thickness, theme.radius
        mon = monitor.get_geometry()
        extent = mon.width if geometry.is_horizontal(spec.edge) else mon.height
        anchor, margin = geometry.anchor_and_margin(
            spec.edge, spec.pos, spec.length + 2 * r, r, extent
        )
        super().__init__(
            layer="top",
            anchor=anchor,
            margin=margin,
            exclusivity="none",
            keyboard_mode="on-demand" if self.wants_keyboard else "none",
            # Fabric's monitor property is an int: a Gdk.Monitor object is silently ignored
            monitor=monitor_index(monitor),
            title=f"edge-shell-{spec.label}-{index}",
            name="edge-panel",
            style_classes=[scope],
            visible=False,
        )
        # Fabric's "none" sets zone 0, which makes KWin push us clear of the frame.
        # -1 lets the panel overlap the frame strip so the two fuse.
        GtkLayerShell.set_exclusive_zone(self, -1)

        self.spec = spec
        self._theme = theme
        self._extended = spec.state == "extended"
        self._hovered = False
        self._d = 0.0
        self._last_rect: tuple[int, int, int, int] | None = None
        self._press: tuple[float, float] | None = None  # drag state (used from Task 17)
        self._press_depth = 0.0
        self._dragging = False
        self._suppress_click = False

        self._canvas = Gtk.DrawingArea()
        self._canvas.connect("draw", self._on_draw)
        self._content = self.build_content()
        self._handle = self._build_handle()
        self.add(Overlay(child=self._canvas, overlays=[self._content, self._handle]))

        # Allocated once at full size; animation never resizes the layer surface.
        w, h = geometry.surface_size(spec.edge, spec.length, spec.depth, t, r)
        self.set_size_request(w, h)
        self._place_content()

        self.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.connect("enter-notify-event", self._on_enter)
        self.connect("leave-notify-event", self._on_leave)

        self._tween = Tween(self, self._apply_depth, theme.duration_ms)
        self._fade = Tween(self, self._content.set_opacity, 170, delay_ms=110)
        self.show_all()
        self._tween.jump_to(spec.depth if self._extended else 0)
        self._fade.jump_to(1.0 if self._extended else 0.0)
        self._sync_handle()

    # ---- override in subclasses ------------------------------------------------
    def build_content(self) -> Gtk.Widget:
        return Box()

    # ---- public ----------------------------------------------------------------
    def toggle(self, *_) -> None:
        self._extended = not self._extended
        self._hovered = False
        self._retarget()

    def set_state(self, state: str) -> None:
        self._extended = state == "extended"
        self._hovered = False
        self._retarget()

    def apply_theme(self, theme: Theme) -> None:
        """Colors only; geometry changes rebuild the panel instead."""
        self._theme = theme
        self._canvas.queue_draw()

    # ---- state -----------------------------------------------------------------
    def _on_enter(self, *_) -> None:
        self._hovered = True
        self._retarget()

    def _on_leave(self, _widget, event) -> None:
        if event.detail == Gdk.NotifyType.INFERIOR:  # pointer moved onto a child widget
            return
        self._hovered = False
        self._retarget()

    def _retarget(self) -> None:
        target = panel_state.target_depth(
            self._extended, self._hovered, self.spec.depth, self._theme.peek
        )
        self._sync_handle()
        self._tween.animate_to(target)
        if self._extended:
            self._fade.animate_to(1.0)  # fades in over the last part of the reveal
        else:
            self._fade.jump_to(0.0)  # fades out at once so text never clips mid-slide

    def _sync_handle(self) -> None:
        self._content.set_sensitive(self._extended)
        name = ("Collapse " if self._extended else "Expand ") + self.spec.label
        self._handle.set_tooltip_text(name)
        self._handle.get_accessible().set_name(name)

    def _on_clicked(self, *_) -> None:
        if self._suppress_click:  # the release that ended a drag
            self._suppress_click = False
            return
        self.toggle()

    # ---- per frame -------------------------------------------------------------
    def _apply_depth(self, d: float) -> None:
        self._d = d
        self._place_handle(d)
        self._update_input_region(d)
        self._canvas.queue_draw()

    def _on_draw(self, _area, cr) -> bool:
        cr.save()
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.restore()
        t = self._theme
        draw_panel(
            cr,
            self.spec.edge,
            self.spec.length,
            self.spec.depth,
            self._d,
            t.thickness,
            t.radius,
            hex_to_rgba(t.frame),
        )
        return False

    def _update_input_region(self, d: float) -> None:
        # Only the body (plus an invisible hover zone while collapsed) takes input.
        t = self._theme
        rect = geometry.input_rect(
            self.spec.edge,
            self.spec.length,
            self.spec.depth,
            d,
            t.thickness,
            t.radius,
            t.hover_zone,
        )
        if rect == self._last_rect:
            return
        self._last_rect = rect
        self.input_shape_combine_region(cairo.Region(cairo.RectangleInt(*rect)))

    # ---- layout ----------------------------------------------------------------
    def _build_handle(self) -> Button:
        vertical = self.spec.edge in ("left", "right")
        dots = Box(
            orientation="v" if vertical else "h",
            spacing=3,
            h_align="center",
            v_align="center",
            children=[Box(style_classes="handle-dot") for _ in range(3)],
        )
        size = (HANDLE_DEPTH, HANDLE_LENGTH) if vertical else (HANDLE_LENGTH, HANDLE_DEPTH)
        handle = Button(name="handle", child=dots, size=size, on_clicked=self._on_clicked)
        return handle

    def _place_handle(self, d: float) -> None:
        inset = max(0, int(self._theme.thickness + d - HANDLE_DEPTH))  # rides the inner edge
        h, edge = self._handle, self.spec.edge
        if edge == "bottom":
            h.set_halign(Gtk.Align.CENTER)
            h.set_valign(Gtk.Align.END)
            h.set_margin_bottom(inset)
        elif edge == "top":
            h.set_halign(Gtk.Align.CENTER)
            h.set_valign(Gtk.Align.START)
            h.set_margin_top(inset)
        elif edge == "left":
            h.set_halign(Gtk.Align.START)
            h.set_valign(Gtk.Align.CENTER)
            h.set_margin_start(inset)
        else:
            h.set_halign(Gtk.Align.END)
            h.set_valign(Gtk.Align.CENTER)
            h.set_margin_end(inset)

    def _place_content(self) -> None:
        c, t, s = self._content, self._theme.thickness, self.spec
        if s.edge in ("bottom", "top"):
            c.set_size_request(s.length, s.depth)
            c.set_halign(Gtk.Align.CENTER)
            if s.edge == "bottom":
                c.set_valign(Gtk.Align.END)
                c.set_margin_bottom(t)
            else:
                c.set_valign(Gtk.Align.START)
                c.set_margin_top(t)
        else:
            c.set_size_request(s.depth, s.length)
            c.set_valign(Gtk.Align.CENTER)
            if s.edge == "left":
                c.set_halign(Gtk.Align.START)
                c.set_margin_start(t)
            else:
                c.set_halign(Gtk.Align.END)
                c.set_margin_end(t)
