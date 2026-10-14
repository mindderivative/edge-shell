"""settings.view: pages, edits through the session, undo, revert, hand edits. The view is a
plain Gtk.Box: no window is created."""

import os

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
pytest.importorskip("tomlkit")

from gi.repository import Gtk  # noqa: E402

if not Gtk.init_check()[0]:
    pytest.skip("no display", allow_module_level=True)

from settings.panels import PanelEditor  # noqa: E402
from settings.session import SettingsSession  # noqa: E402
from settings.view import SettingsView  # noqa: E402
from shell.outputs import Output  # noqa: E402

USER = """\
# gate config
[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]
widget = "dock"
"""
HDMI = Output("HDMI-A-1", 0, 0, 1920, 1080)
DP = Output("DP-1", 0, 1080, 1920, 1080)
SHELL = ("monitors", "HDMI-A-1", "shell")
DEPTH = ("monitors", "HDMI-A-1", "panels", 0, "depth")


@pytest.fixture
def make(tmp_path, fake_registry):
    path = tmp_path / "config.toml"
    path.write_text(USER)

    def _make(outputs=(HDMI, DP)):
        return SettingsView(SettingsSession(path), list(outputs)), path

    return _make


def pages(view):
    return [view.stack.child_get_property(c, "name") for c in view.stack.get_children()]


def row(view, path):
    return next(r for r in view.rows if r.path == path)


