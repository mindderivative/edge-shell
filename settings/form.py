"""Form description generated from the config models' JSON schema. Pure: no GTK, no tomlkit.

A form is a tree of SectionSpec (one per TOML table) holding FieldSpec (one per key). The GTK
renderer (settings.fields, settings.window) turns each FieldSpec into one row; everything a
row needs (kind, bounds, choices) is here, so it is tested without a display. The values shown
in the rows come from settings.values.

Widget properties (panel/widget spec 3.4) are not in Config's schema: PanelConfig collects them
in a plain `widget_props` dict, so the schema cannot say which keys a widget has. The form
reads each widget's own property model instead (WidgetChoice.props, from the registry) and
walks its schema the same way: ConfigForm.widget_props(widget_id).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Literal

from pydantic import BaseModel

from shell.config.models import (
    COLOR_FIELDS,
    CORNER_ONLY_KEYS,
    EDGE_ONLY_KEYS,
    PANEL_KINDS,
    Config,
)

FieldKind = Literal[
    "color", "int", "bool", "enum", "fonts", "font", "length", "widget", "deprecated", "text"
]

# Keys holding a #rrggbb / #rrggbbaa colour. The models check them with a field validator,
# which the JSON schema does not show, so they are recognised by name (pinned by a test).
COLOR_KEYS = frozenset(COLOR_FIELDS) | {"color", "hover_color"}
LENGTH_PX = (60, 4000)  # shell.config.models.check_length
LENGTH_PERCENT = (1, 100)
LENGTH_MODES = ("px", "fill", "content", "percent")
# The unit or meaning shown next to a row, by (model, key): one key can mean different things
# in different tables ("width" of the border vs the width of a corner panel). A widget
# property's hint is its Field(json_schema_extra={"hint": ...}). The label's tooltip is the
# field's Field(description=...) in every model: one short sentence, and a test fails for a
# field of any model (widgets' included) that has none.
HINTS = {
    ("Theme", "thickness"): "px",
    ("Theme", "radius"): "px",
    ("Theme", "peek"): "px",
    ("Theme", "hover_zone"): "px",
    ("Theme", "duration_ms"): "ms",
    ("Theme", "fade_ms"): "ms; 0 turns the fade off",
    ("Border", "width"): "px",
    ("Shadow", "elevation"): "% (100 % = 48 px)",
    ("HandleStyle", "size"): "px along the edge",
    ("HandleStyle", "weight"): "px",
    ("HandleConfig", "size"): "px along the edge",
    ("HandleConfig", "weight"): "px",
    ("HandleConfig", "offset"): "px from the middle of the panel",
    ("LayoutSettings", "gap"): "px between neighbouring panels",
    ("PanelConfig", "name"): "unique on this monitor; shown in logs, notifications and here",
    ("PanelConfig", "panel"): "the panel type (float panels are coming later)",
    ("PanelConfig", "offset"): "px from the aligned end",
    ("PanelConfig", "depth"): "px past the frame",
    ("PanelConfig", "min_length"): "px",
    ("PanelConfig", "max_length"): "px",
    ("PanelConfig", "order"): "within its align slot; equal orders keep the config order",
    ("PanelConfig", "pos"): "deprecated: reset it and use align and offset",
    ("PanelConfig", "width"): "px from the screen corner, frame included",
    ("PanelConfig", "height"): "px from the screen corner, frame included",
}
# Row labels; any other key reads "Some key" (pydantic's own titles read "Duration Ms").
LABELS = {
    "duration_ms": "Duration",
    "fade_ms": "Fade",
    "text_secondary": "Secondary text",
    "surface_hover": "Surface (hover)",
    "handle_hover": "Handle (hover)",
    "hover_color": "Hover colour",
    "color": "Colour",
    "min_length": "Minimum length",
    "max_length": "Maximum length",
    "pos": "Position (deprecated)",
    "shell": "Mode",
    "panel": "Panel type",
}
MODE_HINTS = {
    "edge": "Edge Shell frame and panels",
    "plasma": "no Edge Shell here; Plasma's panels stay as they are",
    "both": "Edge Shell frame and panels next to Plasma's panel: keep Edge Shell panels off "
    "the edge Plasma's panel uses",
    "none": "no Edge Shell here (the same as plasma until the Plasma panel toggle exists)",
}
KIND_LABELS = {"edge": "Edge", "corner": "Corner", "float": "Float (coming soon)"}
LEAD_ROWS = ("name", "widget", "panel")  # every panel section starts with these
# A whole number with both bounds gets a slider (Phil: "If a numeric has a minimum and maximum
# use sliders instead of number spinners") when its range is at most this wide: on a 160 px
# slider that is at most 3 values per pixel (the fade, 0-500 ms, is the widest slider). Wider
# ranges (an offset of +-20000, a corner width of 60-4000 px, a duration of 0-5000 ms, a depth
# of 16-2000 px, an order of 0-1000) keep the spin button, whose arrows step by one.
SLIDER_MAX_SPAN = 500
CORNER_ROWS = (*LEAD_ROWS, "corner", "edge", "width", "height", "state")  # a corner panel


@dataclass(frozen=True)
class FieldSpec:
    key: str  # the key inside its table
    label: str
    kind: FieldKind
    choices: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    hint: str = ""
    tooltip: str = ""  # the label's tooltip: the model field's description (one sentence)
    labels: tuple[str, ...] = ()  # what the choices show (empty: the choices themselves)
    disabled: tuple[str, ...] = ()  # choices shown but not selectable ("coming soon")
    required: bool = False  # the entry needs it: no reset button
    max_length: int | None = None  # a text row: the most characters the entry takes


def uses_slider(spec: FieldSpec) -> bool:
    """True when the row of `spec` is a slider: an int with both bounds and a range of at most
    SLIDER_MAX_SPAN."""
    if spec.kind != "int" or spec.minimum is None or spec.maximum is None:
        return False
    return spec.maximum - spec.minimum <= SLIDER_MAX_SPAN


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


@dataclass(frozen=True)
class WidgetChoice:
    """A registered widget as the form needs it (settings.view builds them from the registry:
    registry_widgets)."""

    id: str
    title: str = ""  # "" = the id
    kinds: tuple[str, ...] = ("edge",)  # the panel kinds it can be shown in
    props: type[BaseModel] | None = None  # its property model (None: no properties)

    @property
    def label(self) -> str:
        return self.title or self.id


def registry_widgets() -> tuple[WidgetChoice, ...]:
    """Every registered widget (shell.registry), for config_form."""
    from shell import registry

    return tuple(
        WidgetChoice(
            name,
            registry.widget_title(name),
            registry.supported_kinds(name),
            registry.widget_props_model(name),
        )
        for name in registry.widget_names()
    )


def _options(prop: dict) -> list[dict]:
    """The non-null alternatives of a property (an optional key is anyOf [..., null])."""
    return [o for o in prop.get("anyOf", [prop]) if o.get("type") != "null"]


def label_for(key: str) -> str:
    return LABELS.get(key, key.replace("_", " ").capitalize())


def widget_choices(widgets: tuple[WidgetChoice, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(ids, labels) of a widget combo: by display name (the registry's title)."""
    ordered = sorted(widgets, key=lambda w: (w.label.casefold(), w.id))
    return tuple(w.id for w in ordered), tuple(w.label for w in ordered)


