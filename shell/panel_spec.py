"""Plain data describing a panel. Pure."""

from __future__ import annotations

from dataclasses import dataclass

from shell.config.models import Align, Corner, Edge, HandleShape, PanelState
from shell.widget import NO_PROPS, WidgetProps

LengthSpec = int | str  # px, "fill", "content" or "NN%" (validated by shell.config.models)


@dataclass(frozen=True)
class HandleSpec:
    """A panel's own handle choices (config entry over widget default). None = the theme's
    value ([theme.handle_style], colours `handle` / `handle_hover`), resolved by
    shell.handle.resolve_handle, so a theme change restyles without touching the request."""

    shape: HandleShape | None = None
    size: int | None = None
    weight: int | None = None
    offset: int = 0  # px along the edge from the body centre; clamped to the body
    color: str | None = None
    hover_color: str | None = None


@dataclass(frozen=True)
class Interaction:
    """Which interactions a panel answers (spec 15). Keyboard activation follows `click`."""

    click: bool = True
    hover: bool = True
    drag: bool = True


THEME_HANDLE = HandleSpec()  # every handle key from the theme
ALL_INTERACTIONS = Interaction()  # click, hover and drag on (spec 15 default)


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
    handle: HandleSpec = HandleSpec()
    interaction: Interaction = Interaction()


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
    # Not part of the layout (PanelGeometry): a change is applied to the live panel in place.
    handle: HandleSpec = HandleSpec()
    interaction: Interaction = Interaction()
    # Not part of the layout either; a change rebuilds the panel (shell.config.diff).
    name: str = ""
    props: WidgetProps = NO_PROPS


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


def default_edge(corner: Corner) -> Edge:
    """The edge a corner panel opens from unless told otherwise: the corner's top or bottom
    edge (the summary block rises out of the bottom edge)."""
    return corner.split("-")[0]  # type: ignore[return-value]


def corner_has_edge(corner: Corner, edge: Edge) -> bool:
    return edge in corner.split("-")


@dataclass(frozen=True)
class CornerDefaults:
    """A corner widget's registered defaults (spec 19). `width` and `height` are px from the
    screen corner, both frame bands included; `edge` is the edge it opens from (None: the
    corner's top or bottom edge, `default_edge`)."""

    corner: Corner
    width: int
    height: int
    label: str
    edge: Edge | None = None
    state: PanelState = "extended"
    handle: HandleSpec = HandleSpec()
    interaction: Interaction = Interaction()


@dataclass(frozen=True)
class CornerRequest:
    """What the config asks for a corner panel (widget defaults + config overrides), before
    layout. `edge` is always one of the corner's two edges."""

    widget: str
    corner: Corner
    edge: Edge
    width: int
    height: int
    state: PanelState
    label: str
    handle: HandleSpec = HandleSpec()
    interaction: Interaction = Interaction()
    name: str = ""  # as PanelRequest: a change rebuilds the panel
    props: WidgetProps = NO_PROPS


@dataclass(frozen=True)
class CornerGeometry:
    """A corner panel resolved by shell.panel_layout. The body is the rectangle from the screen
    corner `along` px along `edge` (the adjacent frame band included) and `thickness + depth`
    px across it; `length` = `along` minus the adjacent band, the part of the body the handle
    centres on (EdgePanel's hit target reads `length`)."""

    widget: str
    corner: Corner
    edge: Edge
    along: int
    length: int
    depth: int
    state: PanelState
    label: str
