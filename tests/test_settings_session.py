"""settings.session: validate, write atomically, back up, undo, revert, hand edits (pure)."""

import os

import pytest

pytest.importorskip("tomlkit")

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
    os.chmod(path.parent, 0o500)
    try:
        with pytest.raises(ConfigError, match="cannot write"):
            s.apply(lambda d: d.set(DEPTH, 80))
        with pytest.raises(ConfigError, match="cannot write"):
            s.revert()
    finally:
        os.chmod(path.parent, 0o700)
    assert path.read_text() == USER and s.history == [] and s.text == USER


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
