"""settings.fields: the GTK row of each field kind (widgets only; no window is shown)."""

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
REAL_TIMEOUT_ADD = GLib.timeout_add


@pytest.fixture(autouse=True)
def immediate(monkeypatch):
    """Debounced edits fire at once (no main loop in tests)."""
    monkeypatch.setattr(fields.GLib, "timeout_add", lambda _ms, fn: fn() and 0)


def row_for(spec, value, is_set=False, path=("theme", "x")):
    changes, resets = [], []
    row = fields.FieldRow(spec, path, lambda p, v: changes.append((p, v)), resets.append)
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


def test_int_row_takes_its_bounds_from_the_schema_and_is_debounced(monkeypatch):
    timers, removed = [], []
    monkeypatch.setattr(
        fields.GLib, "timeout_add", lambda ms, fn: timers.append((ms, fn)) or 6 + len(timers)
    )
    monkeypatch.setattr(fields.GLib, "source_remove", removed.append)
    row, changes, _ = row_for(FORM.theme.field("thickness"), 10)
    spin = row.editor.widget
    assert tuple(spin.get_range()) == (2.0, 64.0)
    spin.set_value(11)
    spin.set_value(12)
    assert changes == []  # waits for the pause
    assert [ms for ms, _fn in timers] == [fields.DEBOUNCE_MS, fields.DEBOUNCE_MS]
    assert removed == [7]  # one timer per pause: the first was cancelled by the second edit
    timers[-1][1]()
    assert changes == [(("theme", "x"), 12)]


def test_a_new_value_cancels_a_pending_edit(monkeypatch):
    removed = []
    monkeypatch.setattr(fields.GLib, "timeout_add", lambda _ms, _fn: 9)
    monkeypatch.setattr(fields.GLib, "source_remove", removed.append)
    row, changes, _ = row_for(FORM.theme.field("thickness"), 10)
    row.editor.widget.set_value(11)
    row.show_value(FieldValue(10, False, "default"))  # e.g. the file was re-read
    assert removed == [9] and changes == []


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


def test_flush_sends_a_pending_spin_value_and_typed_fonts(monkeypatch):
    monkeypatch.setattr(fields.GLib, "timeout_add", lambda _ms, _fn: 5)
    monkeypatch.setattr(fields.GLib, "source_remove", lambda _id: None)
    spin, changes, _ = row_for(FORM.theme.field("thickness"), 10)
    spin.editor.widget.set_value(14)
    fonts, changes2, _ = row_for(FORM.theme.field("font"), ["A"])
    fonts.editor.widget.set_text("B, monospace")  # typed, Enter not pressed
    spin.flush()
    fonts.flush()
    assert changes == [(("theme", "x"), 14)]
    assert changes2 == [(("theme", "x"), ["B", "monospace"])]
    spin.flush()
    assert len(changes) == 1  # nothing pending any more


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


def fake_timers(monkeypatch):
    """Debounce timers that never fire on their own: returns (started, removed) id lists."""
    started, removed = [], []

    def add(_ms, _fn):
        started.append(5 + len(started))
        return started[-1]

    monkeypatch.setattr(fields.GLib, "timeout_add", add)
    monkeypatch.setattr(fields.GLib, "source_remove", removed.append)
    return started, removed


def test_a_destroyed_row_cancels_its_pending_edit(monkeypatch):
    started, removed = fake_timers(monkeypatch)
    row, changes, _ = row_for(FORM.theme.field("thickness"), 10)
    row.editor.widget.set_value(30)
    row.destroy()
    assert removed == started and changes == []


def test_a_destroyed_row_never_writes_when_the_loop_runs(monkeypatch):
    monkeypatch.setattr(fields.GLib, "timeout_add", REAL_TIMEOUT_ADD)
    row, changes, _ = row_for(FORM.theme.field("thickness"), 10)
    row.editor.widget.set_value(30)
    row.destroy()
    deadline = GLib.get_monotonic_time() + 500_000
    while GLib.get_monotonic_time() < deadline:
        GLib.MainContext.default().iteration(False)
    assert changes == []


def test_a_refresh_keeps_the_pending_edit_of_another_row(monkeypatch):
    started, removed = fake_timers(monkeypatch)
    thick, changes, _ = row_for(FORM.theme.field("thickness"), 10)
    thick.editor.widget.set_value(30)
    thick.show_value(FieldValue(10, False, "inherited"), keep_pending=True)
    assert removed == [] and thick.editor.widget.get_value() == 30
    assert thick.source.get_text().endswith("inherited")
    thick.flush()
    assert changes == [(("theme", "x"), 30)]
    thick.editor.widget.set_value(12)  # a plain show_value still drops the edit
    thick.show_value(FieldValue(30, True, "your config"))
    assert thick.editor.widget.get_value() == 30 and removed == [started[0], started[1]]


def test_closing_applies_every_row_even_when_each_apply_refreshes_all(monkeypatch):
    fake_timers(monkeypatch)
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


def test_a_toggle_within_the_pause_does_not_drop_a_pending_spin(monkeypatch):
    fake_timers(monkeypatch)
    result, rows = {}, []

    def on_change(path, value):
        result[path[1]] = value
        for row in rows:
            row.show_value(FieldValue(result.get(row.path[1], 10), True, "x"), True)

    thick = fields.FieldRow(FORM.theme.field("thickness"), ("theme", "t"), on_change, id)
    flag = fields.FieldRow(
        FORM.theme.section("border").field("enabled"), ("theme", "b"), on_change, id
    )
    rows[:] = [thick, flag]
    thick.show_value(FieldValue(10, False, "default"))
    flag.show_value(FieldValue(False, False, "default"))
    thick.editor.widget.set_value(14)
    flag.editor.widget.set_active(True)
    thick.flush()
    assert result == {"t": 14, "b": True}


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


def test_flush_sends_a_number_typed_without_enter(monkeypatch):
    fake_timers(monkeypatch)
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


def test_a_value_changed_back_within_the_pause_is_not_written(monkeypatch):
    fake_timers(monkeypatch)
    row, changes, _ = row_for(FORM.theme.field("thickness"), 10, is_set=False)
    row.editor.widget.set_value(11)
    row.editor.widget.set_value(10)
    row.flush()
    assert changes == []  # an inherited value is not pinned by a no-op
    row.editor.widget.set_value(12)
    row.flush()
    assert changes == [(("theme", "x"), 12)]
    row.editor.widget.set_value(12)
    row.flush()
    assert len(changes) == 1


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
