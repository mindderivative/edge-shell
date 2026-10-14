"""GTK rows for the settings form: one FieldRow per FieldSpec (settings.form). Thin: the
conversions live in settings.form, the values in settings.values."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, GObject, Gtk  # noqa: E402

from settings.form import (  # noqa: E402
    LENGTH_MODES,
    LENGTH_PERCENT,
    LENGTH_PX,
    FieldSpec,
    format_fonts,
    join_length,
    parse_fonts,
    rgba_to_hex,
    split_length,
)
from settings.values import FieldValue  # noqa: E402
from shell.theme import hex_to_rgba  # noqa: E402

DEBOUNCE_MS = 400  # spin buttons: one write per pause, not one per click of the arrows
DEBOUNCED = ("int", "length")
UNBOUNDED = (-100000, 100000)
FALLBACK_PX = 300  # px when switching a length to px with no px value known (never the 60 min)
FALLBACK_PERCENT = 50.0

Emit = Callable[[Any], None]


def wheel_scrolls_the_page(widget: Gtk.Widget) -> None:
    """A mouse wheel over a combo box or spin button scrolls the page instead of changing the
    value. Edits apply live: a stray scroll over DP-1's mode row would otherwise set it to
    `edge` (an Edge Shell frame over the Plasma panel), over thickness rebuild the monitor."""
    widget.connect("scroll-event", _pass_scroll)


def _pass_scroll(widget: Gtk.Widget, _event: Gdk.Event) -> bool:
    GObject.signal_stop_emission_by_name(widget, "scroll-event")  # skip the widget's handler
    return False  # not handled: the event goes on to the page's ScrolledWindow


class _Editor:
    """The value widget of a row: `widget`, `set(value)` (never emits), `emit` on user edits."""

    widget: Gtk.Widget

    def set(self, value: Any) -> None:
        raise NotImplementedError

    def commit(self) -> None:
        """Send a typed but not yet applied value (the window is closing)."""


class ColorEditor(_Editor):
    def __init__(self, emit: Emit):
        self.widget = Gtk.ColorButton(use_alpha=True)  # the ColorChooser property
        self.widget.connect("color-set", lambda b: emit(_hex_of(b.get_rgba())))

    def set(self, value: str) -> None:
        self.widget.set_rgba(Gdk.RGBA(*hex_to_rgba(value)))


def _hex_of(rgba: Gdk.RGBA) -> str:
    return rgba_to_hex(rgba.red, rgba.green, rgba.blue, rgba.alpha)


class IntEditor(_Editor):
    def __init__(self, spec: FieldSpec, emit: Emit):
        low = UNBOUNDED[0] if spec.minimum is None else spec.minimum
        high = UNBOUNDED[1] if spec.maximum is None else spec.maximum
        self.widget = Gtk.SpinButton.new_with_range(low, high, 1)
        self.widget.set_numeric(True)
        wheel_scrolls_the_page(self.widget)
        self.widget.connect("value-changed", lambda s: emit(s.get_value_as_int()))

    def set(self, value: int | None) -> None:
        # None (e.g. min_length not set) shows the lowest value; the source says "not set"
        self.widget.set_value(self.widget.get_range()[0] if value is None else value)


class BoolEditor(_Editor):
    def __init__(self, emit: Emit):
        self.widget = Gtk.Switch(halign=Gtk.Align.START)
        self.widget.connect("notify::active", lambda s, _p: emit(s.get_active()))

    def set(self, value: bool) -> None:
        self.widget.set_active(bool(value))


class ChoiceEditor(_Editor):
    def __init__(self, choices: tuple[str, ...], emit: Emit, labels: tuple[str, ...] = ()):
        self.widget = Gtk.ComboBoxText()
        for choice, label in zip(choices, labels or choices, strict=True):
            self.widget.append(choice, label)
        wheel_scrolls_the_page(self.widget)
        self.widget.connect("changed", self._on_changed, emit)

    @staticmethod
    def _on_changed(combo: Gtk.ComboBoxText, emit: Emit) -> None:
        if combo.get_active_id() is not None:
            emit(combo.get_active_id())

    def set(self, value: str) -> None:
        self.widget.set_active_id(value)


class FontsEditor(_Editor):
    def __init__(self, emit: Emit):
        self.widget = Gtk.Entry(width_chars=40)
        self._shown: list[str] = []
        self._emit = emit
        self.widget.connect("activate", lambda *_a: self.commit())
        self.widget.connect("focus-out-event", lambda *_a: self.commit() or False)

    def commit(self) -> None:
        fonts = parse_fonts(self.widget.get_text())
        if fonts != self._shown:
            self._shown = fonts
            self._emit(fonts)

    def set(self, value: list[str]) -> None:
        self._shown = list(value)
        self.widget.set_text(format_fonts(value))


class LengthEditor(_Editor):
    """A mode (px, fill, content, percent) and a number for px and percent. Switching to px or
    percent uses the last number that mode had (shown or typed), else `fallback_px` (the
    widget's default length, set by FieldRow) or FALLBACK_PERCENT: never the spin's minimum."""

    def __init__(self, emit: Emit):
        self.widget = Gtk.Box(spacing=6)
        self.mode = Gtk.ComboBoxText()
        for mode in LENGTH_MODES:
            self.mode.append(mode, mode)
        self.number = Gtk.SpinButton.new_with_range(*LENGTH_PX, 1)
        self.widget.pack_start(self.mode, False, False, 0)
        self.widget.pack_start(self.number, False, False, 0)
        wheel_scrolls_the_page(self.mode)
        wheel_scrolls_the_page(self.number)
        self.fallback_px = FALLBACK_PX
        self._numbers: dict[str, float] = {}  # the last px / percent number of this row
        self._emit = emit
        self._quiet = False
        self.mode.connect("changed", self._on_mode)
        self.number.connect("value-changed", lambda *_a: self._send())

    def _range(self, mode: str) -> None:
        percent = mode == "percent"
        self.number.set_digits(1 if percent else 0)
        self.number.set_increments(0.5 if percent else 1, 10)
        self.number.set_range(*(LENGTH_PERCENT if percent else LENGTH_PX))
        self.number.set_sensitive(mode in ("px", "percent"))

    def _on_mode(self, _combo) -> None:
        if self._quiet:
            return
        mode = self.mode.get_active_id()
        self._quiet = True
        self._range(mode)  # may clamp the number: no emit for that
        if mode in ("px", "percent"):
            fallback = self.fallback_px if mode == "px" else FALLBACK_PERCENT
            self.number.set_value(self._numbers.get(mode, fallback))
        self._quiet = False
        self._send()

    def _send(self) -> None:
        if self._quiet:
            return
        mode = self.mode.get_active_id()
        if mode in ("px", "percent"):
            self._numbers[mode] = self.number.get_value()
        self._emit(join_length(mode, self.number.get_value()))

    def set(self, value: int | str) -> None:
        mode, number = split_length(value)
        self._quiet = True
        self.mode.set_active_id(mode)
        self._range(mode)
        if number is not None:
            self.number.set_value(number)
            self._numbers[mode] = number
        self._quiet = False


class DeprecatedEditor(_Editor):
    """`pos`: shown, never edited here (the row's reset button removes it)."""

    def __init__(self):
        self.widget = Gtk.Label(xalign=0)

    def set(self, value: Any) -> None:
        self.widget.set_text("not set" if value is None else str(value))


def make_editor(spec: FieldSpec, emit: Emit) -> _Editor:
    if spec.kind == "color":
        return ColorEditor(emit)
    if spec.kind == "int":
        return IntEditor(spec, emit)
    if spec.kind == "bool":
        return BoolEditor(emit)
    if spec.kind in ("enum", "widget"):
        return ChoiceEditor(spec.choices, emit, spec.labels)
    if spec.kind == "fonts":
        return FontsEditor(emit)
    if spec.kind == "length":
        return LengthEditor(emit)
    if spec.kind == "deprecated":
        return DeprecatedEditor()
    raise ValueError(f"no editor for field kind {spec.kind!r}")


class FieldRow(Gtk.Box):
    """Label, editor, where the value comes from, a reset button and an error line.

    `on_change(path, value)` runs when the user edits the value (spin buttons: after a
    DEBOUNCE_MS pause); `on_reset(path)` when the reset button is pressed. Values shown with
    show_value never call back."""

    def __init__(
        self,
        spec: FieldSpec,
        path: tuple,
        on_change: Callable[[tuple, Any], None],
        on_reset: Callable[[tuple], None],
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.spec, self.path = spec, path
        self._on_change = on_change
        self._updating = False
        self._timer = 0
        self._pending: Any = None
        self.editor = make_editor(spec, self._changed)
        line = Gtk.Box(spacing=8)
        name = Gtk.Label(label=spec.label, xalign=0)
        name.set_size_request(150, -1)
        self.source = Gtk.Label(xalign=0)
        self.source.get_style_context().add_class("dim-label")
        self.reset = Gtk.Button.new_from_icon_name("edit-undo-symbolic", Gtk.IconSize.BUTTON)
        self.reset.set_tooltip_text("Remove this key from your config (use the inherited value)")
        self.reset.connect("clicked", lambda *_a: on_reset(path))
        line.pack_start(name, False, False, 0)
        line.pack_start(self.editor.widget, False, False, 0)
        line.pack_start(self.source, True, True, 0)
        line.pack_end(self.reset, False, False, 0)
        self.error = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.error.get_style_context().add_class("error")
        self.error.set_no_show_all(True)
        self.pack_start(line, False, False, 0)
        self.pack_start(self.error, False, False, 0)

    def show_value(self, value: FieldValue) -> None:
        self._cancel()
        self._updating = True
        try:
            if isinstance(self.editor, LengthEditor):
                default = value.default
                self.editor.fallback_px = default if isinstance(default, int) else FALLBACK_PX
            self.editor.set(value.value)
        finally:
            self._updating = False
        note = value.source if not self.spec.hint else f"{self.spec.hint} · {value.source}"
        self.source.set_text(note)
        self.reset.set_sensitive(value.is_set and self.spec.kind != "widget")
        self.show_error(None)

    def show_error(self, message: str | None) -> None:
        self.error.set_text(message or "")
        self.error.set_visible(bool(message))

    def flush(self) -> None:
        """Send what the user changed but has not been applied yet: a debounced spin value
        or a typed font list (the window is closing)."""
        if self._timer:
            self._cancel()
            self._on_change(self.path, self._pending)
        self.editor.commit()

    def _changed(self, value: Any) -> None:
        if self._updating:
            return
        if self.spec.kind not in DEBOUNCED:
            self._on_change(self.path, value)
            return
        self._cancel()
        self._pending = value
        self._timer = GLib.timeout_add(DEBOUNCE_MS, self._flush)

    def _flush(self) -> bool:
        self._timer = 0
        self._on_change(self.path, self._pending)
        return GLib.SOURCE_REMOVE

    def _cancel(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0
