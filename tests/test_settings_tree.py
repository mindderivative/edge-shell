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
