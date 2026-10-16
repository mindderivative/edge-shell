"""settings.view: pages, edits through the session, undo, revert, hand edits. The view is a
plain Gtk.Box: no window is created."""

import os
from typing import Annotated

import pytest
from pydantic import Field

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
pytest.importorskip("tomlkit")

from gi.repository import Gdk, GLib, Gtk  # noqa: E402

if not Gtk.init_check()[0]:
    pytest.skip("no display", allow_module_level=True)

from settings.panels import PanelEditor  # noqa: E402
from settings.screens import mode_of  # noqa: E402
from settings.session import SettingsSession  # noqa: E402
from settings.view import SettingsView  # noqa: E402
from shell.outputs import Output  # noqa: E402
from shell.panel_spec import CornerDefaults, PanelDefaults  # noqa: E402
from shell.widget import Widget, WidgetProps  # noqa: E402

USER = """\
# gate config
[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]
panel = "edge"
name = "dock"
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


def drain():
    """Run what is waiting on the loop (a titled change rebuilds its pages when idle)."""
    ctx = GLib.MainContext.default()
    while ctx.iteration(False):
        pass


def pages(view):
    return [view.stack.child_get_property(c, "name") for c in view.stack.get_children()]


def row(view, path):
    return next(r for r in view.rows if r.path == path)


def shown_mode(view, screen="HDMI-A-1"):
    """The `shell` value the toolbar's checkboxes show for `screen` (its page shown)."""
    view.show_page(f"monitor:{screen}")
    return mode_of(view.toolbar.edge.get_active(), view.toolbar.native.get_active())


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
    assert shown_mode(view, "DP-1") == "plasma"  # not in the file: the default
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
    assert view.session.history


def test_an_invalid_edit_shows_its_error_under_the_row(make):
    view, path = make()
    view._on_change(("monitors", "HDMI-A-1", "panels", 0, "pos"), 400)
    align = ("monitors", "HDMI-A-1", "panels", 0, "align")
    view._on_change(align, "end")
    drain()
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
    drain()
    view._on_change((*P0, "corner"), "top-right")
    drain()
    view._on_change((*P0, "edge"), "right")
    drain()
    view._on_reset((*P0, "corner"))  # back to the bottom-left corner: no right edge there
    drain()
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
    drain()
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
    assert not view.session.history


def test_the_visible_page_survives_a_rebuild(make):
    view, _ = make()
    view.stack.set_visible_child_name("monitor:DP-1")
    view.rebuild()
    assert view.stack.get_visible_child_name() == "monitor:DP-1"


def test_a_hand_edit_is_reloaded_and_announced(make):
    view, path = make()
    path.write_text(USER.replace('shell = "edge"', 'shell = "both"'))
    view.file_changed()
    assert shown_mode(view) == "both"
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
    (preview,) = view.previews["HDMI-A-1"]  # on the monitor page
    assert not preview.get_visible()
    view._on_change(("monitors", "HDMI-A-1", "panels", 0, "length"), 3000)
    assert preview.get_visible() and "monitors.HDMI-A-1" in preview.get_text()


P0 = ("monitors", "HDMI-A-1", "panels", 0)


def test_a_dock_turned_into_a_corner_widget_is_one_edit(make, corner_registry):
    """Spec 19: the widget and the keys only the old kind takes change in ONE write (one
    reload); the entry then shows the corner rows, and its title follows."""
    view, path = make()
    view._on_change((*P0, "align"), "end")
    drain()
    view._on_change((*P0, "widget"), "box")
    drain()
    assert len(view.session.history) == 2  # align, then widget + unset align together
    text = path.read_text()
    assert (
        'panel = "corner"\nname = "dock"\nwidget = "box"' in text
        and "align" not in text
        and "# gate config" in text
    )
    assert row(view, (*P0, "corner")).editor.widget.get_active_id() == "bottom-left"
    assert not any(r.path == (*P0, "align") for r in view.rows)
    expander = panel_editor(view).expanders[0]
    assert expander.get_label() == "1. dock: bottom-left, from bottom, 300x390"  # its name stays
    assert expander.get_expanded()


def test_a_new_corner_drops_an_edge_it_does_not_have(make, corner_registry):
    view, path = make()
    view._on_change((*P0, "widget"), "box")
    drain()
    view._on_change((*P0, "edge"), "left")
    drain()
    view._on_change((*P0, "corner"), "top-right")
    drain()
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
    import settings.view as view_module

    monkeypatch.setattr(view_module.GLib, "timeout_add", lambda _ms, _fn: 3)
    monkeypatch.setattr(view_module.GLib, "source_remove", lambda _id: None)
    view, path = make()
    row(view, DEPTH).editor.widget.set_value(120)  # inside the 400 ms pause
    assert "depth" not in path.read_text()
    view.flush()
    assert "depth = 120" in path.read_text()


@pytest.fixture
def pending(monkeypatch):
    """Spin pauses never fire on their own: a typed value stays pending until flushed."""
    import settings.view as view_module

    monkeypatch.setattr(view_module.GLib, "timeout_add", lambda _ms, _fn: 3)
    monkeypatch.setattr(view_module.GLib, "source_remove", lambda _id: None)


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
    path.write_text(USER.replace('shell = "edge"', 'shell = "both"'))
    view.file_changed()
    assert shown_mode(view) == "both"
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
    drain()
    assert title(view) != plain
    view._on_reset((*P0, "edge"))
    drain()
    assert title(view) == plain and panel_editor(view).expanders[0].get_expanded()

    view._on_change((*P0, "widget"), "box")
    drain()
    boxed = title(view)
    view._on_change((*P0, "width"), 400)
    drain()
    assert title(view) != boxed
    view._on_reset((*P0, "width"))
    drain()
    assert title(view) == boxed and panel_editor(view).expanders[0].get_expanded()


