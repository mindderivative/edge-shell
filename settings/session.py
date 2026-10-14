"""One settings-window session on the user config file. Pure (no GTK).

Every change is applied to the file's current text with settings.document, checked with the
shell's own rules (shell.config.loader + registry.validate_widgets) and only then written,
atomically; the running shell picks it up through its file watcher. A change the shell would
reject is never written. Before the first write of a session the file is copied to
config.toml.bak (`main.py --restore-config` puts it back).
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from settings import files
from settings.document import UserDocument
from shell.config.loader import DEFAULT_PATH, load_config_text
from shell.config.models import Config, ConfigError
from shell.registry import validate_widgets

Edit = Callable[[UserDocument], Any]


class ChangedOutside(ConfigError):
    """The file changed on disk since the session last read it (edited by hand); the
    session has re-read it and the change was not applied."""


def check_text(text: str, default_path: Path = DEFAULT_PATH) -> Config:
    """The config `text` would give, by the shell's rules; ConfigError naming the key path."""
    config = load_config_text(text, default_path)
    validate_widgets(config)
    return config


class SettingsSession:
    def __init__(self, path: Path, default_path: Path = DEFAULT_PATH):
        self.path = path
        self.default_path = default_path
        self.history: list[str] = []  # texts before each write, for undo
        self.backed_up = False
        self.start_text = ""
        self.text = ""
        self.user: dict[str, Any] = {}  # the user file as plain data
        self.config: Config | None = None  # None while the file on disk is invalid
        self.error: str | None = None  # why the file on disk is invalid
        self.reload()
        self.start_text = self.text

    def reload(self) -> None:
        """(Re)read the file. An invalid file is kept as it is: `error` says why, `config` is
        None and edits are still allowed (an edit that fixes the file is written)."""
        self.text = files.read_text(self.path)
        try:
            self.user = tomllib.loads(self.text)
        except tomllib.TOMLDecodeError:
            self.user = {}
        try:
            self.config, self.error = check_text(self.text, self.default_path), None
        except ConfigError as exc:
            self.config, self.error = None, str(exc)

    def changed_outside(self) -> bool:
        return files.read_text(self.path) != self.text

    def rebase(self) -> None:
        """Re-read a file that was changed outside the window (a hand edit): the hand edit
        becomes the new starting point (Revert all goes back to it, never past it) and the
        undo history, which led to a file that no longer exists, is cleared."""
        self.reload()
        self.history.clear()
        self.start_text = self.text

    def apply(self, edit: Edit) -> Config:
        """Apply one change and write it; returns the new config. Raises ChangedOutside (the
        session re-read the file: a new baseline) or ConfigError (nothing written)."""
        if self.changed_outside():
            self.rebase()
            raise ChangedOutside(
                f"{self.path} was changed outside the settings window; it has been re-read "
                "and the last change was not applied"
            )
        doc = UserDocument(self.text)
        edit(doc)
        config = check_text(doc.text, self.default_path)
        if not self.backed_up:
            self._write_file(lambda: files.write_backup(self.path))
            self.backed_up = True
        self._write_file(lambda: files.write_atomic(self.path, doc.text))
        self.history.append(self.text)
        self.text, self.user = doc.text, tomllib.loads(doc.text)
        self.config, self.error = config, None
        return config

    def undo(self) -> bool:
        """Put back the text before the last change; False when there is nothing to undo."""
        if not self.history:
            return False
        if self.changed_outside():
            self.rebase()
            raise ChangedOutside(f"{self.path} was changed outside the settings window")
        self._write_file(lambda: files.write_atomic(self.path, self.history[-1]))
        self.history.pop()
        self.reload()
        return True

    def revert(self) -> None:
        """Back to the file as it was when the session started, or when it was last changed
        by hand (no validation: it was the file on disk). Refused, with ChangedOutside, when
        the file was changed by hand since the last read: that hand edit becomes the start."""
        if self.changed_outside():
            self.rebase()
            raise ChangedOutside(
                f"{self.path} was changed outside the settings window; Revert all keeps that "
                "change (it is the new starting point)"
            )
        self._write_file(lambda: files.write_atomic(self.path, self.start_text))
        self.history.clear()
        self.reload()

    def _write_file(self, write: Callable[[], Any]) -> None:
        """Run one file write; an OSError (read-only folder, disk full) is a ConfigError the
        window shows, never an exception inside a GTK callback."""
        try:
            write()
        except OSError as exc:
            raise ConfigError(f"cannot write {self.path}: {exc}") from None
