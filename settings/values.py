"""What each settings field shows: the value in effect and where it comes from. Pure.

A field is addressed by its TOML key path (settings.document.Path_). `is_set` says the user
file sets that key (the row's reset button removes it); `source` names where an unset value
is inherited from. Panel entries are edge or corner panels (spec 19): the entry's `panel`
key is its kind and decides which keys the entry takes; every key that is not a panel key
(FRAMEWORK_KEYS) is a property of the entry's widget (registry.widget_props_model).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from shell.config.models import (
    CORNER_ONLY_KEYS,
    EDGE_ONLY_KEYS,
    FRAMEWORK_KEYS,
    NAME_MAX_LENGTH,
    Config,
)
from shell.outputs import Output
from shell.panel_layout import layout_monitor
from shell.panel_spec import CornerDefaults, CornerRequest, corner_has_edge, default_edge
from shell.registry import (
    defaults,
    request_for,
    requests_for,
    supported_kinds,
    widget_props_model,
    widget_title,
)
from shell.widget import WidgetProps

# keys whose value in effect is the request's (the entry's, else the widget's default)
PANEL_REQUEST_KEYS = (
    "widget",
    "edge",
    "pos",
    "align",
    "offset",
    "order",
    "length",
    "depth",
    "state",
)
CORNER_REQUEST_KEYS = ("widget", "corner", "edge", "width", "height", "state")
PANEL_OWN_KEYS = ("min_length", "max_length")  # no widget default: None when unset
PLACEMENT_KEYS = ("pos", "align", "offset")  # taken as a whole (shell.registry.request_for)
PLACEMENT_DEFAULT = "placement default (align/offset set)"


@dataclass(frozen=True)
class FieldValue:
    value: Any  # in effect now (None: not set anywhere, e.g. min_length)
    is_set: bool  # the user file sets this key
    source: str  # "your config", or where the value is inherited from
    # the value the key has when it is not set (the widget's default; the length row uses it
    # when switching back to px from fill or content)
    default: Any = field(default=None, compare=False)


def lookup(data: dict, path: tuple) -> tuple[bool, Any]:
    """(found, value) of a key path in plain data; ints index lists."""
    node: Any = data
    for key in path:
        try:
            node = node[key]
        except (KeyError, IndexError, TypeError):
            return False, None
    return True, node


def _attr(obj: Any, keys: tuple) -> Any:
    for key in keys:
        obj = getattr(obj, key)
    return obj


def field_value(config: Config, user: dict, path: tuple) -> FieldValue:
    """The value in effect for `path` under `config` (the merged, validated config) and the
    user file's plain data `user`."""
    is_set, _ = lookup(user, path)
    head, rest = path[0], path[1:]
    if head in ("theme", "layout"):
        value = _attr(config.theme if head == "theme" else config.layout, rest)
        return FieldValue(value, is_set, "your config" if is_set else "default")
    if head != "monitors":
        raise KeyError(f"no settings field for {path}")
    name, table, rest = path[1], path[2], path[3:]
    if table == "shell":
        return FieldValue(config.monitor(name).shell, is_set, _src(is_set, "default"))
    if table == "theme":
        value = _attr(config.theme_for(name), rest)
        return FieldValue(value, is_set, _src(is_set, "global theme"))
    if table == "layout":
        value = _attr(config.layout_for(name), rest)
        return FieldValue(value, is_set, _src(is_set, "global layout"))
    if table == "panels":
        return _panel_value(config, name, rest[0], rest[1:], is_set)
    raise KeyError(f"no settings field for {path}")


def _src(is_set: bool, inherited: str) -> str:
    return "your config" if is_set else inherited