def test_reset_of_a_corner_gives_the_edge_combo_the_default_corners_edges(make, corner_registry):
    view, _ = make()
    view._on_change((*P0, "widget"), "box")
    drain()
    before = (title(view), edge_choices(view))
    view._on_change((*P0, "corner"), "top-right")
    drain()
    assert edge_choices(view)[0] == ["top", "right"]
    view._on_reset((*P0, "corner"))
    drain()
    assert (title(view), edge_choices(view)) == before
    assert edge_choices(view)[1] is not None


@pytest.fixture
def timers(monkeypatch):
    """Spin pauses never fire on their own, but their timer ids are real (a flush cancels)."""
    import settings.view as view_module

    monkeypatch.setattr(view_module.GLib, "timeout_add", lambda _ms, _fn: 3)
    monkeypatch.setattr(view_module.GLib, "source_remove", lambda _id: None)


THICKNESS = ("monitors", "HDMI-A-1", "theme", "thickness")


def test_flush_applies_every_pending_value_even_when_one_rebuilds_the_page(
    make, corner_registry, timers
):
    view, path = make()
    view._on_change((*P0, "widget"), "box")
    drain()
    row(view, (*P0, "width")).editor.widget.set_value(420)  # a title key: its write rebuilds
    row(view, THICKNESS).editor.widget.set_value(17)  # a later row on the same page
    view.flush()
    text = path.read_text()
    assert "width = 420" in text and "thickness = 17" in text
    assert "420x" in title(view)


def test_flush_rebuilds_once_at_the_end(make, corner_registry, timers):
    view, _ = make()
    view._on_change((*P0, "widget"), "box")
    drain()
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
    path.write_text(USER.replace('shell = "edge"', 'shell = "both"'))
    view.revert()
    assert view.banner.get_visible() and "changed outside" in view.banner_label.get_text()
    assert "depth" not in path.read_text() and 'shell = "both"' in path.read_text()


def test_file_changed_with_pending_rows_rebuilds_once(make, timers):
    view, path = make()
    rebuilds = []
    original = view.rebuild
    view.rebuild = lambda: (rebuilds.append(1), original())
    row(view, DEPTH).editor.widget.set_value(120)
    path.write_text(USER.replace('shell = "edge"', 'shell = "both"'))
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
    drain()
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


def test_an_invalid_file_leaves_the_toolbar_without_a_screen(make):
    view, path = make()
    view.show_page("monitor:HDMI-A-1")
    assert view.toolbar.screen == "HDMI-A-1"
    path.write_text('[monitors.HDMI-A-1]\nshell = "sideways"\n')  # invalid: no refresh runs
    view.file_changed()
    assert view.toolbar.screen is None and not view.toolbar.edge.get_sensitive()
    assert not view.toolbar.add_button.get_sensitive()


MIN_LENGTH, MAX_LENGTH = (*P0, "min_length"), (*P0, "max_length")


def type_into(view, path, value):
    """A user edit of a spin row: the value typed, then its 400 ms pause over (the queue)."""
    r = row(view, path)
    r.editor.widget.set_value(value)
    view._queue_due()
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


def test_a_rebuild_from_a_widgets_own_signal_destroys_that_widget_only_when_idle(make):
    """The align combo's "changed" (a title key) rebuilds the page. Destroying the combo inside
    its own emission let GTK finish the emission (the popup menu hiding, popup-shown) on a
    finalized widget: g_object_notify / g_object_set "G_IS_OBJECT" criticals in the settings
    terminal. The old pages leave the stack at once and are destroyed when the loop is idle."""
    view, path = make()
    combo = row(view, (*P0, "align")).editor.widget
    destroyed = []
    combo.connect("destroy", lambda *_a: destroyed.append(combo))
    combo.set_active_id("end")  # as the user's pick in the popup does
    assert 'align = "end"' in path.read_text()
    assert not destroyed and combo.get_parent() is not None  # alive through its emission
    drain()
    assert row(view, (*P0, "align")).editor.widget is not combo  # the page was rebuilt
    assert destroyed == [combo]


def test_a_hand_edit_drops_the_queue_and_its_timer_at_once(make, monkeypatch):
    """The old rows are destroyed when the loop is idle: no queued value may be written
    meanwhile, and none is lost without a word."""
    started, removed = [], []
    monkeypatch.setattr(GLib, "timeout_add", lambda _ms, _fn: started.append(7) or 7)
    monkeypatch.setattr(GLib, "source_remove", removed.append)
    view, path = make()
    row(view, DEPTH).editor.widget.set_value(120)
    assert view.queue.pending(DEPTH) and started == [7]
    path.write_text(USER.replace('shell = "edge"', 'shell = "both"'))
    view.file_changed()  # a hand edit: rebuild; the queue was made for the old file
    assert len(view.queue) == 0 and removed == [7] and not view._queue_timer
    assert "monitors.HDMI-A-1.panels[0].depth = 120" in view.banner_label.get_text()


def test_the_revert_dialog_says_where_an_invalid_hand_edit_is_kept(make):
    view, path = make()
    assert "before-revert" not in view.revert_text()
    path.write_text(USER + "[monitors.DP-2]\nmode = 'edgee'\n")
    view.file_changed()  # a hand edit with a typo: read-only banner, Revert all enabled
    assert "config.toml.before-revert" in view.revert_text()
    view.revert()
    assert path.read_text() == USER
    assert path.with_name("config.toml.before-revert").read_text().endswith("'edgee'\n")
    assert "before-revert" not in view.revert_text()


TWO_PANELS = (
    USER + '\n[[monitors.HDMI-A-1.panels]]\npanel = "edge"\nname = "clock"\nwidget = "clock"\n'
)
SWAPPED = (
    '# gate config\n[monitors.HDMI-A-1]\nshell = "edge"\n\n'
    '[[monitors.HDMI-A-1.panels]]\npanel = "edge"\nname = "clock"\nwidget = "clock"\n\n'
    '[[monitors.HDMI-A-1.panels]]\npanel = "edge"\nname = "dock"\nwidget = "dock"\n'
)


