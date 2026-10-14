"""settings.files: atomic writes, the session backup and restore (pure, stdlib)."""

import os
import stat

import pytest

from settings import files
from shell.config.models import ConfigError


def test_write_atomic_creates_the_file_and_its_directory(tmp_path):
    path = tmp_path / "edge-shell" / "config.toml"
    files.write_atomic(path, "a = 1\n")
    assert path.read_text() == "a = 1\n"
    assert [p.name for p in path.parent.iterdir()] == ["config.toml"]  # no temp file left


def test_write_atomic_replaces_and_keeps_the_mode(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("old\n")
    os.chmod(path, 0o600)
    files.write_atomic(path, "new\n")
    assert path.read_text() == "new\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_write_atomic_follows_a_symlink(tmp_path):
    real = tmp_path / "dotfiles" / "config.toml"
    real.parent.mkdir()
    real.write_text("old\n")
    link = tmp_path / "config.toml"
    link.symlink_to(real)
    files.write_atomic(link, "new\n")
    assert link.is_symlink()
    assert real.read_text() == "new\n"


def test_a_failed_write_leaves_the_old_file_and_no_temp_file(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text("old\n")

    def boom(*_args):
        raise OSError("disk full")

    monkeypatch.setattr(files.os, "replace", boom)
    with pytest.raises(OSError, match="disk full"):
        files.write_atomic(path, "new\n")
    assert path.read_text() == "old\n"
    assert [p.name for p in tmp_path.iterdir()] == ["config.toml"]


def test_read_text_of_a_missing_file_is_empty(tmp_path):
    assert files.read_text(tmp_path / "absent.toml") == ""


def test_read_text_of_an_unreadable_path_names_it(tmp_path):
    (tmp_path / "dir.toml").mkdir()  # IsADirectoryError, an OSError
    with pytest.raises(ConfigError, match="dir.toml"):
        files.read_text(tmp_path / "dir.toml")


def test_backup_copies_the_current_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("a = 1\n")
    assert files.write_backup(path) == tmp_path / "config.toml.bak"
    assert (tmp_path / "config.toml.bak").read_text() == "a = 1\n"


def test_backup_keeps_the_files_mode(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("a = 1\n")
    os.chmod(path, 0o600)  # a private config never gets a world-readable copy
    backup = files.write_backup(path)
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600


def test_backup_of_a_missing_file_is_none(tmp_path):
    assert files.write_backup(tmp_path / "config.toml") is None
    assert list(tmp_path.iterdir()) == []


def test_restore_puts_the_backup_back_and_keeps_the_replaced_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("broken\n")
    (tmp_path / "config.toml.bak").write_text("good\n")
    message = files.restore_backup(path)
    assert path.read_text() == "good\n"
    assert (tmp_path / "config.toml.before-restore").read_text() == "broken\n"
    assert "config.toml.bak" in message and "before-restore" in message


def test_a_second_restore_keeps_the_first_replaced_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("broken\n")
    (tmp_path / "config.toml.bak").write_text("good\n")
    files.restore_backup(path)
    path.write_text("edited again\n")
    message = files.restore_backup(path)
    assert (tmp_path / "config.toml.before-restore").read_text() == "broken\n"
    assert (tmp_path / "config.toml.before-restore.2").read_text() == "edited again\n"
    assert "before-restore.2" in message and path.read_text() == "good\n"


def test_restore_without_a_current_file(tmp_path):
    (tmp_path / "config.toml.bak").write_text("good\n")
    files.restore_backup(tmp_path / "config.toml")
    assert (tmp_path / "config.toml").read_text() == "good\n"
    assert not (tmp_path / "config.toml.before-restore").exists()


def test_restore_without_a_backup_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="no backup"):
        files.restore_backup(tmp_path / "config.toml")
