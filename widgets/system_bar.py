"""System bar: CPU and memory on the right edge."""

from __future__ import annotations

from fabric.utils import invoke_repeater
from fabric.widgets.box import Box
from fabric.widgets.label import Label

from services.sysinfo import cpu_percent, read_cpu_times, read_meminfo_percent
from shell.edge_panel import EdgePanel
from shell.panel_spec import PanelDefaults
from shell.registry import register


@register(
    "system_bar",
    PanelDefaults(edge="right", length=300, depth=56, pos=600, label="system bar"),
)
class SystemBarPanel(EdgePanel):
    def build_content(self):
        self._cpu = Label(style_classes="secondary")
        self._mem = Label(style_classes="secondary")
        self._prev = read_cpu_times()
        invoke_repeater(2000, self._refresh)
        return Box(
            name="system-bar",
            orientation="v",
            spacing=12,
            h_align="center",
            v_align="center",
            children=[self._cpu, self._mem],
        )

    def _refresh(self) -> bool:
        cur = read_cpu_times()
        self._cpu.set_label(f"CPU\n{cpu_percent(self._prev, cur):.0f}%")
        self._prev = cur
        self._mem.set_label(f"RAM\n{read_meminfo_percent():.0f}%")
        return True  # keep repeating
