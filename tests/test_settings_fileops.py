"""settings.fileops: leaving a config with unsaved changes (pure; the question is a callable),
and the file operations of New, Open and Save As."""

import os
import tomllib
from pathlib import Path

import pytest

from settings.fileops import (
    NEW_TEXT,
    Answer,
    check_openable,
    create_new,
    default_folder,
    leave,
    new_name,
    new_path,
    same_file,
    save_copy,
    unsaved_question,
)
from shell.config.models import ConfigError

USER = '[monitors.HDMI-A-1]\nshell = "edge"\n'
SHELL = ("monitors", "HDMI-A-1", "shell")


@pytest.fixture
def session(tmp_path, fake_registry):
    pytest.importorskip("tomlkit")
    from settings.session import SettingsSession

    path = tmp_path / "config.toml"
    path.write_text(USER)
    return SettingsSession(path)


def asker(answer):
    asked = []

    def ask():
        asked.append(answer)
        return answer

    ask.asked = asked
    return ask


def test_a_clean_config_is_left_without_a_question(session):
    ask = asker(Answer.CANCEL)
    assert leave(session, ask) is True and ask.asked == []


def test_cancel_stays_and_changes_nothing(session):
    session.apply(lambda d: d.set(SHELL, "both"))
    ask = asker(Answer.CANCEL)
    assert leave(session, ask) is False and ask.asked == [Answer.CANCEL]
    assert session.dirty and 'shell = "both"' in session.path.read_text()


def test_save_keeps_the_changes_as_the_saved_point(session):
    session.apply(lambda d: d.set(SHELL, "both"))
    assert leave(session, asker(Answer.SAVE)) is True
    assert not session.dirty and 'shell = "both"' in session.path.read_text()
    assert 'shell = "both"' in session.path.with_name("config.toml.bak").read_text()


def test_discard_puts_the_saved_file_back(session):
    session.apply(lambda d: d.set(SHELL, "both"))
    assert leave(session, asker(Answer.DISCARD)) is True
    assert session.path.read_text() == USER and not session.dirty


def test_a_hand_edit_met_by_discard_raises_and_is_kept(session):
    from settings.session import ChangedOutside

    session.apply(lambda d: d.set(SHELL, "both"))
    session.path.write_text(USER + "# by hand\n")
    with pytest.raises(ChangedOutside):
        leave(session, asker(Answer.DISCARD))
    assert session.path.read_text().endswith("# by hand\n")
    assert leave(session, asker(Answer.DISCARD)) is True  # now clean: no question


def test_the_question_names_the_file():
    primary, secondary = unsaved_question(Path("/home/p/.config/edge-shell/config.toml"))
    assert primary == "Save the changes to config.toml?"
    assert "/home/p/.config/edge-shell/config.toml" in secondary and "Discard" in secondary


def test_new_writes_a_config_with_no_keys(tmp_path):
    path = tmp_path / "sub" / "new.toml"  # a missing folder is created
    create_new(path)
    assert path.read_text() == NEW_TEXT and tomllib.loads(NEW_TEXT) == {}


def test_new_never_replaces_a_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(USER)
    with pytest.raises(ConfigError, match="already exists"):
        create_new(path)
    assert path.read_text() == USER
    link = tmp_path / "dangling.toml"
    link.symlink_to(tmp_path / "nowhere.toml")
    with pytest.raises(ConfigError, match="already exists"):
        create_new(link)


