# shell/config/diff.py
"""Turn an old/new config pair into the smallest set of window changes. Pure."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from shell.config.models import Config
from shell.registry import requests_for

Kind = Literal[
    "restyle",
    "relayout",
    "rebuild-monitor",
    "panel-add",
    "panel-remove",
    "panel-rebuild",
    "panel-state",
]
_STRUCTURAL = ("thickness", "radius", "peek", "hover_zone", "duration_ms")


@dataclass(frozen=True)
class Change:
    kind: Kind
    monitor: str
    index: int | None = None


def _has_windows(config: Config, name: str) -> bool:
    return config.monitor(name).shell in ("edge", "both")


def diff_configs(old: Config, new: Config) -> list[Change]:
    changes: list[Change] = []
    for name in sorted(set(old.monitors) | set(new.monitors)):
        was, now = _has_windows(old, name), _has_windows(new, name)
        if not was and not now:
            continue
        if was != now:
            changes.append(Change("rebuild-monitor", name))
            continue
        old_theme, new_theme = old.theme_for(name), new.theme_for(name)
        if any(getattr(old_theme, k) != getattr(new_theme, k) for k in _STRUCTURAL):
            changes.append(Change("rebuild-monitor", name))
            continue
        if old_theme != new_theme:
            changes.append(Change("restyle", name))
        if old.layout_for(name) != new.layout_for(name):
            changes.append(Change("relayout", name))
        changes.extend(_diff_panels(name, requests_for(old, name), requests_for(new, name)))
    return changes


def _diff_panels(name, old, new) -> list[Change]:
    changes: list[Change] = []
    removed: list[Change] = []
    for i in range(max(len(old), len(new))):
        if i >= len(old):
            changes.append(Change("panel-add", name, i))
        elif i >= len(new):
            removed.append(Change("panel-remove", name, i))
        elif old[i] == new[i]:
            continue
        elif replace(old[i], state=new[i].state) == new[i]:
            changes.append(Change("panel-state", name, i))
        else:
            changes.append(Change("panel-rebuild", name, i))
    return changes + removed[::-1]
