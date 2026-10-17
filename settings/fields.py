"""GTK rows for the settings form: one FieldRow per FieldSpec (settings.form). Thin: the
conversions live in settings.form, the values in settings.values."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GObject, Gtk, Pango  # noqa: E402

from settings import fontpicker  # noqa: E402
from settings.fontpicker import FontPicker  # noqa: E402
from settings.fonts import next_font  # noqa: E402
from settings.form import (  # noqa: E402
    LENGTH_MODES,
    LENGTH_PERCENT,
    LENGTH_PX,
    FieldSpec,
    join_length,
    rgba_to_hex,
    split_length,
    uses_slider,
)
from settings.style import SWITCH_CLASS, install_css  # noqa: E402
from settings.values import FieldValue  # noqa: E402
from shell.theme import hex_to_rgba  # noqa: E402

DEBOUNCE_MS = 400  # spin buttons: one write per pause, not one per click of the arrows
DEBOUNCED = ("int", "length")
UNBOUNDED = (-100000, 100000)
FALLBACK_PX = 300  # px when switching a length to px with no px value known (never the 60 min)
FALLBACK_PERCENT = 50.0
SOURCE_CHARS = 28  # the width of a row's note (where its value comes from); longer is cut
SLIDER_WIDTH = 160  # px; with its spin button a slider row stays inside a tab's 640 px

Emit = Callable[[Any], None]
_UNSHOWN = object()
UNSET = object()  # an editor's "remove this key": the row resets it (the inherited value)
THEME_FONT = "Theme font"  # a widget font row's inherited value


def _same(a: Any, b: Any) -> bool:
    return type(a) is type(b) and a == b


def wheel_scrolls_the_page(widget: Gtk.Widget) -> None:
    """A mouse wheel over a combo box or spin button scrolls the page instead of changing the
    value. Edits apply live: a stray scroll over a monitor's mode row would otherwise set it to
    `edge` (an Edge Shell frame over the Plasma panel), over thickness rebuild the monitor."""
    widget.connect("scroll-event", _pass_scroll)


def _pass_scroll(widget: Gtk.Widget, _event: Gdk.Event) -> bool:
    GObject.signal_stop_emission_by_name(widget, "scroll-event")  # skip the widget's handler
    return False  # not handled: the event goes on to the page's ScrolledWindow


def opens_below(combo: Gtk.ComboBox) -> None:
    """The combo's list opens below it at the size of its entries (Phil: it opened one entry
    high with a scrollbar and grew on a mouse-over or a wheel turn). GTK 3.24 pops a combo's
    menu up in one of two ways (gtkcombobox.c, gtk_combo_box_menu_popup). With wrap_width 0
    it lays the menu over the combo with the ACTIVE entry on it: a negative rect_anchor_dy,
    anchor hints slide and resize (no flip), and a scroll offset set once the menu is up. On
    Wayland the compositor then constrains that popup, and GtkMenu shows scroll arrows until a
    motion or wheel event makes it measure again. With wrap_width > 0 GTK anchors the menu
    below the combo (above when there is no room: flip, slide and resize) with no offset. One
    column keeps the list a plain list. The size request is not the cause: popup-fixed-width
    and a menu item's min-height act on widths and row heights, not on this placement."""
    combo.set_wrap_width(1)


class _Editor:
    """The value widget of a row: `widget`, `set(value)` (never emits), `emit` on user edits."""

    widget: Gtk.Widget
    # a tall editor's vertical size group holding its first line: the row's label, note and
    # reset join it (FieldRow); None for a one-line editor
    first_line: Gtk.SizeGroup | None = None

    @property
    def outer(self) -> Gtk.Widget:
        """What the row shows: the value widget itself, or a box around it (a slider)."""
        return self.widget

    def set(self, value: Any) -> None:
        raise NotImplementedError

    def release(self) -> None:
        """The row is retired: drop what would keep this editor alive after its widgets are
        destroyed (a handler on a long-lived GObject, a callback held by GTK)."""

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


