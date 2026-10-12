"""Pydantic models for the Edge Shell config. Pure: no GTK imports."""

from __future__ import annotations

import re
from typing import Annotated, Literal

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

_HEX = re.compile(r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")  # #rrggbb or #rrggbbaa
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
    if not _HEX.match(value):
        raise ValueError("must be a #rrggbb or #rrggbbaa hex color")
    return value.lower()


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


# Same fields as Theme, all optional. Merged over the base theme and re-validated by Theme.
ThemeOverride = create_model(
    "ThemeOverride",
    __base__=_Strict,
    **{name: (field.annotation | None, None) for name, field in Theme.model_fields.items()},
)

Length = Annotated[int, Field(ge=60, le=4000)]
Depth = Annotated[int, Field(ge=16, le=2000)]
Offset = Annotated[int, Field(ge=0, le=20000)]


class PanelConfig(_Strict):
    widget: str
    edge: Edge | None = None
    pos: Offset | Literal["center"] | None = None
    length: Length | None = None
    depth: Depth | None = None
    state: PanelState | None = None


class MonitorConfig(_Strict):
    shell: ShellMode = "plasma"
    theme: ThemeOverride = Field(default_factory=ThemeOverride)
    panels: list[PanelConfig] = Field(default_factory=list)


class Config(_Strict):
    theme: Theme
    monitors: dict[str, MonitorConfig] = Field(default_factory=dict)

    def monitor(self, name: str) -> MonitorConfig:
        return self.monitors.get(name) or MonitorConfig()

    def theme_for(self, name: str) -> Theme:
        override = self.monitor(name).theme.model_dump(exclude_none=True)
        return Theme.model_validate({**self.theme.model_dump(), **override})

    @model_validator(mode="after")
    def _check_overrides(self) -> Config:
        for name in self.monitors:
            try:
                self.theme_for(name)
            except ValidationError as exc:
                detail = "; ".join(
                    f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
                )
                raise ValueError(f"monitors.{name}.theme: {detail}") from None
        return self
