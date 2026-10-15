"""Clock: time of day on the top edge. Its properties: format (a fixed token table,
services.clock_format), font and font_size (None: the theme's)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

import gi

gi.require_version("Gtk", "3.0")
from fabric.utils import invoke_repeater
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from gi.repository import GLib, Gtk
from pydantic import Field, field_validator

from services.clock_format import format_clock, parse_clock_format
from shell.config.models import check_font_name
from shell.panel_spec import PanelDefaults
from shell.registry import register_widget
from shell.theme import label_font_css
from shell.widget import Widget, WidgetProps

REFRESH_MS = 1000  # the minute rolls over within a second of the real change
SECONDS_REFRESH_MS = 250  # a format with `ss`: the second changes within a quarter second
# Above the app's stylesheet (Fabric adds it at USER priority): the label's own font wins.
FONT_PRIORITY = Gtk.STYLE_PROVIDER_PRIORITY_USER + 1


def format_time(now: datetime) -> str:
    """HH:mm (the summary block's time)."""
    return now.strftime("%H:%M")


class ClockProps(WidgetProps):
    format: Annotated[str, Field(min_length=1, max_length=64)] = Field(
        "HH:mm", description="HH mm ss H h a ddd dd MMM MM yyyy; other text in 'single quotes'"
    )
    font: Annotated[str, Field(min_length=1, max_length=100)] | None = Field(
        None, description="a font family; reset: the theme's font"
    )
    font_size: Annotated[int, Field(ge=6, le=96)] | None = Field(
        None, description="pt; reset: the theme's size"
    )

    @field_validator("format")
    @classmethod
    def _format(cls, value: str) -> str:
        parse_clock_format(value)
        return value

    @field_validator("font")
    @classmethod
    def _font(cls, value: str | None) -> str | None:
        return None if value is None else check_font_name(value)


@register_widget(
    "clock",
    title="Clock",
    props=ClockProps,
    edge=PanelDefaults(edge="top", length=168, depth=46, label="clock"),
)
class ClockWidget(Widget):
    def __init__(self) -> None:
        self._destroyed = False
        self._repeater_id = 0
        self._parts = parse_clock_format("HH:mm")

    def build(self, props: ClockProps):
        self._parts = parse_clock_format(props.format)
        self._time = Label(name="clock-time", label=self._text(datetime.now()))
        css = label_font_css(props.font, props.font_size, self.theme_fonts)
        if css:
            provider = Gtk.CssProvider()
            provider.load_from_data(css.encode())
            self._time.get_style_context().add_provider(provider, FONT_PRIORITY)
        shows_seconds = (True, "ss") in self._parts
        interval = SECONDS_REFRESH_MS if shows_seconds else REFRESH_MS
        self._repeater_id = invoke_repeater(interval, self._refresh)
        return Box(name="clock", h_align="center", v_align="center", children=self._time)

    def _text(self, now: datetime) -> str:
        return format_clock(self._parts, now)

    def destroy(self) -> None:
        # Panels are rebuilt on config reload and hot-plug: stop the timer with them.
        self._destroyed = True
        if self._repeater_id:
            GLib.source_remove(self._repeater_id)
            self._repeater_id = 0

    def _refresh(self) -> bool:
        if self._destroyed:
            return False
        text = self._text(datetime.now())
        if text != self._time.get_label():  # avoid a relayout every second
            self._time.set_label(text)
        return True