class SliderEditor(_Editor):
    """A bounded whole number (settings.form.uses_slider): a slider and, beside it, a spin
    button for exact typing; both move one Gtk.Adjustment, so they always show the same
    value and every change is sent once. `widget` is the spin button (typed text, flush and
    the focus after a rebuild work as for a plain number row); `scale` the slider. While the
    mouse button is down on the slider nothing is sent (the spin button shows the number
    live); the final whole number is sent once when the button is released (or the grab is
    broken, the focus lost, or the row is flushed). The keys of a focused slider work and
    send as they go (arrows, Home, End; Page Up raises by a page, Page Down lowers); the
    queue keeps the last value per row (settings.queue). The mouse wheel never edits it
    (wheel_scrolls_the_page). An
    unset optional value (a widget's font size) shows the minimum, as a spin row does."""

    def __init__(self, spec: FieldSpec, emit: Emit):
        low, high = spec.minimum, spec.maximum
        page = max(1, (high - low) // 10)
        self.adjustment = Gtk.Adjustment(
            value=low, lower=low, upper=high, step_increment=1, page_increment=page
        )
        self.scale = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.adjustment, draw_value=False
        )
        self.scale.set_round_digits(0)  # a drag moves in whole numbers
        self.scale.set_size_request(SLIDER_WIDTH, -1)
        self.scale.get_accessible().set_name(spec.label)
        self.widget = Gtk.SpinButton(adjustment=self.adjustment, climb_rate=1, digits=0)
        self.widget.set_numeric(True)
        strict_spin(self.widget)
        self._box = Gtk.Box(spacing=6)
        self._box.pack_start(self.scale, False, False, 0)
        self._box.pack_start(self.widget, False, False, 0)
        for widget in (self.scale, self.widget):
            wheel_scrolls_the_page(widget)
        self._emit = emit
        self._dragging = False  # the mouse button is down on the slider
        self._value_handler = self.adjustment.connect("value-changed", self._on_value)
        self.scale.connect("button-press-event", self._press)
        for signal in ("button-release-event", "grab-broken-event", "focus-out-event"):
            self.scale.connect(signal, self._release)
        self.scale.connect("key-press-event", self._key)

    def release(self) -> None:
        """The adjustment, held by both widgets in C, keeps this editor (its handler) alive."""
        if self._value_handler:
            self.adjustment.disconnect(self._value_handler)
            self._value_handler = 0

    def _value(self) -> int:
        return int(round(self.adjustment.get_value()))

    def _on_value(self, _adjustment) -> None:
        if not self._dragging:
            self._emit(self._value())

    def _press(self, _scale, _event) -> bool:
        self._dragging = True
        return False  # the slider still moves

    def _release(self, _scale, _event) -> bool:
        self._end_drag()
        return False

    def _end_drag(self) -> None:
        if self._dragging:
            self._dragging = False
            self._emit(self._value())

    def _key(self, _scale, event) -> bool:
        """Page Up raises the value by a page, Page Down lowers it (GTK's own bindings for a
        horizontal slider are the other way round)."""
        sign = {
            Gdk.KEY_Page_Up: 1,
            Gdk.KEY_KP_Page_Up: 1,
            Gdk.KEY_Page_Down: -1,
            Gdk.KEY_KP_Page_Down: -1,
        }.get(event.keyval)
        if sign is None:
            return False
        a = self.adjustment
        a.set_value(a.get_value() + sign * a.get_page_increment())
        return True

    @property
    def outer(self) -> Gtk.Widget:
        return self._box

    def commit(self) -> None:
        self._end_drag()  # a flush during a drag applies the value it has now
        commit_spin(self.widget)

    def dirty(self) -> bool:
        return self._dragging or _spin_dirty(self.widget)

    def set(self, value: int | None) -> None:
        self.adjustment.set_value(self.adjustment.get_lower() if value is None else value)


class BoolEditor(_Editor):
    """A toggle: thin, with a round knob (settings.style), centred in its row (a switch
    stretched to the row's height made the knob a tall oval)."""

    def __init__(self, emit: Emit):
        install_css()
        self.widget = Gtk.Switch(halign=Gtk.Align.START, valign=Gtk.Align.CENTER)
        self.widget.get_style_context().add_class(SWITCH_CLASS)
        self.widget.connect("notify::active", lambda s, _p: emit(s.get_active()))

    def set(self, value: bool) -> None:
        self.widget.set_active(bool(value))


