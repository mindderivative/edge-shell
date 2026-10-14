"""One settings-window session on the user config file. Pure (no GTK).

Every change is applied to the file's current text with settings.document, checked with the
shell's own rules (shell.config.loader + registry.validate_widgets) and only then written,
atomically; the running shell picks it up through its file watcher. A change the shell would
reject is never written. Before the first write of a session the file is copied to
config.toml.bak (`main.py --restore-config` puts it back).

Limits, by design: the file is read with universal newlines, so the first edit rewrites CRLF
line endings as LF (the .bak stays byte-exact) and `changed_outside` cannot see a hand edit
that only changes line endings. When the config file is missing at open, an older
config.toml.bak from a previous session survives (the first write only backs up an existing
file), and `--restore-config` would restore that older file. An edit that raises something
other than ConfigError escapes `apply` (UserDocument wraps the realistic ones). A file that
is invalid when the session opens has no valid baseline: Revert all would only rewrite it, so
the window offers the hand fix or `--restore-config` instead.
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
        # An invalid file at open has no valid baseline; keep its text so Revert all is a no-op
        # (a later valid hand edit becomes the baseline through rebase).
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
        """Re-read a file that was changed outside the window (a hand edit): a valid hand edit
        becomes the new starting point (Revert all goes back to it, never past it) and the
        undo history, which led to a file that no longer exists, is cleared. An INVALID hand
        edit does not: the last valid baseline stays, so Revert all (confirmed by the user)
        is a way out of a broken file instead of rewriting the same broken text."""
        self.reload()
        self.history.clear()
        if self.config is not None:
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
        if doc.text == self.text:
            return config  # nothing changed: no backup, no write, no do-nothing undo step
        if not self.backed_up:
            backup = files.backup_path(self.path.resolve())
            self._write_file(lambda: files.write_backup(self.path), backup)
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

    def keeps_hand_edit(self) -> bool:
        """True when Revert all would replace an invalid hand edit (it has no valid baseline
        of its own), which is then kept as config.toml.before-revert."""
        return self.config is None and self.text != self.start_text

    def revert(self) -> None:
        """Back to the file as it was when the session started, or when it was last changed
        by hand (no validation: it was the file on disk). An invalid hand edit being replaced is
        first kept as config.toml.before-revert (if that cannot be written, nothing changes).
        Refused, with ChangedOutside, when the file was changed by hand since the last read:
        that hand edit becomes the start."""
        if self.changed_outside():
            self.rebase()
            raise ChangedOutside(
                f"{self.path} was changed outside the settings window; Revert all keeps that "
                "change (it is the new starting point)"
            )
        if self.start_text != self.text:
            if self.keeps_hand_edit():  # the only copy of that text: keep it first
                self._write_file(lambda: files.keep_before_revert(self.path))
            self._write_file(lambda: files.write_atomic(self.path, self.start_text))
        self.history.clear()
        self.reload()

    def _write_file(self, write: Callable[[], Any], target: Path | None = None) -> None:
        """Run one file write; an OSError (read-only folder, disk full) is a ConfigError the
        window shows, never an exception inside a GTK callback."""
        try:
            write()
        except OSError as exc:
            raise ConfigError(f"cannot write {target or self.path}: {exc}") from None