def test_a_flush_that_met_a_hand_edit_applies_no_further_row(make, pending):
    """The first row's apply is refused (the file was edited by hand); the rows after it must
    not be applied onto the re-read file."""
    view, path = make()
    row(view, DEPTH).editor.widget.set_value(120)
    row(view, THICKNESS).editor.widget.set_value(17)
    path.write_text(USER.replace('shell = "edge"', 'shell = "both"'))
    view.flush()
    assert path.read_text() == USER.replace('shell = "edge"', 'shell = "both"')
    assert view.refused_outside and not view.save_failed
    assert view.banner.get_visible() and "changed outside" in view.banner_label.get_text()
    view.flush()  # a later, clean flush forgets it
    assert not view.refused_outside


def test_a_structural_edit_after_a_refused_flush_is_not_applied(make, pending):
    view, path = make()
    panel_editor(view).add("clock")
    row(view, DEPTH).editor.widget.set_value(120)  # pending on the dock (entry 0)
    path.write_text(SWAPPED)  # by hand: the clock is entry 0 now
    panel_editor(view).remove(1)  # the user meant the clock
    assert path.read_text() == SWAPPED
    assert view.banner.get_visible() and "changed outside" in view.banner_label.get_text()


def test_undo_after_a_refused_flush_does_nothing_more(make, pending):
    view, path = make()
    view._on_change(SHELL, "both")
    row(view, DEPTH).editor.widget.set_value(120)
    path.write_text(USER)  # by hand
    view.undo()
    assert path.read_text() == USER and not view.session.history


FONT = ("theme", "font")


def test_typed_fonts_never_reach_the_file_through_a_hand_edit_rebuild(make):
    """The rebuild unparents the focused entry and GTK sends focus-out: the retired row's
    commit must not write the typed fonts onto the re-read file."""
    view, path = make()
    old = row(view, FONT)
    old.editor.widget.set_text("Typed Font")
    path.write_text(USER.replace('shell = "edge"', 'shell = "both"'))
    view.file_changed()
    old.editor.commit()  # the focus-out of the retired entry
    old.flush()
    assert "Typed Font" not in path.read_text() and not view.session.history


TILE_USER = """\
[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]
panel = "edge"
name = "Tile"
widget = "tile"
size = 12
"""


class TileProps(WidgetProps):
    size: Annotated[int, Field(ge=6, le=96)] = 10


@pytest.fixture
def tile_view(tmp_path, corner_registry):
    corner_registry.register_widget(
        "tile",
        title="Tile",
        props=TileProps,
        edge=PanelDefaults(edge="top", length=200, depth=50, label="tile"),
        corner=CornerDefaults(corner="top-right", width=240, height=200, label="tile"),
    )(type("Tile", (Widget,), {}))
    path = tmp_path / "config.toml"
    path.write_text(TILE_USER)
    return SettingsView(SettingsSession(path), [HDMI]), path


def test_renaming_a_panel_retitles_it_and_keeps_it_open(make):
    view, path = make()
    view._on_change((*P0, "name"), "Bottom dock")
    drain()
    expander = panel_editor(view).expanders[0]
    assert expander.get_label() == "1. Bottom dock: bottom, center" and expander.get_expanded()
    assert 'name = "Bottom dock"' in path.read_text()


def test_a_name_used_twice_is_not_written(make):
    view, path = make()
    panel_editor(view).add("clock")  # a new panel named after the widget's title: "Clock"
    assert 'name = "Clock"' in path.read_text()
    name = ("monitors", "HDMI-A-1", "panels", 1, "name")
    view._on_change(name, "dock")
    assert "names must be unique: 'dock' is used by panels[0] and panels[1]" in (
        row(view, name).error.get_text()
    )
    assert path.read_text().count('name = "dock"') == 1


def test_a_widget_property_is_a_row_and_a_key_of_the_entry(tile_view):
    view, path = tile_view
    size = (*P0, "size")
    assert row(view, size).editor.widget.get_value() == 12
    view._on_change(size, 30)
    assert "size = 30" in path.read_text()
    view._on_change(size, 2)  # below the model's bound: refused under the row
    assert "greater than or equal to 6" in row(view, size).error.get_text()
    assert "size = 30" in path.read_text()


def test_switching_the_widget_drops_its_property_keys_in_one_write(tile_view):
    view, path = tile_view
    view._on_change((*P0, "widget"), "dock")
    drain()
    text = path.read_text()
    assert 'widget = "dock"' in text and "size" not in text and 'name = "Tile"' in text
    assert len(view.session.history) == 1
    assert not any(r.path == (*P0, "size") for r in view.rows)  # the Widget rows went too


def test_the_panel_type_of_a_two_kind_widget_is_switched_in_one_write(tile_view):
    view, path = tile_view
    view._on_change((*P0, "panel"), "corner")
    drain()
    assert 'panel = "corner"' in path.read_text() and len(view.session.history) == 1
    assert panel_editor(view).expanders[0].get_label() == "1. Tile: top-right, from top, 240x200"
    view._on_change((*P0, "panel"), "float")  # listed, greyed out; refused if it gets through
    drain()
    assert "float panels are not implemented yet" in row(view, (*P0, "panel")).error.get_text()


def test_the_widget_list_shows_the_display_names(tmp_path, corner_registry):
    path = tmp_path / "config.toml"
    path.write_text(USER)
    view = SettingsView(SettingsSession(path), [HDMI])
    assert view.form.edge_panel.field("widget").labels == ("Bar", "Box", "Clock", "Dock")


