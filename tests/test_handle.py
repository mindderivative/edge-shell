"""Pure handle rules (shell/handle.py): look, highlight, labels, hit target, input region."""

import pytest

from shell import geometry
from shell import handle as hd
from shell.panel_spec import HandleSpec, Interaction
from shell.theme import hex_to_rgba

ALL = Interaction()
EDGES = ["top", "bottom", "left", "right"]


@pytest.mark.parametrize(
    ("click", "hover", "drag", "shape"),
    [
        (True, True, True, "dots"),
        (True, False, True, "dots"),
        (False, True, True, "bar"),
        (False, False, True, "bar"),
        (True, True, False, "chevron"),
        (True, False, False, "chevron"),
        (False, True, False, "dots"),
        (False, False, False, "none"),
    ],
)
def test_auto_shape_follows_the_interactions(click, hover, drag, shape):
    assert hd.auto_shape(Interaction(click=click, hover=hover, drag=drag)) == shape


def test_the_theme_supplies_every_default(make_config):
    look = hd.resolve_handle(HandleSpec(), ALL, make_config().theme)
    assert look == hd.HandleLook(
        shape="dots",
        size=15,
        weight=3,
        offset=0,
        rgba=hex_to_rgba("#7b7f84"),
        hover_rgba=hex_to_rgba("#e6e8ea"),
    )


def test_panel_choices_win_over_the_theme(make_config):
    theme = make_config(theme={"handle_style": {"shape": "bar", "size": 30}}).theme
    look = hd.resolve_handle(
        HandleSpec(shape="chevron", weight=5, offset=-12, color="#ff000080"), ALL, theme
    )
    assert (look.shape, look.size, look.weight, look.offset) == ("chevron", 30, 5, -12)
    assert look.rgba == hex_to_rgba("#ff000080")
    assert look.hover_rgba == hex_to_rgba("#e6e8ea")  # theme handle_hover


def test_auto_from_the_panel_or_the_theme_follows_the_interactions(make_config):
    theme = make_config().theme  # handle_style.shape = "auto"
    click_only = Interaction(hover=False, drag=False)
    assert hd.resolve_handle(HandleSpec(), click_only, theme).shape == "chevron"
    assert hd.resolve_handle(HandleSpec(shape="auto"), click_only, theme).shape == "chevron"
    bar_theme = make_config(theme={"handle_style": {"shape": "bar"}}).theme
    assert hd.resolve_handle(HandleSpec(), click_only, bar_theme).shape == "bar"  # explicit


def test_a_theme_shape_never_draws_on_an_all_off_panel(make_config):
    off = Interaction(click=False, hover=False, drag=False)
    bar_theme = make_config(theme={"handle_style": {"shape": "bar"}}).theme
    assert hd.resolve_handle(HandleSpec(), off, bar_theme).shape == "none"
    assert hd.resolve_handle(HandleSpec(shape="auto"), off, bar_theme).shape == "none"
    # set on the entry (or by the widget): drawn as decoration
    assert hd.resolve_handle(HandleSpec(shape="bar"), off, bar_theme).shape == "bar"
    assert hd.resolve_handle(HandleSpec(shape="dots"), off, make_config().theme).shape == "dots"


@pytest.mark.parametrize(
    ("prelight", "focused", "hovered", "extended", "interaction", "expected"),
    [
        (True, False, False, False, ALL, True),
        (False, True, False, True, ALL, True),
        (False, False, True, False, ALL, True),  # peeking
        (False, False, True, True, ALL, False),  # extended: only the handle itself lights up
        (False, False, False, False, ALL, False),
        (True, False, False, False, Interaction(click=False, drag=False), False),
        (False, False, True, False, Interaction(hover=False), False),
        (True, False, False, False, Interaction(click=False, hover=False), True),
    ],
)
def test_highlight(prelight, focused, hovered, extended, interaction, expected):
    assert hd.is_highlighted(prelight, focused, hovered, extended, interaction) is expected


@pytest.mark.parametrize(
    ("extended", "interaction", "label"),
    [
        (False, ALL, "Expand dock"),
        (True, ALL, "Collapse dock"),
        (False, Interaction(click=False), "Drag to expand dock"),
        (True, Interaction(click=False, hover=False), "Drag to collapse dock"),
        (False, Interaction(click=False, drag=False), None),
    ],
)
def test_handle_label(extended, interaction, label):
    assert hd.handle_label("dock", extended, interaction) == label


def test_morph_is_the_depth_fraction():
    assert [hd.morph(d, 64) for d in (-1, 0, 32, 64, 80)] == [0.0, 0.0, 0.5, 1.0, 1.0]
    assert hd.morph(5, 0) == 0.0


def test_band_room_keeps_the_shape_clear_of_the_band_edges():
    # 2 px clear on each side from an 8 px band up, 1 px below; never negative
    assert [hd.band_room(t) for t in (10, 8, 12, 20)] == [6, 4, 8, 16]
    assert [hd.band_room(t) for t in (7, 6, 4, 3, 2)] == [5, 4, 2, 1, 0]


