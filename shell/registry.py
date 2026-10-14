"""Widget registry: name -> panel class + default geometry. Pure (no GTK)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import get_args

from pydantic import ValidationError

from shell.config.models import (
    CORNER_ONLY_KEYS,
    CORNERS,
    EDGE_ONLY_KEYS,
    Config,
    ConfigError,
    HandleConfig,
    InteractionConfig,
    PanelConfig,
    PanelState,
)
from shell.panel_spec import (
    CornerDefaults,
    CornerRequest,
    HandleSpec,
    Interaction,
    PanelDefaults,
    PanelRequest,
    corner_has_edge,
    default_edge,
)

_WIDGETS: dict[str, type] = {}
_DEFAULTS: dict[str, PanelDefaults | CornerDefaults] = {}
_PLACEMENT = ("pos", "align", "offset")


def register(name: str, defaults: PanelDefaults | CornerDefaults) -> Callable[[type], type]:
    """Register a widget class. PanelDefaults make it an edge panel, CornerDefaults a corner
    panel (spec 19); the kind decides which config keys its entries take."""
    _check_defaults(name, defaults)  # a bad widget default fails at import, before any window

    def decorate(cls: type) -> type:
        if name in _WIDGETS:
            raise ValueError(f"widget {name!r} is already registered")
        _WIDGETS[name] = cls
        _DEFAULTS[name] = defaults
        return cls

    return decorate


def _check_defaults(name: str, defaults: PanelDefaults | CornerDefaults) -> None:
    """Widget defaults do not pass through the config models: check the handle and interaction
    ones with the same rules as a config entry (spec 15: shape, size 4-40, weight 1-8, offset,
    #rrggbb[aa] colours, strict booleans)."""
    try:
        HandleConfig.model_validate(asdict(defaults.handle))
        InteractionConfig.model_validate(asdict(defaults.interaction))
    except ValidationError as exc:
        raise ValueError(f"widget {name!r}: invalid handle or interaction default: {exc}") from exc
    if isinstance(defaults, CornerDefaults):
        if defaults.corner not in CORNERS:
            raise ValueError(
                f"widget {name!r}: corner {defaults.corner!r} must be one of {', '.join(CORNERS)}"
            )
        states = get_args(PanelState)
        if defaults.state not in states:
            raise ValueError(
                f"widget {name!r}: state {defaults.state!r} must be {' or '.join(states)}"
            )
        if defaults.edge is not None and not corner_has_edge(defaults.corner, defaults.edge):
            raise ValueError(
                f"widget {name!r}: edge {defaults.edge!r} is not an edge of {defaults.corner}"
            )
        if not (60 <= defaults.width <= 4000 and 60 <= defaults.height <= 4000):
            raise ValueError(f"widget {name!r}: width and height must be 60-4000 px")


def widget_names() -> list[str]:
    return sorted(_WIDGETS)


def widget_class(name: str) -> type:
    return _WIDGETS[name]


def widget_kind(name: str) -> str:
    """The widget's kind, "edge" or "corner" (the settings window shows the matching keys)."""
    return "corner" if isinstance(_DEFAULTS[name], CornerDefaults) else "edge"


def defaults(name: str) -> PanelDefaults | CornerDefaults:
    """The widget's registered defaults (the settings window shows them; it never reads
    _DEFAULTS). KeyError for an unknown widget, like widget_class."""
    return _DEFAULTS[name]


def request_for(cfg: PanelConfig) -> PanelRequest | CornerRequest:
    """The widget's defaults overlaid with one config entry. Placement is taken as a whole: if
    the entry sets any of pos / align / offset, the widget's default placement is dropped and
    the keys it leaves out are align = "center", offset = 0 (`pos = "center"` is align =
    "center"). Without any of them the widget's default placement applies."""
    d = _DEFAULTS.get(cfg.widget)
    if d is None:
        known = ", ".join(widget_names()) or "none"
        raise ConfigError(f"unknown widget {cfg.widget!r} (known: {known})")
    if isinstance(d, CornerDefaults):
        return _corner_request(cfg, d)
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
        handle=_handle(cfg, d.handle),
        interaction=_interaction(cfg, d.interaction),
    )