class ChoiceEditor(_Editor):
    """A combo box. `disabled` choices are listed greyed out and are never sent (float panels:
    "coming soon"); if one gets chosen anyway (in GTK3 only a programmatic
    set_active can), the shown value comes back."""

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
        opens_below(self.widget)
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


class _FontLine:
    """One family of a font list: its picker and its Move up, Move down and Remove."""

    def __init__(self, picker: FontPicker, buttons: dict[str, Gtk.Button]):
        self.picker = picker
        self.buttons = buttons
        self.box = Gtk.Box(spacing=4)
        self.box.pack_start(picker.button, False, False, 0)
        for button in buttons.values():
            self.box.pack_start(button, False, False, 0)
        for child in self.box.get_children():
            child.show_all()
        self.box.set_no_show_all(True)  # shown by FontListEditor only while it is in use


FONT_LINE_BUTTONS = (  # action, icon, tooltip
    ("up", "go-up-symbolic", "Move this font up: it is tried earlier"),
    ("down", "go-down-symbolic", "Move this font down: it is tried later"),
    ("remove", "list-remove-symbolic", "Remove this font from the list"),
)
FONT_LINE_NAMES = {  # the accessible name of a line's button, by its 1-based position
    "up": "Move font {} up",
    "down": "Move font {} down",
    "remove": "Remove font {} from the list",
}


class FontListEditor(_Editor):
    """The theme's font list, an ordered fallback list (the first installed family is used):
    one searchable picker per family (settings.fontpicker), each with Move up, Move down and
    Remove, and Add font below. Every change sends the whole list at once (a list of names,
    never joined into one string: a family name may hold a comma); there is no typed text
    (dirty() is False). The list keeps one family (the config needs one): its Remove is
    insensitive. Add font appends the desktop's font (Phil: the default is the system font),
    else a generic family the list does not hold. Lines are hidden, never destroyed, when the
    list gets shorter: a line's own Remove click must not free the button it runs in."""

    def __init__(self, emit: Emit):
        self._emit = emit
        self.fonts: list[str] = []
        self.lines: list[_FontLine] = []  # the first len(fonts) are shown
        self.first_line = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.VERTICAL)
        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.add_button = Gtk.Button(label="Add font", halign=Gtk.Align.START)
        self.add_button.set_tooltip_text("Add a font at the end of the list")
        self.add_button.connect("clicked", lambda _b: self._add())
        self.widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.widget.pack_start(self.list_box, False, False, 0)
        self.widget.pack_start(self.add_button, False, False, 0)

    def release(self) -> None:
        for line in self.lines:
            line.picker.release()

    def set(self, value: list[str]) -> None:
        self.fonts = list(value)
        self._sync()

    def _line(self, index: int) -> _FontLine:
        picker = FontPicker(lambda value: self._replace(index, value))
        buttons = {}
        for action, icon, tip in FONT_LINE_BUTTONS:
            button = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
            button.set_tooltip_text(tip)
            button.connect("clicked", lambda _b, a=action: self._act(index, a))
            buttons[action] = button
        line = _FontLine(picker, buttons)
        self.list_box.pack_start(line.box, False, False, 0)
        if index == 0:
            self.first_line.add_widget(line.box)
        return line

    def _sync(self) -> None:
        while len(self.lines) < len(self.fonts):
            self.lines.append(self._line(len(self.lines)))
        count = len(self.fonts)
        for i, line in enumerate(self.lines):
            line.box.set_visible(i < count)
            if i < count:
                line.picker.set(self.fonts[i])
                for action, button in line.buttons.items():
                    button.get_accessible().set_name(FONT_LINE_NAMES[action].format(i + 1))
                line.buttons["up"].set_sensitive(i > 0)
                line.buttons["down"].set_sensitive(i < count - 1)
                line.buttons["remove"].set_sensitive(count > 1)

    def _send(self, fonts: list[str]) -> None:
        self.fonts = fonts
        self._sync()
        self._emit(list(fonts))

    def _replace(self, index: int, value: str | None) -> None:
        if value is None or index >= len(self.fonts) or self.fonts[index] == value:
            return
        fonts = list(self.fonts)
        fonts[index] = value
        self._send(fonts)

    def _act(self, index: int, action: str) -> None:
        fonts = list(self.fonts)
        if action == "remove" and len(fonts) > 1:
            del fonts[index]
            target = min(index, len(fonts) - 1)  # the font that took its place, or the last
        elif action in ("up", "down"):
            other = index - 1 if action == "up" else index + 1
            if not 0 <= other < len(fonts):
                return
            fonts[index], fonts[other] = fonts[other], fonts[index]
            target = other  # the same font, on its new line
        else:
            return
        self._send(fonts)
        self._focus(target, action)

    def _focus(self, index: int, action: str) -> None:
        """Keyboard focus follows what the user moved: the same button of the same font on
        its new line (the other move button when this one is dead at the end of the list),
        else the Add font button. Without it focus stays on a button at the old position,
        which now belongs to another font."""
        buttons = self.lines[index].buttons
        order = {"up": ("up", "down"), "down": ("down", "up"), "remove": ("remove",)}[action]
        for name in order:
            if buttons[name].get_sensitive():
                buttons[name].grab_focus()
                return
        self.add_button.grab_focus()

    def _add(self) -> None:
        self._send([*self.fonts, next_font(self.fonts, fontpicker.system_family())])
        self.lines[len(self.fonts) - 1].picker.button.grab_focus()


