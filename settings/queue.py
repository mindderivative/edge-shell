"""The settings window's edit queue (Phil, 2026-10-15: "Maybe make a queue to ensure nothing
gets lost"). Pure: no GTK.

Every value edit of a row (a set, or a reset) is pushed here with its key path and applied by
the view in arrival order. Spin buttons push on every step and the view applies the queue once
the user pauses (one shared timer, settings.view); every other edit is applied at once, after
what is queued before it. Per path the last edit wins: a new edit of a queued path replaces it
and moves to the end (the order of the latest edits is kept), and an edit back to the value the
row showed before (its `base`) takes the path out of the queue, so a value changed and changed
back is never written (an inherited value stays inherited).

Structural edits (a panel added, removed, moved), Undo, Redo, Save, leaving the config and
Detect monitors are barriers: the view applies the whole queue first. A rebuild of the pages
never touches the queue (queued edits are not held by the rows). A hand edit met while edits
are queued drops them and the view names them on screen (`describe`): they were made for the
file as it was, and panel entries are tracked by index, so the same path may mean another panel
in the re-read file. Revert all drops them silently: it puts everything back anyway."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

RESET = object()  # the edit "remove this key" (the row's reset button)
_NO_BASE = object()


def _same(a: Any, b: Any) -> bool:
    return type(a) is type(b) and a == b


@dataclass(frozen=True)
class QueuedEdit:
    path: tuple
    value: Any  # the new value, or RESET
    base: Any = _NO_BASE  # what the row showed before its first queued edit


class EditQueue:
    def __init__(self) -> None:
        self._items: dict[tuple, QueuedEdit] = {}  # insertion order = apply order

    def push(self, path: tuple, value: Any, base: Any = _NO_BASE) -> None:
        """Queue `value` (or RESET) for `path`. `base`: the value shown before the edit (a
        spin button's): an edit back to it un-queues the path."""
        old = self._items.pop(path, None)
        if old is not None:
            base = old.base
        if base is not _NO_BASE and _same(value, base):
            return
        self._items[path] = QueuedEdit(path, value, base)

    def pop(self) -> QueuedEdit | None:
        """The oldest edit, removed; None when empty."""
        if not self._items:
            return None
        path = next(iter(self._items))
        return self._items.pop(path)

    def drop(self) -> list[QueuedEdit]:
        """Remove and return every queued edit."""
        items = list(self._items.values())
        self._items.clear()
        return items

    def pending(self, path: tuple) -> bool:
        return path in self._items

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self):
        return iter(list(self._items.values()))


def path_text(path: tuple) -> str:
    """("monitors", "HDMI-A-1", "panels", 0, "depth") -> "monitors.HDMI-A-1.panels[0].depth"."""
    text = ""
    for key in path:
        text += f"[{key}]" if isinstance(key, int) else (f".{key}" if text else str(key))
    return text


def describe(edits: list[QueuedEdit]) -> str:
    """The dropped edits as one line: "theme.thickness = 17, monitors.X.panels[0].depth
    (reset)"."""
    parts = []
    for edit in edits:
        value = "(reset)" if edit.value is RESET else f"= {edit.value!r}"
        parts.append(f"{path_text(edit.path)} {value}")
    return ", ".join(parts)