def test_a_titled_change_from_a_focus_out_rebuilds_only_when_idle(make):
    """The name entry's focus-out runs before the click on Remove or Move is released: the
    rebuild waits for the loop, so that button is not unparented under the click."""
    view, path = make()
    entry = row(view, (*P0, "name")).editor.widget
    remove_button = next(w for w in walk(panel_editor(view)) if isinstance(w, Gtk.Button))
    entry.set_text("Bottom dock")
    entry.emit("focus-out-event", Gdk.Event.new(Gdk.EventType.FOCUS_CHANGE))
    assert 'name = "Bottom dock"' in path.read_text()  # written at once
    assert row(view, (*P0, "name")).editor.widget is entry  # but the rows are still these
    assert entry.get_toplevel() is not entry and remove_button.get_parent() is not None
    drain()
    assert row(view, (*P0, "name")).editor.widget is not entry  # rebuilt once idle
    assert panel_editor(view).expanders[0].get_label().startswith("1. Bottom dock")


def test_a_rename_keeps_the_other_rows_pending_values(tile_view, pending):
    view, path = tile_view
    size = (*P0, "size")
    row(view, size).editor.widget.set_value(30)  # inside the 400 ms pause
    view._on_change((*P0, "name"), "Big clock")  # the rename rebuilds the page
    drain()
    text = path.read_text()
    assert "size = 30" in text and 'name = "Big clock"' in text
    assert row(view, size).editor.widget.get_value() == 30


def _count_rebuilds(view):
    rebuilds = []
    original = view.rebuild
    view.rebuild = lambda: (rebuilds.append(1), original())
    return rebuilds


def test_a_titled_change_with_a_pending_title_value_rebuilds_once_and_only_when_idle(
    make, corner_registry, pending
):
    view, path = make()
    view._on_change((*P0, "widget"), "box")
    drain()
    rebuilds = _count_rebuilds(view)
    row(view, (*P0, "width")).editor.widget.set_value(420)  # pending; its write is titled too
    view._on_change((*P0, "name"), "Big box")  # as a name entry's focus-out does
    assert rebuilds == []  # nothing rebuilt inside the focus-out
    drain()
    assert len(rebuilds) == 1
    text = path.read_text()
    assert "width = 420" in text and 'name = "Big box"' in text


def test_a_title_key_reset_applies_the_other_rows_pending_values_first(
    make, corner_registry, pending
):
    view, path = make()
    view._on_change((*P0, "widget"), "box")
    view._on_change((*P0, "width"), 350)
    drain()
    rebuilds = _count_rebuilds(view)
    row(view, THICKNESS).editor.widget.set_value(17)  # pending on another row
    view._on_reset((*P0, "width"))
    assert rebuilds == []
    drain()
    assert len(rebuilds) == 1
    text = path.read_text()
    assert "thickness = 17" in text and "width = 350" not in text


def test_the_panel_list_buttons_do_not_take_the_focus_on_click(make):
    """A press on Remove, Move or Add must not move the focus out of the name entry: its
    focus-out would rebuild the page before the click is released."""
    view, _ = make()
    ours = ("Move up", "Move down", "Remove this panel")
    buttons = [
        w
        for w in walk(panel_editor(view))
        if isinstance(w, Gtk.Button)
        and (w.get_tooltip_text() in ours or w.get_label() == "Add panel")
    ]
    assert len(buttons) == 4 and not any(b.get_focus_on_click() for b in buttons)


def test_the_view_reports_every_change_of_state_including_a_save(make):
    view, _ = make()
    states = []
    view._on_state = lambda: states.append(1)
    view._on_change(DEPTH, 90)
    assert states  # a write refreshes
    states.clear()
    assert view.save() is True
    assert states  # the saved point moved


def test_save_after_a_refused_flush_copies_nothing_and_keeps_the_warning(make, pending):
    view, path = make()
    row(view, DEPTH).editor.widget.set_value(120)  # typed, inside the spin's pause
    hand = USER.replace('shell = "edge"', 'shell = "both"')
    path.write_text(hand)  # by hand
    assert view.save() is False
    assert path.read_text() == hand and not path.with_name("config.toml.bak").exists()
    assert view.banner.get_visible() and "changed outside" in view.banner_label.get_text()


def test_redo_after_a_refused_flush_does_nothing_more(make, pending):
    view, path = make()
    view._on_change(SHELL, "both")
    view.undo()
    row(view, DEPTH).editor.widget.set_value(120)
    path.write_text(USER.replace('shell = "edge"', 'shell = "none"'))  # by hand
    view.redo()
    assert 'shell = "none"' in path.read_text() and "both" not in path.read_text()
    assert "changed outside" in view.banner_label.get_text()


def test_a_successful_save_clears_an_old_error_banner(make):
    view, _ = make()
    view.show_banner("Not saved: an old error")
    assert view.banner.get_visible()
    assert view.save() is True
    assert not view.banner.get_visible()


@pytest.mark.parametrize("text", ["A & B", "<b>x</b>", "HDMI & <DP>"])
def test_a_heading_with_markup_characters_is_shown_as_text(text):
    assert SettingsView._heading(text).get_text() == text


# ---- the info note keeps its blue background and light text, focused or not ----------------
def test_the_info_note_css_has_the_class_colours_and_a_backdrop_rule():
    from settings.view import INFO_NOTE_CLASS, INFO_NOTE_CSS

    assert f".{INFO_NOTE_CLASS}" in INFO_NOTE_CSS
    assert "#2b5c8a" in INFO_NOTE_CSS  # the background
    assert "#ffffff" in INFO_NOTE_CSS  # the text
    assert ":backdrop" in INFO_NOTE_CSS  # an unfocused window keeps both


def test_the_info_note_css_is_valid_and_installed_once():
    from settings import view as view_module

    provider = Gtk.CssProvider()
    provider.load_from_data(view_module.INFO_NOTE_CSS.encode())  # raises on a parse error
    first = view_module.install_info_note_css()
    assert view_module.install_info_note_css() is first  # a second call reuses it


