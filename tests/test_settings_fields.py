"""settings.fields: the GTK row of each field kind (widgets only; no window is shown)."""

import dataclasses

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, GLib, Gtk  # noqa: E402

if not Gtk.init_check()[0]:
    pytest.skip("no display", allow_module_level=True)

import settings.fields as fields  # noqa: E402
from settings.form import FieldSpec, WidgetChoice, config_form  # noqa: E402
from settings.values import FieldValue  # noqa: E402

FORM = config_form(tuple(WidgetChoice(w) for w in ("clock", "dock", "system_bar")))


def row_for(spec, value, is_set=False, path=("theme", "x"), queued=None):
    """A row; with `queued` (a list) its spin edits go there as (path, value, base), as they
    go to the view's queue."""
    changes, resets = [], []
    on_queue = None if queued is None else lambda p, v, b: queued.append((p, v, b))
    row = fields.FieldRow(spec, path, lambda p, v: changes.append((p, v)), resets.append, on_queue)
    row.show_value(FieldValue(value, is_set, "default"))
    return row, changes, resets


def test_show_value_never_calls_back():
    for spec, value in [
        (FORM.theme.field("accent"), "#8fd3b6"),
        (FORM.theme.field("thickness"), 12),
        (FORM.theme.section("border").field("enabled"), True),
        (FORM.theme.section("handle_style").field("shape"), "bar"),
        (FORM.theme.field("font"), ["A", "B"]),
        (FORM.edge_panel.field("length"), "50%"),
        (FORM.edge_panel.field("pos"), 600),
    ]:
        _, changes, _ = row_for(spec, value)
        assert changes == [], spec.key


def test_colour_row_writes_hex_with_alpha_only_when_needed():
    row, changes, _ = row_for(FORM.theme.field("accent"), "#8fd3b6", path=("theme", "accent"))
    button = row.editor.widget
    assert button.props.use_alpha
    button.set_rgba(Gdk.RGBA(0, 0, 0, 0.5))
    button.emit("color-set")
    button.set_rgba(Gdk.RGBA(1, 1, 1, 1))
    button.emit("color-set")
    assert changes == [(("theme", "accent"), "#00000080"), (("theme", "accent"), "#ffffff")]


def test_int_row_takes_its_bounds_from_the_schema_and_queues_its_edits():
    queued = []
    row, changes, _ = row_for(FORM.theme.field("thickness"), 10, queued=queued)
    spin = row.editor.widget
    assert tuple(spin.get_range()) == (5.0, 64.0)
    spin.set_value(11)
    spin.set_value(12)
    assert changes == []  # the view applies them after the pause
    # the base is the value the row showed, also for the second step (the queue un-queues a
    # change back to it)
    assert queued == [(("theme", "x"), 11, 10), (("theme", "x"), 12, 10)]


def test_a_row_without_a_queue_sends_spin_edits_at_once():
    row, changes, _ = row_for(FORM.theme.field("thickness"), 10)
    row.editor.widget.set_value(11)
    assert changes == [(("theme", "x"), 11)]


def test_unset_optional_int_shows_the_minimum():
    row, _, _ = row_for(FORM.edge_panel.field("min_length"), None)
    assert row.editor.widget.get_value() == 60


def test_bool_enum_and_widget_rows():
    row, changes, _ = row_for(FORM.theme.section("border").field("enabled"), False)
    row.editor.widget.set_active(True)
    row, changes2, _ = row_for(FORM.theme.section("handle_style").field("shape"), "auto")
    assert row.editor.widget.get_active_id() == "auto"
    row.editor.widget.set_active_id("chevron")
    row, changes3, _ = row_for(FORM.edge_panel.field("widget"), "dock")
    row.editor.widget.set_active_id("clock")
    assert [c[1] for c in changes + changes2 + changes3] == [True, "chevron", "clock"]


@pytest.fixture
def fonts(monkeypatch):
    """A fixed font list and desktop font: never the machine's (settings.fontpicker)."""
    from settings import fontpicker

    monkeypatch.setattr(fontpicker, "installed_families", lambda: ("Fira Mono", "Noto Sans"))
    monkeypatch.setattr(fontpicker, "system_family", lambda: "Noto Sans")


def shown_fonts(editor):
    return [line.picker.label.get_text() for line in editor.lines if line.box.get_visible()]


def test_the_font_list_is_one_picker_per_family(fonts):
    row, changes, _ = row_for(FORM.theme.field("font"), ["Hack Nerd Font Mono", "monospace"])
    editor = row.editor
    assert isinstance(editor, fields.FontListEditor)
    assert shown_fonts(editor) == ["Hack Nerd Font Mono", "monospace"]
    first, second = editor.lines
    assert not first.buttons["up"].get_sensitive() and first.buttons["down"].get_sensitive()
    assert second.buttons["up"].get_sensitive() and not second.buttons["down"].get_sensitive()
    assert not row.unsent() and changes == []  # nothing typed, nothing sent by showing


def test_picking_a_family_sends_the_whole_list(fonts):
    row, changes, _ = row_for(FORM.theme.field("font"), ["Hack Nerd Font Mono", "monospace"])
    picker = row.editor.lines[1].picker
    picker.fill()
    picker.search.set_text("fira")
    picker.search.emit("activate")
    assert changes == [(("theme", "x"), ["Hack Nerd Font Mono", "Fira Mono"])]
    assert shown_fonts(row.editor) == ["Hack Nerd Font Mono", "Fira Mono"]


