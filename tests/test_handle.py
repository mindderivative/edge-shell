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


def test_hit_size_has_a_minimum_and_grows_with_the_shape():
    assert hd.hit_size(10, 15, 560) == (44, 14)  # today's handle button
    assert hd.hit_size(10, 40, 560) == (56, 14)  # 8 px past the shape on each side
    assert hd.hit_size(20, 15, 560) == (44, 20)  # thick frame: the band, no more
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


@pytest.mark.parametrize("edge", EDGES)
@pytest.mark.parametrize("d", [0, 8, 16, 40, 64])
def test_the_hover_input_region_contains_the_hit_target(edge, d):
    x, y, w, h = hd.hit_rect(edge, 560, 64, d, 10, 14, (44, 14), 0)
    ix, iy, iw, ih = geometry.input_rect(edge, 560, 64, d, 10, 14, 16)
    assert ix <= x and iy <= y and x + w <= ix + iw and y + h <= iy + ih


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
