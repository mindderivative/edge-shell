"""One settings-window session on the user config file. Pure (no GTK).

Every change is applied to the file's current text with settings.document, checked with the
shell's own rules (shell.config.loader + registry.validate_widgets) and only then written,
atomically; the running shell picks it up through its file watcher. A change the shell would
reject is never written. Before the first write of a session the file is copied to
config.toml.bak (`main.py --restore-config` puts it back).

The saved point (File > Save): live apply stays, every change is still written at once. Save
records the current text as the saved point and copies the file to config.toml.bak; the
session is `dirty` while its text differs from the saved point (an Undo back to it is not
dirty). Discard writes the saved point back (keeping an invalid text it replaces as
config.toml.before-revert, like Revert all). A hand edit, valid or not, becomes the saved
point: it was saved, in another editor, so Discard never writes over it.

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
        self.redo_history: list[str] = []  # texts an undo (or redo) replaced, for redo
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
        self.saved_text = self.text  # the saved point: Save moves it, Discard writes it back

    @property
    def dirty(self) -> bool:
        """The file differs from the saved point (Close, Exit, New and Open ask first)."""
        return self.text != self.saved_text

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
        undo and redo histories, which led to a file that no longer exists, are cleared. An
        INVALID hand edit does not: the last valid baseline stays, so Revert all (confirmed by
        the user) is a way out of a broken file instead of rewriting the same broken text.
        Any hand edit, valid or not, is the new saved point (it was saved, in an editor)."""
        self.reload()
        self.history.clear()
        self.redo_history.clear()
        self.saved_text = self.text
        if self.config is not None:
            self.start_text = self.text

    def apply(self, edit: Edit) -> Config:
        """Apply one change and write it; returns the new config. Raises ChangedOutside (the
        session re-read the file: a new baseline) or ConfigError (nothing written). A written
        change ends the redo line."""
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
        self.redo_history.clear()
        self.text, self.user = doc.text, tomllib.loads(doc.text)
        self.config, self.error = config, None
        return config

    def undo(self) -> bool:
        """Put back the text before the last change; False when there is nothing to undo."""
        return self._step(self.history, self.redo_history)

    def redo(self) -> bool:
        """Put back the text the last Undo replaced; False when there is nothing to redo
        (a new change, Revert all, Discard or a hand edit ends the redo line)."""
        return self._step(self.redo_history, self.history)

    def _step(self, source: list[str], target: list[str]) -> bool:
        """Write the last text of `source`; the text it replaces goes onto `target`."""
        if not source:
            return False
        if self.changed_outside():
            self.rebase()
            raise ChangedOutside(f"{self.path} was changed outside the settings window")
        self._write_file(lambda: files.write_atomic(self.path, source[-1]))
        source.pop()
        target.append(self.text)
        self.reload()
        return True

    def save(self) -> None:
        """File > Save: the current text becomes the saved point and the file is copied to
        config.toml.bak (what `--restore-config` puts back; later changes of this session do
        not overwrite that copy). Refused, with ChangedOutside, after a hand edit (re-read: it
        is the saved point now), and while the file is invalid (the copy would replace a good
        .bak with a broken file). A copy that cannot be written moves nothing."""
        if self.changed_outside():
            self.rebase()
            raise ChangedOutside(
                f"{self.path} was changed outside the settings window; it has been re-read "
                "and is the saved state now"
            )
        if self.config is None:
            raise ConfigError(
                f"{self.path} is invalid ({self.error}); fix it before saving, "
                "Save would copy it over the good config.toml.bak"
            )
        backup = files.backup_path(self.path.resolve())
        self._write_file(lambda: files.write_backup(self.path), backup)
        self.backed_up = True
        self.saved_text = self.text

    def discard(self) -> None:
        """Back to the saved point (Close, Exit, New or Open with unsaved changes, answered
        Discard): the saved text is written back, like Revert all but to the saved point, and
        both histories are cleared. Refused, with ChangedOutside, after a hand edit (which is
        then the saved point: nothing is left to discard)."""
        if self.changed_outside():
            self.rebase()
            raise ChangedOutside(
                f"{self.path} was changed outside the settings window; it has been re-read "
                "and nothing was discarded"
            )
        if self.dirty:
            if self.keeps_hand_edit():  # an invalid text being replaced: keep it first
                self._write_file(lambda: files.keep_before_revert(self.path))
            self._write_file(lambda: files.write_atomic(self.path, self.saved_text))
        self.history.clear()
        self.redo_history.clear()
        self.reload()

    def keeps_hand_edit(self) -> bool:
        """True when Revert all would replace an invalid hand edit (it has no valid baseline
        of its own), which is then kept as config.toml.before-revert."""
        return self.config is None and self.text != self.start_text

    def revert(self) -> None:
        """Back to the file as it was when the session started, or when it was last changed
        by hand (no validation: it was the file on disk). An invalid hand edit being replaced is
        first kept as config.toml.before-revert (if that cannot be written, nothing changes).
        Refused, with ChangedOutside, when the file was changed by hand since the last read:
        that hand edit becomes the start. Clears both histories (Revert all is not undone)."""
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
        self.redo_history.clear()
        self.reload()

    def _write_file(self, write: Callable[[], Any], target: Path | None = None) -> None:
        """Run one file write; an OSError (read-only folder, disk full) is a ConfigError the
        window shows, never an exception inside a GTK callback."""
        try:
            write()
        except OSError as exc:
            raise ConfigError(f"cannot write {target or self.path}: {exc}") from None
