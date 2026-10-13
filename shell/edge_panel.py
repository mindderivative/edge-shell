"""EdgePanel: the content, handle and input window of one panel. Its body is drawn by the
monitor's shape canvas; the panel reports its animated depth through `on_depth`."""

from __future__ import annotations

import math
from collections.abc import Callable

import cairo
import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.overlay import Overlay
from fabric.widgets.wayland import WaylandWindow
from gi.repository import Gdk, GLib, Gtk, GtkLayerShell

from shell import geometry, panel_state
from shell.anim import Tween
from shell.config.models import Theme
from shell.gdk_util import monitor_index
from shell.panel_layout import content_length
from shell.panel_spec import PanelGeometry

HANDLE_DEPTH = 14  # handle size across the depth axis
HANDLE_LENGTH = 44  # handle size along the edge


def _centre_view(adjustment) -> None:
    """Keep clipped content centred: equal parts cut off at both ends of the body."""
    adjustment.set_value(
        (adjustment.get_lower() + adjustment.get_upper() - adjustment.get_page_size()) / 2
    )


def clip_container(child: Gtk.Widget) -> Gtk.ScrolledWindow:
    """Show `child` at its natural size, centred, and clip it at the body edge. The layer
    surface cannot grow either way (Gtk.Overlay never measures its overlay children); without
    this, content longer than a shrunk body (spec 17: shrink to fit, max_length, a small
    percentage) would draw over the joins and the frame. No scrollbars, and wheel events never
    scroll the clipped content."""
    clip = Gtk.ScrolledWindow(
        name="panel-clip",
        hscrollbar_policy=Gtk.PolicyType.EXTERNAL,
        vscrollbar_policy=Gtk.PolicyType.EXTERNAL,
    )
    clip.set_hexpand(True)
    clip.set_vexpand(True)
    clip.add(child)
    for adjustment in (clip.get_hadjustment(), clip.get_vadjustment()):
        adjustment.connect("changed", _centre_view)  # the viewport re-configures on allocate
    clip.connect("scroll-event", lambda *_args: True)  # stop before the class handler scrolls
    return clip