def walk(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from walk(child)


def panel_editor(view, monitor="HDMI-A-1"):
    page = view.stack.get_child_by_name(f"monitor:{monitor}")
    return next(w for w in walk(page) if isinstance(w, PanelEditor))


def test_a_page_for_the_theme_and_each_monitor(make):
    view, _ = make()
    assert pages(view) == ["theme", "monitor:HDMI-A-1", "monitor:DP-1"]
    accent = row(view, ("theme", "accent")).editor.widget.get_rgba()
    assert accent.to_string() == "rgb(143,211,182)"
    assert row(view, ("monitors", "DP-1", "shell")).editor.widget.get_active_id() == "plasma"
    assert row(view, DEPTH).editor.widget.get_value() == 64  # the widget's default


def test_a_configured_monitor_that_is_not_connected_is_listed(make):
    view, _ = make(outputs=())
    assert pages(view) == ["theme", "monitor:HDMI-A-1"]


def test_a_valid_edit_is_written_and_shown(make):
    view, path = make()
    view._on_change(DEPTH, 90)
    assert "depth = 90" in path.read_text() and "# gate config" in path.read_text()
    r = row(view, DEPTH)
    assert r.editor.widget.get_value() == 90 and r.reset.get_sensitive()
    assert view.undo_button.get_sensitive()


def test_an_invalid_edit_shows_its_error_under_the_row(make):
    view, path = make()
    view._on_change(("monitors", "HDMI-A-1", "panels", 0, "pos"), 400)
    align = ("monitors", "HDMI-A-1", "panels", 0, "align")
    view._on_change(align, "end")
    r = row(view, align)
    assert r.error.get_visible() and "pos cannot be combined" in r.error.get_text()
    assert 'align = "end"' not in path.read_text()


def test_reset_removes_the_key(make, corner_registry):
    view, path = make()
    view._on_change(DEPTH, 90)
    view._on_reset(DEPTH)
    assert "depth" not in path.read_text()
    assert row(view, DEPTH).source.get_text().endswith("widget default")

    # resetting a corner also drops an edge the widget's corner cannot hold (one valid edit)
    view._on_change((*P0, "widget"), "box")
    view._on_change((*P0, "corner"), "top-right")
    view._on_change((*P0, "edge"), "right")
    view._on_reset((*P0, "corner"))  # back to the bottom-left corner: no right edge there
    assert "corner =" not in path.read_text() and "edge =" not in path.read_text()
    assert not view.banner.get_visible()
    assert row(view, (*P0, "edge")).source.get_text().endswith("corner default")


def test_adding_and_removing_panels_rebuilds_the_rows(make):
    view, path = make()
    panel_editor(view).add("clock")
    assert any(r.path[:4] == ("monitors", "HDMI-A-1", "panels", 1) for r in view.rows)
    assert panel_editor(view).expanders[1].get_expanded()  # the new panel is open
    panel_editor(view).remove(0)
    assert path.read_text().count("[[monitors.HDMI-A-1.panels]]") == 1
    assert not any(r.path[:4] == ("monitors", "HDMI-A-1", "panels", 1) for r in view.rows)


def test_changing_a_panel_edge_retitles_it_and_keeps_it_open(make):
    view, path = make()
    view._on_change(("monitors", "HDMI-A-1", "panels", 0, "edge"), "top")
    expander = panel_editor(view).expanders[0]
    assert expander.get_label() == "1. dock: top, center" and expander.get_expanded()
    assert 'edge = "top"' in path.read_text()


def test_a_rejected_panel_edit_shows_in_the_banner(make):
    view, path = make()
    panel_editor(view).add("nope")
    assert "unknown widget" in view.banner_label.get_text() and view.banner.get_visible()
    assert path.read_text() == USER


def test_undo_and_revert(make):
    view, path = make()
    view._on_change(DEPTH, 90)
    view._on_change(SHELL, "both")
    view.undo()
    assert "depth = 90" in path.read_text() and 'shell = "edge"' in path.read_text()
    view.revert()
    assert path.read_text() == USER
    assert not view.undo_button.get_sensitive()


def test_the_visible_page_survives_a_rebuild(make):
    view, _ = make()
    view.stack.set_visible_child_name("monitor:DP-1")
    view.rebuild()
    assert view.stack.get_visible_child_name() == "monitor:DP-1"


def test_a_hand_edit_is_reloaded_and_announced(make):
    view, path = make()
    path.write_text(USER.replace('"edge"', '"both"'))
    view.file_changed()
    assert row(view, SHELL).editor.widget.get_active_id() == "both"
    assert view.banner.get_visible() and "changed outside" in view.banner_label.get_text()


def test_our_own_write_does_not_rebuild(make):
    view, _ = make()
    view._on_change(DEPTH, 90)
    rows = list(view.rows)
    view.file_changed()  # the watcher fires for the view's own write
    assert view.rows == rows and not view.banner.get_visible()


def test_an_edit_after_a_hand_edit_is_not_applied(make):
    view, path = make()
    path.write_text(USER + '\n[theme]\naccent = "#112233"\n')
    view._on_change(DEPTH, 90)
    assert "depth" not in path.read_text()
    assert view.banner.get_visible() and "changed outside" in view.banner_label.get_text()


def test_an_invalid_file_is_shown_read_only_with_its_error(make):
    view, path = make()
    path.write_text('[monitors.HDMI-A-1]\nshell = "sideways"\n')
    view.file_changed()
    assert pages(view) == ["theme"]
    assert not view.stack.get_child_by_name("theme").get_sensitive()
    assert "is not valid" in view.banner_label.get_text()
    assert "monitors.HDMI-A-1.shell" in view.banner_label.get_text()


def test_layout_warnings_are_previewed_for_connected_monitors(make):
    view, _ = make()
    preview = view.previews["HDMI-A-1"]
    assert not preview.get_visible()
    view._on_change(("monitors", "HDMI-A-1", "panels", 0, "length"), 3000)
    assert preview.get_visible() and "monitors.HDMI-A-1" in preview.get_text()


P0 = ("monitors", "HDMI-A-1", "panels", 0)


def test_a_dock_turned_into_a_corner_widget_is_one_edit(make, corner_registry):
    """Spec 19: the widget and the keys only the old kind takes change in ONE write (one
    reload); the entry then shows the corner rows, and its title follows."""
    view, path = make()
    view._on_change((*P0, "align"), "end")
    view._on_change((*P0, "widget"), "box")
    assert len(view.session.history) == 2  # align, then widget + unset align together
    text = path.read_text()
    assert 'widget = "box"' in text and "align" not in text and "# gate config" in text
    assert row(view, (*P0, "corner")).editor.widget.get_active_id() == "bottom-left"
    assert not any(r.path == (*P0, "align") for r in view.rows)
    expander = panel_editor(view).expanders[0]
    assert expander.get_label() == "1. box: bottom-left, from bottom, 300x390"
    assert expander.get_expanded()


def test_a_new_corner_drops_an_edge_it_does_not_have(make, corner_registry):
    view, path = make()
    view._on_change((*P0, "widget"), "box")
    view._on_change((*P0, "edge"), "left")
    view._on_change((*P0, "corner"), "top-right")
    assert 'corner = "top-right"' in path.read_text() and "edge = " not in path.read_text()
    edge = row(view, (*P0, "edge"))
    assert [r[0] for r in edge.editor.widget.get_model()] == ["top", "right"]
    assert edge.editor.widget.get_active_id() == "top" and edge.source.get_text() == (
        "corner default"
    )


def test_an_unwritable_folder_shows_in_the_banner(make):
    if os.geteuid() == 0:
        pytest.skip("root can write into a read-only folder")
    view, path = make()
    view._on_change(DEPTH, 90)
    os.chmod(path.parent, 0o500)
    try:
        view.undo()
        view.revert()
    finally:
        os.chmod(path.parent, 0o700)
    assert "cannot write" in view.banner_label.get_text() and view.banner.get_visible()
    assert "depth = 90" in path.read_text()


def test_close_flushes_a_pending_spin_value(make, monkeypatch):
    import settings.fields as fields

    monkeypatch.setattr(fields.GLib, "timeout_add", lambda _ms, _fn: 3)
    monkeypatch.setattr(fields.GLib, "source_remove", lambda _id: None)
    view, path = make()
    row(view, DEPTH).editor.widget.set_value(120)  # inside the 400 ms pause
    assert "depth" not in path.read_text()
    view.flush()
    assert "depth = 120" in path.read_text()


@pytest.fixture
def pending(monkeypatch):
    """Spin pauses never fire on their own: a typed value stays pending until flushed."""
    import settings.fields as fields

    monkeypatch.setattr(fields.GLib, "timeout_add", lambda _ms, _fn: 3)
    monkeypatch.setattr(fields.GLib, "source_remove", lambda _id: None)


def test_another_rows_apply_keeps_a_pending_spin_value(make, pending):
    view, path = make()
    row(view, DEPTH).editor.widget.set_value(120)  # inside the pause
    view._on_change(SHELL, "both")  # refreshes every row
    assert row(view, DEPTH).editor.widget.get_value() == 120
    view.flush()
    assert "depth = 120" in path.read_text() and 'shell = "both"' in path.read_text()


def test_a_pending_value_is_written_before_a_panel_moves(make, pending):
    view, path = make()
    panel_editor(view).add("clock")
    row(view, DEPTH).editor.widget.set_value(120)  # on entry 0, the dock
    panel_editor(view).move(0, 1)
    entry = view.session.user["monitors"]["HDMI-A-1"]["panels"]
    assert [p["widget"] for p in entry] == ["clock", "dock"] and entry[1]["depth"] == 120


def test_a_pending_value_is_written_before_undo_and_revert(make, pending):
    view, path = make()
    view._on_change(SHELL, "both")
    row(view, DEPTH).editor.widget.set_value(120)
    view.undo()  # undoes the pending value's write, not the shell change
    assert 'shell = "both"' in path.read_text() and "depth" not in path.read_text()
    row(view, DEPTH).editor.widget.set_value(130)
    view.revert()
    assert path.read_text() == USER


def test_a_pending_value_does_not_break_a_hand_edit_reload(make, pending):
    view, path = make()
    row(view, DEPTH).editor.widget.set_value(120)
    path.write_text(USER.replace('"edge"', '"both"'))
    view.file_changed()
    assert row(view, SHELL).editor.widget.get_active_id() == "both"
    assert "depth" not in path.read_text()


def edge_choices(view, entry=0):
    combo = row(view, (*("monitors", "HDMI-A-1", "panels", entry), "edge")).editor.widget
    return [r[0] for r in combo.get_model()], combo.get_active_id()


def title(view, entry=0):
    return panel_editor(view).expanders[entry].get_label()


def test_reset_of_a_title_key_retitles_the_panel_and_keeps_it_open(make, corner_registry):
    view, _ = make()
    plain = title(view)
    view._on_change((*P0, "edge"), "top")
    assert title(view) != plain
    view._on_reset((*P0, "edge"))
    assert title(view) == plain and panel_editor(view).expanders[0].get_expanded()

    view._on_change((*P0, "widget"), "box")
    boxed = title(view)
    view._on_change((*P0, "width"), 400)
    assert title(view) != boxed
    view._on_reset((*P0, "width"))
    assert title(view) == boxed and panel_editor(view).expanders[0].get_expanded()


def test_reset_of_a_corner_gives_the_edge_combo_the_default_corners_edges(make, corner_registry):
    view, _ = make()
    view._on_change((*P0, "widget"), "box")
    before = (title(view), edge_choices(view))
    view._on_change((*P0, "corner"), "top-right")
    assert edge_choices(view)[0] == ["top", "right"]
    view._on_reset((*P0, "corner"))
    assert (title(view), edge_choices(view)) == before
    assert edge_choices(view)[1] is not None


@pytest.fixture
def timers(monkeypatch):
    """Spin pauses never fire on their own, but their timer ids are real (a flush cancels)."""
    import settings.fields as fields

    monkeypatch.setattr(fields.GLib, "timeout_add", lambda _ms, _fn: 3)
    monkeypatch.setattr(fields.GLib, "source_remove", lambda _id: None)


THICKNESS = ("monitors", "HDMI-A-1", "theme", "thickness")


def test_flush_applies_every_pending_value_even_when_one_rebuilds_the_page(
    make, corner_registry, timers
):
    view, path = make()
    view._on_change((*P0, "widget"), "box")
    row(view, (*P0, "width")).editor.widget.set_value(420)  # a title key: its write rebuilds
    row(view, THICKNESS).editor.widget.set_value(17)  # a later row on the same page
    view.flush()
    text = path.read_text()
    assert "width = 420" in text and "thickness = 17" in text
    assert "420x" in title(view)


def test_flush_rebuilds_once_at_the_end(make, corner_registry, timers):
    view, _ = make()
    view._on_change((*P0, "widget"), "box")
    rebuilds = []
    original = view.rebuild
    view.rebuild = lambda: (rebuilds.append(1), original())
    row(view, (*P0, "width")).editor.widget.set_value(420)
    row(view, (*P0, "height")).editor.widget.set_value(333)
    row(view, THICKNESS).editor.widget.set_value(17)
    view.flush()
    assert len(rebuilds) == 1


def test_revert_after_a_hand_edit_with_a_pending_value_keeps_the_outside_warning(make, timers):
    view, path = make()
    row(view, DEPTH).editor.widget.set_value(120)
    path.write_text(USER.replace('"edge"', '"both"'))
    view.revert()
    assert view.banner.get_visible() and "changed outside" in view.banner_label.get_text()
    assert "depth" not in path.read_text() and 'shell = "both"' in path.read_text()


def test_file_changed_with_pending_rows_rebuilds_once(make, timers):
    view, path = make()
    rebuilds = []
    original = view.rebuild
    view.rebuild = lambda: (rebuilds.append(1), original())
    row(view, DEPTH).editor.widget.set_value(120)
    path.write_text(USER.replace('"edge"', '"both"'))
    view.file_changed()
    assert len(rebuilds) == 1 and "changed outside" in view.banner_label.get_text()


def test_a_warning_banner_clears_on_the_next_good_edit(make):
    view, _ = make()
    view.show_banner("old", Gtk.MessageType.WARNING)
    view._on_change(DEPTH, 90)
    assert not view.banner.get_visible()


def test_a_banner_clears_after_undo(make):
    view, _ = make()
    view._on_change(DEPTH, 90)
    view.show_banner("old", Gtk.MessageType.WARNING)
    view.undo()
    assert not view.banner.get_visible()


def test_a_rejected_edit_leaves_no_panel_marked_to_open(make):
    view, _ = make()
    view._on_change((*P0, "pos"), 400)
    view._on_change((*P0, "align"), "end")  # a title key, rejected
    assert view._expand == {}
    panel_editor(view).add("nope")  # a structural edit, rejected
    assert view._expand == {}
    view.rebuild()
    assert not panel_editor(view).expanders[0].get_expanded()


def test_the_invalid_file_banner_names_the_restore_command(make):
    view, path = make()
    path.write_text('[monitors.HDMI-A-1]\nshell = "sideways"\n')
    view.file_changed()
    assert "--restore-config" in view.banner_label.get_text()


def test_undo_is_insensitive_after_a_rebuild_with_no_history(make):
    view, path = make()
    view._on_change(DEPTH, 90)
    assert view.undo_button.get_sensitive()
    path.write_text('[monitors.HDMI-A-1]\nshell = "sideways"\n')  # invalid: no refresh runs
    view.file_changed()
    assert not view.session.history and not view.undo_button.get_sensitive()


MIN_LENGTH, MAX_LENGTH = (*P0, "min_length"), (*P0, "max_length")


def type_into(view, path, value):
    """A user edit of a spin row: the value typed, then its 400 ms pause over."""
    r = row(view, path)
    r.editor.widget.set_value(value)
    r.flush()
    return r


def test_a_refused_edit_snaps_back_and_another_rows_reset_leaves_its_row_alone(make):
    """Gate A item 10: min_length 600, max_length 300 refused, then min_length's reset. The
    refused row shows the value in effect at once (not the refused 300 until some other row's
    apply happens to refresh it) and keeps its error until its own next edit or reset."""
    view, path = make()
    type_into(view, MIN_LENGTH, 600)
    refused = type_into(view, MAX_LENGTH, 300)
    assert "max_length" not in path.read_text()
    assert (
        refused.error.get_visible() and "min_length must not be larger" in refused.error.get_text()
    )
    shown = (refused.editor.widget.get_value(), refused.source.get_text())
    assert shown == (60, "px · not set")  # max_length is not set: never the refused 300

    view._on_reset(MIN_LENGTH)
    assert "min_length" not in path.read_text()
    assert (refused.editor.widget.get_value(), refused.source.get_text()) == shown
    assert refused.error.get_visible()  # still true: the 300 was not saved

    type_into(view, MAX_LENGTH, 300)  # the same value again, valid now: written
    assert "max_length = 300" in path.read_text() and not refused.error.get_visible()
