"""Widget registry: name -> panel class + default geometry. Pure (no GTK)."""

from __future__ import annotations

from collections.abc import Callable

from shell.config.models import Config, ConfigError, PanelConfig
from shell.panel_spec import PanelDefaults, PanelRequest

_WIDGETS: dict[str, type] = {}
_DEFAULTS: dict[str, PanelDefaults] = {}
_PLACEMENT = ("pos", "align", "offset")


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


def request_for(cfg: PanelConfig) -> PanelRequest:
    """The widget's defaults overlaid with one config entry. Placement is taken as a whole: if
    the entry sets any of pos / align / offset, the widget's default placement is dropped and
    the keys it leaves out are align = "center", offset = 0 (`pos = "center"` is align =
    "center"). Without any of them the widget's default placement applies."""
    d = _DEFAULTS.get(cfg.widget)
    if d is None:
        known = ", ".join(widget_names()) or "none"
        raise ConfigError(f"unknown widget {cfg.widget!r} (known: {known})")
    if any(getattr(cfg, key) is not None for key in _PLACEMENT):
        pos = None if cfg.pos in (None, "center") else cfg.pos
        align, offset = cfg.align or "center", cfg.offset or 0
    else:
        pos, align, offset = d.pos, d.align, d.offset
    return PanelRequest(
        widget=cfg.widget,
        edge=cfg.edge or d.edge,
        align=align,
        offset=offset,
        pos=pos,
        order=cfg.order or 0,
        length=d.length if cfg.length is None else cfg.length,
        min_length=cfg.min_length,
        max_length=cfg.max_length,
        depth=cfg.depth or d.depth,
        state=cfg.state or d.state,
        label=d.label,
        fallback_length=d.length,
    )


def requests_for(config: Config, monitor: str) -> list[PanelRequest]:
    return [request_for(p) for p in config.monitor(monitor).panels]


def deprecated_pos_paths(config: Config) -> list[str]:
    """Key paths of the panel entries that still use the deprecated `pos` (decision 2:
    EdgeShellApp logs them once per config load; never notified)."""
    return [
        f"monitors.{name}.panels.{i}.pos"
        for name, mon in config.monitors.items()
        for i, panel in enumerate(mon.panels)
        if panel.pos is not None
    ]


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