class FontEditor(_Editor):
    """A widget's font (one family; unset: the theme's font): a searchable picker whose first
    row is "Theme font"; picking it sends UNSET (the row resets the key: nothing is
    written)."""

    def __init__(self, emit: Emit):
        self.picker = FontPicker(
            lambda value: emit(UNSET if value is None else value), inherit_label=THEME_FONT
        )
        self.widget = self.picker.button

    def release(self) -> None:
        self.picker.release()

    def set(self, value: str | None) -> None:
        self.picker.set(value)


class TextEditor(_Editor):
    """A line of text (a panel's name, a widget's text property): sent on Enter or when the
    entry loses focus."""

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
        opens_below(self.mode)
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
        return SliderEditor(spec, emit) if uses_slider(spec) else IntEditor(spec, emit)
    if spec.kind == "bool":
        return BoolEditor(emit)
    if spec.kind in ("enum", "widget"):
        return ChoiceEditor(spec.choices, emit, spec.labels, spec.disabled)
    if spec.kind == "fonts":
        return FontListEditor(emit)
    if spec.kind == "font":
        return FontEditor(emit)
    if spec.kind == "text":
        return TextEditor(emit, spec.max_length)
    if spec.kind == "length":
        return LengthEditor(emit)
    if spec.kind == "deprecated":
        return DeprecatedEditor()
    raise ValueError(f"no editor for field kind {spec.kind!r}")


