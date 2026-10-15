"""Widget registry: id -> widget class, display title, property model and per-kind default
geometry (panel/widget spec 3.4-3.5). Pure (no GTK)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from types import UnionType
from typing import Annotated, Literal, Union, get_args, get_origin

from pydantic import ValidationError

from shell.config.models import (
    CORNER_ONLY_KEYS,
    CORNERS,
    EDGE_ONLY_KEYS,
    FRAMEWORK_KEYS,
    Config,
    ConfigError,
    HandleConfig,
    InteractionConfig,
    PanelConfig,
    PanelState,
    check_panel_name,
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
from shell.widget import WidgetProps


@dataclass(frozen=True)
class WidgetInfo:
    """One registration: the class, its display title, its property model and the defaults
    of each panel kind it can be shown in (None: not in that kind)."""

    cls: type
    title: str
    props: type[WidgetProps]
    edge: PanelDefaults | None
    corner: CornerDefaults | None


_WIDGETS: dict[str, WidgetInfo] = {}
# The property types the settings window has a row for (settings.form: a text row (Task 7), a
# spin button, a switch; a Literal of strings is a combo): anything else is refused at registration.
FORM_TYPES = (str, int, bool)
FORM_TYPES_TEXT = "str, int, bool, a Literal of strings, or one of these | None"
_PLACEMENT = ("pos", "align", "offset")
_KINDS = ("edge", "corner")  # the order supported_kinds lists them in


def register_widget(
    widget_id: str,
    *,
    title: str,
    props: type[WidgetProps] = WidgetProps,
    edge: PanelDefaults | None = None,
    corner: CornerDefaults | None = None,
) -> Callable[[type], type]:
    """Register a widget class. It can be shown in an edge panel when it has `edge` defaults
    and in a corner panel when it has `corner` defaults (both may be given). `title` is its
    name in the settings window and a new panel's name; `props` its property model. Bad
    defaults, a bad title or a property named like a panel key fail here, at import, before
    any window exists."""
    _check_registration(widget_id, title, props, edge, corner)

    def decorate(cls: type) -> type:
        if widget_id in _WIDGETS:
            raise ValueError(f"widget {widget_id!r} is already registered")
        _WIDGETS[widget_id] = WidgetInfo(cls, title, props, edge, corner)
        return cls

    return decorate


def form_type_ok(annotation: object) -> bool:
    """True when the settings window can show a property of this type (FORM_TYPES_TEXT)."""
    origin = get_origin(annotation)
    if origin is Annotated:
        return form_type_ok(get_args(annotation)[0])
    if origin in (Union, UnionType):
        options = [a for a in get_args(annotation) if a is not type(None)]
        return len(options) == 1 and form_type_ok(options[0])
    if origin is Literal:
        return all(isinstance(v, str) for v in get_args(annotation))
    return annotation in FORM_TYPES


def _aliases(field) -> list[str]:
    """The names a property is read from besides its own (alias, validation_alias, choices)."""
    found = [field.alias]
    choices = field.validation_alias
    found += [choices] if isinstance(choices, str) else getattr(choices, "choices", [])
    return [a for a in found if isinstance(a, str)]


def _check_registration(
    widget_id: str,
    title: str,
    props: type[WidgetProps],
    edge: PanelDefaults | None,
    corner: CornerDefaults | None,
) -> None:
    if edge is None and corner is None:
        raise ValueError(f"widget {widget_id!r}: give edge or corner defaults (or both)")
    if edge is not None and not isinstance(edge, PanelDefaults):
        raise ValueError(f"widget {widget_id!r}: edge defaults must be PanelDefaults")
    if corner is not None and not isinstance(corner, CornerDefaults):
        raise ValueError(f"widget {widget_id!r}: corner defaults must be CornerDefaults")
    if not isinstance(title, str):
        raise ValueError(f"widget {widget_id!r}: title must be a string")
    if not 1 <= len(title) <= 40:
        raise ValueError(f"widget {widget_id!r}: title must be 1-40 characters")
    try:
        check_panel_name(title)  # it becomes a new panel's name
    except ValueError as exc:
        raise ValueError(f"widget {widget_id!r}: title {exc}") from None
    if not (isinstance(props, type) and issubclass(props, WidgetProps)):
        raise ValueError(f"widget {widget_id!r}: props must be a WidgetProps model")
    if props.model_config.get("frozen") is not True:
        raise ValueError(f"widget {widget_id!r}: props must stay frozen (frozen=True)")
    if props.model_config.get("extra") != "forbid":
        raise ValueError(f"widget {widget_id!r}: props must forbid extra keys (extra='forbid')")
    reserved = FRAMEWORK_KEYS | {"widget_props"}
    clash = sorted(set(props.model_fields) & reserved)
    if clash:
        raise ValueError(
            f"widget {widget_id!r}: property {clash[0]!r} has the name of a panel key; rename it"
        )
    for name, field in props.model_fields.items():
        for alias in _aliases(field):
            if alias in reserved:
                raise ValueError(
                    f"widget {widget_id!r}: property {name!r} has the alias {alias!r}, the name "
                    "of a panel key; rename it"
                )
    for name, field in props.model_fields.items():
        if not form_type_ok(field.annotation):
            kind = field.annotation
            kind = kind.__name__ if isinstance(kind, type) else repr(kind).replace("typing.", "")
            raise ValueError(
                f"widget {widget_id!r}: property {name!r} is of type {kind}, which the settings "
                f"window cannot show; use {FORM_TYPES_TEXT}"
            )
    try:
        props()
    except ValidationError as exc:
        raise ValueError(f"widget {widget_id!r}: every property needs a default: {exc}") from None
    for d in (edge, corner):
        if d is not None:
            _check_defaults(widget_id, d)


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
    """KeyError for an unknown widget (like every lookup here)."""
    return _WIDGETS[name].cls


def widget_title(name: str) -> str:
    """The display name: the settings window's widget list and a new panel's name."""
    return _WIDGETS[name].title


def widget_props_model(name: str) -> type[WidgetProps]:
    """The widget's property model (the settings window builds its Widget rows from it)."""
    return _WIDGETS[name].props


