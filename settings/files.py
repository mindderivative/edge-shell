"""Safe writes of the user config: atomic replace, one backup per settings session, restore.
Pure: stdlib only (no GTK, no tomlkit), so `main.py --restore-config` works without either.
OS errors (a read-only folder, a full disk) are raised as OSError; settings.session turns
them into ConfigError for the window."""

from __future__ import annotations

import os
import shutil
import stat
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


def write_atomic(path: Path, text: str) -> None:
    """Write `text` to a temporary file next to the target, then rename it over the target, so
    the shell's watcher never reads a half-written file. A symlinked config keeps its link:
    the file it points to is replaced (the shell's ConfigWatcher also watches that file). The
    mode of an existing file is kept."""
    target = path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(tmp, stat.S_IMODE(target.stat().st_mode))
        except FileNotFoundError:
            pass
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)  # only the temporary file this call created
        raise


def write_backup(path: Path) -> Path | None:
    """Copy the current file to config.toml.bak (atomically, with the file's own mode, so a
    private config does not get a world-readable copy); None when there is no file."""
    target = path.resolve()
    if not target.exists():
        return None
    backup = backup_path(target)
    write_atomic(backup, read_text(target))
    shutil.copymode(target, backup)
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
    text = read_text(backup)
    kept = None
    if target.exists():
        kept = _free_name(target.with_name(target.name + ".before-restore"))
        write_atomic(kept, read_text(target))
        shutil.copymode(target, kept)
    write_atomic(target, text)
    return f"restored {target} from {backup}" + (
        f" (the replaced file is {kept})" if kept is not None else ""
    )
