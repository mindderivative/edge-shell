"""Form description generated from the config models' JSON schema. Pure: no GTK, no tomlkit.

A form is a tree of SectionSpec (one per TOML table) holding FieldSpec (one per key). The GTK
renderer (settings.fields, settings.window) turns each FieldSpec into one row; everything a
row needs (kind, bounds, choices) is here, so it is tested without a display. The values shown
in the rows come from settings.values.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from shell.config.models import COLOR_FIELDS, CORNER_ONLY_KEYS, EDGE_ONLY_KEYS, Config

FieldKind = Literal["color", "int", "bool", "enum", "fonts", "length", "widget", "deprecated"]

# Keys holding a #rrggbb / #rrggbbaa colour. The models check them with a field validator,
# which the JSON schema does not show, so they are recognised by name (pinned by a test).
COLOR_KEYS = frozenset(COLOR_FIELDS) | {"color", "hover_color"}
LENGTH_PX = (60, 4000)  # shell.config.models.check_length
LENGTH_PERCENT = (1, 100)
LENGTH_MODES = ("px", "fill", "content", "percent")
# The unit or meaning shown next to a row, by (model, key): one key can mean different things
# in different tables ("width" of the border vs the width of a corner panel).
HINTS = {
    ("Theme", "thickness"): "px",
    ("Theme", "radius"): "px",
    ("Theme", "peek"): "px",
    ("Theme", "hover_zone"): "px",
    ("Theme", "duration_ms"): "ms",
    ("Border", "width"): "px",
    ("Shadow", "elevation"): "% (100 % = 48 px)",
    ("HandleStyle", "size"): "px along the edge",
    ("HandleStyle", "weight"): "px",
    ("HandleConfig", "size"): "px along the edge",
    ("HandleConfig", "weight"): "px",
    ("HandleConfig", "offset"): "px from the middle of the panel",
    ("LayoutSettings", "gap"): "px between neighbouring panels",
    ("PanelConfig", "offset"): "px from the aligned end",
    ("PanelConfig", "depth"): "px past the frame",
    ("PanelConfig", "min_length"): "px",
    ("PanelConfig", "max_length"): "px",
    ("PanelConfig", "pos"): "deprecated: reset it and use align and offset",
    ("PanelConfig", "width"): "px from the screen corner, frame included",
    ("PanelConfig", "height"): "px from the screen corner, frame included",
}
# Row labels; any other key reads "Some key" (pydantic's own titles read "Duration Ms").
LABELS = {
    "duration_ms": "Duration",
    "text_secondary": "Secondary text",
    "surface_hover": "Surface (hover)",
    "handle_hover": "Handle (hover)",
    "hover_color": "Hover colour",
    "color": "Colour",
    "min_length": "Minimum length",
    "max_length": "Maximum length",
    "pos": "Position (deprecated)",
}
MODE_HINTS = {
    "edge": "Edge Shell frame and panels",
    "plasma": "no Edge Shell here; Plasma's panels stay as they are",
    "both": "Edge Shell frame and panels next to Plasma's panel: keep Edge Shell panels off "
    "the edge Plasma's panel uses",
    "none": "no Edge Shell here (the same as plasma until the Plasma panel toggle exists)",
}
CORNER_ROWS = ("widget", "corner", "edge", "width", "height", "state")  # a corner panel's rows


@dataclass(frozen=True)
class FieldSpec:
    key: str  # the key inside its table
    label: str
    kind: FieldKind
    choices: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    hint: str = ""
    labels: tuple[str, ...] = ()  # what the choices show (empty: the choices themselves)


@dataclass(frozen=True)
class SectionSpec:
    key: str  # the table's key inside its parent ("" for the top of a form)
    label: str
    fields: tuple[FieldSpec, ...]
    sections: tuple[SectionSpec, ...] = ()

    def field(self, key: str) -> FieldSpec:
        return next(f for f in self.fields if f.key == key)

    def section(self, key: str) -> SectionSpec:
        return next(s for s in self.sections if s.key == key)


def _options(prop: dict) -> list[dict]:
    """The non-null alternatives of a property (an optional key is anyOf [..., null])."""
    return [o for o in prop.get("anyOf", [prop]) if o.get("type") != "null"]


def label_for(key: str) -> str:
    return LABELS.get(key, key.replace("_", " ").capitalize())


def widget_choices(
    widgets: tuple[str, ...], corner_widgets: tuple[str, ...] = ()
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(choices, labels) of a widget combo: edge widgets first, then the corner widgets,
    labelled as such (a new corner entry is just {"widget": NAME}; spec 19)."""
    edge = tuple(w for w in widgets if w not in corner_widgets)
    corner = tuple(w for w in widgets if w in corner_widgets)
    return edge + corner, edge + tuple(f"{w} (corner panel)" for w in corner)


def _field(
    model: str, key: str, prop: dict, widgets: tuple[str, ...], corner_widgets: tuple[str, ...]
) -> FieldSpec:
    first = _options(prop)[0]
    common = {"key": key, "label": label_for(key), "hint": HINTS.get((model, key), "")}
    if key == "widget":
        choices, labels = widget_choices(widgets, corner_widgets)
        return FieldSpec(kind="widget", choices=choices, labels=labels, **common)
    if key == "pos":
        return FieldSpec(kind="deprecated", **common)
    if key == "length":
        return FieldSpec(kind="length", minimum=LENGTH_PX[0], maximum=LENGTH_PX[1], **common)
    if key in COLOR_KEYS:
        return FieldSpec(kind="color", **common)
    if "enum" in first:
        return FieldSpec(kind="enum", choices=tuple(first["enum"]), **common)
    if first.get("type") == "boolean":
        return FieldSpec(kind="bool", **common)
    if first.get("type") == "integer":
        return FieldSpec(
            kind="int", minimum=first.get("minimum"), maximum=first.get("maximum"), **common
        )
    if key == "font" and first.get("type") == "array":
        return FieldSpec(kind="fonts", **common)
    raise ValueError(f"no form field for {key!r}: {prop}")


