"""settings.session: validate, write atomically, back up, undo, revert, hand edits (pure)."""

import os

import pytest

pytest.importorskip("tomlkit")

from settings import files  # noqa: E402
from settings.session import ChangedOutside, SettingsSession, check_text  # noqa: E402
from shell.config.diff import Change, diff_configs  # noqa: E402
from shell.config.models import ConfigError  # noqa: E402
from shell.config.store import ConfigStore  # noqa: E402

USER = """\
# test config
[monitors.HDMI-A-1]
shell = "edge"   # test monitor

[[monitors.HDMI-A-1.panels]]
widget = "dock"
"""
SHELL = ("monitors", "HDMI-A-1", "shell")
DEPTH = ("monitors", "HDMI-A-1", "panels", 0, "depth")


@pytest.fixture
def path(tmp_path, fake_registry):
    p = tmp_path / "config.toml"
    p.write_text(USER)
    return p


def test_opening_reads_and_checks_the_file(path):
    s = SettingsSession(path)
    assert s.text == USER and s.error is None
    assert s.config.monitor("HDMI-A-1").shell == "edge"
    assert s.user["monitors"]["HDMI-A-1"]["panels"] == [{"widget": "dock"}]
    assert not s.changed_outside()


def test_a_missing_file_is_the_defaults(tmp_path, fake_registry):
    s = SettingsSession(tmp_path / "config.toml")
    assert s.text == "" and s.user == {} and s.config.monitors == {}


def test_an_invalid_file_opens_with_its_error(path):
    path.write_text('[monitors.HDMI-A-1]\nshell = "sideways"\n')
    s = SettingsSession(path)
    assert s.config is None and "monitors.HDMI-A-1.shell" in s.error


def test_apply_writes_a_valid_change_keeping_comments(path):
    s = SettingsSession(path)
    config = s.apply(lambda d: d.set(DEPTH, 80))
    assert config.monitor("HDMI-A-1").panels[0].depth == 80
    text = path.read_text()
    assert "depth = 80" in text and "# test monitor" in text
    assert s.text == text and s.user["monitors"]["HDMI-A-1"]["panels"][0]["depth"] == 80


def test_an_invalid_change_is_not_written(path):
    s = SettingsSession(path)
    with pytest.raises(ConfigError, match="depth"):
        s.apply(lambda d: d.set(DEPTH, 5))  # below the minimum of 16
    assert path.read_text() == USER and s.history == []
    assert not (path.parent / "config.toml.bak").exists()


def test_an_unknown_widget_is_not_written(path):
    s = SettingsSession(path)
    with pytest.raises(ConfigError, match="unknown widget"):
        s.apply(lambda d: d.add_panel("HDMI-A-1", "nope"))
    assert path.read_text() == USER


def test_a_cross_field_rule_is_not_written(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(("monitors", "HDMI-A-1", "panels", 0, "pos"), 400))
    with pytest.raises(ConfigError, match="pos cannot be combined"):
        s.apply(lambda d: d.set(("monitors", "HDMI-A-1", "panels", 0, "align"), "end"))


