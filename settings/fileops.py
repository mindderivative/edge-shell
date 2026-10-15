"""File-menu decisions without GTK: what happens to unsaved changes when the window leaves a
config (Close, Exit, New, Open, Save As, the window's close button). Pure: the questions are
asked through a callable, so tests answer them and no dialog runs."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Any


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
