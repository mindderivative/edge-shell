"""Edit the user's config.toml in place with tomlkit, keeping comments and layout. Pure (no GTK).

Every edit is checked: the edited text is parsed back with tomllib and must equal the same edit
applied to the plain data. tomlkit can misplace a new table (a table added inside a dotted-key
table is written as a top-level header, which moves the keys to another table); such an edit
raises DocumentError instead of producing a file that means something else.

A path is a tuple of keys from the top of the file; an int indexes the panel list, e.g.
("monitors", "HDMI-A-1", "panels", 0, "handle", "shape").
"""

from __future__ import annotations

import copy
import tomllib
from collections import Counter
from collections.abc import Callable
from typing import Any

import tomlkit
from tomlkit.exceptions import TOMLKitError
from tomlkit.items import AoT

from shell.config.models import ConfigError

Path_ = tuple[str | int, ...]


class DocumentError(ConfigError):
    """An edit that could not be made in place (the file is left unchanged)."""


def _container_kind(path: Path_, i: int) -> str:
    """How to create the missing key path[i]: "table" for a top-level table, a monitor's
    table or the monitors table itself (readable headers), "dotted" anywhere deeper (inside a
    [table], a [[panels]] entry or a dotted table; also always valid TOML)."""
    if i == 0 or (i == 1 and path[0] == "monitors"):
        return "table"
    return "dotted"


class UserDocument:
    def __init__(self, text: str = ""):
        try:
            self._doc = tomlkit.parse(text)
            self._data = tomllib.loads(text)
        except (TOMLKitError, tomllib.TOMLDecodeError) as exc:
            raise ConfigError(f"TOML syntax error: {exc}") from None

    @property
    def text(self) -> str:
        return tomlkit.dumps(self._doc)

    @property
    def data(self) -> dict[str, Any]:
        """Plain dicts and lists (a copy)."""
        return copy.deepcopy(self._data)

    # ---- edits ---------------------------------------------------------------------------
    def set(self, path: Path_, value: Any) -> None:
        self._edit(lambda doc: _set(doc, path, value), lambda data: _plain_set(data, path, value))

    def unset(self, path: Path_) -> None:
        """Remove the key (the value is inherited again) and any table left empty by it."""
        self._edit(lambda doc: _unset(doc, path), lambda data: _plain_unset(data, path))

    def add_panel(self, monitor: str, widget: str) -> int:
        """Append a panel entry with only its widget (every other key from the widget's
        defaults); returns its index."""
        self._edit(
            lambda doc: _add_panel(doc, monitor, widget),
            lambda data: _plain_panels(data, monitor, create=True).append({"widget": widget}),
        )
        return len(self._data["monitors"][monitor]["panels"]) - 1

    def remove_panel(self, monitor: str, index: int) -> None:
        self._edit(
            lambda doc: _remove_panel(doc, monitor, index),
            lambda data: _plain_remove_panel(data, monitor, index),
        )

    def move_panel(self, monitor: str, index: int, to: int) -> None:
        """Move the entry at `index` so it ends up at `to` (config order decides ties)."""

        def plain(data):
            panels = _plain_panels(data, monitor)
            panels.insert(to, panels.pop(index))

        self._edit(lambda doc: _move_panel(doc, monitor, index, to), plain)

    def _edit(self, on_doc: Callable[[Any], None], on_data: Callable[[dict], None]) -> None:
        expected = copy.deepcopy(self._data)
        try:
            on_data(expected)
        except (KeyError, IndexError, TypeError) as exc:
            raise DocumentError(f"cannot edit the config: no such key or entry ({exc})") from None
        doc = tomlkit.parse(tomlkit.dumps(self._doc))  # edit a copy; keep self on failure
        try:
            on_doc(doc)
            got = tomllib.loads(tomlkit.dumps(doc))
        except (TOMLKitError, tomllib.TOMLDecodeError, KeyError, IndexError, TypeError) as exc:
            raise DocumentError(f"cannot edit the config in place: {exc}") from None
        if got != expected:
            raise DocumentError(
                "cannot edit the config in place without changing other keys; edit the file by hand"
            )
        lost = _header_comments(self.text) - _comments(tomlkit.dumps(doc))
        if lost:
            raise DocumentError(
                f"cannot edit the config in place without losing the comment {min(lost)!r} "
                "above a table; edit the file by hand"
            )
        self._doc, self._data = doc, expected


