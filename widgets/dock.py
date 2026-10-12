"""Dock: a row of app launchers on the bottom edge."""

from __future__ import annotations

from fabric.utils import exec_shell_command_async
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image

from shell.edge_panel import EdgePanel
from shell.panel_spec import PanelDefaults
from shell.registry import register

APPS = [  # (tooltip, icon name, command)
    ("Terminal", "utilities-terminal-symbolic", "konsole"),
    ("Files", "folder-symbolic", "dolphin"),
    ("Settings", "preferences-system-symbolic", "systemsettings"),
]


@register("dock", PanelDefaults(edge="bottom", length=560, depth=64, label="dock"))
class DockPanel(EdgePanel):
    def build_content(self):
        return Box(
            name="dock",
            orientation="h",
            spacing=8,
            h_align="center",
            v_align="center",
            children=[
                Button(
                    style_classes="icon-button",
                    tooltip_text=tip,
                    child=Image(icon_name=icon, icon_size=20),
                    on_clicked=lambda *_, c=cmd: exec_shell_command_async(c),
                )
                for tip, icon, cmd in APPS
            ],
        )