def _field(
    model: str,
    key: str,
    prop: dict,
    widgets: tuple[WidgetChoice, ...],
    required: bool = False,
    text: bool = False,
) -> FieldSpec:
    """One row. `text` (a widget's properties): the row comes from the type alone, and any
    plain string is a text row. In the config models some keys are known by name (widget,
    panel, pos, length, the colours) and only `name` is a text row: every other string key
    must be classified here (pinned by a test)."""
    first = _options(prop)[0]
    hint = HINTS.get((model, key), prop.get("hint", ""))
    common = {
        "key": key,
        "label": label_for(key),
        "hint": hint,
        "tooltip": prop.get("description", ""),
        "required": required,
    }
    if not text:
        if key == "widget":
            choices, labels = widget_choices(widgets)
            return FieldSpec(kind="widget", choices=choices, labels=labels, **common)
        if key == "panel":
            labels = tuple(KIND_LABELS[k] for k in PANEL_KINDS)
            return FieldSpec(kind="enum", choices=PANEL_KINDS, labels=labels, **common)
        if key == "pos":
            return FieldSpec(kind="deprecated", **common)
        if key == "length":
            return FieldSpec(kind="length", minimum=LENGTH_PX[0], maximum=LENGTH_PX[1], **common)
        if key in COLOR_KEYS:
            return FieldSpec(kind="color", **common)
    if text and len(_options(prop)) != 1:
        raise ValueError(f"no form field for {key!r}: one type (or that type | None) only")
    if "enum" in first or "const" in first:  # a one-value Literal is a const, not an enum
        values = first["enum"] if "enum" in first else [first["const"]]
        if text and not all(isinstance(v, str) for v in values):
            raise ValueError(f"no form field for {key!r}: a Literal of strings only")
        return FieldSpec(kind="enum", choices=tuple(values), **common)
    if first.get("type") == "boolean":
        return FieldSpec(kind="bool", **common)
    if first.get("type") == "integer":
        low, high = first.get("minimum"), first.get("maximum")
        if "exclusiveMinimum" in first:  # gt / lt: the next whole number inside
            low = first["exclusiveMinimum"] + 1
        if "exclusiveMaximum" in first:
            high = first["exclusiveMaximum"] - 1
        return FieldSpec(kind="int", minimum=low, maximum=high, **common)
    if not text and key == "font" and first.get("type") == "array":
        return FieldSpec(kind="fonts", **common)
    if text and key == "font" and first.get("type") == "string":
        return FieldSpec(kind="font", **common)  # a widget's font: one family, unset = theme
    if first.get("type") == "string" and (text or key == "name"):
        return FieldSpec(kind="text", max_length=first.get("maxLength"), **common)
    raise ValueError(f"no form field for {key!r}: {prop}")