# ---- comment census ----------------------------------------------------------------------
# tomlkit keeps the comment lines above a table header inside the table BEFORE it, so removing
# or pruning that table would silently drop them. Whole-line comments above a header (blank
# lines allowed in between) must survive an edit; other comments may go with the key or entry
# they sat in. A comment can still MOVE (a key or panel added at the end of the table before
# it lands below the comment): see decision 2.


def _comments(text: str) -> Counter[str]:
    return Counter(s for s in (line.strip() for line in text.splitlines()) if s.startswith("#"))


def _header_comments(text: str) -> Counter[str]:
    found: Counter[str] = Counter()
    block: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            block.append(s)
        elif s.startswith("["):
            found.update(block)
            block = []
        elif s:
            block = []
    return found


# ---- tomlkit side ------------------------------------------------------------------------


def _set(doc, path: Path_, value: Any) -> None:
    node = doc
    for i, key in enumerate(path[:-1]):
        if isinstance(key, int):
            node = node[key]
            continue
        if key not in node:
            if _container_kind(path, i) == "dotted":
                node.add(tomlkit.key([str(k) for k in path[i:]]), value)
                return
            node[key] = tomlkit.table(is_super_table=key == "monitors")
        node = node[key]
    node[path[-1]] = value


def _unset(doc, path: Path_) -> None:
    chain = [doc]
    for key in path[:-1]:
        chain.append(chain[-1][key])
    del chain[-1][path[-1]]
    # prune tables left empty, deepest first; never a [[panels]] entry (an int key)
    for depth in range(len(path) - 1, 0, -1):
        if isinstance(path[depth - 1], int) or isinstance(path[depth], int):
            break
        if len(chain[depth]) == 0:
            del chain[depth - 1][path[depth - 1]]
        else:
            break


def _monitor_table(doc, monitor: str):
    if "monitors" not in doc:
        doc["monitors"] = tomlkit.table(is_super_table=True)
    if monitor not in doc["monitors"]:
        doc["monitors"][monitor] = tomlkit.table()
    return doc["monitors"][monitor]


def _add_panel(doc, monitor: str, widget: str) -> None:
    table = _monitor_table(doc, monitor)
    entry = tomlkit.table()
    entry["widget"] = widget
    if "panels" not in table:
        table["panels"] = tomlkit.aot()
    elif not isinstance(table["panels"], AoT):  # panels = [{ ... }]: tomlkit writes bad TOML
        raise DocumentError(
            f"monitors.{monitor}.panels is an inline array in your config; add the panel by hand"
        )
    table["panels"].append(entry)


def _remove_panel(doc, monitor: str, index: int) -> None:
    table = doc["monitors"][monitor]
    del table["panels"][index]
    if len(table["panels"]) == 0:
        del table["panels"]


def _move_panel(doc, monitor: str, index: int, to: int) -> None:
    panels = doc["monitors"][monitor]["panels"]
    entry = panels[index]
    del panels[index]
    panels.insert(to, entry)


# ---- plain-data side (what the edit must mean) -------------------------------------------


def _plain_set(data: dict, path: Path_, value: Any) -> None:
    node = data
    for key in path[:-1]:
        node = node[key] if isinstance(key, int) else node.setdefault(key, {})
    node[path[-1]] = value


def _plain_unset(data: dict, path: Path_) -> None:
    chain = [data]
    for key in path[:-1]:
        chain.append(chain[-1][key])
    del chain[-1][path[-1]]
    for depth in range(len(path) - 1, 0, -1):
        if isinstance(path[depth - 1], int) or isinstance(path[depth], int):
            break
        if not chain[depth]:
            del chain[depth - 1][path[depth - 1]]
        else:
            break


def _plain_panels(data: dict, monitor: str, create: bool = False) -> list:
    if create:
        return data.setdefault("monitors", {}).setdefault(monitor, {}).setdefault("panels", [])
    return data["monitors"][monitor]["panels"]


def _plain_remove_panel(data: dict, monitor: str, index: int) -> None:
    panels = _plain_panels(data, monitor)
    del panels[index]
    if not panels:
        del data["monitors"][monitor]["panels"]