def test_the_first_write_backs_up_the_original_once(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.apply(lambda d: d.set(DEPTH, 90))
    assert (path.parent / "config.toml.bak").read_text() == USER


def test_undo_steps_back_one_change_at_a_time(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    after_first = path.read_text()
    s.apply(lambda d: d.set(SHELL, "both"))
    assert s.undo() is True
    assert path.read_text() == after_first and s.config.monitor("HDMI-A-1").shell == "edge"
    assert s.undo() is True
    assert path.read_text() == USER
    assert s.undo() is False


def test_revert_goes_back_to_the_start_of_the_session(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    s.apply(lambda d: d.set(SHELL, "none"))
    s.revert()
    assert path.read_text() == USER and s.history == []
    assert s.config.monitor("HDMI-A-1").shell == "edge"


def test_revert_of_a_session_that_started_without_a_file(tmp_path, fake_registry):
    path = tmp_path / "config.toml"
    s = SettingsSession(path)
    s.apply(lambda d: d.set(("monitors", "HDMI-A-1", "shell"), "edge"))
    s.revert()
    assert path.read_text() == "" and s.config.monitors == {}


def test_a_hand_edit_is_never_overwritten(path):
    s = SettingsSession(path)
    path.write_text(USER + '\n[theme]\naccent = "#112233"\n')  # edited by hand meanwhile
    assert s.changed_outside()
    with pytest.raises(ChangedOutside, match="changed outside"):
        s.apply(lambda d: d.set(DEPTH, 80))
    assert "depth" not in path.read_text()
    assert s.config.theme.accent == "#112233"  # re-read
    s.apply(lambda d: d.set(DEPTH, 80))  # the next change applies on top of the hand edit
    assert 'accent = "#112233"' in path.read_text() and "depth = 80" in path.read_text()


def test_undo_after_a_hand_edit_rereads_instead(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    path.write_text(USER)
    with pytest.raises(ChangedOutside):
        s.undo()
    assert s.history == [] and s.text == USER


def test_revert_after_a_hand_edit_keeps_the_hand_edit(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    hand = USER + '\n[theme]\naccent = "#112233"\n'
    path.write_text(hand)  # edited by hand while the window is open
    with pytest.raises(ChangedOutside, match="keeps that change"):
        s.revert()
    assert path.read_text() == hand
    s.apply(lambda d: d.set(SHELL, "both"))
    s.revert()  # back to the hand edit (the new start), never to the file before it
    assert path.read_text() == hand


def test_an_unwritable_folder_is_an_error_not_a_crash(path):
    if os.geteuid() == 0:
        pytest.skip("root can write into a read-only folder")
    s = SettingsSession(path)
    s.apply(lambda d: d.set(SHELL, "both"))
    changed = path.read_text()
    os.chmod(path.parent, 0o500)
    try:
        with pytest.raises(ConfigError, match="cannot write"):
            s.apply(lambda d: d.set(DEPTH, 80))
        with pytest.raises(ConfigError, match="cannot write"):
            s.revert()
    finally:
        os.chmod(path.parent, 0o700)
    assert path.read_text() == changed and len(s.history) == 1 and s.text == changed


def test_an_edit_can_fix_an_invalid_file(path):
    path.write_text('[monitors.HDMI-A-1]\nshell = "sideways"\n')
    s = SettingsSession(path)
    s.apply(lambda d: d.set(SHELL, "edge"))
    assert s.error is None and s.config.monitor("HDMI-A-1").shell == "edge"


def test_check_text_uses_the_registry(fake_registry):
    with pytest.raises(ConfigError, match="unknown widget"):
        check_text('[[monitors.X.panels]]\nwidget = "nope"\n')


@pytest.mark.parametrize(
    "path_, value, kind",
    [
        (("theme", "accent"), "#112233", "restyle"),
        (DEPTH, 80, "panel-rebuild"),
        (("monitors", "HDMI-A-1", "panels", 0, "state"), "collapsed", "panel-state"),
        (("monitors", "HDMI-A-1", "panels", 0, "handle", "shape"), "bar", "panel-handle"),
        (("monitors", "HDMI-A-1", "layout", "gap"), 20, "relayout"),
        (("theme", "thickness"), 12, "rebuild-monitor"),
        (SHELL, "plasma", "rebuild-monitor"),
    ],
)
def test_a_written_change_reloads_in_the_shell_as_the_expected_kind(path, path_, value, kind):
    """The running shell's ConfigStore reloads the file the session wrote; the diff kind is
    the cheap in-place one where the shell has one (spec 6, live reload table)."""
    store = ConfigStore(path)
    SettingsSession(path).apply(lambda d: d.set(path_, value))
    old, new = store.reload()
    assert [c.kind for c in diff_configs(old, new)] == [kind]


def test_adding_a_panel_reloads_as_panel_add(path):
    store = ConfigStore(path)
    SettingsSession(path).apply(lambda d: d.add_panel("HDMI-A-1", "clock"))
    old, new = store.reload()
    assert diff_configs(old, new) == [Change("panel-add", "HDMI-A-1", 1)]


def test_a_failed_backup_writes_nothing_and_is_tried_again(path):
    (path.parent / "config.toml.bak").mkdir()  # the backup cannot be written
    s = SettingsSession(path)
    with pytest.raises(ConfigError, match=r"cannot write .*config\.toml\.bak"):
        s.apply(lambda d: d.set(DEPTH, 80))
    assert not s.backed_up and path.read_text() == USER and s.history == []
    (path.parent / "config.toml.bak").rmdir()
    s.apply(lambda d: d.set(DEPTH, 80))
    assert (path.parent / "config.toml.bak").read_text() == USER


def test_a_failed_write_changes_nothing(path, monkeypatch):
    s = SettingsSession(path)
    real = files.write_atomic

    def full_disk(target, data, **kw):
        if target == path:
            raise OSError(28, "No space left on device")
        return real(target, data, **kw)

    monkeypatch.setattr(files, "write_atomic", full_disk)
    with pytest.raises(ConfigError, match="No space left"):
        s.apply(lambda d: d.set(DEPTH, 80))
    assert path.read_text() == USER and s.history == [] and s.text == USER


def test_an_edit_that_changes_nothing_writes_nothing(path):
    s = SettingsSession(path)
    inode = path.stat().st_ino
    config = s.apply(lambda d: d.set(SHELL, "edge"))  # already "edge"
    assert config.monitor("HDMI-A-1").shell == "edge"
    assert path.stat().st_ino == inode and path.read_text() == USER
    assert s.history == [] and not s.backed_up
    assert not (path.parent / "config.toml.bak").exists()


def test_revert_with_no_changes_does_not_rewrite_the_file(path):
    s = SettingsSession(path)
    inode = path.stat().st_ino
    s.revert()
    assert path.stat().st_ino == inode and path.read_text() == USER
    s.apply(lambda d: d.set(DEPTH, 80))
    s.undo()
    inode = path.stat().st_ino
    s.revert()
    assert path.stat().st_ino == inode and s.history == []


BROKEN = '[monitors.HDMI-A-1]\nshell = "sideways"\n'


def test_a_hand_break_keeps_the_last_valid_baseline_for_revert(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    path.write_text(BROKEN)  # broken by hand
    with pytest.raises(ChangedOutside):
        s.apply(lambda d: d.set(DEPTH, 90))
    assert s.config is None
    s.revert()
    assert path.read_text() == USER and s.config is not None


def test_a_file_invalid_at_open_can_be_fixed_by_hand_then_reverted(path):
    path.write_text(BROKEN)
    s = SettingsSession(path)
    assert s.config is None
    path.write_text(USER)  # fixed by hand
    with pytest.raises(ChangedOutside):
        s.revert()
    assert s.config is not None and path.read_text() == USER
    s.apply(lambda d: d.set(DEPTH, 80))
    s.revert()
    assert path.read_text() == USER


HAND = USER + "# new hand work\n[monitors.DP-2]\nmode = 'edgee'\n"  # one typo: invalid


def kept(path):
    return sorted(p.name for p in path.parent.iterdir() if "before-revert" in p.name)


def test_revert_keeps_an_invalid_hand_edit_as_before_revert(path):
    """Reviewer's probe: open on valid A, hand-edit new work with a typo, Revert all."""
    s = SettingsSession(path)
    path.write_text(HAND)
    s.rebase()
    assert s.config is None and s.keeps_hand_edit()
    s.revert()
    assert path.read_text() == USER
    assert kept(path) == ["config.toml.before-revert"]
    copy = path.with_name("config.toml.before-revert")
    assert copy.read_bytes() == HAND.encode()
    assert not path.with_name("config.toml.bak").exists()  # no edit this session: no .bak


def test_a_second_revert_numbers_the_copy(path):
    s = SettingsSession(path)
    for n in (1, 2):
        text = HAND + f"# take {n}\n"
        path.write_text(text)
        s.rebase()
        s.revert()
        assert path.read_text() == USER
    assert kept(path) == ["config.toml.before-revert", "config.toml.before-revert.2"]
    assert path.with_name("config.toml.before-revert.2").read_text().endswith("# take 2\n")


def test_the_copy_has_the_files_mode(path):
    path.chmod(0o600)
    s = SettingsSession(path)
    path.write_text(HAND)
    s.rebase()
    s.revert()
    assert (path.with_name("config.toml.before-revert").stat().st_mode & 0o777) == 0o600


def test_a_valid_hand_edit_is_the_baseline_and_needs_no_copy(path):
    s = SettingsSession(path)
    path.write_text(USER + "# valid hand work\n")
    s.rebase()
    assert not s.keeps_hand_edit()
    s.apply(lambda d: d.set(DEPTH, 80))
    s.revert()
    assert path.read_text() == USER + "# valid hand work\n" and kept(path) == []


def test_window_edits_replaced_by_revert_need_no_copy(path):
    s = SettingsSession(path)
    s.apply(lambda d: d.set(DEPTH, 80))
    assert not s.keeps_hand_edit()
    s.revert()
    assert kept(path) == [] and path.read_text() == USER


def test_a_failing_copy_blocks_the_revert_and_leaves_the_file(path, monkeypatch):
    s = SettingsSession(path)
    path.write_text(HAND)
    s.rebase()

    def boom(*_a, **_k):
        raise PermissionError("denied")

    monkeypatch.setattr(files, "keep_before_revert", boom)
    with pytest.raises(ConfigError, match="cannot write"):
        s.revert()
    assert path.read_text() == HAND and kept(path) == []
    monkeypatch.undo()
    s.revert()  # the user can try again
    assert path.read_text() == USER


def test_an_unwritable_folder_blocks_the_revert_of_a_hand_edit(path):
    if os.geteuid() == 0:
        pytest.skip("root can write into a read-only folder")
    s = SettingsSession(path)
    path.write_text(HAND)
    s.rebase()
    os.chmod(path.parent, 0o500)
    try:
        with pytest.raises(ConfigError, match="cannot write"):
            s.revert()
    finally:
        os.chmod(path.parent, 0o700)
    assert path.read_text() == HAND and kept(path) == []
