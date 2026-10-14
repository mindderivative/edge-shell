"""Edit the user's config.toml in place with tomlkit, keeping comments and layout. Pure (no GTK).

Every edit is checked: the edited text is parsed back with tomllib and must equal the same edit
applied to the plain data (types included: true is not 1, 1 is not 1.0). tomlkit can misplace a
new table (a table added inside a dotted-key table is written as a top-level header, which moves
the keys to another table); such an edit raises DocumentError instead of producing a file that
means something else. Any failure inside tomlkit is a DocumentError too; the document is then
left unchanged.

Panel entries ([[monitors.X.panels]]) are moved, removed and added on the text itself, entry by
entry: an entry is its header, its body and its sub-tables, plus its label, the run of
whole-line comments directly above its header (no blank line in between). A moved entry takes
its label with it, a removed entry takes only its own label, and an added entry goes below the
last one (or below the monitor's last table), never between a comment and the header it labels.
Blank lines, and comment blocks separated from a header by a blank line (a file's head comment,
a section banner), belong to the place: they stay where they were. So does a comment directly
under an entry's last line: it stays there, and an entry added after it goes below it (with a
blank line in between), unless it is the next header's label. An added entry is spaced like
the last one (the blank lines above it), unless no blank line follows the last entry.

A new key (or table) set into a table goes right below the table's last line that is neither
blank nor a comment: above the blank lines, banners and the label of the next header (or a
closing comment), never between a label and its header.

A table emptied by an edit (the last panel of a monitor removed, the only key of a table reset)
is removed: its header line goes together with the header's own label (except a label that
starts the file: it may as well be the file's head comment, so it stays); the next table's
label stays.

Known and accepted (decision 2): a CRLF file may get "\n" endings on the lines tomlkit writes;
a comment inside a multi-line array goes when the array is replaced; a set or reset sometimes
drops a blank line; unsetting a whole table leaves its own label behind (the census refuses it
when the next table is labelled; the settings window only resets single keys).

A path is a tuple of keys from the top of the file; an int indexes the panel list, e.g.
("monitors", "HDMI-A-1", "panels", 0, "handle", "shape").
"""

from __future__ import annotations

