"""Plain data describing a panel. Pure."""

from __future__ import annotations

from dataclasses import dataclass

from shell.config.models import Edge, PanelState


@dataclass(frozen=True)
class PanelDefaults:
    edge: Edge
    length: int
    depth: int
    label: str
    pos: int | None = None  # None = centered along the edge
    state: PanelState = "extended"


@dataclass(frozen=True)
class PanelGeometry:
    """A panel with every value resolved (widget defaults + config overrides)."""

    widget: str
    edge: Edge
    pos: int | None
    length: int
    depth: int
    state: PanelState
    label: str
