"""Pydantic models for the Edge Shell config. Pure: no GTK imports."""

from __future__ import annotations

import re
import unicodedata
from typing import Annotated, Any, Literal, get_args

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    ValidationError,
    create_model,
    field_validator,
    model_validator,
)

Edge = Literal["top", "bottom", "left", "right"]
PanelState = Literal["collapsed", "extended"]
ShellMode = Literal["edge", "plasma", "both", "none"]
Align = Literal["start", "center", "end"]
Corner = Literal["top-left", "top-right", "bottom-left", "bottom-right"]
CORNERS: tuple[str, ...] = get_args(Corner)  # the settings window's choices

_HEX = re.compile(r"#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?")  # #rrggbb or #rrggbbaa
_FONT_FORBIDDEN = re.compile(r'["\\{};]')  # font names go unescaped into generated CSS
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")  # and a control character fails the CSS load
COLOR_FIELDS = (
    "frame",
    "text",
    "text_secondary",
    "accent",
    "handle",
    "handle_hover",
    "surface_hover",
)


class ConfigError(Exception):
    """A config problem; the message names the offending key path."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def check_font_name(name: str) -> str:
    """A font family name: it goes unescaped into generated CSS (the theme's font list, a
    widget's font property), so CSS metacharacters are refused."""
    if _CONTROL.search(name):
        raise ValueError(f"font name {name!r} must not contain a control character")
    if _FONT_FORBIDDEN.search(name):
        raise ValueError(
            f"font name {name!r} must not contain a double quote, backslash, {{, }} or ;"
        )
    return name


def check_hex(value: str) -> str:
    if not _HEX.fullmatch(value):
        raise ValueError("must be a #rrggbb or #rrggbbaa hex color")
    return value.lower()


def deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    """`over` on top of `base`; nested tables merge key by key, scalars and lists replace."""
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class Border(_Strict):
    """Border along the outside of the frame and panel outline (spec 18). Opt-in. It adds `width`
    px to the footprint; the frame thickness and panel depth are unchanged."""

    enabled: bool = Field(
        False, description="Draw a line along the outside of the frame and the panels."
    )
    width: Annotated[
        int,
        Field(
            ge=1,
            le=16,
            description="Width of the border line in px; it adds to the frame's footprint.",
        ),
    ] = 2
    color: str = Field(
        "#8fd3b6ff",
        description="Colour of the border: #rrggbb, or #rrggbbaa for a see-through line.",
    )

    @field_validator("color")
    @classmethod
    def _hex(cls, value: str) -> str:
        return check_hex(value)


class Shadow(_Strict):
    """Uniform shadow of the frame and panels (spec 18). Opt-in. `elevation` is 0-100 %."""

    enabled: bool = Field(
        False, description="Cast a soft shadow from the frame and the panels onto the desktop."
    )
    elevation: Annotated[
        int, Field(ge=0, le=100, description="How far the shadow reaches, in % (100 % is 48 px).")
    ] = 50
    color: str = Field(
        "#00000080", description="Colour of the shadow; its alpha (#rrggbbaa) sets how dark it is."
    )

    @field_validator("color")
    @classmethod
    def _hex(cls, value: str) -> str:
        return check_hex(value)


HandleShape = Literal["auto", "dots", "bar", "chevron", "none"]
HANDLE_SHAPES: tuple[str, ...] = get_args(HandleShape)  # the settings window's choices
HandleSize = Annotated[int, Field(ge=4, le=40)]  # px along the edge
HandleWeight = Annotated[int, Field(ge=1, le=8)]  # px: dot diameter, bar and chevron stroke
HandleOffset = Annotated[int, Field(ge=-2000, le=2000)]  # px from the body centre


class HandleStyle(_Strict):
    """The handle look of every panel whose entry (or widget) does not say otherwise (spec 15).
    "auto" picks the shape from the panel's interactions (shell.handle.auto_shape). The colours
    are the theme's `handle` and `handle_hover` tokens."""

    shape: HandleShape = Field(
        "auto",
        description=(
            "The handle's look: auto picks one from the panel's "
            "interactions, or dots, bar, chevron, none."
        ),
    )
    size: HandleSize = Field(15, description="Length of the handle along the edge, in px.")
    weight: HandleWeight = Field(
        3, description="Thickness in px of the dots, the bar or the chevron's stroke."
    )


class Theme(_Strict):
    frame: str = Field(description="Colour of the frame and of the panels that grow out of it.")
    text: str = Field(description="Colour of the text in panels.")
    text_secondary: str = Field(
        description=(
            "Colour of the dimmer text in panels, such as the date and the CPU and RAM lines."
        )
    )
    accent: str = Field(
        description=(
            "Highlight colour for items marked active (the built-in widgets do not use it yet)."
        )
    )
    handle: str = Field(description="Colour of a panel's handle.")
    handle_hover: str = Field(description="Colour of a panel's handle while the pointer is on it.")
    surface_hover: str = Field(
        description="Background colour of a dock icon while the pointer is on it."
    )
    thickness: Annotated[
        int, Field(ge=5, le=64, description="Width of the frame around the screen, in px.")
    ]
    radius: Annotated[
        int,
        Field(
            ge=1,
            le=64,
            description=(
                "Radius in px of the rounded screen corners and of "
                "the curves where panels meet the frame."
            ),
        ),
    ]
    peek: Annotated[
        int,
        Field(
            ge=1,
            le=64,
            description="How far in px a collapsed panel slides out when the pointer rests on it.",
        ),
    ]
    hover_zone: Annotated[
        int,
        Field(
            ge=1,
            le=64,
            description=(
                "Width in px of the invisible strip past the frame "
                "where the pointer wakes a collapsed panel."
            ),
        ),
    ]
    duration_ms: Annotated[
        int,
        Field(ge=0, le=5000, description="Time in ms a panel takes to slide open or closed."),
    ]
    # The fade in and out of a monitor's windows (spec 21); 0 = none. At most 500, so the
    # settings window shows a slider (settings.form.SLIDER_MAX_SPAN).
    fade_ms: Annotated[
        int,
        Field(
            ge=0,
            le=500,
            description=(
                "Time in ms a monitor's frame and panels fade in or out; 0 turns the fade off."
            ),
        ),
    ] = 50
    font: Annotated[
        list[str],
        Field(
            min_length=1,
            description=(
                "Font families for panel text, tried in order; the first installed one is used."
            ),
        ),
    ]
    border: Border = Field(default_factory=Border)
    shadow: Shadow = Field(default_factory=Shadow)
    handle_style: HandleStyle = Field(default_factory=HandleStyle)

    @field_validator(*COLOR_FIELDS)
    @classmethod
    def _hex(cls, value: str) -> str:
        return check_hex(value)

    @field_validator("font")
    @classmethod
    def _font_names(cls, value: list[str]) -> list[str]:
        for name in value:
            if not name.strip():
                raise ValueError("font names must not be empty")
            check_font_name(name)
        return value


def _override_of(name: str, model: type[BaseModel], nested: dict[str, type] | None = None):
    """Same fields as `model`, all optional (None = not set). Nested tables use the override
    model given in `nested`, so a partial `[monitors.X.theme.shadow]` table stays partial."""
    nested = nested or {}
    fields = {
        fname: (nested.get(fname, field.annotation) | None, None)
        for fname, field in model.model_fields.items()
    }
    return create_model(name, __base__=_Strict, **fields)


BorderOverride = _override_of("BorderOverride", Border)
ShadowOverride = _override_of("ShadowOverride", Shadow)
HandleStyleOverride = _override_of("HandleStyleOverride", HandleStyle)
# Merged over the base theme (deep_merge) and re-validated by Theme.
ThemeOverride = _override_of(
    "ThemeOverride",
    Theme,
    {"border": BorderOverride, "shadow": ShadowOverride, "handle_style": HandleStyleOverride},
)

Length = Annotated[int, Field(ge=60, le=4000)]
Depth = Annotated[int, Field(ge=16, le=2000)]
Offset = Annotated[int, Field(ge=0, le=20000)]
SignedOffset = Annotated[int, Field(ge=-20000, le=20000)]
Order = Annotated[int, Field(ge=0, le=1000)]
_PERCENT = re.compile(r"[0-9]{1,3}(\.[0-9]+)?%")


def check_length(value: int | str) -> int | str:
    """A panel length: px (60-4000), "fill" (the free span the neighbours leave), "content"
    (the widget's natural size) or a percentage of the free span such as "50%" (spec 17)."""
    if isinstance(value, int) and not isinstance(value, bool) and 60 <= value <= 4000:
        return value
    if value in ("fill", "content"):
        return value
    if isinstance(value, str) and _PERCENT.fullmatch(value) and 1 <= float(value[:-1]) <= 100:
        return value
    raise ValueError(
        'must be a length in px (60-4000), "fill", "content" or a percentage from "1%" to "100%"'
    )


class LayoutSettings(_Strict):
    """Per-monitor layout settings (spec 16). `gap` is the straight frame left between two
    neighbouring panels' joins on one edge, ON TOP of the joins (r1 + r2), so any value keeps
    the minimum gap the outline needs."""

    gap: Annotated[
        int,
        Field(
            ge=0,
            le=400,
            description=(
                "Extra px of frame between neighbouring panels on "
                "one edge, beyond their curved joins."
            ),
        ),
    ] = 8


LayoutOverride = _override_of("LayoutOverride", LayoutSettings)


class HandleConfig(_Strict):
    """A panel's own handle (spec 15). Every key is optional: a missing one comes from the
    widget's default, then the theme ([theme.handle_style]; colours: the theme's handle and
    handle_hover). `offset` moves the handle along the edge from the body centre (negative:
    towards the start of the edge, left or top); it is clamped to the body."""

    shape: HandleShape | None = Field(
        None, description="This panel's handle look; unset takes the widget's, then the theme's."
    )
    size: HandleSize | None = Field(
        None,
        description="Length of this panel's handle along the edge, in px; unset takes the theme's.",
    )
    weight: HandleWeight | None = Field(
        None, description="Thickness in px of this panel's handle strokes; unset takes the theme's."
    )
    offset: HandleOffset | None = Field(
        None,
        description=(
            "Moves the handle along the edge from the panel's "
            "centre, in px; negative goes towards the start."
        ),
    )
    color: str | None = Field(
        None, description="This panel's handle colour; unset takes the theme's handle colour."
    )
    hover_color: str | None = Field(
        None,
        description=(
            "This panel's handle colour under the pointer; unset takes the theme's hover colour."
        ),
    )

    @field_validator("color", "hover_color")
    @classmethod
    def _hex(cls, value: str | None) -> str | None:
        return None if value is None else check_hex(value)


class InteractionConfig(_Strict):
    """Which interactions open and close a panel (spec 15). A missing key comes from the
    widget's default, else true. Keyboard activation follows `click`."""

    click: StrictBool | None = Field(
        None,
        description=(
            "Whether clicking the handle (or pressing Enter on it) opens or closes the panel."
        ),
    )
    hover: StrictBool | None = Field(
        None, description="Whether resting the pointer on a collapsed panel makes it peek out."
    )
    drag: StrictBool | None = Field(
        None,
        description=(
            "Whether dragging the handle opens or closes the panel; it snaps at the halfway point."
        ),
    )


# The panel keys by kind (spec 19; the settings window reads them): both kinds take
# SHARED_KEYS; an entry mixing EDGE_ONLY_KEYS with CORNER_ONLY_KEYS is rejected. Every other
# key of an entry is a widget key: PanelConfig collects it in `widget_props`.
SHARED_KEYS = ("panel", "name", "widget", "edge", "state", "handle", "interaction")
EDGE_ONLY_KEYS = ("pos", "align", "offset", "order", "length", "min_length", "max_length", "depth")
CORNER_ONLY_KEYS = ("corner", "width", "height")
FRAMEWORK_KEYS = frozenset((*SHARED_KEYS, *EDGE_ONLY_KEYS, *CORNER_ONLY_KEYS))
PanelKind = Literal["edge", "corner", "float"]  # float: reserved, the registry rejects it
PANEL_KINDS: tuple[str, ...] = get_args(PanelKind)  # the settings window's choices
NAME_MAX_LENGTH = 40
PanelName = Annotated[str, Field(min_length=1, max_length=NAME_MAX_LENGTH)]


_BIDI_CONTROLS = frozenset(chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A)))


