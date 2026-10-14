"""EdgePanel: the content, handle and input window of one panel. Its body is drawn by the
monitor's shape canvas; the panel reports its animated depth through `on_depth`."""

from __future__ import annotations

import logging
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
from shell import handle as hd
from shell.anim import Tween
from shell.config.models import Theme
from shell.gdk_util import monitor_index
from shell.handle_draw import draw_handle
from shell.panel_layout import content_length
from shell.panel_spec import (
    ALL_INTERACTIONS,
    THEME_HANDLE,
    HandleSpec,
    Interaction,
    PanelGeometry,
)

log = logging.getLogger(__name__)


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
    scroll the clipped content. The cross axis is clipped and centred too: content deeper than
    the body depth is cut, not overflowing."""
    clip = Gtk.ScrolledWindow(
        name="panel-clip",
        hscrollbar_policy=Gtk.PolicyType.EXTERNAL,
        vscrollbar_policy=Gtk.PolicyType.EXTERNAL,
    )
    clip.set_hexpand(True)
    clip.set_vexpand(True)
    clip.add(child)
    clip.set_can_focus(False)
    clip.set_kinetic_scrolling(False)
    for adjustment in (clip.get_hadjustment(), clip.get_vadjustment()):
        adjustment.connect("changed", _centre_view)  # the viewport re-configures on allocate
        # Any other scroll source snaps back too; set_value with an unchanged value emits
        # nothing, so this cannot recurse.
        adjustment.connect("value-changed", _centre_view)
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
        handle: HandleSpec = THEME_HANDLE,
        interaction: Interaction = ALL_INTERACTIONS,
        on_settings: Callable[[], None] | None = None,
    ):
        """`spec` is resolved by shell.panel_layout (exact pos and length in px); `on_depth(d)`
        is called on every animation frame with the current depth (MonitorShell forwards it to
        the canvas). `handle` and `interaction` come from the PanelRequest (spec 15); both can
        change later in place (set_handle). `on_settings()` is called on a right-click on the
        handle (EdgeShellApp.open_settings)."""
        # resolved before the window exists: a bad look fails without leaving a half-built window
        look = hd.resolve_handle(handle, interaction, theme)
        # a classmethod: the GObject is not initialised yet (CornerPanel overrides it)
        anchor, margin, size = type(self).surface_layout(spec, theme, monitor)
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
        self._on_settings = on_settings  # a right-click on the handle opens the settings
        self._handle_spec = handle
        self._interaction = interaction
        self._look = look
        self._extended = spec.state == "extended"
        self._hovered = False
        self._d = 0.0
        self._last_rect: tuple[tuple[int, int, int, int], ...] | None = None
        self._draw_failed = False  # a draw error is logged once per look
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
        self._size_handle()
        # Transparent base: the body is painted by the shape canvas underneath this window.
        self.add(Overlay(child=Box(name="panel-base"), overlays=[self._content, self._handle]))

        # Allocated once at full size; animation never resizes the layer surface.
        self.set_size_request(*size)
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

    @classmethod
    def surface_layout(
        cls, spec: PanelGeometry, theme: Theme, monitor
    ) -> tuple[str, str, tuple[int, int]]:
        """Layer-shell anchor, margin and the surface size (allocated once, fully extended).
        An edge panel: anchored to its edge, `(length + 2R) x (T + depth)`, moved along the
        edge by the margin (geometry.anchor_and_margin)."""
        t, r = theme.thickness, theme.radius
        mon = monitor.get_geometry()
        extent = mon.width if geometry.is_horizontal(spec.edge) else mon.height
        anchor, margin = geometry.anchor_and_margin(
            spec.edge, spec.pos, spec.length + 2 * r, r, extent
        )
        return anchor, margin, geometry.surface_size(spec.edge, spec.length, spec.depth, t, r)

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
        """A restyle: colours and the theme's handle style are redrawn in place (CSS and the
        canvas repaint the rest); geometry changes rebuild the panel."""
        self._theme = theme
        self._restyle_handle()

    def set_handle(self, handle: HandleSpec, interaction: Interaction) -> None:
        """A reload changed this panel's handle or interactions: update in place, no rebuild."""
        self._handle_spec, self._interaction = handle, interaction
        self._restyle_handle()
        if not interaction.click and self._handle.has_focus():
            self.set_focus(None)  # keyboard follows click: drop focus so the lit state clears
        if self._hovered and not interaction.hover:
            self._hovered = False
            self._retarget()  # drop a peek that hover no longer allows

    # ---- state -----------------------------------------------------------------
    def _on_enter(self, *_) -> None:
        if self._dragging:  # the drag owns the depth until release
            return
        if not self._interaction.hover:  # no peek; the handle still lights up on its own
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
        label = hd.handle_label(self.spec.label, self._extended, self._interaction)
        self._handle.set_tooltip_text(label)  # None: no tooltip
        self._handle.get_accessible().set_name(label or f"{self.spec.label} handle")
        self._handle.set_can_focus(self._interaction.click)  # keyboard follows click
        self._handle_area.queue_draw()  # the peek highlight may have changed

    def _restyle_handle(self) -> None:
        self._look = hd.resolve_handle(self._handle_spec, self._interaction, self._theme)
        self._draw_failed = False
        self._size_handle()
        self._sync_handle()
        self._place_handle(self._d)
        self._last_rect = None
        self._update_input_region(self._d)

    def _on_clicked(self, *_) -> None:
        if self._suppress_click:  # the release that ended a drag
            self._suppress_click = False
            return
        if not self._interaction.click:
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
        # The body (plus an invisible hover zone while collapsed, or only the handle's hit
        # target when hover is off) takes input: shell.handle.input_rects.
        rects = tuple(self._input_rects(d))
        if rects == self._last_rect:
            return
        self._last_rect = rects
        self.input_shape_combine_region(cairo.Region([cairo.RectangleInt(*r) for r in rects]))

    def _input_rects(self, d: float) -> list[tuple[int, int, int, int]]:
        """The input region at depth `d` in surface px (CornerPanel overrides it)."""
        t, s = self._theme, self.spec
        return hd.input_rects(
            s.edge,
            s.length,
            s.depth,
            d,
            t.thickness,
            t.radius,
            t.hover_zone,
            self._interaction,
            self._hit(),
            self._look.offset,
        )

    # ---- handle ----------------------------------------------------------------
    def _build_handle(self) -> Button:
        """The hit target: a Button (click, keyboard, accessible name) whose child draws the
        shape with cairo. Sized by _size_handle."""
        area = Gtk.DrawingArea()
        area.set_has_window(False)  # draws into the Button's window: no GdkWindow of its own
        area.connect("draw", self._on_handle_draw)
        self._handle_area = area
        handle = Button(name="handle", child=area, on_clicked=self._on_clicked)
        handle.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        handle.connect("button-press-event", self._on_press)
        handle.connect("motion-notify-event", self._on_motion)
        handle.connect("button-release-event", self._on_release)
        handle.connect("state-flags-changed", lambda *_args: area.queue_draw())  # hover, focus
        return handle

    def _hit(self) -> tuple[int, int]:
        return hd.hit_size(self._theme.thickness, self._look.size, self.spec.length)

    def _size_handle(self) -> None:
        along, across = self._hit()
        if geometry.is_horizontal(self.spec.edge):
            self._handle.set_size_request(along, across)
        else:
            self._handle.set_size_request(across, along)

    def _on_handle_draw(self, area, cr) -> bool:
        try:
            look, t = self._look, self._theme
            alloc = area.get_allocation()
            cx, cy = hd.shape_centre(
                self.spec.edge, alloc.width, alloc.height, t.thickness, self._d
            )
            flags = self._handle.get_state_flags()
            lit = hd.is_highlighted(
                bool(flags & Gtk.StateFlags.PRELIGHT),
                bool(flags & Gtk.StateFlags.FOCUSED),
                self._hovered,
                self._extended,
                self._interaction,
            )
            draw_handle(
                cr,
                look.shape,
                look.size,
                look.weight,
                look.hover_rgba if lit else look.rgba,
                hd.morph(self._d, self.spec.depth),
                self.spec.edge,
                cx,
                cy,
                hd.shape_room(t.thickness),  # band edges stay clear (decisions 5, 12)
            )
        except Exception:  # never let a draw error escape into GTK's main loop
            if not self._draw_failed:
                self._draw_failed = True
                log.exception("drawing the handle of %s failed", self.spec.label)
        return False

    # ---- drag ------------------------------------------------------------------
    def _on_press(self, _widget, event) -> bool:
        if event.button == 3 and self._on_settings is not None:
            self._on_settings()  # right-click: open the settings window (spec 13)
            return True
        if event.button != 1 or not self._interaction.drag:
            return False  # without drag a press is only ever a click
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
            if not self._interaction.drag:  # turned off while the press was held
                self._press = None
                return False
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
        along, across = self._hit()
        inset = hd.hit_inset(self._theme.thickness, d, across)  # rides the inner edge
        offset = hd.clamp_offset(self._look.offset, self.spec.length, along)
        before, after = hd.along_margins(offset)
        h, edge = self._handle, self.spec.edge
        if geometry.is_horizontal(edge):
            h.set_margin_start(before)
            h.set_margin_end(after)
        else:
            h.set_margin_top(before)
            h.set_margin_bottom(after)
        self._handle_area.queue_draw()  # the shape moves inside the box while it is clamped
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
