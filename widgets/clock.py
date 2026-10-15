"""Clock: time of day on the top edge."""

from __future__ import annotations

from datetime import datetime

from fabric.utils import invoke_repeater
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from gi.repository import GLib

from shell.panel_spec import PanelDefaults
from shell.registry import register_widget
from shell.widget import Widget, WidgetProps

REFRESH_MS = 1000  # the minute rolls over within a second of the real change


def format_time(now: datetime) -> str:
    return now.strftime("%H:%M")


@register_widget(
    "clock", title="Clock", edge=PanelDefaults(edge="top", length=168, depth=46, label="clock")
)
class ClockWidget(Widget):
    def __init__(self) -> None:
        self._destroyed = False
        self._repeater_id = 0

    def build(self, props: WidgetProps):
        self._time = Label(name="clock-time", label=format_time(datetime.now()))
        self._repeater_id = invoke_repeater(REFRESH_MS, self._refresh)
        return Box(name="clock", h_align="center", v_align="center", children=self._time)

    def destroy(self) -> None:
        # Panels are rebuilt on config reload and hot-plug: stop the timer with them.
        self._destroyed = True
        if self._repeater_id:
            GLib.source_remove(self._repeater_id)
            self._repeater_id = 0

    def _refresh(self) -> bool:
        if self._destroyed:
            return False
        text = format_time(datetime.now())
        if text != self._time.get_label():  # avoid a relayout every second
            self._time.set_label(text)
        return True
