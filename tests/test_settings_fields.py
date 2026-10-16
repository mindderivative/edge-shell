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
    assert tuple(spin.get_range()) == (2.0, 64.0)
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


def test_fonts_row_commits_on_enter_only_when_changed():
    row, changes, _ = row_for(FORM.theme.field("font"), ["Hack Nerd Font Mono", "monospace"])
    entry = row.editor.widget
    assert entry.get_text() == "Hack Nerd Font Mono, monospace"
    entry.emit("activate")
    assert changes == []
    entry.set_text("JetBrains Mono, monospace")
    entry.emit("activate")
    assert changes == [(("theme", "x"), ["JetBrains Mono", "monospace"])]


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
        thickness.editor.widget,
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
    fonts, changes2, _ = row_for(FORM.theme.field("font"), ["A"])
    fonts.editor.widget.set_text("B, monospace")
    assert spin.unsent() and fonts.unsent()
    spin.flush()
    fonts.flush()
    assert queued == [(("theme", "x"), 14, 10)] and changes == []
    assert changes2 == [(("theme", "x"), ["B", "monospace"])]
    spin.flush()
    fonts.flush()
    assert len(queued) == 1 and len(changes2) == 1  # nothing typed any more
    assert not spin.unsent() and not fonts.unsent()


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
    font = fields.FieldRow(FORM.theme.field("font"), ("theme", "f"), on_change, id)
    rows[:] = [thick, font]
    thick.shown, font.shown = 10, ["A"]
    for row in rows:
        row.show_value(FieldValue(row.shown, False, "default"))
    thick.editor.widget.set_value(20)
    font.editor.widget.set_text("B, C")
    for row in rows:  # SettingsView.flush
        row.flush()
    assert result == {"t": 20, "f": ["B", "C"]}


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
