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
_UNSHOWN = object()


def _same(a: Any, b: Any) -> bool:
    return type(a) is type(b) and a == b


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

    def dirty(self) -> bool:
        """True while the editor holds typed text that was not sent yet."""
        return False


def _restore_invalid_text(spin: Gtk.SpinButton) -> None:
    """Text that is not a number (empty text would read as 0, a valid offset) goes back to the
    current value before GTK parses it."""
    try:
        float(spin.get_text().strip())
    except ValueError:
        spin.set_text(f"{spin.get_value():.{spin.get_digits()}f}")


def strict_spin(spin: Gtk.SpinButton) -> None:
    """Invalid, empty or out-of-range text reverts to the current value (the default update
    policy ALWAYS would write the minimum, e.g. a 60 px length). Enter and focus-out check
    the text first; commit() does the same."""
    spin.set_update_policy(Gtk.SpinButtonUpdatePolicy.IF_VALID)
    spin.connect("activate", _restore_invalid_text)
    spin.connect("focus-out-event", lambda w, _e: _restore_invalid_text(w) or False)


def commit_spin(spin: Gtk.SpinButton) -> None:
    _restore_invalid_text(spin)
    spin.update()


def _spin_dirty(spin: Gtk.SpinButton) -> bool:
    return spin.get_text() != f"{spin.get_value():.{spin.get_digits()}f}"


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
        strict_spin(self.widget)
        wheel_scrolls_the_page(self.widget)
        self.widget.connect("value-changed", lambda s: emit(s.get_value_as_int()))

    def commit(self) -> None:
        commit_spin(self.widget)  # a typed number without Enter; may re-arm the row's timer

    def dirty(self) -> bool:
        return _spin_dirty(self.widget)

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
    """A combo box. `disabled` choices are listed greyed out and are never sent (float panels:
    "coming soon"); if one gets chosen anyway (the keyboard), the shown value comes back."""

    def __init__(
        self,
        choices: tuple[str, ...],
        emit: Emit,
        labels: tuple[str, ...] = (),
        disabled: tuple[str, ...] = (),
    ):
        self.widget = Gtk.ComboBoxText()
        self.disabled = disabled
        self._shown: str | None = None
        for choice, label in zip(choices, labels or choices, strict=True):
            self.widget.append(choice, label)
        if disabled:
            (cell,) = self.widget.get_cells()
            self.widget.set_cell_data_func(cell, self._grey_out)
        wheel_scrolls_the_page(self.widget)
        self.widget.connect("changed", self._on_changed, emit)

    def _grey_out(self, _layout, cell, model, it, _data=None) -> None:
        cell.set_property("sensitive", model[it][1] not in self.disabled)  # column 1: the id

    def _on_changed(self, combo: Gtk.ComboBoxText, emit: Emit) -> None:
        active = combo.get_active_id()
        if active in self.disabled:
            self.set(self._shown)
            return
        if active is not None:
            emit(active)

    def set(self, value: str) -> None:
        self._shown = value
        if not self.widget.set_active_id(value):
            self.widget.set_active(-1)  # not a choice: show none, never the previous one


class FontsEditor(_Editor):
    def __init__(self, emit: Emit):
        self.widget = Gtk.Entry(width_chars=40)
        self._shown: list[str] = []
        self._emit = emit
        self.widget.connect("activate", lambda *_a: self.commit())
        self.widget.connect("focus-out-event", lambda *_a: self.commit() or False)

    def dirty(self) -> bool:
        return parse_fonts(self.widget.get_text()) != self._shown

    def commit(self) -> None:
        fonts = parse_fonts(self.widget.get_text())
        if fonts != self._shown:
            self._shown = fonts
            self._emit(fonts)

    def set(self, value: list[str]) -> None:
        self._shown = list(value)
        self.widget.set_text(format_fonts(value))


