"""Widget registry: name -> panel class + default geometry. Pure (no GTK)."""

from __future__ import annotations

from collections.abc import Callable

from shell.config.models import Config, ConfigError, PanelConfig
from shell.panel_spec import PanelDefaults, PanelGeometry

_WIDGETS: dict[str, type] = {}
_DEFAULTS: dict[str, PanelDefaults] = {}


def register(name: str, defaults: PanelDefaults) -> Callable[[type], type]:
    def decorate(cls: type) -> type:
        if name in _WIDGETS:
            raise ValueError(f"widget {name!r} is already registered")
        _WIDGETS[name] = cls
        _DEFAULTS[name] = defaults
        return cls

    return decorate


def widget_names() -> list[str]:
    return sorted(_WIDGETS)


def widget_class(name: str) -> type:
    return _WIDGETS[name]


def resolve_panel(cfg: PanelConfig) -> PanelGeometry:
    d = _DEFAULTS.get(cfg.widget)
    if d is None:
        known = ", ".join(widget_names()) or "none"
        raise ConfigError(f"unknown widget {cfg.widget!r} (known: {known})")
    if cfg.pos is None:
        pos = d.pos
    else:
        pos = None if cfg.pos == "center" else cfg.pos
    return PanelGeometry(
        widget=cfg.widget,
        edge=cfg.edge or d.edge,
        pos=pos,
        length=cfg.length or d.length,
        depth=cfg.depth or d.depth,
        state=cfg.state or d.state,
        label=d.label,
    )


def panels_for(config: Config, monitor: str) -> list[PanelGeometry]:
    return [resolve_panel(p) for p in config.monitor(monitor).panels]


def validate_widgets(config: Config) -> None:
    problems = [
        f"monitors.{name}.panels[{i}].widget: unknown widget {panel.widget!r}"
        for name, mon in config.monitors.items()
        for i, panel in enumerate(mon.panels)
        if panel.widget not in _DEFAULTS
    ]
    if problems:
        known = ", ".join(widget_names()) or "none"
        raise ConfigError("\n".join(problems) + f"\nknown widgets: {known}")
