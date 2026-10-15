"""settings.dialogs: the seam (no dialog ever runs here) and the view's Revert all through it."""

import inspect

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from settings.dialogs import Dialogs, GtkDialogs  # noqa: E402


def test_the_real_dialogs_have_the_seams_methods():
    for name, member in inspect.getmembers(Dialogs, inspect.isfunction):
        if name.startswith("_"):
            continue
        real = getattr(GtkDialogs, name)
        assert inspect.signature(real) == inspect.signature(member), name


@pytest.fixture
def view(tmp_path, fake_registry):
    pytest.importorskip("tomlkit")
    from gi.repository import Gtk

    if not Gtk.init_check()[0]:
        pytest.skip("no display")
    from settings.session import SettingsSession
    from settings.view import SettingsView

    path = tmp_path / "config.toml"
    path.write_text('[monitors.HDMI-A-1]\nshell = "edge"\n')
    asked = []
    answer = {"ok": False}

    def confirm(_parent, text):
        asked.append(text)
        return answer["ok"]

    v = SettingsView(SettingsSession(path), [], confirm_revert=confirm)
    v.asked, v.answer, v.path = asked, answer, path
    return v


def test_revert_all_asks_through_the_seam_and_cancel_keeps_the_change(view):
    view._on_change(("monitors", "HDMI-A-1", "shell"), "both")
    view.revert_button.emit("clicked")
    assert len(view.asked) == 1 and "goes back to how it was" in view.asked[0]
    assert 'shell = "both"' in view.path.read_text()


def test_revert_all_confirmed_reverts(view):
    view._on_change(("monitors", "HDMI-A-1", "shell"), "both")
    view.answer["ok"] = True
    view.confirm_revert()
    assert view.path.read_text() == '[monitors.HDMI-A-1]\nshell = "edge"\n'