def test_an_info_banner_gets_the_class_and_others_do_not(make):
    from settings.view import INFO_NOTE_CLASS

    view, _ = make()
    context = view.banner.get_style_context()
    view.show_banner("note", Gtk.MessageType.INFO)
    assert context.has_class(INFO_NOTE_CLASS)
    view.show_banner("oops")
    assert not context.has_class(INFO_NOTE_CLASS)
    view.show_banner("careful", Gtk.MessageType.WARNING)
    assert not context.has_class(INFO_NOTE_CLASS)


# ---- the edit queue (settings.queue) ---------------------------------------------------------


@pytest.fixture
def clock(monkeypatch):
    """The queue's pause timer, by hand: (started ids, removed ids, fire())."""
    started, removed, callbacks = [], [], {}

    def add(_ms, fn):
        started.append(10 + len(started))
        callbacks[started[-1]] = fn
        return started[-1]

    monkeypatch.setattr(GLib, "timeout_add", add)
    monkeypatch.setattr(GLib, "source_remove", removed.append)
    return started, removed, lambda: callbacks[started[-1]]()


def written_in_order(view):
    """The keys each write added, in order (from the undo history and the file)."""
    texts = [*view.session.history, view.session.text]
    return [
        next(line for line in b.splitlines() if line not in a.splitlines())
        for a, b in zip(texts, texts[1:], strict=False)
    ]


def test_spin_edits_of_several_rows_share_one_pause_and_apply_in_order(make, clock):
    started, removed, fire = clock
    view, path = make()
    row(view, DEPTH).editor.widget.set_value(120)
    row(view, THICKNESS).editor.widget.set_value(17)
    assert started == [10, 11] and removed == [10]  # one timer, started again by each edit
    assert "depth" not in path.read_text()
    fire()  # the pause is over
    assert written_in_order(view) == ["depth = 120", "theme.thickness = 17"]
    assert len(view.queue) == 0 and not view._queue_timer


def test_an_edit_applied_at_once_comes_after_the_queued_ones(make, clock):
    view, path = make()
    row(view, DEPTH).editor.widget.set_value(120)
    view._on_change(SHELL, "both")  # a combo or a checkbox: applied now
    assert written_in_order(view) == ["depth = 120", 'shell = "both"']


def test_a_spin_changed_back_within_the_pause_writes_nothing(make, clock):
    view, path = make()
    spin = row(view, DEPTH).editor.widget
    spin.set_value(90)
    spin.set_value(64)  # back to the widget default it showed
    view.flush()
    assert path.read_text() == USER and not view.session.history


def test_a_rebuild_applies_the_queued_edits_first_and_runs_once(make, clock):
    view, path = make()
    rebuilds = _count_rebuilds(view)
    row(view, DEPTH).editor.widget.set_value(120)
    view.rebuild()  # e.g. Detect monitors
    assert "depth = 120" in path.read_text() and len(view.queue) == 0
    assert row(view, DEPTH).editor.widget.get_value() == 120
    assert len(rebuilds) == 2  # the call, and the one it runs after the queue


def test_a_hand_edit_met_while_applying_names_every_dropped_edit(make, clock):
    view, path = make()
    row(view, DEPTH).editor.widget.set_value(120)
    row(view, THICKNESS).editor.widget.set_value(17)
    hand = USER.replace('shell = "edge"', 'shell = "both"')
    path.write_text(hand)
    view.flush()
    assert path.read_text() == hand
    text = view.banner_label.get_text()
    assert "changed outside" in text and "Not applied" in text
    assert "monitors.HDMI-A-1.panels[0].depth = 120" in text
    assert "monitors.HDMI-A-1.theme.thickness = 17" in text


def test_typed_text_dropped_by_a_hand_edit_is_named(make):
    view, path = make()
    row(view, FONT).editor.widget.set_text("Typed Font")
    path.write_text(USER.replace('shell = "edge"', 'shell = "both"'))
    view.file_changed()
    assert "theme.font (typed text)" in view.banner_label.get_text()


def test_the_deferred_rebuild_applies_what_was_queued_meanwhile_once(make, clock):
    view, path = make()
    view._on_change((*P0, "name"), "Bottom dock")  # a title key: rebuilt when idle
    rebuilds = _count_rebuilds(view)
    row(view, DEPTH).editor.widget.set_value(120)  # queued before the loop is idle
    drain()
    assert "depth = 120" in path.read_text() and 'name = "Bottom dock"' in path.read_text()
    assert len(rebuilds) == 1


def test_revert_drops_the_queue_without_a_word(make, clock):
    view, path = make()
    view._on_change(SHELL, "both")
    row(view, DEPTH).editor.widget.set_value(120)
    view.revert()
    assert path.read_text() == USER and len(view.queue) == 0
    assert "Not applied" not in view.banner_label.get_text()


def test_a_retired_view_starts_nothing_later(make, clock):
    started, removed, _ = clock
    view, path = make()
    row(view, DEPTH).editor.widget.set_value(120)
    view.retire()
    assert removed == started and len(view.queue) == 0


# ---- what a drain that meets a hand edit says, and the queue's guards --------------------------

INVALID = '[monitors.HDMI-A-1]\nshell = "sideways"\n'


def _fire(view, clock):
    clock[2]()
    drain()  # the rebuild the timer path defers runs when idle


@pytest.mark.parametrize("how", ["timer", "flush", "save", "undo"])
def test_dropped_edits_are_named_after_an_invalid_hand_edit_rebuild(make, clock, how):
    """The rebuild of an invalid file writes its own banner: the dropped edits and the warning
    are added after it, whichever way the queue was applied."""
    view, path = make()
    row(view, DEPTH).editor.widget.set_value(120)
    path.write_text(INVALID)
    if how == "timer":
        _fire(view, clock)
    else:
        getattr(view, how)()
        drain()
    text = view.banner_label.get_text()
    assert "is not valid" in text and "changed outside" in text
    assert "Not applied" in text and "monitors.HDMI-A-1.panels[0].depth = 120" in text
    assert path.read_text() == INVALID and len(view.queue) == 0