def supported_kinds(name: str) -> tuple[str, ...]:
    """The panel kinds the widget can be shown in, edge before corner."""
    info = _WIDGETS[name]
    return tuple(k for k in _KINDS if getattr(info, k) is not None)


def defaults(name: str, kind: str) -> PanelDefaults | CornerDefaults:
    """The widget's registered defaults for a panel kind (the settings window shows them; it
    never reads _WIDGETS). KeyError for an unknown widget or a kind it does not support."""
    d = getattr(_WIDGETS[name], kind) if kind in _KINDS else None
    if d is None:
        raise KeyError(f"{name} has no {kind} panel defaults")
    return d


def widget_props(cfg: PanelConfig) -> WidgetProps:
    """The entry's widget keys, validated by the widget's model (defaults filled in)."""
    try:
        return _WIDGETS[cfg.widget].props.model_validate(cfg.widget_props)
    except ValidationError as exc:
        lines = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
        raise ConfigError(f"{cfg.widget} properties:\n" + "\n".join(lines)) from None


def _in_a(kind: str) -> str:
    return f"{'an' if kind == 'edge' else 'a'} {kind} panel"


def request_for(cfg: PanelConfig) -> PanelRequest | CornerRequest:
    """The defaults of the entry's panel kind overlaid with the entry. Placement is taken as a
    whole: if the entry sets any of pos / align / offset, the widget's default placement is
    dropped and the keys it leaves out are align = "center", offset = 0 (`pos = "center"` is
    align = "center"). Without any of them the widget's default placement applies."""
    info = _WIDGETS.get(cfg.widget)
    if info is None:
        known = ", ".join(widget_names()) or "none"
        raise ConfigError(f"unknown widget {cfg.widget!r} (known: {known})")
    if cfg.panel not in supported_kinds(cfg.widget):
        raise ConfigError(f"{cfg.widget} cannot be shown in {_in_a(cfg.panel)}")
    props = widget_props(cfg)
    if cfg.panel == "corner":
        return _corner_request(cfg, info.corner, props)
    d = info.edge
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
        name=cfg.name,
        props=props,
    )


