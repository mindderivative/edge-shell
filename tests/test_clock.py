from datetime import datetime

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

from widgets.clock import REFRESH_MS, format_time  # noqa: E402


def test_format_is_24h_zero_padded():
    assert format_time(datetime(2026, 1, 2, 3, 4, 59)) == "03:04"
    assert format_time(datetime(2026, 1, 2, 23, 59, 0)) == "23:59"


def test_refresh_is_fast_enough_for_minute_rollover():
    assert REFRESH_MS <= 1000
