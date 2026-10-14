"""Edit the user's config.toml in place with tomlkit, keeping comments and layout. Pure (no GTK).

Every edit is checked: the edited text is parsed back with tomllib and must equal the same edit
applied to the plain data (types included: true is not 1, 1 is not 1.0). tomlkit can misplace a
new table (a table added inside a dotted-key table is written as a top-level header, which moves
the keys to another table); such an edit raises DocumentError instead of producing a file that
means something else. Any failure inside tomlkit is a DocumentError too; the document is then
left unchanged.

Panel entries ([[monitors.X.panels]]) are moved, removed and added on the text itself, entry by
entry: an entry is its header, its body and its sub-tables, plus its label, the whole-line
comments directly above its header. A moved entry takes its label with it, a removed entry takes
only its own label, and an added entry goes below the last one (or below the monitor's last
table), never between a comment and the header it labels. Blank lines stay where they were.

Known and accepted (decision 2): a key added at the end of a table lands between a comment and
the next header; a CRLF file may get "\n" endings on the lines tomlkit writes; a comment inside
a multi-line array goes when the array is replaced; a set or reset sometimes drops a blank line.

A path is a tuple of keys from the top of the file; an int indexes the panel list, e.g.
("monitors", "HDMI-A-1", "panels", 0, "handle", "shape").
"""

from __future__ import annotations

import copy
import math
import re
import tomllib
from collections import Counter
from collections.abc import Callable
from typing import Any

import tomlkit
from tomlkit.exceptions import TOMLKitError
from tomlkit.items import AoT, InlineTable

from shell.config.models import ConfigError

Path_ = tuple[str | int, ...]

# what tomlkit raises when it cannot make an edit (seen in fuzzing: its own errors, and
# AttributeError / ValueError / KeyError from tables split across the file or inline tables)
_TOMLKIT_FAILURES = (TOMLKitError, KeyError, IndexError, TypeError, AttributeError, ValueError)

UNREADABLE = (
    "this file's layout cannot be edited in place by the settings window (valid TOML, but "
    "tomlkit cannot read it); edit it by hand"
)


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
        if text.startswith("﻿"):
            raise DocumentError("the file starts with a byte order mark (BOM); remove it")
        try:
            self._data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"TOML syntax error: {exc}") from None
        try:
            readable = tomlkit.dumps(tomlkit.parse(text)) == text
        except _TOMLKIT_FAILURES:
            readable = False
        if not readable:
            raise DocumentError(UNREADABLE)
        self._text = text

    @property
    def text(self) -> str:
        return self._text

    @property
    def data(self) -> dict[str, Any]:
        """Plain dicts and lists (a copy)."""
        return copy.deepcopy(self._data)

    # ---- edits ---------------------------------------------------------------------------
    def set(self, path: Path_, value: Any) -> None:
        self._edit(
            _in_doc(lambda doc: _set(doc, path, value)), lambda data: _plain_set(data, path, value)
        )

    def unset(self, path: Path_) -> None:
        """Remove the key (the value is inherited again) and any table left empty by it."""
        self._edit(_in_doc(lambda doc: _unset(doc, path)), lambda data: _plain_unset(data, path))

    def add_panel(self, monitor: str, widget: str) -> int:
        """Append a panel entry with only its widget (every other key from the widget's
        defaults); returns its index."""
        self._edit(
            lambda text: _add_panel_text(text, self._data, monitor, widget),
            lambda data: _plain_panels(data, monitor, create=True).append({"widget": widget}),
        )
        return len(self._data["monitors"][monitor]["panels"]) - 1

    def remove_panel(self, monitor: str, index: int) -> None:
        """Remove the entry with its own label; a monitor left empty goes too."""
        may_lose: Counter[str] = Counter()
        self._edit(
            lambda text: _remove_panel_text(text, self._data, monitor, index, may_lose),
            lambda data: _plain_remove_panel(data, monitor, index),
            may_lose,
        )

    def move_panel(self, monitor: str, index: int, to: int) -> None:
        """Move the entry at `index` so it ends up at `to` (config order decides ties)."""

        def plain(data):
            panels = _plain_panels(data, monitor)
            panels.insert(to, panels.pop(index))

        self._edit(lambda text: _move_panel_text(text, self._data, monitor, index, to), plain)

    def _edit(
        self,
        on_text: Callable[[str], str],
        on_data: Callable[[dict], None],
        may_lose: Counter[str] | None = None,
    ) -> None:
        """Apply on_text to the text and on_data to the plain data; keep the result only when
        both agree and no comment above a table is lost (except those in `may_lose`, filled
        by on_text: a removed entry's own comments)."""
        expected = copy.deepcopy(self._data)
        try:
            on_data(expected)
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise DocumentError(f"cannot edit the config: no such key or entry ({exc})") from None
        old = self._text
        newline = "\r\n" if "\r\n" in old else "\n"
        unterminated = bool(old) and not old.endswith("\n")  # tomlkit needs the newline
        try:
            new = on_text(old + newline if unterminated else old)
            if unterminated and new.endswith(newline):
                new = new[: -len(newline)]
            got = tomllib.loads(new)
        except DocumentError:
            raise
        except (*_TOMLKIT_FAILURES, tomllib.TOMLDecodeError) as exc:
            raise DocumentError(f"cannot edit the config in place: {exc}") from None
        if not _same(got, expected):
            raise DocumentError(
                "cannot edit the config in place without changing other keys; edit the file by hand"
            )
        try:  # the next edit starts from this text
            readable = tomlkit.dumps(tomlkit.parse(new)) == new
        except _TOMLKIT_FAILURES:
            readable = False
        if not readable:
            raise DocumentError(UNREADABLE)
        lost = (_header_comments(old) - (may_lose or Counter())) - _comments(new)
        if lost:
            raise DocumentError(
                f"cannot edit the config in place without losing the comment {min(lost)!r} "
                "above a table; edit the file by hand"
            )
        self._text, self._data = new, got


