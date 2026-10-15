"""The clock's format tokens (panel/widget spec 3.4): a fixed table, never strftime on user
text."""

from datetime import datetime

import pytest

from services.clock_format import TOKENS, format_clock, parse_clock_format

NOW = datetime(2026, 10, 14, 9, 5, 7)  # a Wednesday
EVENING = datetime(2026, 1, 2, 21, 30, 0)  # a Friday


def fmt(text, now=NOW):
    return format_clock(parse_clock_format(text), now)


def test_the_token_table_is_fixed():
    assert set(TOKENS) == {"HH", "mm", "ss", "H", "h", "a", "ddd", "dd", "MMM", "MM", "yyyy"}


@pytest.mark.parametrize(
    ("text", "morning", "evening"),
    [
        ("HH:mm", "09:05", "21:30"),
        ("HH:mm:ss", "09:05:07", "21:30:00"),
        ("H:mm", "9:05", "21:30"),
        ("h:mm a", "9:05 AM", "9:30 PM"),
        ("ddd dd MMM", "Wed 14 Oct", "Fri 02 Jan"),
        ("dd.MM.yyyy", "14.10.2026", "02.01.2026"),
        ("yyyy-MM-dd HH:mm", "2026-10-14 09:05", "2026-01-02 21:30"),
    ],
)
def test_tokens_are_replaced_and_the_rest_is_kept(text, morning, evening):
    assert (fmt(text), fmt(text, EVENING)) == (morning, evening)


def test_midnight_and_noon_on_the_12_hour_clock():
    assert fmt("h a", datetime(2026, 1, 1, 0, 0)) == "12 AM"
    assert fmt("h a", datetime(2026, 1, 1, 12, 0)) == "12 PM"


def test_strftime_sequences_are_plain_text():
    # `%` is literal: no user text ever reaches strftime ("%%", "%n" stay as typed)
    assert fmt("%% %- HH") == "%% %- 09"
    assert fmt("[HH]") == "[09]" and fmt("HH–mm") == "09–05"  # non-ASCII punctuation is text


@pytest.mark.parametrize(
    ("text", "letter", "position"),
    [
        ("%Y", "Y", 2),  # a strftime letter is not a token
        ("HH:m", "m", 4),  # one m is not a token
        ("yy", "y", 1),
        ("MMMM", "M", 4),  # MMM then a lone M
        ("HH at mm", "t", 5),  # unquoted: a is a token, then a lone t
    ],
)
def test_any_other_letter_is_an_error_naming_it(text, letter, position):
    with pytest.raises(ValueError) as exc:
        parse_clock_format(text)
    assert f"unknown token {letter!r} at position {position}" in str(exc.value)
    assert "HH, mm, ss" in str(exc.value) and "single quotes" in str(exc.value)


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ("HH 'at' mm", "09 at 05"),
        ("'Uhr' HH", "Uhr 09"),
        ("'%Y %n' HH", "%Y %n 09"),  # quoted strftime codes stay text
        ("HH''mm", "09'05"),  # two quotes outside quoted text: one quote
        ("'it''s' HH", "it's 09"),  # two quotes inside quoted text: one quote
        ("''", "'"),
        ("HH ''", "09 '"),
        ("'' HH '' mm", "' 09 ' 05"),
        ("HH ''''", "09 ''"),
        ("'' 'x'", "' x"),
    ],
)
def test_quoted_text_is_shown_as_written(text, shown):
    assert fmt(text) == shown


@pytest.mark.parametrize(("text", "position"), [("HH 'at", 4), ("'", 1), ("HH 'it''s", 4)])
def test_an_unterminated_quote_is_an_error(text, position):
    with pytest.raises(ValueError, match=f"unterminated quote at position {position}"):
        parse_clock_format(text)


def test_literal_text_is_kept_together():
    assert parse_clock_format("HH'h'' '") == ((True, "HH"), (False, "h' "))
    # neighbouring literal characters, quoted or not, are one part
    assert parse_clock_format("HH :-) 'x'") == ((True, "HH"), (False, " :-) x"))
    assert parse_clock_format("HH h:mm") == (
        (True, "HH"),
        (False, " "),
        (True, "h"),
        (False, ":"),
        (True, "mm"),
    )


class _NoStrftime(datetime):
    def strftime(self, fmt):  # the names must not come from the process locale
        raise AssertionError(f"strftime({fmt!r}) called")


def test_day_and_month_names_are_fixed_english_whatever_the_locale():
    # strftime's %a and %b follow LC_TIME once Gtk has called setlocale: no token uses it
    assert fmt("ddd MMM", _NoStrftime(2026, 10, 14)) == "Wed Oct"
    names = [fmt("ddd", datetime(2026, 10, 12 + i)) for i in range(7)]
    assert names == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    months = [fmt("MMM", datetime(2026, m, 1)) for m in range(1, 13)]
    assert months == "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def test_the_year_is_zero_padded_to_four_digits():
    assert fmt("yyyy", datetime(5, 1, 1)) == "0005"
    assert fmt("yyyy", datetime(2026, 1, 1)) == "2026"


@pytest.mark.parametrize("text", ["HH\nmm", "HH\tmm", "'a\x00b' HH", "HH\x7f", "\x1b[0m HH"])
def test_control_characters_are_an_error(text):
    with pytest.raises(ValueError, match="control character"):
        parse_clock_format(text)


@pytest.mark.parametrize("text", ["", " ", "   ", "' '", "' ' ' '", "\u00a0"])
def test_a_format_with_nothing_visible_is_an_error(text):
    with pytest.raises(ValueError, match="nothing visible"):
        parse_clock_format(text)


def test_a_format_needs_one_visible_character_not_a_token():
    assert fmt("-") == "-" and fmt(" HH ") == " 09 " and fmt("''") == "'"