def test_typed_text_is_named_when_a_timer_drain_meets_a_hand_edit(make, clock):
    view, path = make()
    row(view, DEPTH).editor.widget.set_value(120)
    row(view, FONT).editor.widget.set_text("Typed Font")
    path.write_text(USER.replace('shell = "edge"', 'shell = "both"'))
    _fire(view, clock)
    text = view.banner_label.get_text()
    assert "theme.font (typed text)" in text and "panels[0].depth = 120" in text


def test_typed_text_is_named_when_an_immediate_edit_meets_a_hand_edit(make):
    view, path = make()
    row(view, FONT).editor.widget.set_text("Typed Font")
    path.write_text(USER.replace('shell = "edge"', 'shell = "both"'))
    view._on_change(SHELL, "both")
    drain()
    text = view.banner_label.get_text()
    assert "theme.font (typed text)" in text and "changed outside" in text


def test_a_refused_revert_names_the_edits_it_dropped(make, clock):
    view, path = make()
    row(view, DEPTH).editor.widget.set_value(120)
    row(view, FONT).editor.widget.set_text("Typed Font")
    hand = USER.replace('shell = "edge"', 'shell = "both"')
    path.write_text(hand)
    view.revert()  # refused: the hand edit is the new starting point
    text = view.banner_label.get_text()
    assert "changed outside" in text and "Not applied" in text
    assert "panels[0].depth = 120" in text and "theme.font (typed text)" in text
    assert path.read_text() == hand and len(view.queue) == 0


def test_typed_text_is_sent_by_a_flush(make, pending):
    """Text typed and not entered (no Enter, no focus-out) is still applied by the barrier."""
    view, path = make()
    spin = row(view, DEPTH).editor.widget
    spin.set_text("130")
    assert view.save() and "depth = 130" in path.read_text()
    row(view, FONT).editor.widget.set_text("Typed Font")
    view.flush()
    assert "Typed Font" in path.read_text()


def test_a_nested_run_of_the_queue_inside_a_flush_does_nothing(make, clock):
    """Typed text sent by a flush calls _on_change: it must not drain the queue itself (it
    would clear the flush's flags in the middle of it)."""
    view, path = make()
    view.queue.push(DEPTH, 120)
    view._flushing = True
    view._run_queue()
    assert view._flushing and len(view.queue) == 1 and "depth" not in path.read_text()


def test_a_flush_leaves_no_pause_timer(make, clock):
    started, removed, _ = clock
    view, path = make()
    row(view, DEPTH).editor.widget.set_value(120)
    assert view._queue_timer
    view.flush()
    assert not view._queue_timer and removed == started


def test_a_destroyed_view_writes_nothing_and_leaves_no_timer(make, clock):
    started, removed, _ = clock
    view, path = make()
    row(view, DEPTH).editor.widget.set_value(120)
    view.destroy()  # the window closed during the pause
    assert path.read_text() == USER and len(view.queue) == 0
    assert not view._queue_timer and removed == started


def test_the_not_applied_list_is_capped_at_eight_entries(make):
    from settings.queue import QueuedEdit

    view, _path = make()
    edits = [QueuedEdit(("theme", f"key{i}"), i) for i in range(11)]
    view._tell_dropped(edits, [])
    text = view.banner_label.get_text()
    assert "theme.key7 = 7" in text and "theme.key8" not in text and "... and 3 more" in text
    view._tell_dropped(edits[:8], [])
    assert "more" not in view.banner_label.get_text().splitlines()[-1]


# ---- the tree and the tabbed pages (panel/widget spec 7) -----------------------------------


def notebook(view, page):
    return next(w for w in walk(view.stack.get_child_by_name(page)) if isinstance(w, Gtk.Notebook))


def tabs(view, page):
    nb = notebook(view, page)
    return [nb.get_tab_label_text(c) for c in nb.get_children()]


def current_tab(view, page):
    nb = notebook(view, page)
    return nb.get_tab_label_text(nb.get_nth_page(nb.get_current_page()))


def show_tab(view, page, title):
    notebook(view, page).set_current_page(tabs(view, page).index(title))  # as a click does


def texts(widget):
    return [w.get_text() for w in walk(widget) if isinstance(w, Gtk.Label)]


def click_row(view, page):
    """Select a tree row as a click does."""
    view.tree.list.select_row(view.tree.row_of(page))


def test_the_tree_lists_the_theme_and_the_monitors_beside_the_pages(make):
    view, _ = make()
    assert [p for p, _t in view.tree.rows()][:2] == ["theme", "monitor:HDMI-A-1"]
    assert ("monitor:DP-1", "DP-1") in view.tree.rows()
    assert view.tree.selected() == "theme" == view.stack.get_visible_child_name()
    paned = view.tree.get_parent()
    assert isinstance(paned, Gtk.Paned) and paned.get_child2() is view.stack
    assert view.tree.get_size_request()[0] >= 200


def test_selecting_a_tree_row_shows_its_page(make):
    view, _ = make()
    click_row(view, "monitor:DP-1")
    assert view.stack.get_visible_child_name() == "monitor:DP-1"


def test_the_theme_page_has_its_tabs(make):
    view, _ = make()
    assert tabs(view, "theme") == ["General", "Borders", "Shadows", "Handle", "Layout"]
    assert "Theme (every monitor)" in texts(view.stack.get_child_by_name("theme"))


def test_a_monitor_page_has_the_theme_tabs_under_an_override_banner(make):
    view, _ = make()
    assert tabs(view, "monitor:HDMI-A-1")[:5] == tabs(view, "theme")
    page = view.stack.get_child_by_name("monitor:HDMI-A-1")
    assert any("These values override the Theme for HDMI-A-1" in t for t in texts(page))
    accent = row(view, ("monitors", "HDMI-A-1", "theme", "accent"))
    assert accent.source.get_text() == "global theme"  # not set here: the Theme's value
    assert row(view, ("monitors", "HDMI-A-1", "layout", "gap")).source.get_text() == (
        "px between neighbouring panels · global layout"
    )


