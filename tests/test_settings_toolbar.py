"""settings.toolbar: the per-screen toolbar (a plain widget; no window is created)."""

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gtk  # noqa: E402

if not Gtk.init_check()[0]:
    pytest.skip("no display", allow_module_level=True)

from settings.form import FLOAT_CHOICE, WidgetChoice, add_choices  # noqa: E402
from settings.screens import SHELL_NOTE  # noqa: E402
from settings.toolbar import NO_SCREEN, ScreenToolbar  # noqa: E402

CHOICES = add_choices((WidgetChoice("clock", "Clock"), WidgetChoice("box", "Box", ("corner",))))


@pytest.fixture
def toolbar():
    modes, adds = [], []
    t = ScreenToolbar(
        CHOICES,
        "KDE Plasma",
        lambda screen, mode: modes.append((screen, mode)),
        lambda screen, choice: adds.append((screen, choice.id)),
    )
    t.modes, t.adds = modes, adds
    yield t
    t.destroy()


def checks(t):
    return t.edge.get_active(), t.native.get_active()


def test_with_no_screen_it_is_insensitive(toolbar):
    assert toolbar.title.get_text() == NO_SCREEN and toolbar.screen is None
    for w in (toolbar.edge, toolbar.native, toolbar.kind.widget, toolbar.add_button):
        assert not w.get_sensitive()
    toolbar.add_button.clicked()
    assert toolbar.adds == []


def test_it_shows_the_screen_and_its_mode_without_calling_back(toolbar):
    toolbar.show_screen("HDMI-A-1", "HDMI-A-1", "both")
    assert toolbar.title.get_text() == "HDMI-A-1" and checks(toolbar) == (True, True)
    toolbar.show_screen("DP-2", "DP-2 (not connected)", "plasma")
    assert toolbar.title.get_text() == "DP-2 (not connected)"
    assert checks(toolbar) == (False, True) and toolbar.edge.get_sensitive()
    assert toolbar.modes == []
    assert 'shell = "plasma"' in toolbar.title.get_tooltip_text()


@pytest.mark.parametrize(
    "start, toggle, written",
    [
        ("plasma", "edge", "both"),
        ("both", "native", "edge"),
        ("edge", "edge", "none"),
        ("none", "native", "plasma"),
    ],
)
def test_a_toggle_writes_the_mode_of_both_checkboxes(toolbar, start, toggle, written):
    toolbar.show_screen("HDMI-A-1", "HDMI-A-1", start)
    check = getattr(toolbar, toggle)
    check.set_active(not check.get_active())  # as a click does
    assert toolbar.modes == [("HDMI-A-1", written)]


def test_the_labels_and_the_note(toolbar):
    assert toolbar.edge.get_label() == "Enable" and toolbar.native.get_label() == "KDE Plasma"
    assert toolbar.note.get_text() == SHELL_NOTE


def test_add_sends_the_chosen_panel_type(toolbar):
    toolbar.show_screen("HDMI-A-1", "HDMI-A-1", "edge")
    assert toolbar.chosen().id == "edge:clock"  # the first one
    toolbar.kind.widget.set_active_id("corner:box")
    toolbar.add_button.clicked()
    assert toolbar.adds == [("HDMI-A-1", "corner:box")]


def test_float_is_listed_but_cannot_be_chosen(toolbar):
    toolbar.show_screen("HDMI-A-1", "HDMI-A-1", "edge")
    toolbar.kind.widget.set_active_id("corner:box")
    labels = [r[0] for r in toolbar.kind.widget.get_model()]
    assert labels[-1] == "Float panel (coming soon)"
    toolbar.kind.widget.set_active_id(FLOAT_CHOICE)  # greyed out; only the program can
    assert toolbar.chosen().id == "corner:box"  # the last real choice comes back
    toolbar.add_button.clicked()
    assert toolbar.adds == [("HDMI-A-1", "corner:box")]


def test_add_does_nothing_for_a_choice_that_is_not_enabled(toolbar):
    toolbar.show_screen("HDMI-A-1", "HDMI-A-1", "edge")
    toolbar.chosen = lambda: CHOICES[-1]  # the float entry, however it came to be chosen
    toolbar.add_button.clicked()
    assert toolbar.adds == []


def test_the_add_button_keeps_the_focus_where_it_is(toolbar):
    assert not toolbar.add_button.get_focus_on_click()


@pytest.mark.parametrize(
    "panel, up, down, remove",
    [
        (None, False, False, False),  # a monitor page
        ((0, 1), False, False, True),  # the only panel
        ((0, 3), False, True, True),
        ((1, 3), True, True, True),
        ((2, 3), True, False, True),
    ],
)
def test_the_panel_buttons_follow_the_panel_shown(panel, up, down, remove):
    actions = []
    t = ScreenToolbar(CHOICES, "KDE Plasma", lambda *_a: None, lambda *_a: None, actions.append)
    t.show_screen("HDMI-A-1", "HDMI-A-1", "edge", panel)
    sensitive = {a: b.get_sensitive() for a, b in t.panel_buttons.items()}
    assert sensitive == {"up": up, "down": down, "remove": remove}
    t.panel_buttons["remove"].clicked()
    assert actions == ["remove"]  # the view checks that a panel page is shown
    t.destroy()