def section_for(
    schema: dict,
    name: str,
    key: str = "",
    label: str = "",
    widgets: tuple[WidgetChoice, ...] = (),
    skip: tuple[str, ...] = (),
    text: bool = False,
    required: tuple[str, ...] = (),
) -> SectionSpec:
    """The section for the model `name` in `schema["$defs"]`. Nested models become
    sub-sections; keys in `skip` are left out (the panel list is edited in the tree and the
    toolbar; a panel section leaves out the other kind's keys); keys in `required` get no
    reset button (a panel entry's panel, name and widget: the file must have them, while a
    theme key the model requires comes from the defaults file)."""
    model = schema["$defs"][name]
    fields: list[FieldSpec] = []
    sections: list[SectionSpec] = []
    for fkey, prop in model["properties"].items():
        if fkey in skip:
            continue
        ref = _options(prop)[0].get("$ref")
        if ref is not None:
            if text:  # a widget property is one row, never a table
                raise ValueError(f"no form field for {fkey!r}: a nested model")
            sub = ref.rsplit("/", 1)[-1]
            title = fkey.replace("_", " ").capitalize()
            sections.append(section_for(schema, sub, fkey, title, widgets, text=text))
        else:
            fields.append(_field(name, fkey, prop, widgets, fkey in required, text))
    return SectionSpec(key, label or name, tuple(fields), tuple(sections))


def props_section(model: type[BaseModel]) -> SectionSpec | None:
    """The "Widget" section of a widget's property model: one row per property (keys of the
    panel entry itself, so the section key is ""); None when it has no properties."""
    schema = model.model_json_schema()
    if not schema.get("properties"):
        return None
    defs = {**schema.get("$defs", {}), model.__name__: schema}
    return section_for({"$defs": defs}, model.__name__, "", "Widget", text=True)


def _ranked(section: SectionSpec, order: tuple[str, ...]) -> SectionSpec:
    rank = {k: i for i, k in enumerate(order)}
    rows = sorted(section.fields, key=lambda f: rank.get(f.key, len(order)))
    return replace(section, fields=tuple(rows))


