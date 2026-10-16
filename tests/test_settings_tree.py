"""settings.tree: the left column's tree of pages (a plain widget; no window is created)."""

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, GLib, Gtk  # noqa: E402

if not Gtk.init_check()[0]:
    pytest.skip("no display", allow_module_level=True)

from settings.pages import TreeEntry  # noqa: E402
from settings.tree import MIN_WIDTH, NO_MONITORS, SettingsTree  # noqa: E402

ENTRIES = (
    TreeEntry("theme", "Theme"),
    TreeEntry(
        "monitor:HDMI-A-1",
        "HDMI-A-1",
        (TreeEntry("panel:HDMI-A-1:0", "Dock"), TreeEntry("panel:HDMI-A-1:1", "Clock")),
    ),
    TreeEntry("monitor:DP-1", "DP-1", (TreeEntry("panel:DP-1:0", "Bar"),)),
    TreeEntry("monitor:DP-2", "DP-2 (not connected)"),
)


@pytest.fixture
def tree():
    picked, actions = [], []
    t = SettingsTree(picked.append, lambda page, action: actions.append((page, action)))
    t.picked, t.actions = picked, actions
    t.show(ENTRIES)
    yield t
    t.destroy()


def click(tree, page):
    tree.list.select_row(tree.row_of(page))  # as a click (or Up/Down) does


def press(tree, keyval):
    event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
    event.keyval = keyval
    return tree.list.emit("key-press-event", event)


def visible(tree):
    return [r.page for r in tree._rows if r.get_visible()]


def drain():
    ctx = GLib.MainContext.default()
    while ctx.iteration(False):
        pass


def test_the_rows_are_theme_monitors_and_their_panels(tree):
    assert tree.rows() == [
        ("theme", "Theme"),
        ("monitor:HDMI-A-1", "HDMI-A-1"),
        ("panel:HDMI-A-1:0", "Dock"),
        ("panel:HDMI-A-1:1", "Clock"),
        ("monitor:DP-1", "DP-1"),
        ("panel:DP-1:0", "Bar"),
        ("monitor:DP-2", "DP-2 (not connected)"),
    ]
    assert visible(tree) == [p for p, _t in tree.rows()]  # every monitor starts open
    assert tree.is_expanded("monitor:HDMI-A-1") and not tree.is_expanded("monitor:DP-2")
    assert tree.row_of("panel:DP-1:0").get_children()[0].get_margin_start() == 24  # indented
    assert not tree.row_of("monitor:DP-2").arrow.get_visible()  # no panels: no arrow


def test_it_is_at_least_200_px_wide(tree):
    assert MIN_WIDTH == 200 and tree.get_size_request()[0] == 200


def test_a_users_click_asks_for_the_page(tree):
    click(tree, "panel:HDMI-A-1:1")
    assert tree.picked == ["panel:HDMI-A-1:1"] and tree.selected() == "panel:HDMI-A-1:1"


def test_select_by_the_program_does_not_call_back(tree):
    assert tree.select("monitor:DP-1") and tree.selected() == "monitor:DP-1"
    assert tree.picked == []
    assert not tree.select("monitor:nope") and tree.selected() == "monitor:DP-1"
    click(tree, "panel:DP-1:0")  # the program's select leaves the tree answering a user's click
    assert tree.picked == ["panel:DP-1:0"]


def test_the_arrow_collapses_and_the_monitor_stays_collapsed_when_the_rows_change(tree):
    tree.row_of("monitor:HDMI-A-1").arrow.clicked()
    assert "panel:HDMI-A-1:0" not in visible(tree) and tree.collapsed == {"monitor:HDMI-A-1"}
    tree.show_all()  # the window's show_all must not open a collapsed monitor
    assert "panel:HDMI-A-1:0" not in visible(tree)
    more = (*ENTRIES, TreeEntry("monitor:HDMI-A-2", "HDMI-A-2 (not connected)"))
    tree.show(more)  # another shape: the rows are made again
    assert "panel:HDMI-A-1:0" not in visible(tree) and "panel:DP-1:0" in visible(tree)
    tree.row_of("monitor:HDMI-A-1").arrow.clicked()
    assert "panel:HDMI-A-1:0" in visible(tree) and tree.collapsed == set()


def test_collapsing_hides_a_selected_panel_and_selects_its_monitor(tree):
    click(tree, "panel:HDMI-A-1:1")
    tree.row_of("monitor:HDMI-A-1").arrow.clicked()
    assert tree.selected() == "monitor:HDMI-A-1" and tree.picked[-1] == "monitor:HDMI-A-1"