def test_shape_room_stops_growing_at_the_default_thickness():
    # Gate B (thickness 64): the chevron grew taller with the frame. The shape's room across
    # is band_room up to the default 10 px band and 6 px above it; thinner frames still shrink.
    assert [hd.shape_room(t) for t in (10, 12, 20, 64)] == [6, 6, 6, 6]
    assert [hd.shape_room(t) for t in (8, 7, 6, 4, 2)] == [4, 5, 4, 2, 0]


def test_centre_inset_is_fixed_from_the_default_thickness_up():
    assert [hd.centre_inset(t) for t in (10, 11, 20, 64)] == [5, 5, 5, 5]
    assert [hd.centre_inset(t) for t in (8, 6, 3, 2)] == [4, 3, 1.5, 1]  # thin: mid-band


def test_hit_size_has_a_minimum_and_grows_with_the_shape():
    assert hd.hit_size(10, 15, 560) == (44, 14)  # today's handle button
    assert hd.hit_size(10, 40, 560) == (56, 14)  # 8 px past the shape on each side
    # Was (44, 20) (the target held the whole band, the shape sat in its middle). The shape
    # now stays 5 px inside the body's inner edge on any frame, so 14 px still holds it.
    assert hd.hit_size(20, 15, 560) == (44, 14)
    assert hd.hit_size(64, 15, 560) == (44, 14)  # Gate B: not the whole 64 px band
    assert hd.hit_size(6, 15, 560) == (44, 14)  # thin frame: never below today's 14
    assert hd.hit_size(10, 40, 50) == (50, 14)  # never longer than the body


def test_offset_is_clamped_to_the_body():
    assert [hd.clamp_offset(o, 560, 44) for o in (300, -300, 10, 0)] == [258, -258, 10, 0]
    assert hd.clamp_offset(30, 44, 44) == 0
    assert hd.along_margins(12) == (24, 0)
    assert hd.along_margins(-5) == (0, 10)


def test_the_hit_target_rides_the_inner_edge():
    assert hd.hit_inset(10, 0, 14) == 0
    assert hd.hit_inset(10, 3.5, 14) == 0
    assert hd.hit_inset(10, 64, 14) == 60  # 10 + 64 - 14: ends at the body's inner edge


@pytest.mark.parametrize(
    ("edge", "size", "d", "centre"),
    [
        ("bottom", (44, 14), 0, (22, 9)),  # 5 px from the screen edge: mid-band
        ("bottom", (44, 14), 64, (22, 5)),  # 5 px inside the inner edge
        ("top", (44, 14), 0, (22, 5)),
        ("top", (44, 14), 64, (22, 9)),
        ("left", (14, 44), 0, (5, 22)),
        ("right", (14, 44), 0, (9, 22)),
        ("right", (14, 44), 2, (7, 22)),  # moves with the depth while the box is clamped
    ],
)
def test_shape_centre(edge, size, d, centre):
    assert hd.shape_centre(edge, *size, 10, d) == centre


@pytest.mark.parametrize(
    ("edge", "d", "offset", "rect"),
    [
        ("bottom", 0, 0, (272, 60, 44, 14)),
        ("bottom", 64, 0, (272, 0, 44, 14)),
        ("top", 0, 0, (272, 0, 44, 14)),
        ("left", 0, 0, (0, 272, 14, 44)),
        ("right", 0, 0, (60, 272, 14, 44)),
        ("bottom", 0, 300, (530, 60, 44, 14)),  # clamped to the body (258)
        ("left", 0, -20, (0, 252, 14, 44)),  # negative: towards the top
    ],
)
def test_hit_rect_in_surface_px(edge, d, offset, rect):
    assert hd.hit_rect(edge, 560, 64, d, 10, 14, (44, 14), offset) == rect


def test_thick_band_pinned_cases():
    # T = 20, re-derived by hand for the Gate B rule (was a 20 px target, centre (22, 10)
    # = mid-band). The target is 14 px; the surface is 20 + 64 = 84 px across.
    # Extended: hit_inset = 20 + 64 - 14 = 70, so v0 = 84 - 70 - 14 = 0.
    assert hd.hit_rect("bottom", 560, 64, 64, 20, 14, (44, 14), 0) == (272, 0, 44, 14)
    # Collapsed: hit_inset = 20 - 14 = 6, so v0 = 84 - 6 - 14 = 64 (box = 6..20 px from the
    # screen edge, its far side on the band's inner edge).
    assert hd.hit_rect("bottom", 560, 64, 0, 20, 14, (44, 14), 0) == (272, 64, 44, 14)
    # Centre 20 - 5 = 15 px from the screen edge = 15 - 6 = 9 px above the box's bottom,
    # i.e. y = 14 - 9 = 5: 5 px inside the band's inner edge (was 10 px, mid-band).
    assert hd.shape_centre("bottom", 44, 14, 20, 0) == (22, 5)
    # T = 64 collapsed (Phil's case): hit_inset 50, centre 59 px from the screen edge
    assert hd.hit_rect("bottom", 560, 64, 0, 64, 14, (44, 14), 0) == (272, 64, 44, 14)
    assert hd.shape_centre("bottom", 44, 14, 64, 0) == (22, 5)
    assert hd.shape_centre("right", 14, 44, 64, 0) == (5, 22)  # screen side is x = 14
    # extended: hit_inset 64 + 64 - 14 = 114, centre 123 px from the screen edge: 9 px in
    assert hd.shape_centre("top", 44, 14, 64, 64) == (22, 9)