def test_new_in_an_unwritable_folder_is_an_error(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root can write into a read-only folder")
    os.chmod(tmp_path, 0o500)
    try:
        with pytest.raises(ConfigError, match="cannot create"):
            create_new(tmp_path / "config.toml")
    finally:
        os.chmod(tmp_path, 0o700)


def test_new_name_is_free(tmp_path):
    assert new_name(tmp_path) == "config.toml"
    (tmp_path / "config.toml").write_text("")
    (tmp_path / "config-2.toml").write_text("")
    assert new_name(tmp_path) == "config-3.toml"


def test_the_choosers_start_in_the_config_folder(tmp_path):
    user = tmp_path / ".config" / "edge-shell" / "config.toml"
    assert default_folder(user) == user.parent and user.parent.is_dir()  # created
    blocked = tmp_path / "file"
    blocked.write_text("")
    assert default_folder(blocked / "edge-shell" / "config.toml") == Path.home()


def test_same_file_through_a_symlink(tmp_path):
    real = tmp_path / "a.toml"
    real.write_text("")
    link = tmp_path / "link.toml"
    link.symlink_to(real)
    assert same_file(real, link) and not same_file(real, tmp_path / "b.toml")


def test_check_openable(tmp_path):
    text = tmp_path / "not-a-config.toml"
    text.write_text("this is [not toml\n")
    check_openable(text)  # opens, read-only with its error, like at start
    with pytest.raises(ConfigError, match="does not exist"):
        check_openable(tmp_path / "missing.toml")
    with pytest.raises(ConfigError):
        check_openable(tmp_path)  # a folder
    binary = tmp_path / "image.png"
    binary.write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe")
    with pytest.raises(ConfigError):
        check_openable(binary)


def test_save_as_writes_the_text_and_keeps_a_replaced_file(tmp_path):
    source = tmp_path / "config.toml"
    source.write_text(USER)
    target = tmp_path / "other.toml"
    assert save_copy(source, USER, target) is None and target.read_text() == USER
    target.write_text("# older\n")
    kept = save_copy(source, USER, target)
    assert kept == target.with_name("other.toml.before-save-as")
    assert kept.read_text() == "# older\n" and target.read_text() == USER
    target.write_text("# oldest\n")
    assert save_copy(source, USER, target).name == "other.toml.before-save-as.2"


def test_save_as_of_a_private_config_is_private(tmp_path):
    source = tmp_path / "config.toml"
    source.write_text(USER)
    source.chmod(0o600)
    target = tmp_path / "copy.toml"
    save_copy(source, USER, target)
    assert target.stat().st_mode & 0o777 == 0o600


def test_save_as_into_an_unwritable_folder_is_an_error(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root can write into a read-only folder")
    folder = tmp_path / "ro"
    folder.mkdir()
    os.chmod(folder, 0o500)
    try:
        with pytest.raises(ConfigError, match="cannot write"):
            save_copy(tmp_path / "missing.toml", USER, folder / "x.toml")
    finally:
        os.chmod(folder, 0o700)


def test_new_name_goes_on_past_three(tmp_path):
    for name in ("config.toml", "config-2.toml", "config-3.toml"):
        (tmp_path / name).write_text("")
    assert new_name(tmp_path) == "config-4.toml"


def test_new_adds_toml_to_a_name_without_a_suffix(tmp_path):
    assert new_path(tmp_path / "work") == tmp_path / "work.toml"
    assert new_path(tmp_path / "work.toml") == tmp_path / "work.toml"
    assert new_path(tmp_path / "work.conf") == tmp_path / "work.conf.toml"
    assert create_new(tmp_path / "plain") == tmp_path / "plain.toml"
    assert (tmp_path / "plain.toml").read_text() == NEW_TEXT and not (tmp_path / "plain").exists()
    assert create_new(tmp_path / "x.conf") == tmp_path / "x.conf.toml"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("x", "x.toml"),
        ("x.", "x.toml"),
        ("x...", "x.toml"),
        ("x.toml", "x.toml"),
        ("X.TOML", "X.TOML"),
        (".toml", "config.toml"),
        (".TOML", "config.toml"),
        ("a.b", "a.b.toml"),
        ("my.config", "my.config.toml"),
        ("dir/x", "dir/x.toml"),
    ],
)
def test_new_path_is_the_same_on_every_python_version(tmp_path, name, expected):
    """By name, never Path.suffix (its reading of 'x.' and '.toml' changed between versions):
    trailing dots go, a bare '.toml' becomes config.toml, .toml is added unless already there
    (any case), so the Open filter always shows the file."""
    assert new_path(tmp_path / name) == tmp_path / expected


def test_only_regular_files_are_read(tmp_path):
    """A FIFO would block the GTK loop for ever (never opened here), a device has no end."""
    fifo = tmp_path / "pipe.toml"
    os.mkfifo(fifo)
    with pytest.raises(ConfigError, match="not a regular file"):
        check_openable(fifo)
    with pytest.raises(ConfigError, match="not a regular file"):
        check_openable(tmp_path)
    with pytest.raises(ConfigError, match="not a regular file"):
        check_openable(Path("/dev/zero"))
    link = tmp_path / "link.toml"
    link.symlink_to(fifo)  # also through a symlink
    with pytest.raises(ConfigError, match="not a regular file"):
        check_openable(link)
    real = tmp_path / "real.toml"
    real.write_text(USER)
    ok = tmp_path / "ok.toml"
    ok.symlink_to(real)
    check_openable(ok)  # a symlink to a regular file is fine


def test_save_as_never_reads_a_target_that_is_not_a_regular_file(tmp_path):
    source = tmp_path / "config.toml"
    source.write_text(USER)
    fifo = tmp_path / "pipe.toml"
    os.mkfifo(fifo)
    with pytest.raises(ConfigError, match="not a regular file"):
        save_copy(source, USER, fifo)
    with pytest.raises(ConfigError, match="not a regular file"):
        save_copy(source, USER, tmp_path)