def test_selecting_a_panel_opens_its_monitor(tree):
    tree.row_of("monitor:DP-1").arrow.clicked()
    assert tree.select("panel:DP-1:0")
    assert tree.is_expanded("monitor:DP-1") and "panel:DP-1:0" in visible(tree)


def test_the_selected_panel_row_shows_its_buttons(tree):
    def shown(page):
        return [a for a, b in tree.row_of(page).buttons.items() if b.get_visible()]

    assert shown("panel:HDMI-A-1:0") == []
    click(tree, "panel:HDMI-A-1:0")
    assert shown("panel:HDMI-A-1:0") == ["up", "down", "remove"]
    buttons = tree.row_of("panel:HDMI-A-1:0").buttons
    assert not buttons["up"].get_sensitive() and buttons["down"].get_sensitive()  # the first
    last = tree.row_of("panel:HDMI-A-1:1").buttons
    assert last["up"].get_sensitive() and not last["down"].get_sensitive()
    assert not any(b.get_focus_on_click() for b in buttons.values())
    assert buttons["remove"].get_tooltip_text() == "Remove this panel"
    click(tree, "panel:HDMI-A-1:1")
    assert shown("panel:HDMI-A-1:0") == [] and shown("panel:HDMI-A-1:1") == [
        "up",
        "down",
        "remove",
    ]
    tree.show_all()  # the window's show_all never shows the hidden buttons or rows
    assert shown("panel:HDMI-A-1:0") == []


def test_a_row_button_sends_its_action(tree):
    click(tree, "panel:HDMI-A-1:1")
    tree.row_of("panel:HDMI-A-1:1").buttons["up"].clicked()
    tree.row_of("panel:HDMI-A-1:1").buttons["remove"].clicked()
    assert tree.actions == [("panel:HDMI-A-1:1", "up"), ("panel:HDMI-A-1:1", "remove")]


def test_left_and_right_collapse_expand_and_go_up(tree):
    click(tree, "panel:HDMI-A-1:0")
    assert press(tree, Gdk.KEY_Left) is True  # a panel: to its monitor
    assert tree.selected() == "monitor:HDMI-A-1" and tree.picked[-1] == "monitor:HDMI-A-1"
    press(tree, Gdk.KEY_Left)  # the monitor: collapse
    assert not tree.is_expanded("monitor:HDMI-A-1")
    press(tree, Gdk.KEY_plus)
    assert tree.is_expanded("monitor:HDMI-A-1")
    press(tree, Gdk.KEY_minus)
    press(tree, Gdk.KEY_Right)
    assert tree.is_expanded("monitor:HDMI-A-1")
    assert press(tree, Gdk.KEY_Down) is False  # left to the list box


def test_a_rename_only_changes_the_title_and_keeps_the_selection(tree):
    click(tree, "panel:HDMI-A-1:0")
    old = tree.row_of("panel:HDMI-A-1:0")
    renamed = (
        ENTRIES[0],
        TreeEntry(
            "monitor:HDMI-A-1",
            "HDMI-A-1",
            (
                TreeEntry("panel:HDMI-A-1:0", "Bottom dock"),
                TreeEntry("panel:HDMI-A-1:1", "Clock"),
            ),
        ),
        *ENTRIES[2:],
    )
    tree.show(renamed)
    assert tree.row_of("panel:HDMI-A-1:0") is old and old.title == "Bottom dock"
    assert tree.selected() == "panel:HDMI-A-1:0" and tree.picked == ["panel:HDMI-A-1:0"]


def test_new_rows_never_call_back_and_old_ones_go_when_idle(tree):
    click(tree, "panel:HDMI-A-1:1")
    old = tree.row_of("panel:HDMI-A-1:1")
    gone = []
    old.connect("destroy", lambda *_a: gone.append(1))
    tree.show(ENTRIES[:2])  # DP-1 gone: the rows are made again (inside a button's signal)
    assert tree.picked == ["panel:HDMI-A-1:1"] and gone == []
    drain()
    assert gone == [1]


def test_with_only_the_theme_it_says_there_is_no_monitor(tree):
    assert not tree.hint.get_visible()
    tree.show(ENTRIES[:1])
    assert tree.hint.get_visible() and tree.hint.get_text() == NO_MONITORS
    tree.show(ENTRIES)
    assert not tree.hint.get_visible()


