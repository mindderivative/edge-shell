"""The summary corner widget (spec 19; it was widget_panel): registration, text and refresh (no
window)."""

from datetime import datetime
from types import SimpleNamespace

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import widgets.summary as sm  # noqa: E402
from shell import registry  # noqa: E402
from shell.panel_spec import CornerDefaults  # noqa: E402
from shell.widget import Widget  # noqa: E402


class FakeLabel:
    def __init__(self, text=""):
        self.text, self.sets = text, 0

    def get_label(self):
        return self.text

    def set_label(self, text):
        self.text, self.sets = text, self.sets + 1


def test_it_is_registered_as_the_spec_corner_widget():
    assert registry.widget_class("summary") is sm.SummaryWidget
    assert issubclass(sm.SummaryWidget, Widget)
    assert registry.supported_kinds("summary") == ("corner",)
    assert registry.widget_title("summary") == "Summary"
    assert registry.defaults("summary", "corner") == CornerDefaults(
        corner="bottom-left", width=300, height=390, label="summary"
    )


def test_date_and_stats_text():
    assert sm.format_date(datetime(2026, 10, 14, 9, 5)) == "Wed 14 Oct"
    assert sm.stats_lines(12.4, 56.6) == ("CPU 12%", "RAM 57%")


def test_refresh_updates_the_time_every_tick_and_the_stats_every_second(monkeypatch):
    monkeypatch.setattr(sm, "datetime", SimpleNamespace(now=lambda: datetime(2026, 10, 14, 9, 5)))
    monkeypatch.setattr(sm, "read_cpu_times", lambda: (100, 50))  # (total, idle) jiffies
    monkeypatch.setattr(sm, "read_meminfo_percent", lambda: 40.0)
    s = SimpleNamespace(
        _destroyed=False,
        _ticks=0,
        _prev=(0, 0),
        _time=FakeLabel(),
        _date=FakeLabel(),
        _cpu=FakeLabel("CPU --%"),
        _mem=FakeLabel("RAM --%"),
    )
    assert sm.SummaryWidget._refresh(s) is True
    assert s._time.sets == 1 and s._cpu.text == "CPU --%"  # stats wait for the second tick
    assert sm.SummaryWidget._refresh(s) is True
    assert s._time.sets == 1  # the same minute: no relayout
    assert (s._cpu.text, s._mem.text) == ("CPU 50%", "RAM 40%")  # (100 - 50) / 100 busy


def test_a_destroyed_widget_stops_refreshing():
    assert sm.SummaryWidget._refresh(SimpleNamespace(_destroyed=True)) is False


def test_destroy_stops_the_timer(monkeypatch):
    removed = []
    monkeypatch.setattr(sm.GLib, "source_remove", removed.append)
    w = sm.SummaryWidget()
    w._repeater_id = 7
    w.destroy()
    assert w._destroyed and removed == [7] and w._repeater_id == 0
    w.destroy()  # twice: nothing more to stop
    assert removed == [7]


def test_destroy_before_build_is_harmless(monkeypatch):
    removed = []
    monkeypatch.setattr(sm.GLib, "source_remove", removed.append)
    sm.SummaryWidget().destroy()
    assert removed == []