class TextEditor(_Editor):
    """A line of text (a panel's name, a widget's text property): sent on Enter or when the
    entry loses focus, like the font list."""

    def __init__(self, emit: Emit, max_length: int | None = None):
        self.widget = Gtk.Entry(width_chars=30)
        if max_length:  # the schema's maxLength: the extra character cannot be typed
            self.widget.set_max_length(max_length)
        self._shown = ""
        self._emit = emit
        self.widget.connect("activate", lambda *_a: self.commit())
        self.widget.connect("focus-out-event", lambda *_a: self.commit() or False)

    def dirty(self) -> bool:
        return self.widget.get_text() != self._shown

    def commit(self) -> None:
        text = self.widget.get_text()
        if text != self._shown:
            self._shown = text
            self._emit(text)

    def set(self, value: str | None) -> None:
        self._shown = "" if value is None else str(value)
        self.widget.set_text(self._shown)


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
        strict_spin(self.number)
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

    def commit(self) -> None:
        commit_spin(self.number)

    def dirty(self) -> bool:
        return self.number.get_sensitive() and _spin_dirty(self.number)

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
        return ChoiceEditor(spec.choices, emit, spec.labels, spec.disabled)
    if spec.kind == "fonts":
        return FontsEditor(emit)
    if spec.kind == "text":
        return TextEditor(emit, spec.max_length)
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
        self._discarding = False  # retired by a rebuild: nothing it holds may be written
        self._pending: Any = None
        self._shown: Any = _UNSHOWN  # the value last shown or written: a no-op is not written
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
        self.connect("destroy", lambda *_a: self._cancel())  # a stale timer must not write

    def show_value(self, value: FieldValue, keep_pending: bool = False) -> None:
        """Show `value` and clear the error. With `keep_pending` (refreshing every row after
        another row's apply) the error stays, and a row holding an edit that is not applied yet
        (a debounced spin value, typed text) only updates its source and reset, so that the
        refresh never drops it."""
        self._shown = value.value
        if not keep_pending:
            self.show_error(None)
        if keep_pending and (self._timer or self.editor.dirty()):
            self._show_note(value)
            return
        self._cancel()
        self._updating = True
        try:
            if isinstance(self.editor, LengthEditor):
                default = value.default
                self.editor.fallback_px = default if isinstance(default, int) else FALLBACK_PX
            self.editor.set(value.value)
        finally:
            self._updating = False
        self._show_note(value)

    def _show_note(self, value: FieldValue) -> None:
        note = value.source if not self.spec.hint else f"{self.spec.hint} · {value.source}"
        self.source.set_text(note)
        self.reset.set_sensitive(value.is_set and not self.spec.required)  # name, widget, panel

    def show_error(self, message: str | None) -> None:
        self.error.set_text(message or "")
        self.error.set_visible(bool(message))

    def flush(self) -> None:
        """Send what the user changed but has not been applied yet: a debounced spin value
        or a typed font list (the window is closing)."""
        self.editor.commit()  # before the timer check: update() re-arms it through _changed
        if self._timer:
            self._cancel()
            self._write(self._pending)

    def _changed(self, value: Any) -> None:
        if self._updating or self._discarding:
            return
        if self.spec.kind not in DEBOUNCED:
            self._write(value)
            return
        self._cancel()
        self._pending = value
        self._timer = GLib.timeout_add(DEBOUNCE_MS, self._flush)

    def _flush(self) -> bool:
        self._timer = 0
        self._write(self._pending)
        return GLib.SOURCE_REMOVE

    def _write(self, value: Any) -> None:
        if self._discarding:
            return
        if _same(value, self._shown):
            return  # a no-op must not turn an inherited value into an explicit one
        self._shown = value
        self._on_change(self.path, value)

    def cancel_pending(self) -> None:
        """Drop a debounced value without writing it (the row is about to be discarded)."""
        self._cancel()

    def discard(self) -> None:
        """The row is retired (a rebuild or a hand-edit reload): drop what it holds and never
        call back again, also for the focus-out GTK sends when its entry is unparented."""
        self._discarding = True
        self._cancel()

    def _cancel(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0
