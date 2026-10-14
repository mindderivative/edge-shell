"""settings.fields: the GTK row of each field kind (widgets only; no window is shown)."""

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, Gtk  # noqa: E402

if not Gtk.init_check()[0]:
    pytest.skip("no display", allow_module_level=True)

import settings.fields as fields  # noqa: E402
from settings.form import FieldSpec, config_form  # noqa: E402
from settings.values import FieldValue  # noqa: E402

FORM = config_form(("clock", "dock", "system_bar"))


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
    timers = []
    monkeypatch.setattr(fields.GLib, "timeout_add", lambda ms, fn: timers.append((ms, fn)) or 7)
    monkeypatch.setattr(fields.GLib, "source_remove", lambda _id: None)
    row, changes, _ = row_for(FORM.theme.field("thickness"), 10)
    spin = row.editor.widget
    assert tuple(spin.get_range()) == (2.0, 64.0)
    spin.set_value(11)
    spin.set_value(12)
    assert changes == []  # waits for the pause
    assert [ms for ms, _fn in timers] == [fields.DEBOUNCE_MS, fields.DEBOUNCE_MS]
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
    for widget in (mode.editor.widget, thickness.editor.widget, length.editor.mode):
        assert scroll(widget) is False  # not handled: the page's ScrolledWindow scrolls
    scroll(length.editor.number)
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
    form = config_form(("box", "clock"), corner_widgets=("box",))
    row, _, _ = row_for(form.edge_panel.field("widget"), "clock")
    assert [r[0] for r in row.editor.widget.get_model()] == ["clock", "box (corner panel)"]
    row.editor.widget.set_active_id("box")
    assert row.editor.widget.get_active_text() == "box (corner panel)"


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