class EdgePanel(WaylandWindow):
    """Base class for panels. Subclasses implement build_content()."""

    wants_keyboard = False

    def __init__(
        self,
        spec: PanelGeometry,
        theme: Theme,
        monitor,
        index: int,
        scope: str,
        on_depth: Callable[[float], None] | None = None,
    ):
        """`spec` is resolved by shell.panel_layout (exact pos and length in px); `on_depth(d)`
        is called on every animation frame with the current depth (MonitorShell forwards it to
        the canvas)."""
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
        self._on_depth = on_depth
        self._extended = spec.state == "extended"
        self._hovered = False
        self._d = 0.0
        self._last_rect: tuple[int, int, int, int] | None = None
        self._press: tuple[float, float] | None = None  # drag state
        self._press_depth = 0.0
        self._dragging = False
        self._suppress_click = False

        # Centring container: the widget's own content is centred inside the body box
        # that _place_content sizes and positions (a Box packs children at the start).
        inner = self.build_content()
        inner.set_hexpand(True)
        inner.set_vexpand(True)
        inner.set_halign(Gtk.Align.CENTER)
        inner.set_valign(Gtk.Align.CENTER)
        self._inner = inner
        self._content = Box(name="panel-content", children=[clip_container(inner)])
        self._handle = self._build_handle()
        # Transparent base: the body is painted by the shape canvas underneath this window.
        self.add(Overlay(child=Box(name="panel-base"), overlays=[self._content, self._handle]))

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

    def do_size_allocate(self, alloc) -> None:
        # Fabric's Window.do_size_allocate resets the input shape to the whole surface
        # (set_pass_through(False) -> input_shape_combine_region(None)) on EVERY allocate,
        # which would undo our region after the per-frame margin changes. Re-apply it here.
        WaylandWindow.do_size_allocate(self, alloc)
        if hasattr(self, "_theme") and hasattr(self, "_d"):
            self._last_rect = None
            self._update_input_region(self._d)

    def natural_length(self) -> int:
        """The body length the content needs along the edge (natural size plus padding): the
        measured input of a `length = "content"` panel (MonitorShell._measure)."""
        if geometry.is_horizontal(self.spec.edge):
            _minimum, natural = self._inner.get_preferred_width()
        else:
            _minimum, natural = self._inner.get_preferred_height()
        return content_length(natural)

    def raise_to_top(self) -> None:
        """Re-map the window so the compositor stacks it above the shape canvas.

        The frame strips are on the bottom layer; the canvas shares the panels' layer, so
        stacking follows map order, and a collapsed handle is hidden if the canvas lands
        above it. Hiding drops the
        pointer state, so hover is reset; a drag in progress is never interrupted.
        """
        if self._dragging:
            return
        self._hovered = False
        self.hide()
        self.show_all()
        self._last_rect = None
        self._update_input_region(self._d)

    def apply_theme(self, theme: Theme) -> None:
        """Colors only (CSS and the canvas repaint them); geometry changes rebuild the panel."""
        self._theme = theme

    # ---- state -----------------------------------------------------------------
    def _on_enter(self, *_) -> None:
        if self._dragging:  # the drag owns the depth until release
            return
        self._hovered = True
        self._retarget()

    def _on_leave(self, _widget, event) -> None:
        if self._dragging:
            return
        if event.detail == Gdk.NotifyType.INFERIOR:  # pointer moved onto a child widget
            return
        self._hovered = False
        self._retarget()

    def _retarget(self) -> None:
        if self._dragging:  # the drag owns the depth until release
            return
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
        if self._on_depth is not None:
            self._on_depth(d)  # the canvas redraws the body's damaged box

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
        handle.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        handle.connect("button-press-event", self._on_press)
        handle.connect("motion-notify-event", self._on_motion)
        handle.connect("button-release-event", self._on_release)
        return handle

    # ---- drag ------------------------------------------------------------------
    def _on_press(self, _widget, event) -> bool:
        if event.button != 1:
            return False
        self._press = (event.x_root, event.y_root)
        self._press_depth = self._d
        self._dragging = False
        self._suppress_click = False
        return False  # let the button track the press so a plain click still toggles

    def _on_motion(self, _widget, event) -> bool:
        if self._press is None:
            return False
        if not event.state & Gdk.ModifierType.BUTTON1_MASK:
            # primary button not held: the release was lost (grab break, remap)
            self._finish_drag()
            return False
        dx = event.x_root - self._press[0]
        dy = event.y_root - self._press[1]
        if not self._dragging:
            if panel_state.is_click(math.hypot(dx, dy)):
                return False
            self._dragging = True
            self._suppress_click = True
            self._hovered = False
        delta = dy if geometry.is_horizontal(self.spec.edge) else dx
        d = panel_state.drag_depth(self._press_depth, delta, self.spec.depth, self.spec.edge)
        self._tween.jump_to(d)  # follow the pointer exactly; cancels any running animation
        fraction = d / self.spec.depth
        self._fade.jump_to(max(0.0, (fraction - 0.6) / 0.4))
        return True

    def _on_release(self, _widget, event) -> bool:
        if event.button != 1:
            return False
        self._finish_drag()
        return False  # always let Gtk.Button finish its release (resets pressed state)

    def _finish_drag(self) -> None:
        """End a press: snap and settle if it was a drag. Also used when the release was lost."""
        was_dragging = self._dragging
        self._press = None
        self._dragging = False  # must be cleared before _retarget()
        if was_dragging:
            self._extended = panel_state.snap_extended(self._d, self.spec.depth)
            self._retarget()
            # the button's own release handler still runs and may emit "clicked", which
            # _on_clicked ignores; clear the flag once this event is fully dispatched
            GLib.idle_add(self._clear_suppress)

    def _clear_suppress(self) -> bool:
        self._suppress_click = False
        return GLib.SOURCE_REMOVE

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
