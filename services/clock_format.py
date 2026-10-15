"""The clock's format: a fixed token table, never user text in strftime (panel/widget spec 3.4).
Pure.

Tokens: HH (hour 00-23), H (0-23), h (1-12), a (AM/PM), mm (minute), ss (second), dd (day
01-31), ddd (weekday, abbreviated), MM (month 01-12), MMM (month, abbreviated), yyyy (year).
Text in single quotes is shown as written, letters included ('at', 'Uhr'); two single quotes
('') are one quote, inside or outside quoted text; a quote that is never closed is an error.
Every other letter is an error; any other character (digits, spaces, punctuation, `%`, other
scripts) is shown as it is. The longest token wins: "MMM" is the month name, "MMMM" is MMM
then an M on its own, which is an error. Literal text never goes through strftime, and the
day and month names are fixed English tables: the output never follows the locale.
The character rules are a panel name's (control characters, line separators, bidirectional
overrides, an invisible format character at either end are errors), and so is a format with
nothing visible (no token, only spaces and format characters) in it.
"""

from __future__ import annotations

import unicodedata
from datetime import datetime

from shell.config.models import check_text_characters

TOKENS = ("HH", "mm", "ss", "H", "h", "a", "ddd", "dd", "MMM", "MM", "yyyy")
_LONGEST_FIRST = sorted(TOKENS, key=len, reverse=True)
Part = tuple[bool, str]  # (is a token, the token or the literal text)
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")  # datetime.weekday() order
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _quoted(text: str, start: int) -> tuple[str, int]:
    """The text of the quote opened at `start` and the index after its closing quote."""
    out = []
    i = start + 1
    while i < len(text):
        if text.startswith("''", i):  # a quote inside quoted text
            out.append("'")
            i += 2
        elif text[i] == "'":
            return "".join(out), i + 1
        else:
            out.append(text[i])
            i += 1
    raise ValueError(
        f"unterminated quote at position {start + 1}; close it with ' (write '' for a quote)"
    )


def _visible(char: str) -> bool:
    return not char.isspace() and unicodedata.category(char) != "Cf"


def parse_clock_format(text: str) -> tuple[Part, ...]:
    """The format as tokens and literal text; ValueError naming the first unknown letter, a
    control character, an unterminated quote, or a format with nothing visible."""
    try:
        check_text_characters(text)  # the same character rules as a panel name
    except ValueError as exc:
        raise ValueError(f"the format {exc}") from None
    parts: list[Part] = []

    def literal(chars: str) -> None:
        if parts and not parts[-1][0]:
            parts[-1] = (False, parts[-1][1] + chars)
        elif chars:
            parts.append((False, chars))

    i = 0
    while i < len(text):
        if text.startswith("''", i):
            literal("'")
            i += 2
            continue
        if text[i] == "'":
            chars, i = _quoted(text, i)
            literal(chars)
            continue
        token = next((t for t in _LONGEST_FIRST if text.startswith(t, i)), None)
        if token is not None:
            parts.append((True, token))
            i += len(token)
            continue
        char = text[i]
        if char.isascii() and char.isalpha():
            raise ValueError(
                f"unknown token {char!r} at position {i + 1}; use {', '.join(TOKENS)}, or "
                "put text in single quotes"
            )
        literal(char)
        i += 1
    if not any(is_token or any(_visible(c) for c in value) for is_token, value in parts):
        raise ValueError("the format shows nothing visible; add a token or some text")
    return tuple(parts)


def _token(token: str, now: datetime) -> str:
    match token:
        case "HH":
            return f"{now.hour:02d}"
        case "H":
            return str(now.hour)
        case "h":
            return str(now.hour % 12 or 12)
        case "a":
            return "AM" if now.hour < 12 else "PM"
        case "mm":
            return f"{now.minute:02d}"
        case "ss":
            return f"{now.second:02d}"
        case "dd":
            return f"{now.day:02d}"
        case "ddd":
            return WEEKDAYS[now.weekday()]
        case "MM":
            return f"{now.month:02d}"
        case "MMM":
            return MONTHS[now.month - 1]
        case "yyyy":
            return f"{now.year:04d}"
    raise ValueError(f"unknown token {token!r}")


def format_clock(parts: tuple[Part, ...], now: datetime) -> str:
    return "".join(_token(value, now) if is_token else value for is_token, value in parts)