def test_the_detect_button_is_above_the_list(tree):
    assert tree.get_children()[0] is tree.detect_button
    assert tree.detect_button.get_label() == "Detect monitors"
    assert tree.list.get_accessible().get_name() == "Settings pages"


# ---- keyboard focus, accessibility, the hint (review of Tasks 5 and 6) ---------------------


def realize_all(widget):
    """Realize `widget` and every visible widget below it (top down), without showing a window."""
    if widget.get_visible():
        widget.realize()
        if isinstance(widget, Gtk.Container):
            for child in widget.get_children():
                realize_all(child)


@pytest.fixture
def focused(tree):
    """The tree in a window that is never shown (realized, so key events can reach its
    widgets); tests put the focus on one of its rows."""
    window = Gtk.Window()
    window.add(tree)
    tree.show_all()
    window.realize()
    realize_all(tree)
    yield window
    window.remove(tree)  # the tree fixture destroys it
    window.destroy()


def key_from(widget, keyval):
    """A key press the way GTK delivers it: to the focus widget, then up through its parents
    until one handles it (an unshown window cannot take real events)."""
    event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
    event.keyval = keyval
    event.window = widget.get_toplevel().get_window()  # realized, never mapped
    while widget is not None:
        if widget.emit("key-press-event", event):
            return True
        widget = widget.get_parent()
    return False


def focus_row(window, tree, page):
    click(tree, page)
    tree.row_of(page).grab_focus()
    assert window.get_focus() is tree.row_of(page)


def test_left_moves_the_focus_with_the_selection(tree, focused):
    focus_row(focused, tree, "panel:HDMI-A-1:1")
    key_from(focused.get_focus(), Gdk.KEY_Left)
    assert tree.selected() == "monitor:HDMI-A-1"
    assert focused.get_focus() is tree.row_of("monitor:HDMI-A-1")


def test_the_second_left_collapses_and_the_focus_stays_on_the_monitor(tree, focused):
    focus_row(focused, tree, "panel:HDMI-A-1:1")
    key_from(focused.get_focus(), Gdk.KEY_Left)
    key_from(focused.get_focus(), Gdk.KEY_Left)
    assert not tree.is_expanded("monitor:HDMI-A-1")
    assert focused.get_focus() is tree.row_of("monitor:HDMI-A-1")  # not dropped with the panel
    key_from(focused.get_focus(), Gdk.KEY_Right)
    assert tree.is_expanded("monitor:HDMI-A-1")
    assert focused.get_focus() is tree.row_of("monitor:HDMI-A-1")


def test_the_arrow_collapsing_a_focused_panels_monitor_takes_the_focus_there(tree, focused):
    focus_row(focused, tree, "panel:HDMI-A-1:0")
    tree.row_of("monitor:HDMI-A-1").arrow.clicked()
    assert tree.selected() == "monitor:HDMI-A-1"
    assert focused.get_focus() is tree.row_of("monitor:HDMI-A-1")


def test_the_focus_is_not_taken_when_the_list_does_not_have_it(tree, focused):
    tree.detect_button.grab_focus()
    click(tree, "panel:HDMI-A-1:0")
    press(tree, Gdk.KEY_Left)
    assert tree.selected() == "monitor:HDMI-A-1"
    assert focused.get_focus() is tree.detect_button


def test_up_after_left_starts_from_the_monitor(tree, focused):
    focus_row(focused, tree, "panel:HDMI-A-1:1")
    key_from(focused.get_focus(), Gdk.KEY_Left)
    # what Up does in the list box (a synthetic key cannot find its binding): it moves from the
    # row that has the focus, so that must be the monitor
    tree.list.emit("move-cursor", Gtk.MovementStep.DISPLAY_LINES, -1)
    assert tree.selected() == "theme"


def test_delete_on_a_focused_panel_row_removes_it(tree, focused):
    focus_row(focused, tree, "panel:HDMI-A-1:1")
    key_from(focused.get_focus(), Gdk.KEY_Delete)
    assert tree.actions == [("panel:HDMI-A-1:1", "remove")]


def test_delete_does_nothing_on_a_monitor_or_theme(tree, focused):
    focus_row(focused, tree, "monitor:HDMI-A-1")
    key_from(focused.get_focus(), Gdk.KEY_Delete)
    focus_row(focused, tree, "theme")
    key_from(focused.get_focus(), Gdk.KEY_Delete)
    assert tree.actions == []


