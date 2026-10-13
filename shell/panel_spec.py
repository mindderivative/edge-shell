"""Plain data describing a panel. Pure."""

from __future__ import annotations

from dataclasses import dataclass

from shell.config.models import Align, Edge, PanelState

LengthSpec = int | str  # px, "fill", "content" or "NN%" (validated by shell.config.models)


@dataclass(frozen=True)
class PanelDefaults:
    """A widget's registered defaults. `length` is px; it is also the length a "content" panel
    gets until the widget has been measured."""

    edge: Edge
    length: int
    depth: int
    label: str
    pos: int | None = None  # deprecated absolute start (see PanelRequest.pos)
    state: PanelState = "extended"
    align: Align = "center"
    offset: int = 0


@dataclass(frozen=True)
class PanelRequest:
    """What the config asks for (widget defaults + config overrides), before layout.

    `pos` is the deprecated alias: the body starts `pos` px from the start of the screen edge
    (left for top/bottom, top for left/right), clamped to the corner clearance. When it is set
    it wins: the panel is placed there on its own, outside the align slots."""

    widget: str
    edge: Edge
    align: Align
    offset: int
    pos: int | None
    order: int  # within its slot; ties keep config order
    length: LengthSpec
    min_length: int | None
    max_length: int | None
    depth: int
    state: PanelState
    label: str
    fallback_length: int  # px for "content" until the widget has been measured


@dataclass(frozen=True)
class PanelGeometry:
    """A panel resolved by shell.panel_layout: exact body start and length in px."""

    widget: str
    edge: Edge
    pos: int
    length: int
    depth: int
    state: PanelState
    label: str