def test_moving_removing_and_adding_fonts(fonts):
    row, changes, _ = row_for(FORM.theme.field("font"), ["A", "B", "C"])
    editor = row.editor
    editor.lines[2].buttons["up"].clicked()
    editor.lines[0].buttons["remove"].clicked()
    editor.add_button.clicked()  # the desktop's font
    editor.add_button.clicked()  # it is listed: the first generic family not listed
    assert [v for _p, v in changes] == [
        ["A", "C", "B"],
        ["C", "B"],
        ["C", "B", "Noto Sans"],
        ["C", "B", "Noto Sans", "monospace"],
    ]
    assert shown_fonts(editor) == ["C", "B", "Noto Sans", "monospace"]


def test_a_pick_that_changes_nothing_sends_nothing(fonts):
    sent = []
    editor = fields.FontListEditor(sent.append)
    editor.set(["A", "B"])
    editor.lines[0].picker._on_pick("A")  # the family already there
    editor.lines[0].picker._on_pick(None)  # no inherited row in a list: nothing to pick
    assert sent == []
    editor.lines[1].picker._on_pick("A")  # a duplicate is the user's choice: it is sent
    assert sent == [["A", "A"]]


def test_a_family_name_with_a_comma_is_never_split_or_joined(fonts):
    row, changes, _ = row_for(FORM.theme.field("font"), ["Odd, Name", "monospace"])
    assert shown_fonts(row.editor) == ["Odd, Name", "monospace"]
    row.editor.lines[1].buttons["up"].clicked()
    row.editor.add_button.clicked()
    assert [v for _p, v in changes] == [
        ["monospace", "Odd, Name"],
        ["monospace", "Odd, Name", "Noto Sans"],
    ]
    assert all(isinstance(v, list) for _p, v in changes)


def test_the_last_font_cannot_be_removed_and_a_shorter_list_hides_lines(fonts):
    row, changes, _ = row_for(FORM.theme.field("font"), ["A", "B"])
    editor = row.editor
    editor.lines[1].buttons["remove"].clicked()  # the line's own button: hidden, not destroyed
    assert shown_fonts(editor) == ["A"] and len(editor.lines) == 2
    assert not editor.lines[0].buttons["remove"].get_sensitive()
    editor.lines[0].buttons["remove"].clicked()  # insensitive in the window; never sent anyway
    assert [v for _p, v in changes] == [["A"]]
    row.show_value(FieldValue(["X", "Y", "Z"], True, "your config"))  # a re-read: lines grow
    assert shown_fonts(editor) == ["X", "Y", "Z"] and len(editor.lines) == 3


def test_length_row_modes():
    row, changes, _ = row_for(FORM.edge_panel.field("length"), 300)
    editor = row.editor
    assert editor.mode.get_active_id() == "px" and editor.number.get_value() == 300
    editor.mode.set_active_id("fill")
    assert not editor.number.get_sensitive()
    editor.mode.set_active_id("percent")
    editor.number.set_value(25)
    editor.mode.set_active_id("px")
    assert [c[1] for c in changes] == ["fill", "50%", "25%", 300]  # each mode keeps its number


def test_a_fill_length_switched_to_px_takes_the_widget_default_not_the_minimum():
    changes = []
    for shown, default, expected in (("fill", 560, 560), ("content", "fill", fields.FALLBACK_PX)):
        row = fields.FieldRow(
            FORM.edge_panel.field("length"), ("p",), lambda _p, v: changes.append(v), id
        )
        row.show_value(FieldValue(shown, True, "your config", default=default))
        row.editor.mode.set_active_id("px")
        assert changes[-1] == expected  # the widget's px default, else 300: never 60 px


def test_the_mouse_wheel_never_edits_a_row():
    """Live apply: a wheel over DP-1's mode row must scroll the page, not set it to edge."""
    edits = []

    def scroll(widget):
        event = Gdk.Event.new(Gdk.EventType.SCROLL)
        event.scroll.direction = Gdk.ScrollDirection.UP
        return widget.emit("scroll-event", event)

    mode = fields.FieldRow(
        FORM.monitor.field("shell"), ("monitors", "DP-1", "shell"), lambda p, v: edits.append(v), id
    )
    mode.show_value(FieldValue("plasma", True, "your config"))
    thickness, changes, _ = row_for(FORM.theme.field("thickness"), 10)
    length, changes2, _ = row_for(FORM.edge_panel.field("length"), 300)
    for widget in (
        mode.editor.widget,
        thickness.editor.widget,  # a slider's spin button
        thickness.editor.scale,  # and the slider itself
        length.editor.mode,
        length.editor.number,
    ):
        assert scroll(widget) is False  # not handled: the page's ScrolledWindow scrolls
    assert mode.editor.widget.get_active_id() == "plasma"
    assert thickness.editor.widget.get_value() == 10 and length.editor.number.get_value() == 300
    assert edits == changes == changes2 == []