def _corner_request(cfg: PanelConfig, d: CornerDefaults) -> CornerRequest:
    """A corner widget's defaults overlaid with one entry. The edge it opens from: the entry's,
    else the widget's when it is an edge of the corner, else the corner's top or bottom edge
    (so moving a panel to another corner never leaves it with an impossible edge)."""
    corner = cfg.corner or d.corner
    edge = cfg.edge or d.edge
    if edge is None or not corner_has_edge(corner, edge):
        edge = default_edge(corner)
    return CornerRequest(
        widget=cfg.widget,
        corner=corner,
        edge=edge,
        width=cfg.width or d.width,
        height=cfg.height or d.height,
        state=cfg.state or d.state,
        label=d.label,
        handle=_handle(cfg, d.handle),
        interaction=_interaction(cfg, d.interaction),
    )


def _handle(cfg: PanelConfig, default: HandleSpec) -> HandleSpec:
    """Key by key: the entry's [handle] value, else the widget's default (None = the theme's)."""
    own = cfg.handle
    return HandleSpec(
        **{
            key: getattr(default, key) if getattr(own, key) is None else getattr(own, key)
            for key in ("shape", "size", "weight", "offset", "color", "hover_color")
        }
    )


def _interaction(cfg: PanelConfig, default: Interaction) -> Interaction:
    own = cfg.interaction
    return Interaction(
        **{
            key: getattr(default, key) if getattr(own, key) is None else getattr(own, key)
            for key in ("click", "hover", "drag")
        }
    )


def requests_for(config: Config, monitor: str) -> list[PanelRequest | CornerRequest]:
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


def moved_default_paths(config: Config) -> list[str]:
    """Key paths of the `system_bar` entries whose old default place changed: they set edge,
    length or depth but none of pos / align / offset, so the built-in default placement
    (align = "end", offset = 142; it was pos = 600) applies to a bar that is no longer the
    default size or edge. Logged once per config load by EdgeShellApp."""
    return [
        f"monitors.{name}.panels.{i}"
        for name, mon in config.monitors.items()
        for i, panel in enumerate(mon.panels)
        if panel.widget == "system_bar"
        and any(v is not None for v in (panel.edge, panel.length, panel.depth))
        and all(getattr(panel, k) is None for k in _PLACEMENT)
    ]


_ALL_OFF = Interaction(click=False, hover=False, drag=False)


def all_off_paths(config: Config) -> list[str]:
    """Key paths of the panel entries whose click, hover and drag are all off (entry over the
    widget's default): they open and close only through `state` (decision 7). EdgeShellApp
    logs them once per config load; unknown widgets are left to validate_widgets."""
    return [
        f"monitors.{name}.panels.{i}"
        for name, mon in config.monitors.items()
        for i, panel in enumerate(mon.panels)
        if panel.widget in _DEFAULTS
        and _interaction(panel, _DEFAULTS[panel.widget].interaction) == _ALL_OFF
    ]


def _kind_problems(where: str, panel: PanelConfig) -> list[str]:
    """Keys an entry sets that its widget's kind does not take (spec 19)."""
    d = _DEFAULTS[panel.widget]
    if isinstance(d, CornerDefaults):
        wrong = [k for k in EDGE_ONLY_KEYS if getattr(panel, k) is not None]
        problems = [
            f"{where}.{key}: {panel.widget} is a corner panel; it takes corner, edge, width "
            f"and height, not {key}"
            for key in wrong
        ]
        corner = panel.corner or d.corner
        if panel.edge is not None and not corner_has_edge(corner, panel.edge):
            first, second = corner.split("-")
            problems.append(
                f"{where}.edge: {panel.edge!r} is not an edge of the {corner} corner "
                f"(use {first} or {second})"
            )
        return problems
    return [
        f"{where}.{key}: {panel.widget} is an edge panel; corner, width and height only "
        "apply to corner panels"
        for key in CORNER_ONLY_KEYS
        if getattr(panel, key) is not None
    ]


def validate_widgets(config: Config) -> None:
    problems = []
    for name, mon in config.monitors.items():
        for i, panel in enumerate(mon.panels):
            where = f"monitors.{name}.panels[{i}]"
            if panel.widget not in _DEFAULTS:
                problems.append(f"{where}.widget: unknown widget {panel.widget!r}")
            else:
                problems.extend(_kind_problems(where, panel))
    if problems:
        known = ", ".join(widget_names()) or "none"
        raise ConfigError("\n".join(problems) + f"\nknown widgets: {known}")