@dataclass(frozen=True)
class ConfigForm:
    theme: SectionSpec  # [theme], also the per-monitor [monitors.NAME.theme] override
    layout: SectionSpec  # [layout], also [monitors.NAME.layout]
    monitor: SectionSpec  # [monitors.NAME] keys other than its tables: the shell mode
    edge_panel: SectionSpec  # a [[monitors.NAME.panels]] entry of an edge panel
    corner_panel: SectionSpec  # ... of a corner panel (spec 19)
    # widget id -> its "Widget" section (only widgets that have properties)
    widget_sections: dict[str, SectionSpec] = field(default_factory=dict)

    def panel_for(
        self, kind: str, corner: str | None = None, kinds: tuple[str, ...] = ()
    ) -> SectionSpec:
        """The section of a panel entry of `kind` (its `panel` key: "edge" or "corner").
        Given the `corner` in effect, a corner panel's edge row offers only that corner's two
        edges (corner.split("-")). `kinds`: the kinds the entry's widget supports; with more
        than one the "Panel type" row is shown, the kinds it does not support (and float)
        greyed out; with one it is left out."""
        if kind == "edge":
            section = self.edge_panel
        elif kind == "corner":
            section = self.corner_panel
        else:
            raise ValueError(f"unknown panel kind {kind!r}")
        fields = []
        for f in section.fields:
            if f.key == "panel":
                if len(kinds) < 2:
                    continue
                f = replace(f, disabled=tuple(k for k in f.choices if k not in kinds))
            if f.key == "edge" and kind == "corner" and corner is not None:
                f = replace(f, choices=tuple(corner.split("-")))
            fields.append(f)
        return replace(section, fields=tuple(fields))

    def widget_props(self, widget_id: str) -> SectionSpec | None:
        """The "Widget" section of a widget's properties; None when it has none (or is not
        known)."""
        return self.widget_sections.get(widget_id)


def config_form(widgets: tuple[WidgetChoice, ...] = ()) -> ConfigForm:
    """Every section the settings window shows; `widgets`: the registered widgets
    (registry_widgets()).

    Per-monitor overrides use the base models (Theme, LayoutSettings), not ThemeOverride /
    LayoutOverride: those are built with create_model from the bare annotations and lose the
    bounds (their schema has no minimum / maximum). The two panel sections split PanelConfig
    by the models' own key sets: an edge panel skips CORNER_ONLY_KEYS, a corner panel skips
    EDGE_ONLY_KEYS (SHARED_KEYS are in both); `widget_props` is the widget keys' bag, shown
    per widget (widget_props(widget_id))."""
    schema = Config.model_json_schema()

    required = tuple(schema["$defs"]["PanelConfig"]["required"])  # panel, name, widget

    def panel(skip: tuple[str, ...]) -> SectionSpec:
        skip += ("widget_props",)
        return section_for(schema, "PanelConfig", "", "Panel", widgets, skip, required=required)

    sections = {}
    for w in widgets:
        section = None if w.props is None else props_section(w.props)
        if section is not None:
            sections[w.id] = section
    return ConfigForm(
        theme=section_for(schema, "Theme", "theme", "Theme"),
        layout=section_for(schema, "LayoutSettings", "layout", "Layout"),
        monitor=section_for(
            schema, "MonitorConfig", "", "Monitor", skip=("theme", "layout", "panels")
        ),
        edge_panel=_ranked(panel(CORNER_ONLY_KEYS), LEAD_ROWS),
        corner_panel=_ranked(panel(EDGE_ONLY_KEYS), CORNER_ROWS),
        widget_sections=sections,
    )


# ---- tabs: which rows each page shows on which tab (panel/widget spec 7) ------------------
# The Theme page and every monitor page have these tabs; [layout] is the Layout tab, and every
# [theme] key or table goes on the tab THEME_TAB_OF names, any other one (a key added to the
# model later included) on General.
THEME_TABS = ("General", "Borders", "Shadows", "Handle", "Layout")
THEME_TAB_OF = {
    "border": "Borders",
    "shadow": "Shadows",
    "handle": "Handle",  # the handle colour
    "handle_hover": "Handle",
    "handle_style": "Handle",
}
# A panel page's tabs; every key of the entry goes on the tab PANEL_TAB_OF names, any other
# one (edge, align, length, corner, width, ... and a key added later) on Position. Widget is
# the widget's own properties, absent when it has none.
PANEL_TABS = ("Panel", "Position", "Handle", "Interaction", "Widget")
PANEL_TAB_OF = {
    "name": "Panel",
    "widget": "Panel",
    "panel": "Panel",
    "handle": "Handle",
    "interaction": "Interaction",
    "state": "Interaction",
}