def test_flush_sends_typed_text_only():
    queued = []
    spin, changes, _ = row_for(FORM.theme.field("thickness"), 10, queued=queued)
    spin.editor.widget.set_text("14")  # typed, Enter not pressed
    name, changes2, _ = row_for(FORM.edge_panel.field("name"), "Dock")
    name.editor.widget.set_text("Bottom dock")
    assert spin.unsent() and name.unsent()
    spin.flush()
    name.flush()
    assert queued == [(("theme", "x"), 14, 10)] and changes == []
    assert changes2 == [(("theme", "x"), "Bottom dock")]
    spin.flush()
    name.flush()
    assert len(queued) == 1 and len(changes2) == 1  # nothing typed any more
    assert not spin.unsent() and not name.unsent()


def test_choices_show_their_labels():
    form = config_form(
        (WidgetChoice("summary", "Summary", ("corner",)), WidgetChoice("clock", "Clock"))
    )
    row, _, _ = row_for(form.edge_panel.field("widget"), "clock")
    assert [r[0] for r in row.editor.widget.get_model()] == ["Clock", "Summary"]
    row.editor.widget.set_active_id("summary")
    assert row.editor.widget.get_active_text() == "Summary"


def test_length_row_shows_percent_with_one_decimal():
    row, _, _ = row_for(FORM.edge_panel.field("length"), "12.5%")
    assert row.editor.mode.get_active_id() == "percent"
    assert row.editor.number.get_value() == 12.5 and row.editor.number.get_digits() == 1


def test_reset_button_follows_is_set_and_calls_back():
    row, _, resets = row_for(FORM.theme.field("accent"), "#8fd3b6", is_set=False)
    assert not row.reset.get_sensitive()
    row.show_value(FieldValue("#112233", True, "your config"))
    assert row.reset.get_sensitive()
    row.reset.clicked()
    assert resets == [("theme", "x")]


def test_the_widget_of_a_panel_cannot_be_reset():
    row, _, _ = row_for(FORM.edge_panel.field("widget"), "dock", is_set=True)
    assert not row.reset.get_sensitive()


def test_source_shows_the_hint_and_the_origin():
    row, _, _ = row_for(FORM.theme.field("thickness"), 10)
    assert row.source.get_text() == "px · default"


def test_errors_show_under_the_row_until_the_next_value():
    row, _, _ = row_for(FORM.theme.field("thickness"), 10)
    row.show_error("theme.thickness: too thick")
    assert row.error.get_visible() and "too thick" in row.error.get_text()
    row.show_value(FieldValue(10, False, "default"))
    assert not row.error.get_visible()


def test_an_unknown_kind_has_no_editor():
    with pytest.raises(ValueError):
        fields.make_editor(FieldSpec("x", "X", "blob"), lambda _v: None)  # type: ignore[arg-type]


def test_a_discarded_row_never_calls_back():
    queued = []
    spin, changes, _ = row_for(FORM.theme.field("thickness"), 10, queued=queued)
    name, changes2, _ = row_for(FORM.edge_panel.field("name"), "Dock")
    for row in (spin, name):
        row.discard()  # retired by a rebuild
    spin.editor.widget.set_value(30)
    name.editor.widget.set_text("Typed")
    name.editor.widget.emit("activate")  # or the focus-out GTK sends when it is unparented
    spin.flush()
    name.flush()
    assert queued == changes == changes2 == []


def test_a_row_starts_no_timer(monkeypatch):
    """The spin pause is the view's one queue timer: a row never starts a timer of its own."""

    def no_timer(*_a):
        raise AssertionError("a row started a timer")

    monkeypatch.setattr(GLib, "timeout_add", no_timer)
    queued = []
    row, _, _ = row_for(FORM.theme.field("thickness"), 10, queued=queued)
    row.editor.widget.set_value(30)
    length, _, _ = row_for(FORM.edge_panel.field("length"), 300, queued=queued)
    length.editor.number.set_value(400)
    assert [v for _p, v, _b in queued] == [30, 400]


def test_a_refresh_keeps_a_queued_edit_and_typed_text():
    queued, pending = [], set()

    def on_queue(path, value, base):
        queued.append(value)
        pending.add(path)

    thick = fields.FieldRow(
        FORM.theme.field("thickness"), ("theme", "x"), id, id, on_queue, pending.__contains__
    )
    thick.show_value(FieldValue(10, False, "default"))
    thick.editor.widget.set_value(30)
    thick.show_value(FieldValue(10, False, "inherited"), keep_pending=True)  # another apply
    assert thick.editor.widget.get_value() == 30  # still the queued 30
    assert thick.source.get_text().endswith("inherited")
    pending.clear()  # the view applied it
    thick.show_value(FieldValue(30, True, "your config"), keep_pending=True)
    assert thick.editor.widget.get_value() == 30 and thick.source.get_text().endswith("config")
    thick.editor.widget.set_value(12)  # queued again; a plain show_value (a re-read) shows
    thick.show_value(FieldValue(30, True, "your config"))  # the file's value all the same
    assert thick.editor.widget.get_value() == 30


def test_closing_applies_every_row_even_when_each_apply_refreshes_all():
    result, rows = {}, []

    def on_change(path, value):
        result[path[1]] = value
        for row in rows:  # SettingsView.refresh after each apply
            row.show_value(FieldValue(result.get(row.path[1], row.shown), True, "x"), True)

    thick = fields.FieldRow(FORM.theme.field("thickness"), ("theme", "t"), on_change, id)
    name = fields.FieldRow(FORM.edge_panel.field("name"), ("theme", "n"), on_change, id)
    rows[:] = [thick, name]
    thick.shown, name.shown = 10, "Dock"
    for row in rows:
        row.show_value(FieldValue(row.shown, False, "default"))
    thick.editor.widget.set_value(20)
    name.editor.widget.set_text("Bottom dock")
    for row in rows:  # SettingsView.flush
        row.flush()
    assert result == {"t": 20, "n": "Bottom dock"}


