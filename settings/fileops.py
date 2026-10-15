"""File-menu work without GTK: what happens to unsaved changes when the window leaves a config
(Close, Exit, New, Open, Save As, the window's close button), and the file operations of New,
Open and Save As. Pure: the questions are asked through a callable, so tests answer them and
no dialog runs; file-system errors come back as ConfigError, for the window to show."""

from __future__ import annotations

import stat
from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Any

from settings import files
from shell.config.loader import USER_PATH
from shell.config.models import ConfigError

# File > New writes this: valid TOML with no keys, so every value is the default
NEW_TEXT = "# Edge Shell config. Keys left out take their defaults (config.default.toml).\n"


class Answer(Enum):
    SAVE = "save"
    DISCARD = "discard"
    CANCEL = "cancel"


def unsaved_question(path: Path) -> tuple[str, str]:
    """The unsaved-changes dialog's two lines."""
    return (
        f"Save the changes to {path.name}?",
        f"{path} has changes since it was last saved. They are already applied to the "
        "file (and to a shell that reads it). Save keeps them; Discard puts the file back "
        "as it was last saved.",
    )


def leave(session: Any, ask: Callable[[], Answer]) -> bool:
    """May the window leave `session`'s config? True at once when nothing changed since the
    last save; otherwise `ask` decides: Save (the saved point moves to the current text),
    Discard (the saved text is written back) or Cancel (False: stay). A failed save or
    discard raises (ConfigError, or ChangedOutside after a hand edit): the caller shows it
    and stays."""
    if not session.dirty:
        return True
    answer = ask()
    if answer is Answer.CANCEL:
        return False
    if answer is Answer.SAVE:
        session.save()
    else:
        session.discard()
    return True


def default_folder(user_path: Path = USER_PATH) -> Path:
    """Where the file choosers start: the default config's folder (~/.config/edge-shell),
    created when missing; the home folder if it cannot be."""
    folder = user_path.parent
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        return Path.home()
    return folder


def new_name(folder: Path) -> str:
    """A file name File > New suggests: config.toml, or config-2.toml, -3, ... when taken."""
    name, n = "config.toml", 2
    while (folder / name).exists():
        name, n = f"config-{n}.toml", n + 1
    return name


def same_file(a: Path, b: Path) -> bool:
    """The same file, also through a symlink or a relative path."""
    return a.resolve() == b.resolve()


def new_path(path: Path) -> Path:
    """The file File > New creates for a chosen name, the same on every Python version (it
    reads the name, never Path.suffix): trailing dots go ('x.' is 'x'), a name that is only
    '.toml' becomes config.toml, and '.toml' is added unless the name already ends with it in
    any case ('x' -> x.toml, 'my.config' -> my.config.toml, 'X.TOML' is kept), so the Open
    filter always shows the file."""
    name = path.name.rstrip(".")
    if name.lower() == ".toml":
        name = "config.toml"
    elif not name.lower().endswith(".toml"):
        name += ".toml"
    return path.with_name(name)


def check_new(path: Path) -> None:
    """File > New never replaces a file: an existing path (also a dangling symlink) is
    refused, before anything is asked or written."""
    if path.exists() or path.is_symlink():
        raise ConfigError(
            f"{path} already exists; New never replaces a file: choose another name, or open "
            "it with File > Open"
        )


def create_new(path: Path) -> Path:
    """File > New: write NEW_TEXT at `path` (see new_path; missing folders are created) and
    return the file written. Never replaces a file: an existing path is refused."""
    path = new_path(path)
    check_new(path)
    try:
        files.write_atomic(path, NEW_TEXT)
    except OSError as exc:
        raise ConfigError(f"cannot create {path}: {exc}") from None
    return path


def require_regular(path: Path) -> None:
    """Only a regular file (after following symlinks) is read: a FIFO would block the window
    for ever, a device never ends. Raises ConfigError; a missing path passes (callers check)."""
    if path.exists() and not stat.S_ISREG(path.stat().st_mode):
        raise ConfigError(f"{path} is not a regular file")


def check_openable(path: Path) -> None:
    """File > Open: refuse what the settings window could not show (missing, a folder,
    unreadable, not UTF-8 text). A text that is not a valid config does open (read-only, with
    its error), as at start."""
    if not path.exists():
        raise ConfigError(f"{path} does not exist")
    require_regular(path)
    files.read_text(path)  # ConfigError for a folder, no permission or a binary file


def save_copy(source: Path, text: str, target: Path) -> Path | None:
    """File > Save As: write `text` to `target`. A file already there (the chooser asked
    before replacing it) is first kept as target.before-save-as (.2, .3, ...; returned). A
    new file gets the mode of `source` (a private config stays private), a replaced one keeps
    its own."""
    kept = None
    mode = None
    try:
        if target.exists():
            require_regular(target)  # before keep_copy reads it
            kept = files.keep_copy(target, ".before-save-as")
        elif source.exists():
            mode = stat.S_IMODE(source.stat().st_mode)
        files.write_atomic(target, text, mode=mode)
    except OSError as exc:
        raise ConfigError(f"cannot write {target}: {exc}") from None
    return kept
