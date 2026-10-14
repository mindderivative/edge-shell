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


def _spy_modes(monkeypatch):
    """Record the mode of every regular file at each fsync and at each replace."""
    seen: list[int] = []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(fd):
        if stat.S_ISREG(os.fstat(fd).st_mode):
            seen.append(stat.S_IMODE(os.fstat(fd).st_mode))
        return real_fsync(fd)

    def replace(src, dst):
        seen.append(stat.S_IMODE(os.stat(src).st_mode))
        return real_replace(src, dst)

    monkeypatch.setattr(files.os, "fsync", fsync)
    monkeypatch.setattr(files.os, "replace", replace)
    return seen


def _private(tmp_path, data=b"secret = 1\n"):
    path = tmp_path / "config.toml"
    path.write_bytes(data)
    os.chmod(path, 0o600)
    return path


def test_write_atomic_temp_is_never_broader_than_the_target(tmp_path, monkeypatch):
    path = _private(tmp_path)
    seen = _spy_modes(monkeypatch)
    files.write_atomic(path, "secret = 2\n")
    assert seen and all(m & ~0o600 == 0 for m in seen)


def test_write_backup_is_private_throughout(tmp_path, monkeypatch):
    path = _private(tmp_path)
    seen = _spy_modes(monkeypatch)
    backup = files.write_backup(path)
    assert seen and all(m & ~0o600 == 0 for m in seen)
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600


def test_restore_is_private_throughout(tmp_path, monkeypatch):
    path = _private(tmp_path)
    files.write_backup(path)
    path.write_text("secret = 9\n")
    seen = _spy_modes(monkeypatch)
    files.restore_backup(path)
    assert seen and all(m & ~0o600 == 0 for m in seen)
    kept = tmp_path / "config.toml.before-restore"
    assert stat.S_IMODE(kept.stat().st_mode) == 0o600


def test_write_atomic_explicit_mode(tmp_path):
    path = tmp_path / "c.toml"
    files.write_atomic(path, "a = 1\n", mode=0o640)
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


def test_a_planted_file_or_symlink_at_the_old_temp_name_is_left_alone(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("old\n")
    victim = tmp_path / "victim"
    victim.write_text("keep\n")
    planted = tmp_path / f".config.toml.{os.getpid()}.tmp"
    planted.symlink_to(victim)
    files.write_atomic(path, "new\n")
    assert victim.read_text() == "keep\n"
    assert planted.is_symlink()
    assert path.read_text() == "new\n"
    # and a failing write does not remove a file it did not create
    planted.unlink()
    planted.write_text("mine\n")
    files.write_atomic(path, "newer\n")
    assert planted.read_text() == "mine\n"


def test_the_parent_directory_is_fsynced_after_the_replace(tmp_path, monkeypatch):
    order: list[str] = []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            order.append("dir")
        return real_fsync(fd)

    def replace(src, dst):
        order.append("replace")
        return real_replace(src, dst)

    monkeypatch.setattr(files.os, "fsync", fsync)
    monkeypatch.setattr(files.os, "replace", replace)
    files.write_atomic(tmp_path / "c.toml", "a = 1\n")
    assert order == ["replace", "dir"]


def test_backup_and_restore_are_byte_exact(tmp_path):
    data = b"a = 1\r\nb = 2\r\n"
    path = tmp_path / "config.toml"
    path.write_bytes(data)
    backup = files.write_backup(path)
    assert backup.read_bytes() == data
    path.write_bytes(b"changed\n")
    files.restore_backup(path)
    assert path.read_bytes() == data
    assert (tmp_path / "config.toml.before-restore").read_bytes() == b"changed\n"


def test_a_non_utf8_file_backs_up_and_restores(tmp_path):
    data = b"a = '\xff\xfe'\n"
    path = tmp_path / "config.toml"
    path.write_bytes(data)
    assert files.write_backup(path).read_bytes() == data
    path.write_bytes(b"x\n")
    files.restore_backup(path)
    assert path.read_bytes() == data
