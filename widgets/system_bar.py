"""System bar: CPU and memory on the right edge."""

from __future__ import annotations

from fabric.utils import invoke_repeater
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from gi.repository import GLib

from services.sysinfo import cpu_percent, read_cpu_times, read_meminfo_percent
from shell.edge_panel import EdgePanel
from shell.panel_spec import PanelDefaults
from shell.registry import register


@register(
    "system_bar",
    # y = 600 on a 1080 px tall monitor (free span ends at 1042: 1042 - 142 - 300 = 600)
    PanelDefaults(edge="right", length=300, depth=56, label="system bar", align="end", offset=142),
)
class SystemBarPanel(EdgePanel):
    def build_content(self):
        self._cpu = Label(style_classes="secondary")
        self._mem = Label(style_classes="secondary")
        self._prev = read_cpu_times()
        self._destroyed = False
        self._repeater_id = invoke_repeater(2000, self._refresh)
        self.connect("destroy", self._on_destroy)
        return Box(
            name="system-bar",
            orientation="v",
            spacing=12,
            h_align="center",
            v_align="center",
            children=[self._cpu, self._mem],
        )

    def _on_destroy(self, *_args) -> None:
        # Panels are rebuilt on config reload and monitor hot-plug: stop the timer with them.
        self._destroyed = True
        if self._repeater_id:
            GLib.source_remove(self._repeater_id)  # no-op (False) if it already ended
            self._repeater_id = 0

    def _refresh(self) -> bool:
        if self._destroyed:
            return False
        cur = read_cpu_times()
        self._cpu.set_label(f"CPU\n{cpu_percent(self._prev, cur):.0f}%")
        self._prev = cur
        self._mem.set_label(f"RAM\n{read_meminfo_percent():.0f}%")
        return True  # keep repeating