def _same(a: Any, b: Any) -> bool:
    """Equal values of the same types (== says True == 1 and 1 == 1.0)."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, float) and math.isnan(a):
        return math.isnan(b)
    return a == b


# ---- comment census ----------------------------------------------------------------------
# tomlkit keeps the comment lines above a table header inside the table BEFORE it, so removing
# or pruning that table would silently drop them. Whole-line comments above a header (blank
# lines allowed in between) and at the end of the file must survive an edit; other comments
# may go with the key or entry they sat in, and a removed panel entry takes its own label. A
# comment can still MOVE (a key added at the end of the table before it lands below the
# comment): see decision 2. The census counts comment texts, so it cannot tell two identical
# comments apart (one surviving copy hides the loss of the other).


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
    found.update(block)  # the end of the file counts like a header
    return found


# ---- panel entries on the text -----------------------------------------------------------
# A header line is found by parsing the line alone with tomllib (so quoting and spacing do not
# matter); a line inside a multi-line string or array that looks like a header can fool it, but
# then the re-parsed result differs and the edit is refused.

_LINE = re.compile(r"[^\n]*\n|[^\n]+")


def _lines(text: str) -> list[str]:
    return _LINE.findall(text)


def _header(line: str) -> tuple[tuple[str, ...], bool] | None:
    """(key path, is an [[array]] entry) for a table header line, else None."""
    s = line.strip()
    if not s.startswith("["):
        return None
    try:
        node: Any = tomllib.loads(s)
    except tomllib.TOMLDecodeError:
        return None
    path: list[str] = []
    while isinstance(node, dict) and len(node) == 1:
        ((key, node),) = node.items()
        path.append(key)
        if node == {}:
            return tuple(path), False
        if node == [{}]:
            return tuple(path), True
    return None


def _blank_or_comment(line: str) -> bool:
    s = line.strip()
    return not s or s.startswith("#")


def _label_start(lines: list[str], header: int) -> int:
    """First line of the comment and blank lines directly above line `header`."""
    i = header
    while i > 0 and _blank_or_comment(lines[i - 1]):
        i -= 1
    return i


def _first_content(lines: list[str], start: int, stop: int) -> int:
    """First non-blank line in lines[start:stop] (stop if none): the blank lines above a
    label stay in place, only the label moves."""
    while start < stop and not lines[start].strip():
        start += 1
    return start


class _Spans:
    """The panel entries of one monitor in the text: entry k is lines[start[k]:end[k]], its
    blank lines lines[start[k]:body[k]] belong to its place, the rest moves with it."""

    def __init__(self, lines: list[str], panels: tuple[str, ...], count: int):
        heads = [(i, h) for i, line in enumerate(lines) if (h := _header(line))]
        tail = len(lines)
        while tail > 0 and _blank_or_comment(lines[tail - 1]):
            tail -= 1
        self.head: list[int] = []
        self.start: list[int] = []
        self.body: list[int] = []
        self.end: list[int] = []

        def inside(path):  # a sub-table of an entry: [monitors.X.panels.handle]
            return len(path) > len(panels) and path[: len(panels)] == panels

        for n, (i, (path, aot)) in enumerate(heads):
            if path != panels or not aot:
                continue
            nxt = next((j for j, (p, _) in heads[n + 1 :] if not inside(p)), None)
            start = _label_start(lines, i)
            self.head.append(i)
            self.start.append(start)
            self.body.append(_first_content(lines, start, i))
            self.end.append(max(i + 1, tail) if nxt is None else _label_start(lines, nxt))
        if len(self.start) != count:
            raise DocumentError(
                f"cannot find the {count} [[{'.'.join(panels)}]] entries in the file; "
                "edit the file by hand"
            )


def _panel_path(monitor: str) -> tuple[str, ...]:
    return ("monitors", monitor, "panels")


def _panel_count(data: dict, monitor: str) -> int:
    panels = data["monitors"][monitor]["panels"]
    return len(panels)


def _is_inline(text: str, monitor: str) -> bool:
    """The panel list exists in the data but has no [[...]] headers: an inline array."""
    path = _panel_path(monitor)
    return not any(_header(line) == (path, True) for line in _lines(text))


def _move_panel_text(text: str, data: dict, monitor: str, index: int, to: int) -> str:
    count = _panel_count(data, monitor)
    if _is_inline(text, monitor):
        return _in_doc(lambda doc: _move_panel(doc, monitor, index, to))(text)
    lines = _lines(text)
    s = _Spans(lines, _panel_path(monitor), count)
    order = list(range(count))
    order.insert(to, order.pop(index))
    out = lines[: s.start[0]]
    for slot, entry in enumerate(order):
        out += lines[s.start[slot] : s.body[slot]]  # the place's blank lines
        out += lines[s.body[entry] : s.end[entry]]  # the entry with its label
        out += lines[s.end[slot] : s.start[slot + 1]] if slot + 1 < count else lines[s.end[slot] :]
    return "".join(out)


def _remove_panel_text(
    text: str, data: dict, monitor: str, index: int, may_lose: Counter[str]
) -> str:
    count = _panel_count(data, monitor)
    if _is_inline(text, monitor):
        return _in_doc(lambda doc: _remove_panel(doc, monitor, index))(text)
    lines = _lines(text)
    s = _Spans(lines, _panel_path(monitor), count)
    k = range(count)[index]
    may_lose.update(_comments("".join(lines[s.start[k] : s.end[k]])))
    lines[s.start[k] : s.end[k]] = []
    if count == 1:  # the monitor may be left empty: its own table header goes too
        rest = copy.deepcopy(data)
        _plain_remove_panel(rest, monitor, index)
        if monitor not in rest.get("monitors", {}):
            lines = _drop_empty_header(lines, ("monitors", monitor), may_lose)
        if "monitors" not in rest:
            lines = _drop_empty_header(lines, ("monitors",), may_lose)
    return "".join(lines)


def _drop_empty_header(lines: list[str], path: tuple[str, ...], may_lose: Counter[str]):
    """Remove the [path] header line and its own label when its table has no lines left (the
    comments in its body label the next header and stay)."""
    for i, line in enumerate(lines):
        if _header(line) != (path, False):
            continue
        j = i + 1
        while j < len(lines) and not _header(lines[j]):
            if not _blank_or_comment(lines[j]):
                return lines
            j += 1
        start = _label_start(lines, i)
        first = _first_content(lines, start, i)
        may_lose.update(_comments("".join(lines[first:i])))
        out = lines[:first] + lines[i + 1 :]
        if 0 < first < len(out) and not out[first - 1].strip() and not out[first].strip():
            del out[first]  # no double blank line where the header was
        return out
    return lines


def _key_parts(line: str) -> list[str]:
    """The parts of a header line's key as written (quotes kept), e.g. ['monitors', '"DP-2"']:
    tomlkit only reads a file back unchanged when every header of a table spells it alike."""
    s = line.strip().lstrip("[")
    parts, part, quote, i = [], "", "", 0
    while i < len(s):
        c = s[i]
        if quote:
            part += c
            if c == "\\" and quote == '"':
                part += s[i + 1 : i + 2]
                i += 1
            elif c == quote:
                quote = ""
        elif c in "\"'":
            part, quote = part + c, c
        elif c in ".]":
            parts.append(part.strip())
            part = ""
            if c == "]":
                break
        else:
            part += c
        i += 1
    return parts


def _new_entry(text: str, key: str, widget: str, blank: bool) -> list[str]:
    newline = "\r\n" if "\r\n" in text else "\n"
    body = "widget = " + tomlkit.item(widget).as_string()
    return ([newline] if blank else []) + ["[[" + key + "]]" + newline, body + newline]


def _add_panel_text(text: str, data: dict, monitor: str, widget: str) -> str:
    lines = _lines(text)
    monitors = data.get("monitors", {})
    if monitor in monitors and "panels" in monitors[monitor]:
        count = _panel_count(data, monitor)
        if _is_inline(text, monitor):
            raise DocumentError(
                f"monitors.{monitor}.panels is an inline array in your config; "
                "add the panel by hand"
            )
        s = _Spans(lines, _panel_path(monitor), count)
        at = s.end[-1]
        key = ".".join(_key_parts(lines[s.head[-1]]))
        entry = _new_entry(text, key, widget, False)
        return "".join(lines[:at] + lines[s.start[-1] : s.body[-1]] + entry + lines[at:])
    tail = len(lines)
    while tail > 0 and _blank_or_comment(lines[tail - 1]):
        tail -= 1
    heads = [(i, h[0]) for i, line in enumerate(lines) if (h := _header(line))]
    own = [n for n, (_, path) in enumerate(heads) if path[:2] == ("monitors", monitor)]
    if own:  # below the monitor's last table
        nxt = own[-1] + 1
        at = _label_start(lines, heads[nxt][0]) if nxt < len(heads) else tail
        key = ".".join(_key_parts(lines[heads[own[-1]][0]])[:2] + ["panels"])
    elif monitor not in monitors:  # a new monitor: at the end, above a closing comment
        at = tail
        key = tomlkit.key(list(_panel_path(monitor))).as_string()
    else:  # a monitor known only from dotted keys or an inline table
        return _in_doc(lambda doc: _add_panel(doc, monitor, widget))(text)
    blank = at > 0 and bool(lines[at - 1].strip())
    return "".join(lines[:at] + _new_entry(text, key, widget, blank) + lines[at:])


# ---- tomlkit side ------------------------------------------------------------------------


def _in_doc(edit: Callable[[Any], None]) -> Callable[[str], str]:
    def run(text: str) -> str:
        doc = tomlkit.parse(text)
        edit(doc)
        return tomlkit.dumps(doc)

    return run


def _set(doc, path: Path_, value: Any) -> None:
    node = doc
    for i, key in enumerate(path[:-1]):
        if isinstance(key, int):
            node = node[key]
            continue
        if key not in node:
            if isinstance(node, InlineTable):  # tomlkit writes `shadow. = elevation = 80`
                name = ".".join(str(k) for k in path[:i])
                raise DocumentError(
                    f"cannot add nested keys under the inline table {name!r} in place; "
                    "edit the file by hand"
                )
            if _container_kind(path, i) == "dotted":
                # item assignment, not .add(): a table split across the file is a proxy
                node[tomlkit.key([str(k) for k in path[i:]])] = value
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
    """Only for a monitor without any header of its own (the text side handles the rest)."""
    table = _monitor_table(doc, monitor)
    entry = tomlkit.table()
    entry["widget"] = widget
    if "panels" not in table:
        table["panels"] = tomlkit.aot()
    elif not isinstance(table["panels"], AoT):
        raise DocumentError(
            f"monitors.{monitor}.panels is an inline array in your config; add the panel by hand"
        )
    table["panels"].append(entry)


def _remove_panel(doc, monitor: str, index: int) -> None:
    """An inline panel array."""
    table = doc["monitors"][monitor]
    del table["panels"][index]
    if len(table["panels"]) == 0:
        del table["panels"]
        if len(table) == 0:
            del doc["monitors"][monitor]
            if len(doc["monitors"]) == 0:
                del doc["monitors"]


def _move_panel(doc, monitor: str, index: int, to: int) -> None:
    """An inline panel array."""
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
    """Remove the entry; a panel list, monitor and monitors table left empty go too."""
    panels = _plain_panels(data, monitor)
    del panels[index]
    if not panels:
        del data["monitors"][monitor]["panels"]
        if not data["monitors"][monitor]:
            del data["monitors"][monitor]
            if not data["monitors"]:
                del data["monitors"]