import copy
import difflib
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
# an edit of a readable file whose result tomlkit cannot write or read back
UNWRITABLE = "this edit cannot be written in place; edit the file by hand"


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
            _in_doc(lambda doc: _set(doc, path, value)),
            lambda data: _plain_set(data, path, value),
            path,
        )

    def unset(self, path: Path_) -> None:
        """Remove the key (the value is inherited again) and any table left empty by it (an
        emptied table's header goes with its own label)."""
        may_lose: Counter[str] = Counter()
        self._edit(
            lambda text: _unset_text(text, self._data, path, may_lose),
            lambda data: _plain_unset(data, path),
            path,
            may_lose,
        )

    def add_panel(self, monitor: str, entry: dict[str, Any]) -> int:
        """Append a panel entry with the keys of `entry`, in that order, one per line (the
        settings window gives panel, name and widget; every other key comes from the widget's
        defaults); returns its index."""
        entry = dict(entry)
        self._edit(
            lambda text: _add_panel_text(text, self._data, monitor, entry),
            lambda data: _plain_panels(data, monitor, create=True).append(dict(entry)),
            (*_panel_path(monitor), 0),
        )
        return len(self._data["monitors"][monitor]["panels"]) - 1

    def remove_panel(self, monitor: str, index: int) -> None:
        """Remove the entry with its own label; a monitor left empty goes too."""
        may_lose: Counter[str] = Counter()
        self._edit(
            lambda text: _remove_panel_text(text, self._data, monitor, index, may_lose),
            lambda data: _plain_remove_panel(data, monitor, index),
            (*_panel_path(monitor), index),
            may_lose,
        )

    def move_panel(self, monitor: str, index: int, to: int) -> None:
        """Move the entry at `index` so it ends up at `to`, an index into the list as it is
        (0 to the number of panels - 1; anything else is refused)."""

        def plain(data):
            panels = _plain_panels(data, monitor)
            if not 0 <= to < len(panels):
                raise DocumentError(
                    f"cannot move the panel to position {to}: monitors.{monitor} has "
                    f"{len(panels)} panels (positions 0 to {len(panels) - 1})"
                )
            panels.insert(to, panels.pop(index))

        self._edit(
            lambda text: _move_panel_text(text, self._data, monitor, index, to),
            plain,
            (*_panel_path(monitor), index),
        )

    def _edit(
        self,
        on_text: Callable[[str], str],
        on_data: Callable[[dict], None],
        path: Path_,
        may_lose: Counter[str] | None = None,
    ) -> None:
        """Apply on_text to the text and on_data to the plain data; keep the result only when
        both agree and no comment above a table is lost (except those in `may_lose`, filled
        by on_text: a removed entry's or emptied table's own comments). `path` is what the
        edit goes through, to name a value standing where a table should be."""
        expected = copy.deepcopy(self._data)
        try:
            on_data(expected)
        except (TypeError, AttributeError) as exc:
            raise DocumentError(_not_a_table(self._data, path) or _no_such(exc)) from None
        except (KeyError, IndexError) as exc:
            raise DocumentError(_no_such(exc)) from None
        old = self._text
        newline = "\r\n" if "\r\n" in old else "\n"
        unterminated = bool(old) and not old.endswith("\n")  # tomlkit needs the newline
        try:
            new = on_text(old + newline if unterminated else old)
            got = tomllib.loads(new)
        except DocumentError:
            raise
        except (TypeError, AttributeError):
            raise DocumentError(_not_a_table(self._data, path) or UNWRITABLE) from None
        except (*_TOMLKIT_FAILURES, tomllib.TOMLDecodeError):
            raise DocumentError(UNWRITABLE) from None
        if unterminated:  # it stays so (tomlkit may end its own lines with "\n" in a CRLF file)
            new = new.rstrip("\r\n")
        if not _same(got, expected):
            raise DocumentError(
                "cannot edit the config in place without changing other keys; edit the file by hand"
            )
        try:  # the next edit starts from this text
            readable = tomlkit.dumps(tomlkit.parse(new)) == new
        except _TOMLKIT_FAILURES:
            readable = False
        if not readable:
            raise DocumentError(UNWRITABLE)
        lost = (_header_comments(old) - (may_lose or Counter())) - _comments(new)
        if lost:
            raise DocumentError(
                f"cannot edit the config in place without losing the comment {min(lost)!r} "
                "above a table; edit the file by hand"
            )
        self._text, self._data = new, got


def _no_such(exc: Exception) -> str:
    return f"cannot edit the config: no such key or entry ({exc})"


def _not_a_table(data: dict, path: Path_) -> str | None:
    """The message for the first part of `path` that is a value where the edit needs a table
    (or a list of panel entries), or None."""
    node: Any = data
    for i, key in enumerate(path):
        name = ".".join(str(k) for k in path[:i])
        if not isinstance(node, (dict, list)):
            return f"{name} is a value, not a table: edit the file by hand"
        if isinstance(key, int) != isinstance(node, list):
            kind = "a list of panel entries" if isinstance(key, int) else "a table"
            return f"{name} is not {kind}: edit the file by hand"
        if isinstance(node, list) and not -len(node) <= key < len(node):  # type: ignore[operator]
            return None
        if isinstance(node, dict) and key not in node:
            return None
        node = node[key]  # type: ignore[index]
    return None


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
# may go with the key or entry they sat in, and a removed panel entry (or the header of a table
# emptied by the edit) takes its own label. A key added at the end of a table is moved above
# those comments (_below_last_line). The census counts comment texts, so it cannot tell two
# identical comments apart (one surviving copy hides the loss of the other).


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


def _comment(line: str) -> bool:
    return line.lstrip().startswith("#")


def _label_start(lines: list[str], header: int) -> int:
    """First line of the label of line `header`: the comment lines directly above it (a blank
    line ends the label; what is above it belongs to the place)."""
    i = header
    while i > 0 and _comment(lines[i - 1]):
        i -= 1
    return i


def _cut(lines: list[str], start: int, end: int) -> None:
    """Delete lines[start:end]; the blank lines around it belong to the places and stay, but no
    doubled blank line is left there, nor a blank line at the top or the end of the file."""
    del lines[start:end]
    _close_gap(lines, start)