def _corner_request(cfg: PanelConfig, d: CornerDefaults, props: WidgetProps) -> CornerRequest:
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
        name=cfg.name,
        props=props,
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
        and panel.panel == "edge"
        and any(v is not None for v in (panel.edge, panel.length, panel.depth))
        and all(getattr(panel, k) is None for k in _PLACEMENT)
    ]


_ALL_OFF = Interaction(click=False, hover=False, drag=False)


def _supports(panel: PanelConfig) -> bool:
    return panel.widget in _WIDGETS and panel.panel in supported_kinds(panel.widget)


def all_off_paths(config: Config) -> list[str]:
    """Key paths of the panel entries whose click, hover and drag are all off (entry over the
    widget's default): they open and close only through `state` (decision 7). EdgeShellApp
    logs them once per config load; unknown widgets and kinds are left to validate_widgets."""
    return [
        f"monitors.{name}.panels.{i}"
        for name, mon in config.monitors.items()
        for i, panel in enumerate(mon.panels)
        if _supports(panel)
        and _interaction(panel, defaults(panel.widget, panel.panel).interaction) == _ALL_OFF
    ]


def _kind_problems(where: str, panel: PanelConfig) -> list[str]:
    """Keys an entry sets that its panel kind does not take (spec 19)."""
    if panel.panel == "corner":
        wrong = [k for k in EDGE_ONLY_KEYS if getattr(panel, k) is not None]
        problems = [
            f"{where}.{key}: a corner panel takes corner, edge, width and height, not {key}"
            for key in wrong
        ]
        corner = panel.corner or defaults(panel.widget, "corner").corner
        if panel.edge is not None and not corner_has_edge(corner, panel.edge):
            first, second = corner.split("-")
            problems.append(
                f"{where}.edge: {panel.edge!r} is not an edge of the {corner} corner "
                f"(use {first} or {second})"
            )
        return problems
    return [
        f"{where}.{key}: an edge panel takes no {key}; corner, width and height only apply "
        "to corner panels"
        for key in CORNER_ONLY_KEYS
        if getattr(panel, key) is not None
    ]


def _props_problems(where: str, panel: PanelConfig) -> list[str]:
    """The entry's widget keys against the widget's property model."""
    try:
        _WIDGETS[panel.widget].props.model_validate(panel.widget_props)
    except ValidationError as exc:
        problems = []
        for error in exc.errors():
            key = ".".join(str(p) for p in error["loc"])
            if error["type"] == "extra_forbidden":
                problems.append(f"{where}.{key}: unknown key for widget {panel.widget!r}")
            else:
                problems.append(f"{where}.{key}: {error['msg']}")
        return problems
    return []


def _name_problems(where: str, panels: list[PanelConfig]) -> list[str]:
    """A name used twice on one monitor: reported at every later use, naming the first."""
    first: dict[str, int] = {}
    problems = []
    for i, panel in enumerate(panels):
        if panel.name in first:
            problems.append(
                f"{where}[{i}].name: names must be unique: {panel.name!r} is used by "
                f"panels[{first[panel.name]}] and panels[{i}]"
            )
        else:
            first[panel.name] = i
    return problems


def _entry_problems(where: str, panel: PanelConfig) -> list[str]:
    if panel.panel == "float":
        return [f"{where}.panel: float panels are not implemented yet"]
    if panel.widget not in _WIDGETS:
        return [f"{where}.widget: unknown widget {panel.widget!r}"]
    kinds = supported_kinds(panel.widget)
    if panel.panel not in kinds:
        return [
            f"{where}.panel: {panel.widget} cannot be shown in {_in_a(panel.panel)} "
            f"(it supports: {', '.join(kinds)})"
        ]
    return _kind_problems(where, panel) + _props_problems(where, panel)


def validate_widgets(config: Config) -> None:
    problems = []
    for name, mon in config.monitors.items():
        for i, panel in enumerate(mon.panels):
            problems.extend(_entry_problems(f"monitors.{name}.panels[{i}]", panel))
        problems.extend(_name_problems(f"monitors.{name}.panels", mon.panels))
    if problems:
        text = "\n".join(problems)
        if any(": unknown widget " in p for p in problems):  # only that error needs the list
            text += f"\nknown widgets: {', '.join(widget_names()) or 'none'}"
        raise ConfigError(text)