def test_a_toggle_within_the_pause_does_not_drop_a_queued_spin():
    result, rows, queue = {}, [], {}

    def on_change(path, value):
        result[path[1]] = value
        for row in rows:
            row.show_value(FieldValue(result.get(row.path[1], 10), True, "x"), True)

    def on_queue(path, value, _base):
        queue[path] = value

    thick = fields.FieldRow(
        FORM.theme.field("thickness"), ("theme", "t"), on_change, id, on_queue, queue.__contains__
    )
    flag = fields.FieldRow(
        FORM.theme.section("border").field("enabled"), ("theme", "b"), on_change, id
    )
    rows[:] = [thick, flag]
    thick.show_value(FieldValue(10, False, "default"))
    flag.show_value(FieldValue(False, False, "default"))
    thick.editor.widget.set_value(14)
    flag.editor.widget.set_active(True)  # applied now: every row is refreshed
    assert result == {"b": True} and queue == {("theme", "t"): 14}
    assert thick.editor.widget.get_value() == 14


def test_empty_or_invalid_spin_text_writes_nothing():
    for spec, value in [
        (FORM.theme.field("thickness"), 10),
        (FORM.edge_panel.field("offset"), 5),
        (FORM.edge_panel.field("length"), 300),
    ]:
        row, changes, _ = row_for(spec, value)
        spin = getattr(row.editor, "number", row.editor.widget)
        for text in ("", "abc"):
            spin.set_text(text)
            spin.emit("activate")  # Enter; focus-out and flush take the same path
            assert changes == [], (spec.key, text)
            assert spin.get_value() == value
        if spec.key != "offset":  # 0 is a valid offset: GTK itself reads "" as 0 there
            for text in ("", "abc"):
                spin.set_text(text)
                spin.update()  # the policy alone reverts a value below the minimum
                assert changes == [], (spec.key, text)


def test_flush_sends_a_number_typed_without_enter():
    for spec, value, typed, expected in [
        (FORM.theme.field("thickness"), 10, "20", 20),
        (FORM.edge_panel.field("length"), 300, "200", 200),
    ]:
        row, changes, _ = row_for(spec, value)
        spin = getattr(row.editor, "number", row.editor.widget)
        spin.set_text(typed)
        row.flush()
        assert changes == [(("theme", "x"), expected)], spec.key
        spin.set_text("abc")
        row.flush()
        assert len(changes) == 1  # invalid text sends nothing


def test_a_value_changed_back_is_queued_with_the_shown_value_as_its_base():
    """The queue then un-queues it (settings.queue): an inherited value is not pinned."""
    queued = []
    row, changes, _ = row_for(FORM.theme.field("thickness"), 10, queued=queued)
    row.editor.widget.set_value(11)
    row.editor.widget.set_value(10)
    assert queued == [(("theme", "x"), 11, 10), (("theme", "x"), 10, 10)] and changes == []


def test_choosing_the_same_colour_writes_nothing():
    row, changes, _ = row_for(FORM.theme.field("accent"), "#8fd3b6")
    row.editor.widget.emit("color-set")
    assert changes == []


def test_a_choice_not_in_the_list_clears_the_selection():
    row, _, _ = row_for(FORM.theme.section("handle_style").field("shape"), "chevron")
    row.show_value(FieldValue("bogus", False, "default"))
    assert row.editor.widget.get_active_id() is None


def test_a_text_row_sends_on_enter_or_flush_only_when_changed():
    row, changes, _ = row_for(FORM.edge_panel.field("name"), "Dock")
    entry = row.editor.widget
    assert entry.get_text() == "Dock" and not row.editor.dirty()
    entry.emit("activate")
    assert changes == []
    entry.set_text("Dock 2")
    assert row.editor.dirty()
    entry.emit("activate")
    entry.set_text("Bottom dock")  # typed, Enter not pressed: the window is closing
    row.flush()
    assert changes == [(("theme", "x"), "Dock 2"), (("theme", "x"), "Bottom dock")]


def test_a_text_row_shows_an_unset_value_as_empty():
    row, changes, _ = row_for(FieldSpec("font", "Font", "text"), None)
    assert row.editor.widget.get_text() == "" and not row.editor.dirty() and changes == []


def test_a_disabled_choice_is_greyed_out_and_never_sent():
    spec = FieldSpec(
        "panel",
        "Panel type",
        "enum",
        choices=("edge", "corner", "float"),
        labels=("Edge", "Corner", "Float (coming soon)"),
        disabled=("float",),
        required=True,
    )
    row, changes, _ = row_for(spec, "edge")
    combo = row.editor.widget

    def sensitive(combo):
        model, (cell,) = combo.get_model(), combo.get_cells()
        out = []
        for i in range(3):  # what GTK does for each row before it draws it
            combo.get_area().apply_attributes(model, model.get_iter(i), False, False)
            out.append(cell.get_property("sensitive"))
        return out

    assert sensitive(combo) == [True, True, False]
    plain, _, _ = row_for(dataclasses.replace(spec, disabled=()), "edge")
    assert sensitive(plain.editor.widget) == [True, True, True]
    combo.set_active_id("float")  # chosen programmatically: not sent, edge comes back
    assert changes == [] and combo.get_active_id() == "edge"
    combo.set_active_id("corner")
    assert changes == [(("theme", "x"), "corner")]