def test_a_rebuild_keeps_the_page_and_its_tab(make):
    view, _ = make()
    click_row(view, "monitor:HDMI-A-1")
    show_tab(view, "monitor:HDMI-A-1", "Borders")
    view._on_change(("monitors", "HDMI-A-1", "theme", "border", "width"), 4)
    view.rebuild()
    assert view.stack.get_visible_child_name() == "monitor:HDMI-A-1"
    assert view.tree.selected() == "monitor:HDMI-A-1"
    assert current_tab(view, "monitor:HDMI-A-1") == "Borders"
    assert current_tab(view, "theme") == "General"  # each page keeps its own


def test_a_page_that_is_gone_after_a_hand_edit_falls_back_to_the_theme(make):
    view, path = make(outputs=())
    click_row(view, "monitor:HDMI-A-1")
    path.write_text('[theme]\naccent = "#112233"\n')  # by hand: no monitor any more
    view.file_changed()
    assert pages(view) == ["theme"]
    assert view.stack.get_visible_child_name() == "theme" == view.tree.selected()


def test_an_invalid_file_shows_only_the_theme_in_the_tree(make):
    view, path = make()
    path.write_text('[monitors.HDMI-A-1]\nshell = "sideways"\n')
    view.file_changed()
    assert view.tree.rows() == [("theme", "Theme")]
    assert not view.tree.hint.get_visible()  # not "connect a monitor": the file is the problem
    assert not view.stack.get_child_by_name("theme").get_sensitive()


def test_a_later_part_of_a_tab_has_its_own_heading(make):
    view, _ = make()
    nb = notebook(view, "theme")
    handle = nb.get_nth_page(tabs(view, "theme").index("Handle"))
    assert "Handle style" in texts(handle)
    borders = nb.get_nth_page(tabs(view, "theme").index("Borders"))
    assert "Border" not in texts(borders)  # one part: no heading


# ---- review of Tasks 5 and 6: banner colours, window width, rows once per page --------------


def leaf_paths(section, prefix):
    """Every field path of `section` at `prefix`, its sub-sections included."""
    paths = [(*prefix, spec.key) for spec in section.fields]
    for sub in section.sections:
        paths += leaf_paths(sub, (*prefix, sub.key))
    return paths


def page_paths(view, page):
    """The paths of the rows on `page`, the panel rows left out (their own tests)."""
    prefix = ("theme",) if page == "theme" else ("monitors", page.partition(":")[2])
    return [r.path for r in view.rows if r.path[: len(prefix)] == prefix and "panels" not in r.path]


def test_every_key_of_the_form_is_on_its_page_exactly_once(make):
    view, _ = make()
    form = view.form
    theme_page = [*leaf_paths(form.theme, ("theme",)), *leaf_paths(form.layout, ("layout",))]
    paths = [r.path for r in view.rows if r.path[0] != "monitors"]
    assert sorted(paths) == sorted(theme_page)  # each once: no key missing, none twice
    for name in ("HDMI-A-1", "DP-1"):
        prefix = ("monitors", name)
        expected = [
            *leaf_paths(form.theme, (*prefix, "theme")),
            *leaf_paths(form.layout, (*prefix, "layout")),
        ]  # the monitor's own keys (shell) are the toolbar's now
        assert sorted(page_paths(view, f"monitor:{name}")) == sorted(expected)


def banner_of(view, page):
    page_widget = view.stack.get_child_by_name(page)
    return [w for w in walk(page_widget) if isinstance(w, Gtk.InfoBar)]


def test_the_override_banner_keeps_the_info_notes_colours(make):
    from settings.view import INFO_NOTE_CLASS

    view, _ = make()
    (bar,) = banner_of(view, "monitor:HDMI-A-1")
    assert bar.get_style_context().has_class(INFO_NOTE_CLASS)  # not the theme's orange or white


def test_the_theme_page_has_no_override_banner(make):
    view, _ = make()
    assert banner_of(view, "theme") == []
    assert not any("override" in t for t in texts(view.stack.get_child_by_name("theme")))


def test_the_banner_is_hidden_on_the_panels_tab_only(make):
    view, _ = make()
    (bar,) = banner_of(view, "monitor:HDMI-A-1")
    assert bar.get_visible()
    show_tab(view, "monitor:HDMI-A-1", "Panels")  # the panel list is not a Theme override
    assert not bar.get_visible()
    show_tab(view, "monitor:HDMI-A-1", "Layout")
    assert bar.get_visible()


def test_the_banner_is_hidden_after_a_rebuild_on_the_panels_tab(make):
    view, _ = make()
    show_tab(view, "monitor:HDMI-A-1", "Panels")
    view.rebuild()
    (bar,) = banner_of(view, "monitor:HDMI-A-1")
    assert current_tab(view, "monitor:HDMI-A-1") == "Panels" and not bar.get_visible()


def test_a_monitor_page_is_sensitive_and_the_theme_page_too(make):
    view, _ = make()
    assert view.stack.get_child_by_name("monitor:HDMI-A-1").get_sensitive()
    assert view.stack.get_child_by_name("monitor:DP-1").get_sensitive()
    assert view.stack.get_child_by_name("theme").get_sensitive()


def test_a_monitor_page_is_headed_by_its_tree_title(make):
    view, _ = make(outputs=(HDMI,))  # DP-1 is not connected, but the config knows it
    view.session.apply(lambda d: d.set(("monitors", "DP-1", "shell"), "edge"))
    view.rebuild()
    assert "HDMI-A-1" in texts(view.stack.get_child_by_name("monitor:HDMI-A-1"))
    assert "DP-1 (not connected)" in texts(view.stack.get_child_by_name("monitor:DP-1"))


