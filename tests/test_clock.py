from datetime import datetime

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import widgets.clock as ck  # noqa: E402
import widgets.system_bar as sb  # noqa: E402
from widgets.clock import REFRESH_MS, format_time  # noqa: E402


def test_format_is_24h_zero_padded():
    assert format_time(datetime(2026, 1, 2, 3, 4, 59)) == "03:04"
    assert format_time(datetime(2026, 1, 2, 23, 59, 0)) == "23:59"


def test_refresh_is_fast_enough_for_minute_rollover():
    assert REFRESH_MS <= 1000


@pytest.mark.parametrize("module, cls", [(ck, "ClockWidget"), (sb, "SystemBarWidget")])
def test_destroy_stops_the_timer_once(monkeypatch, module, cls):
    removed = []
    monkeypatch.setattr(module.GLib, "source_remove", removed.append)
    widget = getattr(module, cls)()
    widget._repeater_id = 9
    widget.destroy()
    widget.destroy()
    assert removed == [9] and widget._destroyed
    assert widget._refresh() is False  # a refresh already queued does nothing