def test_a_required_key_has_no_reset_button():
    row, _, _ = row_for(FORM.edge_panel.field("name"), "Dock", is_set=True)
    assert not row.reset.get_sensitive()


def test_a_text_row_takes_no_more_characters_than_the_schema_allows():
    name = FORM.edge_panel.field("name")
    assert name.max_length == 40
    row, _, _ = row_for(name, "Dock")
    assert row.editor.widget.get_max_length() == 40
    row, _, _ = row_for(FieldSpec("font", "Font", "text"), None)
    assert row.editor.widget.get_max_length() == 0  # no limit in the schema: none


def test_activating_or_leaving_an_unset_text_row_sends_nothing():
    row, changes, _ = row_for(FieldSpec("font", "Font", "text"), None)
    row.editor.widget.emit("activate")
    row.editor.widget.emit("focus-out-event", Gdk.Event.new(Gdk.EventType.FOCUS_CHANGE))
    row.flush()
    assert changes == []


def test_a_text_row_sends_when_the_entry_loses_focus():
    row, changes, _ = row_for(FORM.edge_panel.field("name"), "Dock")
    entry = row.editor.widget
    entry.set_text("Dock 3")
    assert entry.emit("focus-out-event", Gdk.Event.new(Gdk.EventType.FOCUS_CHANGE)) is False
    assert changes == [(("theme", "x"), "Dock 3")]


def test_a_combo_opens_below_itself_with_every_entry():
    """Phil: a dropdown opened one entry high with a scrollbar. wrap_width 1 takes GTK's
    popup path that anchors the menu below the combo (settings.fields.opens_below)."""
    shape, _, _ = row_for(FORM.theme.section("handle_style").field("shape"), "auto")
    length, _, _ = row_for(FORM.edge_panel.field("length"), 300)
    for combo in (shape.editor.widget, length.editor.mode):
        assert combo.get_wrap_width() == 1
        menu = combo.get_popup_accessible().get_widget()  # built by GTK, never shown here
        assert len(menu.get_children()) == len(combo.get_model())  # one item per entry


def test_a_toggle_is_centred_in_its_row_with_a_round_knob():
    """Phil: thinner, with a round knob. The row is about 30 px high (its Reset button); the
    switch keeps its own height, so its content stays 2:1 and the knob a circle."""
    from settings.style import BORDER_PX, KNOB_PX, SWITCH_CLASS, TRACK_PADDING_PX

    row, _, _ = row_for(FORM.theme.section("border").field("enabled"), True)
    row.show_all()  # widget flags only: no window exists
    alloc = Gdk.Rectangle()
    alloc.width = row.get_preferred_width().natural_width
    alloc.height = row.get_preferred_height().natural_height
    row.size_allocate(alloc)
    switch = row.editor.widget
    assert switch.get_style_context().has_class(SWITCH_CLASS)
    assert switch.get_allocated_height() == switch.get_preferred_height().minimum_height
    assert switch.get_allocated_height() < alloc.height  # centred, not stretched
    edge = 2 * (TRACK_PADDING_PX + BORDER_PX)
    assert switch.get_allocated_width() - edge == 2 * (switch.get_allocated_height() - edge)
    assert switch.get_allocated_height() - edge == KNOB_PX


def test_a_toggle_installs_the_stylesheet(monkeypatch):
    calls = []
    monkeypatch.setattr(fields, "install_css", lambda: calls.append(1))
    fields.BoolEditor(lambda _v: None)
    assert calls == [1]


def test_a_bounded_number_is_a_slider_beside_a_spin_with_one_value():
    queued = []
    row, changes, _ = row_for(FORM.theme.field("thickness"), 10, queued=queued)
    editor = row.editor
    assert isinstance(editor, fields.SliderEditor)
    assert editor.outer.get_children() == [editor.scale, editor.widget]
    assert editor.outer.is_ancestor(row)  # the row packs the box of both
    adjustment = editor.scale.get_adjustment()
    assert (adjustment.get_lower(), adjustment.get_upper()) == (5.0, 64.0)
    assert editor.scale.get_value() == editor.widget.get_value() == 10
    assert not editor.scale.get_draw_value()  # the spin button shows the number
    assert editor.scale.get_accessible().get_name() == "Thickness"
    editor.scale.set_value(20)  # the slider moves the spin button
    assert editor.widget.get_value() == 20
    editor.widget.set_value(30)  # and the spin button the slider
    assert editor.scale.get_value() == 30
    assert queued == [(("theme", "x"), 20, 10), (("theme", "x"), 30, 10)] and changes == []


def test_a_slider_drag_is_one_queued_edit_and_a_drag_back_none():
    """Every whole number on the way is pushed; the view's queue keeps the last one per row,
    and dragging back to the shown value un-queues it (an inherited value stays inherited)."""
    from settings.queue import EditQueue

    queue = EditQueue()
    row = fields.FieldRow(FORM.theme.field("thickness"), ("theme", "t"), id, id, queue.push)
    row.show_value(FieldValue(10, False, "default"))
    for value in range(11, 31):
        row.editor.scale.set_value(value)
    assert [(e.path, e.value) for e in queue] == [(("theme", "t"), 30)]
    for value in range(29, 9, -1):
        row.editor.scale.set_value(value)
    assert len(queue) == 0