def centre_from_screen(edge, thickness, d):
    """Distance of the drawn shape's centre from the screen edge, through the real
    placement path: hit_size -> hit_rect (surface px) -> shape_centre (box px)."""
    hit = hd.hit_size(thickness, 15, 560)
    x, y, w, h = hd.hit_rect(edge, 560, 64, d, thickness, 14, hit, 0)
    cx, cy = hd.shape_centre(edge, w, h, thickness, d)
    total = thickness + 64  # surface px across
    px, py = x + cx, y + cy
    return {"top": py, "bottom": total - py, "left": px, "right": total - px}[edge]


@pytest.mark.parametrize("edge", EDGES)
@pytest.mark.parametrize("thickness", [10, 12, 20, 64])
@pytest.mark.parametrize("d", [0, 2, 16, 32, 64])
def test_the_shape_sits_a_fixed_inset_inside_the_body_edge(edge, thickness, d):
    # Gate B: the same 5 px inside the body's inner edge (T + d from the screen edge) on any
    # frame from the default up, collapsed (d = 0: inside the band's inner edge) or extended.
    assert thickness + d - centre_from_screen(edge, thickness, d) == 5


@pytest.mark.parametrize("edge", EDGES)
@pytest.mark.parametrize("thickness", [5, 6, 8])
@pytest.mark.parametrize("d", [0, 64])
def test_a_thin_frame_still_centres_the_shape_in_its_band(edge, thickness, d):
    assert thickness + d - centre_from_screen(edge, thickness, d) == thickness / 2


@pytest.mark.parametrize("edge", EDGES)
@pytest.mark.parametrize("thickness", [10, 20, 64])
@pytest.mark.parametrize("d", [0, 8, 64])
def test_the_hit_target_holds_the_shape_room(edge, thickness, d):
    # the target's far side is the body's inner edge; the shape's room (centre +- 3) is in it
    hit = hd.hit_size(thickness, 15, 560)
    x, y, w, h = hd.hit_rect(edge, 560, 64, d, thickness, 14, hit, 0)
    across = h if edge in ("top", "bottom") else w
    centre = centre_from_screen(edge, thickness, d)
    near = {"top": y, "left": x, "bottom": thickness + 64 - y - h, "right": thickness + 64 - x - w}
    room = hd.shape_room(thickness) / 2
    assert near[edge] <= centre - room and centre + room <= near[edge] + across
    # far side on the body's inner edge (or 14 px from the screen edge while that is nearer)
    assert near[edge] + across == max(thickness + d, across)
    assert centre + room <= thickness + d - 2  # 2 px of the mass stay clear inside the edge


@pytest.mark.parametrize("edge", EDGES)
@pytest.mark.parametrize("d", [0, 8, 16, 40, 64])
@pytest.mark.parametrize("thickness", [10, 20, 64])
def test_the_hover_input_region_contains_the_hit_target(edge, d, thickness):
    hit = hd.hit_size(thickness, 15, 560)
    x, y, w, h = hd.hit_rect(edge, 560, 64, d, thickness, 14, hit, 0)
    ix, iy, iw, ih = geometry.input_rect(edge, 560, 64, d, thickness, 14, 16)
    assert ix <= x and iy <= y and x + w <= ix + iw and y + h <= iy + ih


def test_input_region_without_hover_on_a_thick_frame():
    # T = 64 (Gate B): only the 14 px target at the band's inner edge, not the whole band
    click = Interaction(hover=False, drag=False)
    hit = hd.hit_size(64, 15, 560)
    got = hd.input_rects("bottom", 560, 64, 0, 64, 14, 16, click, hit, 0)
    assert got == [(272, 64, 44, 14)]  # 128 px surface: 50..64 px from the screen edge
    body = geometry.body_rect("bottom", 560, 64, 64, 64, 14)
    got = hd.input_rects("bottom", 560, 64, 64, 64, 14, 16, click, hit, 0)
    assert got == [body, (272, 0, 44, 14)]


def rects(d, interaction, edge="bottom"):
    return hd.input_rects(edge, 560, 64, d, 10, 14, 16, interaction, (44, 14), 0)


def test_input_region_with_hover_is_unchanged():
    for d in (0, 30, 64):
        assert rects(d, ALL) == [geometry.input_rect("bottom", 560, 64, d, 10, 14, 16)]


def test_input_region_without_hover():
    click = Interaction(hover=False, drag=False)
    nothing = Interaction(click=False, hover=False, drag=False)
    body = geometry.body_rect("bottom", 560, 64, 64, 10, 14)
    assert rects(0, click) == [(272, 60, 44, 14)]  # collapsed: only the hit target
    assert rects(0, nothing) == []  # all off: the strip is click-through
    assert rects(64, nothing) == [body]  # the content still takes input
    assert rects(64, click) == [body, (272, 0, 44, 14)]