def _close_gap(lines: list[str], at: int) -> None:
    """After lines were removed at `at`: see _cut."""
    if at == 0:
        while lines and not lines[0].strip():
            del lines[0]
    elif at < len(lines):  # the longer of the two blank runs that meet there is kept
        up = down = 0
        while up < at and not lines[at - 1 - up].strip():
            up += 1
        while at + down < len(lines) and not lines[at + down].strip():
            down += 1
        del lines[at : at + min(up, down)]
    elif not lines[at - 1].strip():
        del lines[at - 1]


class _Spans:
    """The panel entries of one monitor in the text: entry k is lines[start[k]:end[k]], its
    label, header, body and sub-tables up to its last non-comment line; the lines between
    entries (blank lines, comments not directly above a header, other tables) are the places."""

    def __init__(self, lines: list[str], panels: tuple[str, ...], count: int):
        heads = [(i, h) for i, line in enumerate(lines) if (h := _header(line))]
        self.head: list[int] = []
        self.start: list[int] = []
        self.end: list[int] = []

        def inside(path):  # a sub-table of an entry: [monitors.X.panels.handle]
            return len(path) > len(panels) and path[: len(panels)] == panels

        for n, (i, (path, aot)) in enumerate(heads):
            if path != panels or not aot:
                continue
            stop = next((j for j, (p, _) in heads[n + 1 :] if not inside(p)), len(lines))
            while stop > i + 1 and _blank_or_comment(lines[stop - 1]):
                stop -= 1
            self.head.append(i)
            self.start.append(_label_start(lines, i))
            self.end.append(stop)
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
        out += lines[s.start[entry] : s.end[entry]]  # the entry with its label
        out += lines[s.end[slot] : s.start[slot + 1]] if slot + 1 < count else lines[s.end[slot] :]
    return "".join(out)


def _table_headers(lines: list[str]) -> set[tuple[str, ...]]:
    return {h[0] for line in lines if (h := _header(line)) and not h[1]}


def _remove_panel_text(
    text: str, data: dict, monitor: str, index: int, may_lose: Counter[str]
) -> str:
    count = _panel_count(data, monitor)
    lines = _lines(text)
    if _is_inline(text, monitor):
        # tomlkit prunes only tables without a header; the text drops an emptied header
        headed = _table_headers(lines)
        lines = _lines(_in_doc(lambda doc: _remove_panel(doc, monitor, index, headed))(text))
    else:
        s = _Spans(lines, _panel_path(monitor), count)
        k = range(count)[index]
        may_lose.update(_comments("".join(lines[s.start[k] : s.end[k]])))
        _cut(lines, s.start[k], s.end[k])
    if count == 1:  # the monitor may be left empty: its own table header goes too
        rest = copy.deepcopy(data)
        _plain_remove_panel(rest, monitor, index)
        if monitor not in rest.get("monitors", {}):
            lines = _drop_empty_header(lines, ("monitors", monitor), may_lose)
        if "monitors" not in rest:
            lines = _drop_empty_header(lines, ("monitors",), may_lose)
    return "".join(lines)


def _drop_empty_header(
    lines: list[str],
    path: tuple[str, ...],
    may_lose: Counter[str],
    within: tuple[int, int] | None = None,
):
    """Remove the [path] header line (the first one in lines[within], e.g. a panel entry) and
    its own label when its table has no lines left (the comments in its body stay: tomlkit
    keeps the next header's label there). A label at the very top of the file stays too: it
    may as well be the file's head comment."""
    lo, hi = within or (0, len(lines))
    for i in range(lo, hi):
        if _header(lines[i]) != (path, False):
            continue
        j = i + 1
        while j < len(lines) and not _header(lines[j]):
            if not _blank_or_comment(lines[j]):
                return lines
            j += 1
        start = _label_start(lines, i) or i
        may_lose.update(_comments("".join(lines[start:i])))
        out = lines[:]
        _cut(out, start, i + 1)
        return out
    return lines