def section_for(
    schema: dict,
    name: str,
    key: str = "",
    label: str = "",
    widgets: tuple[str, ...] = (),
    skip: tuple[str, ...] = (),
    corner_widgets: tuple[str, ...] = (),
) -> SectionSpec:
    """The section for the model `name` in `schema["$defs"]`. Nested models become
    sub-sections; keys in `skip` are left out (the panel list has its own editor; a panel
    section leaves out the other kind's keys)."""
    model = schema["$defs"][name]
    fields: list[FieldSpec] = []
    sections: list[SectionSpec] = []
    for fkey, prop in model["properties"].items():
        if fkey in skip:
            continue
        ref = _options(prop)[0].get("$ref")
        if ref is not None:
            sub = ref.rsplit("/", 1)[-1]
            title = fkey.replace("_", " ").capitalize()
            sections.append(section_for(schema, sub, fkey, title, widgets))
        else:
            fields.append(_field(name, fkey, prop, widgets, corner_widgets))
    return SectionSpec(key, label or name, tuple(fields), tuple(sections))


@dataclass(frozen=True)
class ConfigForm:
    theme: SectionSpec  # [theme], also the per-monitor [monitors.NAME.theme] override
    layout: SectionSpec  # [layout], also [monitors.NAME.layout]
    monitor: SectionSpec  # [monitors.NAME] keys other than its tables: the shell mode
    edge_panel: SectionSpec  # a [[monitors.NAME.panels]] entry of an edge widget
    corner_panel: SectionSpec  # ... of a corner widget (spec 19)

    def panel_for(self, kind: str, corner: str | None = None) -> SectionSpec:
        """The section of a panel entry whose widget is of `kind` (registry.widget_kind:
        "edge" or "corner"). Given the `corner` in effect, a corner panel's edge row offers
        only that corner's two edges (corner.split("-"))."""
        if kind == "edge":
            return self.edge_panel
        if kind != "corner":
            raise ValueError(f"unknown panel kind {kind!r}")
        if corner is None:
            return self.corner_panel
        edges = tuple(corner.split("-"))
        fields = tuple(
            replace(f, choices=edges) if f.key == "edge" else f for f in self.corner_panel.fields
        )
        return replace(self.corner_panel, fields=fields)


def config_form(widgets: tuple[str, ...], corner_widgets: tuple[str, ...] = ()) -> ConfigForm:
    """Every section the settings window shows; `widgets` is registry.widget_names() and
    `corner_widgets` those whose registry.widget_kind is "corner".

    Per-monitor overrides use the base models (Theme, LayoutSettings), not ThemeOverride /
    LayoutOverride: those are built with create_model from the bare annotations and lose the
    bounds (their schema has no minimum / maximum). The two panel sections split PanelConfig
    by the models' own key sets: an edge panel skips CORNER_ONLY_KEYS, a corner panel skips
    EDGE_ONLY_KEYS (SHARED_KEYS are in both)."""
    schema = Config.model_json_schema()

    def panel(skip: tuple[str, ...]) -> SectionSpec:
        return section_for(schema, "PanelConfig", "", "Panel", widgets, skip, corner_widgets)

    corner = panel(EDGE_ONLY_KEYS)
    rows = tuple(sorted(corner.fields, key=lambda f: CORNER_ROWS.index(f.key)))
    return ConfigForm(
        theme=section_for(schema, "Theme", "theme", "Theme"),
        layout=section_for(schema, "LayoutSettings", "layout", "Layout"),
        monitor=section_for(
            schema, "MonitorConfig", "", "Monitor", skip=("theme", "layout", "panels")
        ),
        edge_panel=panel(CORNER_ONLY_KEYS),
        corner_panel=replace(corner, fields=rows),
    )


# ---- value conversions between the config and the editor widgets ------------------------


def rgba_to_hex(red: float, green: float, blue: float, alpha: float) -> str:
    """A colour chooser's 0..1 channels as #rrggbb, or #rrggbbaa when it is not opaque."""
    parts = [round(max(0.0, min(1.0, c)) * 255) for c in (red, green, blue, alpha)]
    text = "#" + "".join(f"{p:02x}" for p in parts[:3])
    return text if parts[3] == 255 else text + f"{parts[3]:02x}"


def split_length(value: int | str) -> tuple[str, float | None]:
    """A panel length as (mode, number): 300 -> ("px", 300), "fill" -> ("fill", None),
    "content" -> ("content", None), "12.5%" -> ("percent", 12.5)."""
    if isinstance(value, int):
        return "px", float(value)
    if value in ("fill", "content"):
        return value, None
    if value.endswith("%"):
        return "percent", float(value[:-1])
    raise ValueError(f"not a panel length: {value!r}")


def join_length(mode: str, number: float | None) -> int | str:
    """The inverse of split_length; the number is ignored for fill and content."""
    if mode == "px":
        return int(round(number or 0))
    if mode in ("fill", "content"):
        return mode
    if mode == "percent":
        text = f"{number:.1f}".rstrip("0").rstrip(".")
        return f"{text}%"
    raise ValueError(f"unknown length mode {mode!r}")


def parse_fonts(text: str) -> list[str]:
    """'Hack Nerd Font Mono, monospace' -> ['Hack Nerd Font Mono', 'monospace']."""
    return [name.strip() for name in text.split(",") if name.strip()]


def format_fonts(fonts: list[str]) -> str:
    return ", ".join(fonts)