def test_a_slider_sends_whole_numbers_and_takes_its_keys():
    row, changes, _ = row_for(FORM.theme.field("thickness"), 10)
    scale = row.editor.scale
    scale.emit("change-value", Gtk.ScrollType.JUMP, 12.6)  # a drag between two values
    assert scale.get_value() == 13 and changes[-1] == (("theme", "x"), 13)
    assert type(changes[-1][1]) is int
    scale.emit("move-slider", Gtk.ScrollType.STEP_FORWARD)  # Right arrow
    assert changes[-1][1] == 14
    scale.emit("move-slider", Gtk.ScrollType.END)  # End
    assert changes[-1][1] == 64
    scale.emit("move-slider", Gtk.ScrollType.START)  # Home
    assert changes[-1][1] == 5


def _key(scale, keyval):
    event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
    event.keyval = keyval
    scale.emit("key-press-event", event)
    return event  # held by the caller while the handler runs


def test_a_slider_pages_by_a_tenth_of_its_range_and_page_up_raises_the_value():
    spec = FieldSpec("font_size", "Font size", "int", minimum=6, maximum=96)
    row, changes, _ = row_for(spec, 6)
    assert row.editor.adjustment.get_page_increment() == 9
    _key(row.editor.scale, Gdk.KEY_Page_Up)
    assert changes[-1][1] == 15  # Page Up: up by a page
    _key(row.editor.scale, Gdk.KEY_Page_Up)
    assert changes[-1][1] == 24
    _key(row.editor.scale, Gdk.KEY_Page_Down)
    assert changes[-1][1] == 15  # Page Down: down by a page
    _key(row.editor.scale, Gdk.KEY_KP_Page_Up)
    assert changes[-1][1] == 24
    for _ in range(20):
        _key(row.editor.scale, Gdk.KEY_Page_Up)
    assert changes[-1][1] == 96  # clamped
    for _ in range(20):
        _key(row.editor.scale, Gdk.KEY_Page_Down)
    assert changes[-1][1] == 6


def _mouse(scale, kind, button=1):
    event = Gdk.Event.new(kind)
    event.button.button = button
    scale.emit(
        "button-press-event" if kind == Gdk.EventType.BUTTON_PRESS else "button-release-event",
        event,
    )
    return event


def _queue_row():
    from settings.queue import EditQueue

    queue = EditQueue()
    row = fields.FieldRow(FORM.theme.field("thickness"), ("theme", "t"), id, id, queue.push)
    row.show_value(FieldValue(10, False, "default"))
    return row, queue


def test_a_slider_drag_queues_nothing_until_the_button_is_released():
    row, queue = _queue_row()
    scale, spin = row.editor.scale, row.editor.widget
    held = _mouse(scale, Gdk.EventType.BUTTON_PRESS)
    for value in (12, 20, 31):
        scale.set_value(value)  # the pointer moves; a slow mouse pauses on the way
        assert len(queue) == 0
        assert spin.get_value() == value  # the number follows the drag live
    assert row.unsent()  # the drag is not applied yet
    released = _mouse(scale, Gdk.EventType.BUTTON_RELEASE)
    assert [(e.path, e.value) for e in queue] == [(("theme", "t"), 31)]
    assert not row.unsent()
    assert held and released


def test_a_slider_drag_that_ends_where_it_began_writes_nothing():
    row, queue = _queue_row()
    held = _mouse(row.editor.scale, Gdk.EventType.BUTTON_PRESS)
    row.editor.scale.set_value(40)
    row.editor.scale.set_value(10)
    released = _mouse(row.editor.scale, Gdk.EventType.BUTTON_RELEASE)
    assert len(queue) == 0 and held and released


def test_a_click_on_the_trough_writes_on_release():
    row, queue = _queue_row()
    held = _mouse(row.editor.scale, Gdk.EventType.BUTTON_PRESS)
    row.editor.scale.set_value(50)  # the press moved the slider to the click
    assert len(queue) == 0
    released = _mouse(row.editor.scale, Gdk.EventType.BUTTON_RELEASE)
    assert [e.value for e in queue] == [50] and held and released


def test_a_broken_grab_or_lost_focus_ends_the_slider_drag():
    for signal, make in (
        ("grab-broken-event", lambda: Gdk.Event.new(Gdk.EventType.GRAB_BROKEN)),
        ("focus-out-event", lambda: Gdk.Event.new(Gdk.EventType.FOCUS_CHANGE)),
    ):
        row, queue = _queue_row()
        held = _mouse(row.editor.scale, Gdk.EventType.BUTTON_PRESS)
        row.editor.scale.set_value(25)
        assert len(queue) == 0
        event = make()
        row.editor.scale.emit(signal, event)
        assert [e.value for e in queue] == [25], signal
        row.editor.scale.set_value(26)  # no longer dragging: the pause behaviour
        assert [e.value for e in queue] == [26], signal
        assert held and event


def test_a_flush_during_a_slider_drag_applies_the_current_value():
    row, queue = _queue_row()
    held = _mouse(row.editor.scale, Gdk.EventType.BUTTON_PRESS)
    row.editor.scale.set_value(33)
    assert row.unsent()
    row.flush()  # Undo, Save or a structural edit
    assert [e.value for e in queue] == [33] and not row.unsent() and held
    row.editor.scale.set_value(34)  # the drag went on after the flush: still released later
    _mouse(row.editor.scale, Gdk.EventType.BUTTON_RELEASE)
    assert [e.value for e in queue] == [34]