def test_the_window_can_be_narrow(make):
    view, _ = make()
    view.show_all()  # a widget flag only: no window exists to show it
    assert view.get_preferred_width().minimum_width < 800  # 947 px after the tabs (was 757)


def test_a_default_size_of_860_is_honoured(make):
    view, _ = make()
    window = Gtk.Window()  # never shown
    window.add(view)
    window.set_default_size(860, 680)
    view.show_all()
    assert window.get_preferred_width().minimum_width <= 860
    assert window.get_default_size() == (860, 680)
    window.remove(view)
    window.destroy()


def test_a_tab_scrolls_sideways_rather_than_widening_the_window(make):
    view, _ = make()
    for page in ("theme", "monitor:HDMI-A-1"):
        nb = notebook(view, page)
        scrollers = nb.get_children()
        assert scrollers and all(s.get_policy()[0] == Gtk.PolicyType.AUTOMATIC for s in scrollers)


# ---- the per-screen toolbar ------------------------------------------------------------------


def test_the_toolbar_follows_the_selected_screen(make):
    view, _ = make()
    assert view.toolbar.screen is None  # the Theme page
    click_row(view, "monitor:HDMI-A-1")
    assert view.toolbar.screen == "HDMI-A-1"
    assert (view.toolbar.edge.get_active(), view.toolbar.native.get_active()) == (True, False)
    click_row(view, "theme")
    assert view.toolbar.screen is None and not view.toolbar.edge.get_sensitive()


def test_a_checkbox_writes_the_mode_in_one_change(make):
    view, path = make()
    click_row(view, "monitor:HDMI-A-1")
    view.toolbar.native.set_active(True)  # as a click does: edge + native
    assert 'shell = "both"' in path.read_text() and len(view.session.history) == 1
    view.toolbar.edge.set_active(False)
    view.toolbar.native.set_active(False)
    assert 'shell = "none"' in path.read_text()
    assert shown_mode(view) == "none"


def test_a_monitor_with_no_shell_key_shows_the_default(make):
    view, path = make()
    assert shown_mode(view, "DP-1") == "plasma"  # in no file: plasma
    view.toolbar.edge.set_active(True)  # writes a [monitors.DP-1] table (a test file only)
    assert '[monitors.DP-1]\nshell = "both"' in path.read_text()


def test_a_refused_mode_change_shows_the_mode_in_the_file(make):
    view, path = make()
    click_row(view, "monitor:HDMI-A-1")
    hand = USER.replace('shell = "edge"', 'shell = "plasma"')
    path.write_text(hand)  # by hand, not seen yet
    view.toolbar.native.set_active(True)  # the user meant edge -> both
    drain()
    assert path.read_text() == hand
    assert "changed outside" in view.banner_label.get_text()
    assert shown_mode(view) == "plasma"  # the re-read file, not the click


def test_add_puts_the_chosen_panel_on_the_selected_screen(make):
    view, path = make()
    click_row(view, "monitor:HDMI-A-1")
    view.toolbar.kind.widget.set_active_id("edge:clock")
    view.toolbar.add_button.clicked()
    entries = view.session.user["monitors"]["HDMI-A-1"]["panels"]
    assert entries[-1] == {"panel": "edge", "name": "Clock", "widget": "clock"}
    assert view.stack.get_visible_child_name() == "monitor:HDMI-A-1"


def test_the_mode_row_left_the_monitor_page(make):
    view, _ = make()
    assert not any(r.path == SHELL for r in view.rows)


def test_a_failed_mode_write_shows_the_mode_in_the_file(make, monkeypatch):
    from shell.config.models import ConfigError

    view, path = make()
    click_row(view, "monitor:HDMI-A-1")

    def refuse(_edit):
        raise ConfigError("disk full")

    monkeypatch.setattr(view.session, "apply", refuse)
    view.toolbar.native.set_active(True)  # the user meant edge -> both
    assert "Not saved" in view.banner_label.get_text()
    assert (view.toolbar.edge.get_active(), view.toolbar.native.get_active()) == (True, False)
    assert path.read_text() == USER  # the checkboxes show the file's mode, not the click


def test_the_toolbar_names_no_screen_while_the_config_cannot_be_read(make, monkeypatch):
    view, _ = make()
    click_row(view, "monitor:HDMI-A-1")
    monkeypatch.setattr(view.session, "config", None)
    view._sync_toolbar()
    assert view.toolbar.screen is None


def test_add_a_corner_panel_writes_the_corner_kind(make, corner_registry):
    view, _ = make()
    click_row(view, "monitor:HDMI-A-1")
    view.toolbar.kind.widget.set_active_id("corner:box")
    view.toolbar.add_button.clicked()
    entries = view.session.user["monitors"]["HDMI-A-1"]["panels"]
    assert entries[-1]["panel"] == "corner" and entries[-1]["widget"] == "box"


def test_the_toolbar_shows_a_mode_written_by_another_way(make):
    view, _ = make()
    click_row(view, "monitor:HDMI-A-1")
    view._on_change(SHELL, "both")  # not a click on the toolbar: the checkboxes still follow
    assert (view.toolbar.edge.get_active(), view.toolbar.native.get_active()) == (True, True)
    view.undo()
    assert (view.toolbar.edge.get_active(), view.toolbar.native.get_active()) == (True, False)


def test_the_toolbar_names_a_screen_that_is_not_connected(make):
    view, _ = make(outputs=(HDMI,))
    view.session.apply(lambda d: d.set(("monitors", "DP-1", "shell"), "edge"))
    view.rebuild()
    view.show_page("monitor:DP-1")
    assert view.toolbar.title.get_text() == "DP-1 (not connected)"
    view.show_page("monitor:HDMI-A-1")
    assert view.toolbar.title.get_text() == "HDMI-A-1"