def check_text_characters(value: str) -> str:
    """The character rules for text that is shown as one line (a panel's name, the clock's
    format): no control characters, line or paragraph separators, bidirectional overrides,
    and no invisible format character at either end."""
    if any(unicodedata.category(c) == "Cc" for c in value):
        raise ValueError("must not contain control characters (tab, newline, ...)")
    if any(unicodedata.category(c) in ("Zl", "Zp") for c in value):
        raise ValueError("must not contain a line or paragraph separator (U+2028, U+2029)")
    if any(c in _BIDI_CONTROLS for c in value):
        raise ValueError(
            "must not contain bidirectional control characters (U+202A-202E, U+2066-2069)"
        )
    if value and any(unicodedata.category(c) == "Cf" for c in (value[0], value[-1])):
        raise ValueError(
            "must not start or end with an invisible format character (zero-width space, BOM, ...)"
        )
    return value


def check_panel_name(value: str) -> str:
    """A panel's name: its label in logs, notifications and the settings window."""
    check_text_characters(value)
    if value != value.strip():
        raise ValueError("must not start or end with whitespace (a space, a no-break space, ...)")
    return value


class PanelConfig(_Strict):
    """One panel entry. `panel` is its kind: edge panels use edge / align / offset / order /
    length / depth; corner panels (spec 19) use corner / edge (the edge they open from) /
    width / height. Every key that is not in FRAMEWORK_KEYS is a widget key: it is collected
    in `widget_props` and checked against the widget's property model by
    shell.registry.validate_widgets, which also checks the kind keys against `panel`; an entry
    that mixes the two kinds' keys is rejected here already.

    The widget bag is built from file data only: dump-then-validate is not idempotent, because
    a dumped `widget_props` would nest as a widget key of the next entry. The model is frozen
    but the bag is a mutable, unhashable dict; requests that travel carry a frozen WidgetProps
    instead."""

    panel: PanelKind = Field(
        description=(
            "The kind of panel: edge (a strip on a screen edge) or corner (a block in a corner)."
        )
    )
    name: PanelName = Field(
        description=(
            "The panel's name in logs, notifications and this window; unique on the monitor."
        )
    )
    widget: str = Field(description="Which widget the panel shows (its content).")
    edge: Edge | None = Field(
        None,
        description=(
            "An edge panel: the screen edge it sits on. A corner panel: the edge it opens out from."
        ),
    )
    pos: Offset | Literal["center"] | None = Field(  # deprecated: align + offset
        None, description="Deprecated: px from the start of the edge. Use align and offset instead."
    )
    align: Align | None = Field(
        None,
        description="Where the panel sits along its edge: at the start, the centre or the end.",
    )
    offset: SignedOffset | None = Field(
        None,
        description=(
            "Shifts the panel along the edge from its aligned "
            "end, in px; negative only when centred."
        ),
    )
    order: Order | None = Field(
        None,
        description=(
            "Orders panels sharing one align slot: lower comes "
            "first, equal ones keep the file order."
        ),
    )
    length: int | str | None = Field(
        None,
        description=(
            "Size along the edge: px, fill (the free space), content "
            "(the widget's size) or a percent such as 50%."
        ),
    )
    min_length: Length | None = Field(
        None,
        description="The panel never gets shorter than this many px, whatever its length setting.",
    )
    max_length: Length | None = Field(
        None,
        description="The panel never gets longer than this many px, whatever its length setting.",
    )
    depth: Depth | None = Field(
        None, description="How far the open panel reaches past the frame, in px."
    )
    state: PanelState | None = Field(
        None, description="Whether the panel starts collapsed (only its handle) or extended (open)."
    )
    handle: HandleConfig = Field(default_factory=HandleConfig)
    interaction: InteractionConfig = Field(default_factory=InteractionConfig)
    corner: Corner | None = Field(None, description="Which screen corner the panel sits in.")
    width: Length | None = Field(  # px from the screen corner, both frame bands included
        None, description="Width of the corner panel in px, counted from the screen corner."
    )
    height: Length | None = Field(
        None, description="Height of the corner panel in px, counted from the screen corner."
    )
    widget_props: dict[str, Any] = Field(default_factory=dict)  # never a key in the file

    @model_validator(mode="before")
    @classmethod
    def _collect_widget_keys(cls, data: Any) -> Any:
        """Every key that is not a framework key goes to `widget_props`, a key that is itself
        called "widget_props" too (in the file it can only be a widget key)."""
        if not isinstance(data, dict):
            return data
        own = {k: v for k, v in data.items() if k in FRAMEWORK_KEYS}
        return {**own, "widget_props": {k: v for k, v in data.items() if k not in FRAMEWORK_KEYS}}

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return check_panel_name(value)

    @field_validator("length")
    @classmethod
    def _length(cls, value: int | str | None) -> int | str | None:
        return None if value is None else check_length(value)

    @model_validator(mode="after")
    def _placement(self) -> PanelConfig:
        corner_keys = [k for k in CORNER_ONLY_KEYS if getattr(self, k) is not None]
        edge_keys = [k for k in EDGE_ONLY_KEYS if getattr(self, k) is not None]
        if corner_keys and edge_keys:
            raise ValueError(
                f"{', '.join(edge_keys)} cannot be combined with {', '.join(corner_keys)}: a "
                "corner panel takes corner, edge, width and height; an edge panel takes edge, "
                "align, offset, order, length, min_length, max_length and depth"
            )
        if self.corner is not None and self.edge is not None:
            if self.edge not in self.corner.split("-"):
                first, second = self.corner.split("-")
                raise ValueError(
                    f"edge {self.edge!r} is not an edge of the {self.corner} corner "
                    f"(use {first} or {second})"
                )
        if self.pos is not None and (self.align is not None or self.offset is not None):
            advice = (
                "drop pos; center is the default align (use offset to shift it)"
                if self.pos == "center"
                else 'pos = N is align = "start", offset = N - 38 at the default theme '
                "(38 = thickness + radius + join radius; 32-38 depending on depth)"
            )
            raise ValueError(
                f"pos cannot be combined with align or offset (pos is deprecated): {advice}"
            )
        if self.offset is not None and self.offset < 0 and (self.align or "center") != "center":
            raise ValueError('a negative offset only works with align = "center"')
        if (
            self.min_length is not None
            and self.max_length is not None
            and self.min_length > self.max_length
        ):
            raise ValueError("min_length must not be larger than max_length")
        return self