def _panel_value(config: Config, name: str, index: int, keys: tuple, is_set: bool) -> FieldValue:
    entry = config.monitor(name).panels[index]
    req = request_for(entry)
    d = defaults(entry.widget, entry.panel)  # public registry API: never _WIDGETS
    key = keys[0]
    if key in ("name", "panel"):  # required: always in the file
        return FieldValue(getattr(entry, key), is_set, _src(is_set, "not set"))
    if key not in FRAMEWORK_KEYS:  # a widget property: the entry's, else the model's default
        model = widget_props_model(entry.widget)
        if key not in model.model_fields:
            raise KeyError(f"{entry.widget} has no property {key!r}")
        default = model.model_fields[key].default
        source = _src(is_set, "widget default")
        return FieldValue(getattr(req.props, key), is_set, source, default)
    if key == "interaction":
        # always "default": no widget registers interaction defaults today (if one does, the
        # label should become "widget default" for it)
        return FieldValue(getattr(req.interaction, keys[1]), is_set, _src(is_set, "default"))
    if key == "handle":
        sub = keys[1]
        own = getattr(req.handle, sub)
        if own is not None:
            return FieldValue(own, is_set, _src(is_set, "widget default"))
        theme = config.theme_for(name)
        if sub == "shape" and not (
            req.interaction.click or req.interaction.hover or req.interaction.drag
        ):  # shell.handle.resolve_handle draws no theme shape on a panel nobody can act on
            return FieldValue(theme.handle_style.shape, is_set, "none (all interactions off)")
        if sub == "color":
            return FieldValue(theme.handle, is_set, "theme")
        if sub == "hover_color":
            return FieldValue(theme.handle_hover, is_set, "theme")
        return FieldValue(getattr(theme.handle_style, sub), is_set, "theme")
    if isinstance(req, CornerRequest):
        return _corner_value(req, d, key, is_set)
    if key in PANEL_REQUEST_KEYS:
        source = "widget default"
        if key in PLACEMENT_KEYS and any(getattr(entry, k) is not None for k in PLACEMENT_KEYS):
            source = PLACEMENT_DEFAULT  # the widget's own align / offset no longer apply
        if key == "order":
            source = "default"  # PanelDefaults has no order: 0 is the shell's own default
        value = getattr(req, key)
        if key == "pos" and entry.pos is not None:
            value = entry.pos  # the request turns "center" into None; show what the file says
        return FieldValue(value, is_set, _src(is_set, source), getattr(d, key, None))
    if key in PANEL_OWN_KEYS:
        return FieldValue(getattr(entry, key), is_set, _src(is_set, "not set"))
    if key in CORNER_ONLY_KEYS:
        return FieldValue(None, is_set, "not used by edge panels")
    raise KeyError(f"no settings field for panel key {keys}")


def _corner_value(req: CornerRequest, d: CornerDefaults, key: str, is_set: bool) -> FieldValue:
    """A corner panel's key (spec 19): corner, edge, width, height and state come from the
    entry, else the widget's CornerDefaults; `edge` unset is the widget's edge when it is an
    edge of the corner, else the corner's top or bottom edge (shell.panel_spec.default_edge)."""
    if key in CORNER_REQUEST_KEYS:
        source = "widget default"
        default = getattr(d, key, None)
        if key == "edge" and not (d.edge is not None and corner_has_edge(req.corner, d.edge)):
            source, default = "corner default", default_edge(req.corner)
        return FieldValue(getattr(req, key), is_set, _src(is_set, source), default)
    if key in EDGE_ONLY_KEYS:
        return FieldValue(None, is_set, "not used by corner panels")
    raise KeyError(f"no settings field for panel key {key!r}")