def _unset_text(text: str, data: dict, path: Path_, may_lose: Counter[str]) -> str:
    """Unset with tomlkit; a table emptied by it that has a [header] in the text is not pruned
    by tomlkit (that would take the next table's label, kept in its body, with it) but
    dropped from the text with its own label."""
    rest = copy.deepcopy(data)
    _plain_unset(rest, path)
    pruned = []  # the tables _plain_unset prunes, deepest first (never a panel entry)
    for depth in range(len(path) - 1, 0, -1):
        if isinstance(path[depth - 1], int) or isinstance(path[depth], int):
            break
        if _has(rest, path[:depth]):
            break
        pruned.append(path[:depth])
    headers = _table_headers(_lines(text))
    headed = [table for table in pruned if _header_key(table) in headers]
    keep = len(headed[0]) if headed else 0
    new = _in_doc(lambda doc: _unset(doc, path, keep))(text)
    lines = _lines(new)
    for table in headed:
        key = _header_key(table)
        within = None
        if len(table) > 3 and isinstance(table[3], int):  # a sub-table of a panel entry
            monitor, count = str(table[1]), _panel_count(data, str(table[1]))
            k = range(count)[table[3]]
            s = _Spans(lines, _panel_path(monitor), count)
            within = (s.head[k], s.head[k + 1] if k + 1 < count else len(lines))
        lines = _drop_empty_header(lines, key, may_lose, within)  # type: ignore[arg-type]
    return "".join(lines)


def _header_key(table: Path_) -> tuple | None:
    """The key a [header] line of this table spells: a panel entry's sub-table is written
    [monitors.X.panels.handle] (no index); None for any other path with an index."""
    if not any(isinstance(k, int) for k in table):
        return tuple(table)
    if table[:1] == ("monitors",) and table[2:3] == ("panels",) and isinstance(table[3], int):
        rest = table[4:]
        if not any(isinstance(k, int) for k in rest):
            return (*table[:3], *rest)
    return None


def _has(data: dict, path: Path_) -> bool:
    node: Any = data
    for key in path:
        if isinstance(key, int):
            if not isinstance(node, list) or not -len(node) <= key < len(node):
                return False
        elif not isinstance(node, dict) or key not in node:
            return False
        node = node[key]
    return True


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


