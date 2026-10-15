"""Summary: the spec's corner panel (spec 3 and 19) in the bottom-left corner, rising out
of the bottom edge, 300 x 390 px from the corner (both frame bands included): the time, the
date, CPU and RAM in one column. (It was the `widget_panel` widget.)"""

from __future__ import annotations

from datetime import datetime

from fabric.utils import invoke_repeater
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from gi.repository import GLib

from services.sysinfo import cpu_percent, read_cpu_times, read_meminfo_percent
from shell.panel_spec import CornerDefaults
from shell.registry import register_widget
from shell.widget import Widget, WidgetProps
from widgets.clock import format_time

REFRESH_MS = 1000  # the minute rolls over within a second of the real change
STATS_EVERY = 2  # CPU and RAM every second tick (the system bar's 2 s)


def format_date(now: datetime) -> str:
    return now.strftime("%a %d %b")


def stats_lines(cpu: float, ram: float) -> tuple[str, str]:
    return f"CPU {cpu:.0f}%", f"RAM {ram:.0f}%"


def _set(label, text: str) -> None:
    if label.get_label() != text:  # avoid a relayout every tick
        label.set_label(text)


@register_widget(
    "summary",
    title="Summary",
    corner=CornerDefaults(corner="bottom-left", width=300, height=390, label="summary"),
)
class SummaryWidget(Widget):
    def __init__(self) -> None:
        self._destroyed = False
        self._repeater_id = 0

    def build(self, props: WidgetProps):
        self._ticks = 0
        self._prev = read_cpu_times()
        now = datetime.now()
        self._time = Label(name="summary-time", label=format_time(now))
        self._date = Label(style_classes="secondary", label=format_date(now))
        self._cpu = Label(style_classes="secondary", label="CPU --%")
        self._mem = Label(style_classes="secondary", label="RAM --%")
        self._repeater_id = invoke_repeater(REFRESH_MS, self._refresh)
        return Box(
            name="summary",
            orientation="v",
            spacing=8,
            h_align="center",
            v_align="center",
            children=[self._time, self._date, self._cpu, self._mem],
        )

    def destroy(self) -> None:
        # Panels are rebuilt on config reload and hot-plug: stop the timer with them.
        self._destroyed = True
        if self._repeater_id:
            GLib.source_remove(self._repeater_id)
            self._repeater_id = 0

    def _refresh(self) -> bool:
        if self._destroyed:
            return False
        now = datetime.now()
        _set(self._time, format_time(now))
        _set(self._date, format_date(now))
        self._ticks += 1
        if self._ticks % STATS_EVERY == 0:
            cur = read_cpu_times()
            cpu, ram = stats_lines(cpu_percent(self._prev, cur), read_meminfo_percent())
            self._prev = cur
            _set(self._cpu, cpu)
            _set(self._mem, ram)
        return True