def panel_ops(entry: dict, key: str, value: Any) -> list[tuple[str, str, Any]]:
    """Setting one key of a panel entry (`entry`: its plain data in the user file), as steps
    (("set" | "unset", key, value)) applied as ONE edit: one write, one reload.

    - A widget that cannot be shown in the entry's kind also sets `panel` to the first kind
      it supports and unsets the keys only the old kind takes (a dock turned into a corner
      widget loses its align, length, ...; spec 19), else the shell rejects it. The widget
      keys the new widget does not have go too. The entry keeps its name.
    - A new `panel` kind unsets the keys only the old kind takes, as above.
    - `value` None for "corner" is a reset: the key is unset and the widget's corner applies.
    - An unknown widget, float or a kind the widget does not support is a plain set (the
      session's check rejects it with the shell's text, ConfigError).
    - A corner (or a corner widget whose corner) that does not contain the entry's edge also
      unsets that edge: the panel then opens from the widget's edge or the corner's default."""
    if value is None and key == "corner":  # reset: back to the widget's corner
        ops: list[tuple[str, str, Any]] = [("unset", key, None)]
    else:
        ops = [("set", key, value)]
    corner = None
    if key == "widget":
        try:
            kinds = supported_kinds(value)
        except KeyError:  # unknown widget: the session's check rejects it with the shell's text
            return ops
        kind = entry.get("panel") if entry.get("panel") in kinds else kinds[0]
        if entry.get("panel") != kind:
            ops.append(("set", "panel", kind))
        model = widget_props_model(value)
        ops += [
            ("unset", k, None)
            for k in entry
            if k not in FRAMEWORK_KEYS and not _fits(model, k, entry[k])
        ]
        ops += _kind_ops(entry, kind)
        if kind == "corner":
            corner = entry.get("corner", defaults(value, "corner").corner)
    elif key == "panel":
        try:
            supported = value in supported_kinds(entry["widget"])
        except KeyError:  # unknown widget: the session's check says so
            supported = False
        if not supported:  # float, or a kind the widget lacks: rejected by the session
            return ops
        ops += _kind_ops(entry, value)
        if value == "corner":
            corner = entry.get("corner", defaults(entry["widget"], "corner").corner)
    elif key == "corner":
        corner = value or defaults(entry["widget"], "corner").corner
    edge = entry.get("edge")
    if corner is not None and edge is not None and not corner_has_edge(corner, edge):
        ops.append(("unset", "edge", None))
    return ops


def _fits(model: type[WidgetProps], key: str, value: Any) -> bool:
    """True when the new widget has the property `key` and takes `value` for it: a key the two
    widgets share is kept only then (their types may differ)."""
    if key not in model.model_fields:
        return False
    try:
        model.model_validate({key: value})
    except ValidationError as exc:
        return not any(err["loc"][:1] == (key,) for err in exc.errors())
    return True


def _kind_ops(entry: dict, kind: str) -> list[tuple[str, str, Any]]:
    """Unset the keys of the other panel kind (spec 19)."""
    stale = CORNER_ONLY_KEYS if kind == "edge" else EDGE_ONLY_KEYS
    return [("unset", k, None) for k in stale if k in entry]


def unique_name(base: str, taken: list[str]) -> str:
    """`base`, or "base 2", "base 3", ...: the first that is not in `taken`. The result is at
    most NAME_MAX_LENGTH characters (a panel name's limit): a long base is cut to make room."""
    base = base[:NAME_MAX_LENGTH].rstrip()
    if base not in taken:
        return base
    n = 2
    while True:
        suffix = f" {n}"
        name = base[: NAME_MAX_LENGTH - len(suffix)].rstrip() + suffix
        if name not in taken:
            return name
        n += 1


def new_panel_entry(user: dict, monitor: str, widget: str) -> dict[str, str]:
    """The keys a new panel of `widget` on `monitor` is written with (`user`: the user file's
    plain data): the first kind the widget supports, a name made from its title that is not
    used on that monitor yet ("Clock", "Clock 2", ...) and the widget; every other key comes
    from the widget's defaults. An unknown widget is written as an edge panel named after its
    id (the session's check rejects it with the shell's text)."""
    try:
        kind, title = supported_kinds(widget)[0], widget_title(widget)
    except KeyError:
        kind, title = "edge", widget
    _, panels = lookup(user, ("monitors", monitor, "panels"))
    taken = [p.get("name") for p in panels or () if isinstance(p, dict)]
    return {"panel": kind, "name": unique_name(title, taken), "widget": widget}


def monitor_names(config: Config, outputs: list[Output]) -> list[tuple[str, bool]]:
    """(name, connected) for every monitor in the config or connected now: connected ones
    first in kscreen order, then configured but disconnected ones by name."""
    connected = [o.name for o in outputs]
    rest = sorted(n for n in config.monitors if n not in connected)
    return [(n, True) for n in connected] + [(n, False) for n in rest]


def layout_preview(config: Config, name: str, width: int, height: int) -> list[str]:
    """The layout warnings the shell would report for this monitor (panels shrunk, moved or
    hidden; corner panels in a taken corner or shrunk to fit), from the same resolver.
    "content" panels count at their widget's default length (the shell measures them after
    building)."""
    theme = config.theme_for(name)
    return layout_monitor(
        requests_for(config, name),
        width,
        height,
        theme.thickness,
        theme.radius,
        config.layout_for(name).gap,
        where=f"monitors.{name}",
    ).warnings