def test_a_refresh_during_a_slider_drag_keeps_the_dragged_value():
    row, queue = _queue_row()
    held = _mouse(row.editor.scale, Gdk.EventType.BUTTON_PRESS)
    row.editor.scale.set_value(33)
    row.show_value(FieldValue(10, False, "default"), keep_pending=True)
    assert row.editor.scale.get_value() == 33 and held


def test_slider_keys_and_the_spin_buttons_keep_the_pause_behaviour():
    row, queue = _queue_row()
    _key(row.editor.scale, Gdk.KEY_Right)
    row.editor.scale.emit("move-slider", Gtk.ScrollType.STEP_FORWARD)
    assert [e.value for e in queue] == [11]
    row.editor.widget.spin(Gtk.SpinType.STEP_FORWARD, 1)  # a spin arrow
    assert [e.value for e in queue] == [12]


def test_a_wide_or_open_range_keeps_its_spin_button():
    for spec in (
        FORM.edge_panel.field("offset"),
        FORM.edge_panel.field("depth"),
        FORM.theme.field("duration_ms"),
        FORM.corner_panel.field("width"),
    ):
        row, _, _ = row_for(spec, 100)
        assert isinstance(row.editor, fields.IntEditor), spec.key
        assert row.editor.outer is row.editor.widget


def test_an_unset_optional_slider_shows_its_minimum_and_sends_nothing():
    row, changes, _ = row_for(
        FieldSpec("font_size", "Font size", "int", minimum=6, maximum=96), None
    )
    assert row.editor.scale.get_value() == 6 and not row.unsent()
    row.flush()
    assert changes == []


def test_a_widget_font_row_picks_a_family_or_resets_to_the_theme_font(fonts):
    spec = FieldSpec("font", "Font", "font")
    changes, resets = [], []
    row = fields.FieldRow(spec, ("p", "font"), lambda p, v: changes.append((p, v)), resets.append)
    row.show_value(FieldValue(None, False, "widget default"))
    picker = row.editor.picker
    assert picker.label.get_text() == fields.THEME_FONT  # unset: the theme's font
    picker.fill()
    assert picker.visible_labels()[:2] == [fields.THEME_FONT, "Noto Sans (system font)"]
    picker.search.set_text("fira")
    picker.search.emit("activate")
    assert changes == [(("p", "font"), "Fira Mono")] and resets == []
    picker.fill()
    picker.list.emit("row-activated", picker.list.get_row_at_index(0))  # "Theme font"
    assert resets == [("p", "font")] and len(changes) == 1  # reset: nothing written
    assert not row.unsent()


def test_a_widget_font_that_is_not_installed_is_shown_and_kept(fonts):
    row, changes, resets = row_for(FieldSpec("font", "Font", "font"), "Gone Font", is_set=True)
    picker = row.editor.picker
    picker.fill()
    assert picker.label.get_text() == "Gone Font"
    assert picker.visible_labels()[1] == "Gone Font (not installed)"
    row.flush()
    assert changes == resets == []


def allocated(widget, width=None):
    """Lay an unshown widget out at its preferred size (no window is mapped)."""
    widget.show_all()
    minimum, natural = widget.get_preferred_width()
    width = max(minimum, width or natural)
    height = widget.get_preferred_height_for_width(width).natural_height
    rect = Gdk.Rectangle()
    rect.x, rect.y, rect.width, rect.height = 0, 0, width, height
    widget.size_allocate(rect)
    return width, height


def centre(widget):
    return widget.get_allocation().y + widget.get_allocation().height / 2


def row_label(row):
    return next(c for c in row.get_children()[0].get_children() if isinstance(c, Gtk.Label))


@pytest.mark.parametrize("count", [3, 50])
def test_the_font_rows_reset_button_label_and_note_stay_one_entry_high(fonts, count):
    """A row's reset button was packed with valign FILL: beside a font list it stretched to the
    list's whole height (30 x 136 px for 3 fonts, 30 x 1781 for 50). Label and reset are level
    with the FIRST picker."""
    row, _c, _r = row_for(FORM.theme.field("font"), [f"Font {i}" for i in range(count)])
    allocated(row)
    editor_height = row.editor.outer.get_allocated_height()
    assert editor_height > 100 * count / 4  # the list itself is tall ...
    assert row.reset.get_allocated_height() <= 40  # ... its row's button is not
    assert row.source.get_allocated_height() <= 40
    first = centre(row.editor.lines[0].box)
    assert abs(centre(row_label(row)) - first) <= 2
    assert abs(centre(row.reset) - first) <= 2


ALIGNED = [
    ("theme", "accent", "#8fd3b6", lambda e: e.widget),
    ("theme.section.handle_style", "shape", "bar", lambda e: e.widget),
    ("edge_panel", "min_length", 100, lambda e: e.widget),
    ("theme", "thickness", 10, lambda e: e.widget),  # slider row: the spin button
    ("theme.section.border", "enabled", True, lambda e: e.widget),
    ("edge_panel", "name", "Dock", lambda e: e.widget),
    ("edge_panel", "length", "50%", lambda e: e.mode),
]


