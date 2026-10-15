"""settings.dialogs: the seam (no dialog ever runs here) and the view's Revert all through it."""

import inspect
from pathlib import Path

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gtk  # noqa: E402

from settings.dialogs import (  # noqa: E402
    CHOOSERS,
    Dialogs,
    GtkDialogs,
    chosen_path,
    revert_confirmed,
    unsaved_answer,
)
from settings.fileops import Answer  # noqa: E402

R = Gtk.ResponseType


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


@pytest.mark.parametrize(
    "response, answer",
    [
        (R.ACCEPT, Answer.SAVE),  # the _Save button
        (R.REJECT, Answer.DISCARD),  # the _Discard button
        (R.CANCEL, Answer.CANCEL),
        (R.DELETE_EVENT, Answer.CANCEL),  # Escape or the close button
        (R.NONE, Answer.CANCEL),
    ],
)
def test_the_unsaved_prompt_answers(response, answer):
    assert unsaved_answer(response) is answer


@pytest.mark.parametrize(
    "response, ok",
    [(R.OK, True), (R.CANCEL, False), (R.DELETE_EVENT, False), (R.ACCEPT, False)],
)
def test_only_ok_confirms_revert_all(response, ok):
    assert revert_confirmed(response) is ok


@pytest.mark.parametrize(
    "response, filename, path",
    [
        (R.ACCEPT, "/tmp/x/c.toml", Path("/tmp/x/c.toml")),
        (R.ACCEPT, None, None),  # not a local file (the portal gave a URI)
        (R.ACCEPT, "", None),
        (R.CANCEL, "/tmp/x/c.toml", None),  # a preset name is not an answer
        (R.DELETE_EVENT, "/tmp/x/c.toml", None),
        (R.OK, "/tmp/x/c.toml", None),  # only ACCEPT is the chooser's yes
    ],
)
def test_a_chooser_returns_a_path_only_for_accept_with_a_filename(response, filename, path):
    assert chosen_path(response, filename) == path


def test_only_save_as_asks_before_overwriting():
    assert {k: spec.overwrite for k, spec in CHOOSERS.items()} == {
        "new": False,
        "open": False,
        "save_as": True,
    }


def test_each_chooser_uses_its_own_spec(monkeypatch):
    used = []
    monkeypatch.setattr(
        GtkDialogs, "_choose", staticmethod(lambda spec, *_a: used.append(spec) or None)
    )
    dialogs = GtkDialogs()
    folder = Path("/tmp")
    dialogs.choose_new(None, folder, "n.toml")
    dialogs.choose_open(None, folder)
    dialogs.choose_save_as(None, folder, "s.toml")
    assert used == [CHOOSERS["new"], CHOOSERS["open"], CHOOSERS["save_as"]]
    assert [s.overwrite for s in used] == [False, False, True]


class FakeChooser:
    """Stands in for Gtk.FileChooserNative: records the calls, runs nothing."""

    def __init__(self, response, filename):
        self.response, self.filename, self.overwrite = response, filename, None

    def __getattr__(self, name):
        return lambda *_a, **_k: None  # set_modal, set_current_folder, add_filter, destroy...

    def set_do_overwrite_confirmation(self, flag):
        self.overwrite = flag

    def run(self):
        return self.response

    def get_filename(self):
        return self.filename


@pytest.mark.parametrize(
    "method, args, overwrite",
    [("choose_new", ("n.toml",), False), ("choose_save_as", ("s.toml",), True)],
)
def test_the_save_choosers_get_their_overwrite_flag(monkeypatch, tmp_path, method, args, overwrite):
    fake = FakeChooser(Gtk.ResponseType.ACCEPT, str(tmp_path / "x.toml"))
    monkeypatch.setattr(Gtk.FileChooserNative, "new", staticmethod(lambda *_a: fake))
    assert getattr(GtkDialogs(), method)(None, tmp_path, *args) == tmp_path / "x.toml"
    assert fake.overwrite is overwrite


def test_a_cancelled_chooser_returns_none_even_with_a_preset_name(monkeypatch, tmp_path):
    fake = FakeChooser(Gtk.ResponseType.CANCEL, str(tmp_path / "n.toml"))
    monkeypatch.setattr(Gtk.FileChooserNative, "new", staticmethod(lambda *_a: fake))
    assert GtkDialogs().choose_new(None, tmp_path, "n.toml") is None