class FieldRow(Gtk.Box):
    """Label, editor, where the value comes from, a reset button and an error line.

    `on_change(path, value)` runs when the user edits the value; `on_reset(path)` when the reset
    button is pressed. A spin button's edits (DEBOUNCED kinds) go to `on_queue(path, value,
    base)` instead, `base` being the value the row showed (the view's EditQueue applies them
    after the pause: settings.queue); without `on_queue` they go to on_change at once. The row
    holds no timer and no pending value of its own: only text typed and not yet sent (a name,
    a number without Enter), which flush() sends. `is_pending(path)` says whether
    the view still has an edit of this row queued (a refresh then keeps the editor as it is).
    Values shown with show_value never call back."""

    def __init__(
        self,
        spec: FieldSpec,
        path: tuple,
        on_change: Callable[[tuple, Any], None],
        on_reset: Callable[[tuple], None],
        on_queue: Callable[[tuple, Any, Any], None] | None = None,
        is_pending: Callable[[tuple], bool] | None = None,
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.spec, self.path = spec, path
        self._on_change = on_change
        self._on_reset = on_reset
        self._on_queue = on_queue
        self._is_pending = is_pending or (lambda _path: False)
        self._updating = False
        self._discarding = False  # retired by a rebuild: nothing it holds may be written
        self._shown: Any = _UNSHOWN  # the value last shown or written: a no-op is not written
        self.editor = make_editor(spec, self._changed)
        line = Gtk.Box(spacing=8)
        # label, note and reset are centred beside a one-line editor. Beside a tall one (the
        # font list) they would stretch or float to its middle: there they start at the top and
        # share a height with the first picker's line (editor.first_line), so they stay one
        # entry high and level with the first picker
        align = Gtk.Align.START if self.editor.first_line is not None else Gtk.Align.CENTER
        name = Gtk.Label(label=spec.label, xalign=0, valign=align)
        name.set_size_request(150, -1)
        # a Gtk.Label shows a tooltip without an event box; only the label has this one (the
        # editors, the note and the reset button keep their own)
        name.set_tooltip_text(spec.tooltip or None)
        self.name_label = name
        self.source = Gtk.Label(xalign=0, valign=align)
        # a long hint never widens the page (its Reset button would sit off screen): the end
        # is cut, the whole text is the tooltip
        self.source.set_ellipsize(Pango.EllipsizeMode.END)
        self.source.set_max_width_chars(SOURCE_CHARS)
        self.source.get_style_context().add_class("dim-label")
        self.reset = Gtk.Button.new_from_icon_name("edit-undo-symbolic", Gtk.IconSize.BUTTON)
        self.reset.set_valign(align)
        if self.editor.first_line is not None:
            for widget in (name, self.source, self.reset):
                self.editor.first_line.add_widget(widget)
        self.reset.set_tooltip_text("Remove this key from your config (use the inherited value)")
        self.reset.connect("clicked", lambda *_a: self._on_reset(path))
        line.pack_start(name, False, False, 0)
        line.pack_start(self.editor.outer, False, False, 0)
        line.pack_start(self.source, True, True, 0)
        line.pack_end(self.reset, False, False, 0)
        self.error = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.error.get_style_context().add_class("error")
        self.error.set_no_show_all(True)
        self.pack_start(line, False, False, 0)
        self.pack_start(self.error, False, False, 0)

    def show_value(self, value: FieldValue, keep_pending: bool = False) -> None:
        """Show `value` and clear the error. With `keep_pending` (refreshing every row after
        another row's apply) the error stays, and a row with an edit that is not applied yet
        (queued in the view, or typed text) only updates its source and reset, so that the
        refresh never drops it."""
        self._shown = value.value
        if not keep_pending:
            self.show_error(None)
        if keep_pending and (self._is_pending(self.path) or self.editor.dirty()):
            self._show_note(value)
            return
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
        self.source.set_tooltip_text(note)
        self.reset.set_sensitive(value.is_set and not self.spec.required)  # name, widget, panel

    def show_error(self, message: str | None) -> None:
        self.error.set_text(message or "")
        self.error.set_visible(bool(message))

    def flush(self) -> None:
        """Send text typed and not sent yet (a name or a number without Enter): the view
        applies it with the queue (the window is closing, the pages are about to be
        rebuilt)."""
        self.editor.commit()

    def unsent(self) -> bool:
        """True while the editor holds typed text that was not sent."""
        return self.editor.dirty()

    def _changed(self, value: Any) -> None:
        if self._updating or self._discarding:
            return
        if value is UNSET:  # the editor's inherited row (a widget font's "Theme font")
            self._shown = None
            self._on_reset(self.path)
            return
        if self.spec.kind in DEBOUNCED and self._on_queue is not None:
            self._on_queue(self.path, value, self._shown)  # the queue un-queues a change back
            return
        self._write(value)

    def _write(self, value: Any) -> None:
        if _same(value, self._shown):
            return  # a no-op must not turn an inherited value into an explicit one
        self._shown = value
        self._on_change(self.path, value)

    def discard(self) -> None:
        """The row is retired (a rebuild or a hand-edit reload): never call back again, also
        for the focus-out GTK sends when its entry is unparented. Its queued edits stay in the
        view's queue (they are not the row's)."""
        self._discarding = True
        self.editor.release()