def aligned_spec(where, key):
    node = FORM.theme if where.startswith("theme") else FORM.edge_panel
    if "." in where:
        node = node.section(where.split(".")[-1])
    return node.field(key)


@pytest.mark.parametrize("where, key, value, control", ALIGNED)
def test_every_rows_label_is_level_with_its_control(where, key, value, control):
    row, _c, _r = row_for(aligned_spec(where, key), value)
    allocated(row)
    assert abs(centre(row_label(row)) - centre(control(row.editor))) <= 2


def test_the_font_picker_row_label_is_level_with_its_control(fonts):
    row, _c, _r = row_for(FieldSpec("font", "Font", "font"), None)
    allocated(row)
    assert abs(centre(row_label(row)) - centre(row.editor.widget)) <= 2


def line_names(editor):
    return [
        [line.buttons[a].get_accessible().get_name() for a in ("up", "down", "remove")]
        for line in editor.lines
        if line.box.get_visible()
    ]


def test_the_font_line_buttons_have_names_of_their_own_that_follow_the_list(fonts):
    row, _c, _r = row_for(FORM.theme.field("font"), ["A", "B", "C"])
    assert line_names(row.editor) == [
        ["Move font 1 up", "Move font 1 down", "Remove font 1 from the list"],
        ["Move font 2 up", "Move font 2 down", "Remove font 2 from the list"],
        ["Move font 3 up", "Move font 3 down", "Remove font 3 from the list"],
    ]
    row.editor.lines[2].buttons["remove"].clicked()
    row.editor.add_button.clicked()
    row.editor.add_button.clicked()
    names = line_names(row.editor)
    assert [n[0] for n in names] == [f"Move font {i} up" for i in range(1, 5)]
    assert len({n for line in names for n in line}) == 12  # all distinct
    row.show_value(FieldValue(["X"], True, "your config"))  # a re-read: one line
    assert line_names(row.editor) == [
        ["Move font 1 up", "Move font 1 down", "Remove font 1 from the list"]
    ]


@pytest.fixture
def focused_list(fonts):
    """A font list of 3 in an unshown window, realized so that focus can move."""
    row, changes, _ = row_for(FORM.theme.field("font"), ["A", "B", "C"])
    window = Gtk.Window()
    window.add(row)
    row.show_all()
    window.realize()
    yield row.editor, window, changes
    window.destroy()


def test_focus_follows_a_font_that_is_moved(focused_list):
    editor, window, _changes = focused_list
    editor.lines[1].buttons["down"].grab_focus()
    editor.lines[1].buttons["down"].clicked()  # B moves to the end, where Move down is dead
    assert window.get_focus() is editor.lines[2].buttons["up"]  # Move down is insensitive there
    editor.lines[2].buttons["up"].clicked()  # and up again: B is the middle line, same button
    assert window.get_focus() is editor.lines[1].buttons["up"]
    editor.lines[1].buttons["up"].clicked()  # B first: Move up is insensitive, Move down is kept
    assert window.get_focus() is editor.lines[0].buttons["down"]


def test_focus_after_a_remove_goes_to_the_last_or_the_next_line(focused_list):
    editor, window, _changes = focused_list
    editor.lines[2].buttons["remove"].grab_focus()
    editor.lines[2].buttons["remove"].clicked()  # the last line: the previous one's button
    assert window.get_focus() is editor.lines[1].buttons["remove"]
    editor.add_button.clicked()
    editor.lines[0].buttons["remove"].clicked()  # the first: the font that took its place
    assert editor.fonts == ["B", "Noto Sans"]
    assert window.get_focus() is editor.lines[0].buttons["remove"]
    editor.lines[0].buttons["remove"].clicked()  # one font left: its Remove is dead,
    assert editor.fonts == ["Noto Sans"]  # focus goes to Add font
    assert window.get_focus() is editor.add_button


def test_focus_after_add_font_goes_to_the_new_lines_picker(focused_list):
    editor, window, _changes = focused_list
    editor.add_button.grab_focus()
    editor.add_button.clicked()
    assert len(editor.fonts) == 4
    assert window.get_focus() is editor.lines[3].picker.button


def test_removed_lines_stay_hidden_when_the_page_is_shown_again(fonts):
    row, _c, _r = row_for(FORM.theme.field("font"), ["A", "B", "C"])
    row.show_all()
    editor = row.editor
    editor.lines[2].buttons["remove"].clicked()
    assert not editor.lines[2].box.get_visible()
    row.show_all()  # what a page's show_all does after a rebuild
    assert not editor.lines[2].box.get_visible() and editor.lines[0].box.get_visible()
    assert editor.lines[2].box.get_no_show_all()


def test_a_widget_font_rows_inherited_label_is_the_theme_font_constant():
    assert fields.THEME_FONT == "Theme font"  # the text the window shows, once, literally
    picker = fields.FontEditor(lambda _v: None).picker
    assert picker.inherit_label == fields.THEME_FONT
    picker.set(None)
    assert picker.label.get_text() == "Theme font"


def test_a_font_line_reads_move_up_move_down_remove():
    assert [a for a, _i, _t in fields.FONT_LINE_BUTTONS] == ["up", "down", "remove"]
    row, _, _ = row_for(FORM.theme.field("font"), ["A", "B"])
    line = row.editor._line(0)
    kids = line.box.get_children()
    assert kids[1:] == [line.buttons[a] for a in ("up", "down", "remove")]  # packed from the start