class MonitorConfig(_Strict):
    shell: ShellMode = Field(
        "plasma",
        description=(
            "What runs on this screen: Edge Shell's frame (edge), "
            "only Plasma (plasma), both or neither (none)."
        ),
    )
    theme: ThemeOverride = Field(default_factory=ThemeOverride)
    layout: LayoutOverride = Field(default_factory=LayoutOverride)
    panels: list[PanelConfig] = Field(default_factory=list)


class Config(_Strict):
    theme: Theme
    layout: LayoutSettings = Field(default_factory=LayoutSettings)
    monitors: dict[str, MonitorConfig] = Field(default_factory=dict)

    def monitor(self, name: str) -> MonitorConfig:
        return self.monitors.get(name) or MonitorConfig()

    def theme_for(self, name: str) -> Theme:
        override = self.monitor(name).theme.model_dump(exclude_none=True)
        return Theme.model_validate(deep_merge(self.theme.model_dump(), override))

    def layout_for(self, name: str) -> LayoutSettings:
        override = self.monitor(name).layout.model_dump(exclude_none=True)
        return LayoutSettings.model_validate({**self.layout.model_dump(), **override})

    @model_validator(mode="after")
    def _check_overrides(self) -> Config:
        for name in self.monitors:
            for table, resolve in (("theme", self.theme_for), ("layout", self.layout_for)):
                try:
                    resolve(name)
                except ValidationError as exc:
                    detail = "; ".join(
                        f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
                    )
                    raise ValueError(f"monitors.{name}.{table}: {detail}") from None
        return self