Part = tuple[tuple[str, ...], SectionSpec]


@dataclass(frozen=True)
class TabSpec:
    """One tab of a page: its title and its parts. A part is a section shown at a key path
    relative to the page's own (the Theme page: (); a monitor page: ("monitors", NAME); a panel
    page: ("monitors", NAME, "panels", i)); a sub-table's part shows its rows flat."""

    title: str
    parts: tuple[Part, ...]


def _parts(
    section: SectionSpec, key: tuple[str, ...], tab_of: dict[str, str], title: str, default: str
) -> tuple[Part, ...]:
    """The parts of `section` (at `key`) on the tab `title`: its own rows on that tab in one
    part, then each of its sub-tables on that tab as a part of its own."""
    rows = tuple(f for f in section.fields if tab_of.get(f.key, default) == title)
    parts: list[Part] = [(key, replace(section, fields=rows, sections=()))] if rows else []
    for sub in section.sections:
        if tab_of.get(sub.key, default) == title:
            parts.append(((*key, sub.key), sub))
    return tuple(parts)


def theme_tabs(form: ConfigForm) -> tuple[TabSpec, ...]:
    """The tabs of the Theme page (a monitor page shows the same at its own prefix)."""
    tabs = [
        TabSpec(title, _parts(form.theme, ("theme",), THEME_TAB_OF, title, "General"))
        for title in THEME_TABS[:-1]
    ]
    tabs.append(TabSpec("Layout", ((("layout",), form.layout),)))
    return tuple(t for t in tabs if t.parts)


def panel_tabs(section: SectionSpec, props: SectionSpec | None = None) -> tuple[TabSpec, ...]:
    """The tabs of a panel page: `section` is the entry's rows (ConfigForm.panel_for), `props`
    its widget's "Widget" section (ConfigForm.widget_props; None: no Widget tab)."""
    tabs = [
        TabSpec(title, _parts(section, (), PANEL_TAB_OF, title, "Position"))
        for title in PANEL_TABS[:-1]
    ]
    if props is not None:
        tabs.append(TabSpec("Widget", (((), props),)))
    return tuple(t for t in tabs if t.parts)


# ---- the toolbar's panel type list ---------------------------------------------------------
KIND_NOUNS = {"edge": "edge panel", "corner": "corner panel"}
FLOAT_CHOICE = "float"


@dataclass(frozen=True)
class AddChoice:
    id: str  # "edge:clock" (kind:widget), or FLOAT_CHOICE
    label: str  # "Clock (edge panel)"
    kind: str
    widget: str | None  # None: the float entry (nothing to add yet)
    enabled: bool = True


def add_choices(widgets: tuple[WidgetChoice, ...]) -> tuple[AddChoice, ...]:
    """The panel types the toolbar can add: one per widget and panel kind it can be shown in,
    by display name ("Clock (edge panel)", "Summary (corner panel)"; two widgets with one title
    add their id: "Clock (clock, edge panel)"), edge panels first, each kind sorted by display
    name without case; then "Float panel (coming soon)", listed and disabled (spec
    3.3: float panels are reserved)."""
    ordered = sorted(widgets, key=lambda w: (w.label.casefold(), w.id))
    titles = Counter(w.label for w in ordered)

    def label(w: WidgetChoice, noun: str) -> str:
        # widgets that share a title are told apart by their id: "Clock (clock, edge panel)"
        return f"{w.label} ({w.id}, {noun})" if titles[w.label] > 1 else f"{w.label} ({noun})"

    choices = [
        AddChoice(f"{kind}:{w.id}", label(w, noun), kind, w.id)
        for kind, noun in KIND_NOUNS.items()
        for w in ordered
        if kind in w.kinds
    ]
    choices.append(AddChoice(FLOAT_CHOICE, "Float panel (coming soon)", "float", None, False))
    return tuple(choices)


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
