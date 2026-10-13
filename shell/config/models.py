"""Pydantic models for the Edge Shell config. Pure: no GTK imports."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    create_model,
    field_validator,
    model_validator,
)

Edge = Literal["top", "bottom", "left", "right"]
PanelState = Literal["collapsed", "extended"]
ShellMode = Literal["edge", "plasma", "both", "none"]
Align = Literal["start", "center", "end"]

_HEX = re.compile(r"#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?")  # #rrggbb or #rrggbbaa
_FONT_FORBIDDEN = re.compile(r'["\\{};]')  # font names go unescaped into generated CSS
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

    enabled: bool = False
    width: Annotated[int, Field(ge=1, le=16)] = 2
    color: str = "#8fd3b6ff"

    @field_validator("color")
    @classmethod
    def _hex(cls, value: str) -> str:
        return check_hex(value)


class Shadow(_Strict):
    """Uniform shadow of the frame and panels (spec 18). Opt-in. `elevation` is 0-100 %."""

    enabled: bool = False
    elevation: Annotated[int, Field(ge=0, le=100)] = 50
    color: str = "#00000080"

    @field_validator("color")
    @classmethod
    def _hex(cls, value: str) -> str:
        return check_hex(value)


class Theme(_Strict):
    frame: str
    text: str
    text_secondary: str
    accent: str
    handle: str
    handle_hover: str
    surface_hover: str
    thickness: Annotated[int, Field(ge=2, le=64)]
    radius: Annotated[int, Field(ge=1, le=64)]
    peek: Annotated[int, Field(ge=1, le=64)]
    hover_zone: Annotated[int, Field(ge=1, le=64)]
    duration_ms: Annotated[int, Field(ge=0, le=5000)]
    font: Annotated[list[str], Field(min_length=1)]
    border: Border = Field(default_factory=Border)
    shadow: Shadow = Field(default_factory=Shadow)

    @field_validator(*COLOR_FIELDS)
    @classmethod
    def _hex(cls, value: str) -> str:
        return check_hex(value)

    @field_validator("font")
    @classmethod
    def _font_names(cls, value: list[str]) -> list[str]:
        for name in value:
            if _FONT_FORBIDDEN.search(name):
                raise ValueError(
                    f"font name {name!r} must not contain a double quote, backslash, {{, }} or ;"
                )
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
# Merged over the base theme (deep_merge) and re-validated by Theme.
ThemeOverride = _override_of(
    "ThemeOverride", Theme, {"border": BorderOverride, "shadow": ShadowOverride}
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

    gap: Annotated[int, Field(ge=0, le=400)] = 8


LayoutOverride = _override_of("LayoutOverride", LayoutSettings)


class PanelConfig(_Strict):
    widget: str
    edge: Edge | None = None
    pos: Offset | Literal["center"] | None = None  # deprecated: align + offset
    align: Align | None = None
    offset: SignedOffset | None = None
    order: Order | None = None
    length: int | str | None = None
    min_length: Length | None = None
    max_length: Length | None = None
    depth: Depth | None = None
    state: PanelState | None = None

    @field_validator("length")
    @classmethod
    def _length(cls, value: int | str | None) -> int | str | None:
        return None if value is None else check_length(value)

    @model_validator(mode="after")
    def _placement(self) -> PanelConfig:
        if self.pos is not None and (self.align is not None or self.offset is not None):
            raise ValueError(
                "pos cannot be combined with align or offset (pos is deprecated): "
                'pos = N is align = "start", offset = N - 38 at the default theme '
                "(38 = thickness + radius + join radius; 32-38 depending on depth)"
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
    shell: ShellMode = "plasma"
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