def _bracket(line: str) -> str:
    """The [[...]] of a header line exactly as written (spaces and quotes kept, the comment
    after it left out)."""
    s = line.strip()
    quote, i = "", 0
    while i < len(s):
        c = s[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 1
            elif c == quote:
                quote = ""
        elif c in "\"'":
            quote = c
        elif s.startswith("]]", i):
            return s[: i + 2]
        i += 1
    return s


def _new_entry(text: str, header: str, entry: dict[str, Any], blank: bool) -> list[str]:
    newline = "\r\n" if "\r\n" in text else "\n"
    body = [
        f"{tomlkit.key(key).as_string()} = {tomlkit.item(value).as_string()}{newline}"
        for key, value in entry.items()
    ]
    return ([newline] if blank else []) + [header + newline, *body]


def _add_panel_text(text: str, data: dict, monitor: str, entry: dict[str, Any]) -> str:
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
        # the place after the last entry stays as it is, directly under it: a comment run there
        # stays under the last entry (unless it is the next header's label)
        at = below = s.end[-1]
        while below < len(lines) and _comment(lines[below]):
            below += 1
        if below == len(lines) or not lines[below].strip():
            at = below
        # the blank lines above the last entry, none of the comments (the place's, not its),
        # when that place is spaced too (a file without blank lines between tables gets none)
        above = s.start[-1]
        while above > 0 and not lines[above - 1].strip():
            above -= 1
        gap = lines[above : s.start[-1]] if at == len(lines) or not lines[at].strip() else []
        # never directly below a comment (it would read as the new entry's label)
        blank = at > s.end[-1] and not gap
        new = _new_entry(text, _bracket(lines[s.head[-1]]), entry, blank)
        return "".join(lines[:at] + gap + new + lines[at:])
    tail = len(lines)
    while tail > 0 and _blank_or_comment(lines[tail - 1]):
        tail -= 1
    heads = [(i, h[0]) for i, line in enumerate(lines) if (h := _header(line))]
    own = [n for n, (_, path) in enumerate(heads) if path[:2] == ("monitors", monitor)]
    if own:  # below the monitor's last table
        nxt = own[-1] + 1
        at = heads[nxt][0] if nxt < len(heads) else tail
        while at > 0 and _blank_or_comment(lines[at - 1]):
            at -= 1  # above the next header's label and the place's lines
        key = ".".join(_key_parts(lines[heads[own[-1]][0]])[:2] + ["panels"])
        header = "[[" + key + "]]"
    elif monitor not in monitors:  # a new monitor: at the end, above a closing comment
        at = tail or len(lines)  # a file of only comments: below them
        header = "[[" + tomlkit.key(list(_panel_path(monitor))).as_string() + "]]"
    else:  # a monitor known only from dotted keys or an inline table
        return _in_doc(lambda doc: _add_panel(doc, monitor, entry))(text)
    blank = at > 0 and bool(lines[at - 1].strip())
    return "".join(lines[:at] + _new_entry(text, header, entry, blank) + lines[at:])


# ---- tomlkit side ------------------------------------------------------------------------


def _in_doc(edit: Callable[[Any], None]) -> Callable[[str], str]:
    def run(text: str) -> str:
        doc = tomlkit.parse(text)
        edit(doc)
        return _below_last_line(text, tomlkit.dumps(doc))

    return run


def _below_last_line(old: str, new: str) -> str:
    """tomlkit adds a new key (or table) at the END of a table's body, below the blank lines
    and comments there, so below the label of the next header (or a closing comment): move
    the added lines up, right below the table's last line that is neither blank nor a comment
    (a value replaced by a table is removed from its line and added there too). Only lines
    added just above a header or the end of the file are moved, and only past unchanged blank
    lines and comments, so the data is the same."""
    o, n = _lines(old), _lines(new)
    out: list[str] = []
    for tag, i1, _i2, j1, j2 in difflib.SequenceMatcher(None, o, n, autojunk=False).get_opcodes():
        if tag == "insert" and (i1 == len(o) or _header(o[i1])):
            top = i1
            while top > 0 and _blank_or_comment(o[top - 1]):
                top -= 1
            if top == 0:  # only comments above: a header's own label stays directly above it
                # (a [monitors] header tomlkit adds above its first monitor); a file of only
                # comments keeps them above what is added at its end
                top = i1 if i1 == len(o) else _label_start(o, i1)
            below = len(out) - (i1 - top)  # where o[top:i1] went in out
            if i1 > top and out[below:] == o[top:i1]:
                out[below:below] = n[j1:j2]
                continue
        out += n[j1:j2]
    return "".join(out)


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


def _unset(doc, path: Path_, keep: int = 0) -> None:
    """Delete the key and prune the tables left empty, deepest first, but never a [[panels]]
    entry (an int key) nor a table path[:depth] with depth <= keep (the text drops those)."""
    chain = [doc]
    for key in path[:-1]:
        chain.append(chain[-1][key])
    # a table split across the file is a proxy over its parts: deleting through it drops an
    # emptied part with its header and the comments in its body (the next table's label), so
    # delete from the one part that holds the key (a key in several parts, e.g. a panel list,
    # goes through the proxy)
    holders = [part for part in getattr(chain[-1], "_tables", ()) if path[-1] in part]
    del (holders[0] if len(holders) == 1 else chain[-1])[path[-1]]
    for depth in range(len(path) - 1, keep, -1):
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


def _add_panel(doc, monitor: str, keys: dict[str, Any]) -> None:
    """Only for a monitor without any header of its own (the text side handles the rest)."""
    table = _monitor_table(doc, monitor)
    entry = tomlkit.table()
    for key, value in keys.items():
        entry[key] = value
    if "panels" not in table:
        table["panels"] = tomlkit.aot()
    elif not isinstance(table["panels"], AoT):
        raise DocumentError(
            f"monitors.{monitor}.panels is an inline array in your config; add the panel by hand"
        )
    table["panels"].append(entry)


def _remove_panel(doc, monitor: str, index: int, headed: set[tuple[str, ...]]) -> None:
    """An inline panel array; an emptied table is pruned only when it has no [header] in the
    text (`headed`): the text drops such a header with its own label."""
    table = doc["monitors"][monitor]
    del table["panels"][index]
    if len(table["panels"]) == 0:
        del table["panels"]
        if len(table) == 0 and ("monitors", monitor) not in headed:
            del doc["monitors"][monitor]
            if len(doc["monitors"]) == 0 and ("monitors",) not in headed:
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