def test_left_and_right_on_a_row_button_leave_the_selection_under_it(tree, focused):
    focus_row(focused, tree, "panel:HDMI-A-1:1")
    button = tree.row_of("panel:HDMI-A-1:1").buttons["up"]
    button.grab_focus()
    assert focused.get_focus() is button
    for keyval in (Gdk.KEY_Left, Gdk.KEY_Right, Gdk.KEY_minus, Gdk.KEY_plus, Gdk.KEY_Delete):
        key_from(button, keyval)
    assert tree.selected() == "panel:HDMI-A-1:1" and tree.actions == []
    assert tree.is_expanded("monitor:HDMI-A-1") and focused.get_focus() is button


def test_the_hint_is_not_shown_for_an_invalid_file(tree):
    tree.show(ENTRIES[:1], readable=False)  # the file is invalid: read-only, Theme alone
    assert not tree.hint.get_visible()
    tree.show(ENTRIES[:1])
    assert tree.hint.get_visible()


def test_the_hint_with_exactly_one_monitor_is_not_shown(tree):
    tree.show(ENTRIES[:2])
    assert not tree.hint.get_visible()


def test_a_collapsed_monitor_that_gets_its_first_panel_shows_it(tree):
    tree.row_of("monitor:DP-1").arrow.clicked()
    assert tree.collapsed == {"monitor:DP-1"}
    bare = tuple(TreeEntry(e.page, e.title) if e.page == "monitor:DP-1" else e for e in ENTRIES)
    tree.show(bare)  # its last panel was removed: nothing left to collapse
    assert tree.collapsed == set()
    tree.show(ENTRIES)  # and one comes back
    assert "panel:DP-1:0" in visible(tree) and tree.is_expanded("monitor:DP-1")


def with_children(page, children, title=None):
    """ENTRIES with `page`'s children (and title) replaced."""
    return tuple(
        TreeEntry(e.page, title or e.title, children) if e.page == page else e for e in ENTRIES
    )


def test_the_arrow_has_an_accessible_name_that_follows_the_state(tree):
    arrow = tree.row_of("monitor:HDMI-A-1").arrow
    assert arrow.get_accessible().get_name() == "Collapse HDMI-A-1"
    arrow.clicked()
    assert arrow.get_accessible().get_name() == "Expand HDMI-A-1"
    tree.show(with_children("monitor:DP-1", ENTRIES[2].children, "Renamed"))  # a rename
    name = tree.row_of("monitor:DP-1").arrow.get_accessible().get_name()
    assert name == "Collapse Renamed"


def test_a_monitor_row_says_whether_it_is_expandable_and_expanded(tree):
    import gi

    gi.require_version("Atk", "1.0")
    from gi.repository import Atk

    def states(page):
        s = tree.row_of(page).get_accessible().ref_state_set()
        return s.contains_state(Atk.StateType.EXPANDABLE), s.contains_state(Atk.StateType.EXPANDED)

    assert states("monitor:HDMI-A-1") == (True, True)
    assert states("monitor:DP-2") == (False, False)  # no panels
    tree.row_of("monitor:HDMI-A-1").arrow.clicked()
    assert states("monitor:HDMI-A-1") == (True, False)


def test_the_row_buttons_are_named_for_a_screen_reader(tree):
    buttons = tree.row_of("panel:HDMI-A-1:0").buttons
    names = {a: b.get_accessible().get_name() for a, b in buttons.items()}
    assert names == {"up": "Move up", "down": "Move down", "remove": "Remove panel Dock"}
    tree.show(with_children("monitor:HDMI-A-1", (TreeEntry("panel:HDMI-A-1:0", "Bottom dock"),)))
    renamed = tree.row_of("panel:HDMI-A-1:0").buttons["remove"]
    assert renamed.get_accessible().get_name() == "Remove panel Bottom dock"


def test_a_long_name_is_ellipsized_and_does_not_widen_the_tree(tree):
    from gi.repository import Pango

    long = "A very long panel name " * 8
    tree.show(with_children("monitor:HDMI-A-1", (TreeEntry("panel:HDMI-A-1:0", long),)))
    label = tree.row_of("panel:HDMI-A-1:0").label
    assert label.get_ellipsize() == Pango.EllipsizeMode.END
    assert tree.get_preferred_width().minimum_width <= MIN_WIDTH + 60  # not the name's width
