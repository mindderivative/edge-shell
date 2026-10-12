"""Clock: time of day on the top edge."""

from __future__ import annotations

from fabric.widgets.box import Box
from fabric.widgets.datetime import DateTime

from shell.edge_panel import EdgePanel
from shell.panel_spec import PanelDefaults
from shell.registry import register


@register("clock", PanelDefaults(edge="top", length=168, depth=46, label="clock"))
class ClockPanel(EdgePanel):
    def build_content(self):
        return Box(
            name="clock",
            h_align="center",
            v_align="center",
            children=DateTime(formatters=["%H:%M"], interval=10_000, name="clock-time"),
        )
