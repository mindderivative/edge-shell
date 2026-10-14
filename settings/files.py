"""Safe writes of the user config: atomic replace, one backup per settings session, restore.
Pure: no GTK, no tomlkit (it imports shell.config.models for ConfigError), so
`main.py --restore-config` works without either.
OS errors (a read-only folder, a full disk) are raised as OSError; settings.session turns
them into ConfigError for the window."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

from shell.config.models import ConfigError


def backup_path(path: Path) -> Path:
    """config.toml -> config.toml.bak, next to the file the path points to."""
    path = path.resolve()
    return path.with_name(path.name + ".bak")


def read_text(path: Path) -> str:
    """The file's text; "" when it does not exist (the defaults apply)."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"{path}: {exc}") from None


def write_atomic(path: Path, data: str | bytes, *, mode: int | None = None) -> None:
    """Write `data` to a temporary file next to the target, then rename it over the target, so
    the shell's watcher never reads a half-written file. A symlinked config keeps its link:
    the file it points to is replaced (the shell's ConfigWatcher also watches that file). A
    broken symlink's missing target directories are created (the first change creates the
    file). The temporary file is created private (0600, O_EXCL, never through a symlink) and
    given its final mode before anything is written, so a private config is never readable by
    others, not even briefly. `mode` is that final mode; by default the mode of an existing
    file, else the usual 0666 minus the umask."""
    target = path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if mode is None:
        try:
            mode = stat.S_IMODE(target.stat().st_mode)
        except FileNotFoundError:
            umask = os.umask(0)
            os.umask(umask)
            mode = 0o666 & ~umask
    raw = data.encode("utf-8") if isinstance(data, str) else data
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        try:
            os.fchmod(fd, mode)
            with os.fdopen(fd, "wb") as handle:
                fd = -1
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            if fd != -1:
                os.close(fd)
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)  # only the temporary file this call created
        raise
    _fsync_dir(target.parent)


def _fsync_dir(directory: Path) -> None:
    """Make the rename durable; best effort."""
    try:
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def write_backup(path: Path) -> Path | None:
    """Copy the current file, byte for byte, to config.toml.bak (atomically, private from the
    start when the file is: with the file's own mode, so a private config does not get a
    world-readable copy); None when there is no file."""
    target = path.resolve()
    if not target.exists():
        return None
    backup = backup_path(target)
    write_atomic(backup, target.read_bytes(), mode=stat.S_IMODE(target.stat().st_mode))
    return backup


def _free_name(path: Path) -> Path:
    """`path`, or path.2, path.3, ... when it exists (an earlier restore's file is kept)."""
    n = 2
    candidate = path
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.{n}")
        n += 1
    return candidate


def restore_backup(path: Path) -> str:
    """Put config.toml.bak back in place. The current file is kept first as
    config.toml.before-restore (config.toml.before-restore.2, .3, ... when an earlier restore
    left one: it is never overwritten), so a restore can itself be undone by hand. Returns a
    line for the user; raises ConfigError when there is no backup."""
    target = path.resolve()
    backup = backup_path(target)
    if not backup.exists():
        raise ConfigError(f"no backup to restore: {backup} does not exist")
    data = backup.read_bytes()
    kept = None
    if target.exists():
        kept = _free_name(target.with_name(target.name + ".before-restore"))
        write_atomic(kept, target.read_bytes(), mode=stat.S_IMODE(target.stat().st_mode))
    write_atomic(
        target, data, mode=stat.S_IMODE(target.stat().st_mode) if target.exists() else None
    )
    return f"restored {target} from {backup}" + (
        f" (the replaced file is {kept})" if kept is not None else ""
    )
