"""settings.session: redo, the saved point (Save, dirty, Discard) and how hand edits, Revert all
and the backup meet them (pure)."""

import pytest

pytest.importorskip("tomlkit")

from settings import files  # noqa: E402
from settings.session import ChangedOutside, SettingsSession  # noqa: E402
from shell.config.models import ConfigError  # noqa: E402

USER = """\
# test config
[monitors.HDMI-A-1]
shell = "edge"   # test monitor

[[monitors.HDMI-A-1.panels]]
panel = "edge"
name = "dock"
widget = "dock"
"""
SHELL = ("monitors", "HDMI-A-1", "shell")
DEPTH = ("monitors", "HDMI-A-1", "panels", 0, "depth")
BROKEN = '[monitors.HDMI-A-1]\nshell = "sideways"\n'


@pytest.fixture
def path(tmp_path, fake_registry):
    p = tmp_path / "config.toml"
    p.write_text(USER)
    return p


def bak(path):
    return path.with_name("config.toml.bak")


def test_redo_puts_back_what_undo_replaced(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    one = path.read_text()
    s.apply(lambda d: d.set(SHELL, "both"))
    two = path.read_text()
    s.undo()
    s.undo()
    assert path.read_text() == USER and len(s.redo_history) == 2
    assert s.redo() is True
    assert path.read_text() == one and s.text == one
    assert s.redo() is True
    assert path.read_text() == two and s.config.monitor("HDMI-A-1").shell == "both"
    assert s.redo() is False and len(s.history) == 2
    assert s.undo() is True and path.read_text() == one  # and back again


def test_a_new_change_ends_the_redo_line(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.undo()
    s.apply(lambda d: d.set(SHELL, "both"))
    assert s.redo_history == [] and s.redo() is False
    assert "depth" not in path.read_text()


def test_an_edit_that_changes_nothing_keeps_the_redo_line(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.undo()
    s.apply(lambda d: d.set(SHELL, "edge"))  # already "edge": nothing is written
    assert s.redo() is True and "depth = 80" in path.read_text()


def test_redo_after_a_hand_edit_rereads_instead(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.undo()
    hand = USER + "# by hand\n"
    path.write_text(hand)
    with pytest.raises(ChangedOutside):
        s.redo()
    assert path.read_text() == hand and s.redo_history == [] and s.history == []


def test_revert_ends_the_redo_line(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.apply(lambda d: d.set(SHELL, "both"))
    s.undo()
    s.revert()
    assert path.read_text() == USER and s.redo_history == [] and s.redo() is False


def test_a_new_session_is_clean_and_a_change_makes_it_dirty(path):
    s = SettingsSession(path)
    assert not s.dirty and s.saved_text == USER
    s.apply(lambda d: d.set(DEPTH, 80))
    assert s.dirty


def test_undo_back_to_the_saved_text_is_not_dirty(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.undo()
    assert not s.dirty
    s.redo()
    assert s.dirty


def test_save_moves_the_saved_point_and_refreshes_the_backup(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    assert bak(path).read_text() == USER  # the first change's backup
    s.save()
    saved = path.read_text()
    assert not s.dirty and s.saved_text == saved and bak(path).read_text() == saved
    s.apply(lambda d: d.set(SHELL, "both"))
    assert s.dirty and bak(path).read_text() == saved  # later changes keep the saved copy
    s.undo()
    assert not s.dirty  # back at the saved point


def test_save_before_any_change_backs_up_the_file(path):
    s = SettingsSession(path)
    s.save()
    assert bak(path).read_text() == USER and s.backed_up
    s.apply(lambda d: d.set(DEPTH, 80))
    assert bak(path).read_text() == USER


def test_save_of_a_session_without_a_file(tmp_path, fake_registry):
    path = tmp_path / "config.toml"
    s = SettingsSession(path)
    s.save()  # nothing on disk yet: no copy, nothing to fail
    assert not bak(path).exists() and not s.dirty
    s.apply(lambda d: d.set(SHELL, "edge"))
    assert s.dirty
    s.save()
    assert bak(path).read_text() == path.read_text() and not s.dirty


def test_a_failed_save_moves_nothing(path, monkeypatch):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))

    def boom(_path):
        raise PermissionError("denied")

    monkeypatch.setattr(files, "write_backup", boom)
    with pytest.raises(ConfigError, match=r"cannot write .*config\.toml\.bak"):
        s.save()
    assert s.dirty and s.saved_text == USER


def test_discard_writes_the_saved_point_back(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.save()
    saved = path.read_text()
    s.apply(lambda d: d.set(SHELL, "both"))
    s.apply(lambda d: d.set(SHELL, "none"))
    s.discard()
    assert path.read_text() == saved and s.text == saved and not s.dirty
    assert s.history == [] and s.redo_history == []
    assert s.config.monitor("HDMI-A-1").panels[0].depth == 80


def test_discard_of_a_clean_session_writes_nothing(path):
    s = SettingsSession(path)
    inode = path.stat().st_ino
    s.discard()
    assert path.stat().st_ino == inode and path.read_text() == USER


def test_discard_without_a_save_goes_back_to_the_opened_file(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.discard()
    assert path.read_text() == USER


@pytest.mark.parametrize("hand", [USER + "# valid hand work\n", BROKEN])
def test_a_hand_edit_is_the_saved_point(path, hand):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    path.write_text(hand)
    s.rebase()
    assert not s.dirty and s.saved_text == hand


def test_save_after_a_hand_edit_rereads_it_as_saved(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    hand = USER + "# by hand\n"
    path.write_text(hand)
    with pytest.raises(ChangedOutside, match="saved state now"):
        s.save()
    assert not s.dirty and s.text == hand
    assert bak(path).read_text() == USER  # the copy was not refreshed


def test_discard_never_writes_over_a_hand_edit(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    path.write_text(BROKEN)  # an invalid hand edit: it must survive a Discard
    with pytest.raises(ChangedOutside, match="nothing was discarded"):
        s.discard()
    assert path.read_text() == BROKEN and not s.dirty
    s.discard()  # asked again: nothing to do
    assert path.read_text() == BROKEN


def test_revert_after_save_goes_to_the_start_and_is_dirty(path):
    """Revert all keeps its meaning (the file as the window opened it); Save does not move it."""
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.save()
    s.revert()
    assert path.read_text() == USER and s.dirty


def kept(path):
    return sorted(p.name for p in path.parent.iterdir() if "before-revert" in p.name)


def broken_then_fixed_and_saved(path):
    """Open on valid text, save a broken file by hand, fix it in the session and Save."""
    s = SettingsSession(path)
    path.write_text(BROKEN)
    s.rebase()
    s.apply(lambda d: d.set(SHELL, "edge"))
    s.save()
    return s


def test_discard_keeps_an_invalid_text_like_revert_all(path):
    s = broken_then_fixed_and_saved(path)
    saved = path.read_text()
    assert s.undo() is True
    assert path.read_text() == BROKEN and s.dirty and s.keeps_hand_edit()
    s.discard()
    assert path.read_text() == saved and not s.dirty
    assert kept(path) == ["config.toml.before-revert"]
    assert path.with_name("config.toml.before-revert").read_text() == BROKEN


def test_discard_stops_when_the_invalid_text_cannot_be_kept(path, monkeypatch):
    s = broken_then_fixed_and_saved(path)
    s.undo()

    def boom(_path):
        raise PermissionError("denied")

    monkeypatch.setattr(files, "keep_before_revert", boom)
    with pytest.raises(ConfigError, match="cannot write"):
        s.discard()
    assert path.read_text() == BROKEN and s.dirty and kept(path) == []


def test_discard_of_a_valid_change_keeps_no_copy(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.discard()
    assert path.read_text() == USER and kept(path) == []


def test_save_refuses_while_the_file_is_invalid(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))  # the first write backs up USER
    path.write_text(BROKEN)
    s.rebase()
    assert s.config is None
    with pytest.raises(ConfigError, match="invalid"):
        s.save()
    assert bak(path).read_text() == USER  # the good copy is not replaced by the broken file


def test_discard_clears_the_redo_line(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.save()
    s.apply(lambda d: d.set(SHELL, "both"))
    s.undo()
    assert s.redo_history
    s.discard()
    assert s.redo_history == [] and s.redo() is False


def test_discard_after_save_and_undo_writes_the_saved_text_back(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.save()
    saved = path.read_text()
    s.undo()
    assert path.read_text() == USER and s.dirty
    s.discard()
    assert path.read_text() == saved and not s.dirty


def test_discard_after_save_writes_nothing(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.save()
    inode = path.stat().st_ino
    assert s.history and not s.dirty  # history left, but nothing unsaved
    s.discard()
    assert path.stat().st_ino == inode and s.history == []


def test_a_failed_write_leaves_both_stacks_alone(path, monkeypatch):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.apply(lambda d: d.set(SHELL, "both"))
    s.undo()
    before = (list(s.history), list(s.redo_history), s.text)

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(files, "write_atomic", boom)
    with pytest.raises(ConfigError):
        s.undo()
    with pytest.raises(ConfigError):
        s.redo()
    with pytest.raises(ConfigError):
        s.apply(lambda d: d.set(SHELL, "none"))
    assert (s.history, s.redo_history, s.text) == before
