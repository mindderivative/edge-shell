"""The layout resolver (spec 16-17): slots, order, gap, offsets, pos, clamping, overlap."""

import pytest

from shell.panel_layout import (
    CONTENT_PAD,
    MIN_LENGTH,
    content_length,
    free_span,
    layout_edge,
    layout_monitor,
)
from shell.panel_spec import PanelRequest

W, H, T, R, GAP = 1920, 1080, 10, 14, 8


def req(
    widget="dock",
    edge="bottom",
    align="center",
    offset=0,
    pos=None,
    order=0,
    length=560,
    depth=64,
    min_length=None,
    max_length=None,
    fallback=200,
):
    return PanelRequest(
        widget, edge, align, offset, pos, order, length, min_length, max_length, depth,
        "extended", widget, length if isinstance(length, int) else fallback,
    )  # fmt: skip


def placed(*requests, width=W, height=H, gap=GAP, natural=None):
    layout = layout_monitor(list(requests), width, height, T, R, gap, natural, "monitors.X")
    return [None if p is None else (p.pos, p.length) for p in layout.panels], layout.warnings


# ---- free span ----------------------------------------------------------------------


def test_free_span_is_the_corner_clearance_at_full_depth():
    assert free_span(1920, T, R, 64) == (38, 1882)  # r = 14
    assert free_span(1080, T, R, 16) == (32, 1048)  # r = 8
    assert free_span(1920, T, R, 27) == (38, 1882)  # r = 13.5: rounded inward


def test_layout_edge_returns_positions_by_config_index():
    got, notes = layout_edge([(3, req(align="start")), (7, req(align="end"))], W, T, R, GAP)
    assert got == {3: (38, 560), 7: (1322, 560)} and notes == []


# ---- slots ----------------------------------------------------------------------------


def test_centred_panel_keeps_the_old_centring():
    assert placed(req())[0] == [(680, 560)]
    assert placed(req("clock", "top", length=168, depth=46))[0] == [(876, 168)]


def test_start_and_end_sit_at_the_corner_clearance():
    assert placed(req(align="start"), req("clock", align="end", length=168, depth=46)) == (
        [(38, 560), (1882 - 168, 168)],
        [],
    )


def test_offset_is_measured_from_the_aligned_end():
    assert placed(req(align="start", offset=100))[0] == [(138, 560)]
    assert placed(req(align="end", offset=20))[0] == [(1882 - 20 - 560, 560)]


def test_the_system_bar_default_keeps_its_place():
    # widgets/system_bar.py: align = "end", offset = 142 -> y = 600 on a 1080 px edge
    assert placed(req("bar", "right", "end", offset=142, length=300, depth=56))[0] == [(600, 300)]


def test_two_centred_panels_are_packed_side_by_side_r1_plus_r2_plus_gap_apart():
    got, warnings = placed(req(), req("clock", length=168, depth=46))
    total = 560 + (14 + 14 + GAP) + 168
    first = (W - total) // 2
    assert got == [(first, 560), (first + 560 + 36, 168)] and warnings == []


def test_order_sorts_within_a_slot_and_ties_keep_config_order():
    a = req("a", "top", "start", order=1, length=168, depth=46)
    b = req("b", "top", "start", order=0, length=168, depth=46)
    c = req("c", "top", "start", order=1, length=100, depth=46)
    assert placed(a, b, c)[0] == [(38 + 168 + 36, 168), (38, 168), (38 + 2 * (168 + 36), 100)]


def test_the_first_end_panel_is_nearest_the_end():
    a = req("a", "top", "end", length=168, depth=46)
    b = req("b", "top", "end", length=168, depth=46)
    assert placed(a, b)[0] == [(1714, 168), (1714 - 36 - 168, 168)]


@pytest.mark.parametrize(("gap", "second"), [(0, 38 + 168 + 28), (8, 38 + 168 + 36), (50, 284)])
def test_gap_is_added_to_the_joins(gap, second):
    a = req("a", "top", "start", length=168, depth=46)
    b = req("b", "top", "start", length=168, depth=46)
    assert placed(a, b, gap=gap)[0][1] == (second, 168)


def test_a_later_panels_offset_is_extra_space_before_it():
    a = req("a", "top", "start", length=168, depth=46)
    b = req("b", "top", "start", offset=10, length=168, depth=46)
    assert placed(a, b)[0][1] == (38 + 168 + 36 + 10, 168)


@pytest.mark.parametrize(("offset", "pos"), [(100, 780), (-100, 580)])
def test_center_offset_shifts_the_group(offset, pos):
    assert placed(req(offset=offset)) == ([(pos, 560)], [])


def test_center_offset_past_the_corner_is_clamped_with_a_warning():
    assert placed(req(offset=1000)) == (
        [(1322, 560)],
        [
            "monitors.X.panels.0 (dock): offset 1000 would run into a screen corner or a "
            "neighbour; moved to 1322"
        ],
    )


def test_start_offset_past_the_corner_is_clamped_with_a_warning():
    assert placed(req(align="start", offset=5000)) == (
        [(1322, 560)],
        ["monitors.X.panels.0 (dock): offset 5000 would run into a screen corner; moved to 1322"],
    )


def test_the_center_group_is_pushed_clear_of_the_start_group():
    got, warnings = placed(req(align="start", length=1000), req("clock", length=168, depth=46))
    assert got == [(38, 1000), (38 + 1000 + 36, 168)] and warnings == []


def test_a_centre_offset_counts_from_where_the_neighbours_pushed_the_group():
    got, warnings = placed(
        req(align="start", length=1000), req("clock", offset=50, length=168, depth=46)
    )
    assert got == [(38, 1000), (38 + 1000 + 36 + 50, 168)] and warnings == []


def test_a_negative_offset_on_a_later_centre_panel_counts_as_zero():
    a = req("a", "top", length=168, depth=46)
    b = req("b", "top", offset=-50, length=168, depth=46)
    assert placed(a, b) == ([(774, 168), (978, 168)], [])  # as without the offset


# ---- pos (deprecated alias) -------------------------------------------------------------


@pytest.mark.parametrize(
    ("pos", "expected"), [(0, 38), (37, 38), (38, 38), (5000, 1920 - 38 - 560)]
)
def test_pos_is_clamped_to_the_corner_clearance(pos, expected):
    got, warnings = placed(req(pos=pos))
    assert got == [(expected, 560)]
    if pos == expected:
        assert warnings == []
    else:
        assert warnings == [
            f"monitors.X.panels.0 (dock): pos {pos} would run into a screen corner; "
            f"moved to {expected}"
        ]


def test_clearance_uses_the_join_radius_of_a_shallow_panel():
    assert placed(req(pos=0, depth=16))[0] == [(32, 560)]
    assert placed(req(pos=0, depth=27))[0] == [(38, 560)]


def test_pos_panel_stays_out_of_the_slots():
    got, _ = placed(req("bar", "right", pos=600, length=300, depth=56), req("x", "right"))
    assert got == [(600, 300), None]  # the centred one would sit on it: the later one goes


# ---- shrink, no room, overlap ------------------------------------------------------------


def test_too_long_is_shrunk_to_the_free_span():
    got, warnings = placed(req("bar", "right", pos=100, length=1500, depth=56))
    assert got == [(38, 1004)]
    assert "shrunk to 1004" in warnings[0]


def test_no_room_at_all_hides_the_panel():
    got, warnings = placed(req("bar", "right", pos=0, length=300, depth=56), height=130)
    assert got == [None]
    assert "has no room for it; not shown" in warnings[0]


def test_pos_neighbours_need_a_gap_of_r1_plus_r2():
    a = req(pos=400, length=300)  # ends at 700, r = 14
    ok = req("clock", pos=700 + 14 + 8, length=100, depth=16)  # r = 8: gap exactly 22
    tight = req("clock", pos=700 + 14 + 7, length=100, depth=16)
    assert placed(a, ok)[1] == []
    got, warnings = placed(a, tight)
    assert got[1] is None and got[0] is not None
    assert warnings[0].startswith("monitors.X.panels.1 (clock): overlaps monitors.X.panels.0")


def test_deep_panels_on_neighbouring_edges_must_not_cross():
    top = req("a", "top", pos=40, length=300, depth=400)
    left = req("b", "left", pos=40, length=300, depth=400)
    assert placed(top, left)[0][1] is None
    far = req("b", "left", pos=600, length=300, depth=400)
    assert placed(top, far)[1] == []


def test_corner_neighbours_on_adjacent_edges_collide():
    clock = req("clock", "bottom", "end", length=168, depth=46)

    def bar(offset):
        return req("bar", "right", "end", offset=offset, length=300, depth=56)

    got, warnings = placed(clock, bar(0))
    assert got[1] is None and warnings == [
        "monitors.X.panels.1 (bar): overlaps monitors.X.panels.0 (clock) or leaves less than "
        "the minimum gap between their joins; not shown"
    ]
    assert placed(clock, bar(45))[0][1] is None
    assert placed(clock, bar(46))[1] == []  # offset >= the clock's depth + r - R (= 46)
    top = req("a", "top", "start", length=168, depth=46)
    left = req("b", "left", "start", length=168, depth=46)
    assert placed(top, left)[0][1] is None
    assert placed(top, req("b", "left", "start", offset=46, length=168, depth=46))[1] == []


def test_warnings_come_in_config_order_whatever_the_edge():
    _, warnings = placed(req(pos=0), req("clock", "top", pos=0, length=168, depth=46))
    assert [w.split(" ")[0] for w in warnings] == ["monitors.X.panels.0", "monitors.X.panels.1"]


# ---- length modes ---------------------------------------------------------------------


def test_content_length_pads_the_natural_size_and_keeps_the_floor():
    assert content_length(200) == 200 + 2 * CONTENT_PAD
    assert content_length(5) == MIN_LENGTH


def test_percent_is_of_the_free_span():
    assert placed(req(length="50%"))[0] == [((W - 922) // 2, 922)]  # 50% of 1844


def test_percent_below_the_floor_gets_the_floor():
    assert placed(req(length="1%"))[0][0][1] == MIN_LENGTH


def test_min_and_max_clamp_every_mode():
    assert placed(req(length="50%", max_length=600))[0][0][1] == 600
    assert placed(req(length=300, min_length=400))[0][0][1] == 400
    assert placed(req(length="fill", max_length=500))[0] == [(710, 500)]


def test_min_length_beyond_the_free_span_is_shrunk_with_a_warning():
    got, warnings = placed(req("bar", "right", length=300, min_length=2000, depth=56))
    assert got == [(38, 1004)] and "length 2000 px does not fit" in warnings[0]


def test_content_uses_the_measured_length_or_the_fallback():
    assert placed(req(length="content", fallback=300))[0][0][1] == 300
    assert placed(req(length="content"), natural={0: 240})[0][0][1] == 240


def test_fill_alone_spans_the_free_span():
    assert placed(req(length="fill")) == ([(38, 1844)], [])


def test_fill_takes_what_the_neighbours_leave():
    a = req("a", "top", "start", length=168, depth=46)
    f = req("f", "top", length="fill", depth=46)
    c = req("c", "top", "end", length=168, depth=46)
    got, warnings = placed(a, f, c)
    assert got == [(38, 168), (242, 1436), (1714, 168)] and warnings == []
    assert 242 - (38 + 168) == 36 and 1714 - (242 + 1436) == 36  # joins + gap either side


def test_fills_share_equally_and_the_first_gets_the_odd_pixel():
    a = req("a", "top", length="fill", depth=46)
    b = req("b", "top", length="fill", depth=46)
    assert placed(a, b, gap=9)[0] == [(38, 904), (38 + 904 + 37, 903)]


def test_a_fill_without_room_gets_the_floor_and_the_later_neighbour_goes():
    a = req("a", "top", "start", length=1100, depth=46)
    fill = req("f", "top", length="fill", depth=46)
    c = req("c", "top", "end", length=700, depth=46)
    got, warnings = placed(a, fill, c)
    assert got == [(38, 1100), (38 + 1100 + 36, MIN_LENGTH), None]
    assert warnings == [
        f"monitors.X.panels.1 (f): no room to fill; shown at {MIN_LENGTH} px",
        "monitors.X.panels.2 (c): overlaps monitors.X.panels.1 (f) or leaves less than the "
        "minimum gap between their joins; not shown",
    ]


def test_fill_with_a_pos_runs_to_the_end_of_the_free_span():
    assert placed(req("bar", "right", pos=600, length="fill", depth=56))[0] == [(600, 442)]


@pytest.mark.parametrize(("offset", "expected"), [(100, (138, 1744)), (-100, (38, 1744))])
def test_a_centred_fill_gives_up_its_offset_and_moves_that_way(offset, expected):
    assert placed(req(length="fill", offset=offset)) == ([expected], [])


def test_a_centred_fill_between_neighbours_leaves_its_offset_free_before_it():
    a = req("a", "top", "start", length=168, depth=46)
    f = req("f", "top", offset=40, length="fill", depth=46)
    c = req("c", "top", "end", length=168, depth=46)
    assert placed(a, f, c) == ([(38, 168), (282, 1396), (1714, 168)], [])


def test_a_smaller_monitor_recentres_rescales_and_clamps():
    got, warnings = placed(
        req(),
        req("p", "top", length="50%", depth=46),
        req("bar", "right", pos=600, length=300, depth=56),
        width=1280,
        height=720,
    )
    assert got == [(360, 560), ((1280 - 602) // 2, 602), (382, 300)]
    assert warnings == [
        "monitors.X.panels.2 (bar): pos 600 would run into a screen corner; moved to 382"
    ]


# ---- review amendments to the slot logic --------------------------------------------------


def test_an_end_panels_offset_is_extra_space_before_the_second_end_panel():
    a = req("a", "top", "end", length=168, depth=46)
    b = req("b", "top", "end", offset=10, length=168, depth=46)
    assert placed(a, b) == ([(1714, 168), (1714 - 36 - 10 - 168, 168)], [])


def test_a_centre_group_is_pushed_left_by_a_long_end_group():
    long_end = req("e", "top", "end", length=1000, depth=46)
    clock = req("c", "top", length=168, depth=46)
    assert placed(long_end, clock) == ([(882, 1000), (882 - 36 - 168, 168)], [])


def test_a_panel_hidden_by_overlap_keeps_its_slot_space():
    a = req("a", "top", "start", length=168, depth=46)
    b = req("b", "left", "start", length=168, depth=46)  # collides with a at the corner
    c = req("c", "left", "start", length=168, depth=46)
    got, _ = placed(a, b, c)
    assert got == [(38, 168), None, (38 + 168 + 36, 168)]  # c does not close up on b's slot


def test_a_start_panel_pushed_into_the_corner_clearance_is_reported():
    a = req("a", "top", "start", length=1000, depth=46)
    b = req("b", "top", "start", length=800, depth=46)
    got, warnings = placed(a, b, gap=50)
    assert got == [(38, 1000), (1082, 800)]  # 1882 - 800; not the 1116 the gap asks for
    assert warnings == [
        "monitors.X.panels.1 (b): no room after its neighbours in the start slot; moved to 1082"
    ]


def test_an_end_panel_pushed_into_the_corner_clearance_is_reported():
    a = req("a", "top", "end", length=1000, depth=46)
    b = req("b", "top", "end", length=800, depth=46)
    got, warnings = placed(a, b, gap=50)
    assert got == [(882, 1000), (38, 800)]
    assert warnings == [
        "monitors.X.panels.1 (b): no room after its neighbours in the end slot; moved to 38"
    ]


def test_a_later_start_panel_with_an_offset_pushed_by_its_neighbour_gets_the_neighbour_text():
    a = req("a", "top", "start", offset=10, length=1000, depth=46)
    b = req("b", "top", "start", offset=300, length=800, depth=46)
    got, warnings = placed(a, b)
    assert got[1] == (1082, 800)
    assert warnings == [
        "monitors.X.panels.1 (b): no room after its neighbours in the start slot; moved to 1082"
    ]


def test_the_centre_offset_warning_reports_the_position_the_panel_ends_up_at():
    a = req("a", "top", "start", offset=427, length=580, depth=46)
    b = req("b", "top", "center", offset=299, length=683, depth=46)
    c = req("c", "top", "start", length=312, depth=46)
    got, warnings = placed(a, b, c)
    assert got[1] == (1199, 683)  # the offset alone asked for 1429; the warning used to say so
    assert warnings[0] == (
        "monitors.X.panels.1 (b): offset 299 would run into a screen corner or a neighbour; "
        "moved to 1199"
    )


# ---- fix round 1: half-pixel joins, stub fills, later-slot offsets ---------------------------


def test_fill_room_counts_each_pair_rounded_up_as_the_placement_does():
    # depth 17 -> r = 8.5: the fill/end pair spaces 16.5 and places 17; the fill must not run
    # 1 px long into the end panel
    a = req("a", "top", "start", length=100, depth=16)
    f = req("f", "top", length="fill", depth=17)
    c = req("c", "top", "end", length=100, depth=16)
    assert placed(a, f, c, gap=0) == ([(32, 100), (149, 1622), (1788, 100)], [])


def test_a_fill_floored_for_lack_of_room_says_so():
    got, warnings = placed(req(length="fill", offset=2000), gap=0)
    assert got == [(1882 - MIN_LENGTH, MIN_LENGTH)]
    assert warnings == [f"monitors.X.panels.0 (dock): no room to fill; shown at {MIN_LENGTH} px"]


def test_a_later_start_panels_own_offset_into_the_corner_gets_the_corner_text():
    a = req("a", "top", "start", length=100, depth=46)
    b = req("b", "top", "start", offset=1800, length=800, depth=46)
    got, warnings = placed(a, b)
    assert got[1] == (1082, 800)
    assert warnings == [
        "monitors.X.panels.1 (b): offset 1800 would run into a screen corner; moved to 1082"
    ]


def test_the_centre_group_total_rounds_every_pair_up_with_half_pixel_joins():
    # depths 17, 16, 17 -> pair spacing 16.5 each, placed as 17 each: the group is 334 long
    # and centred on that, not on 333
    a = req("a", "top", length=100, depth=17)
    b = req("b", "top", length=100, depth=16)
    c = req("c", "top", length=100, depth=17)
    got, warnings = placed(a, b, c, gap=0)
    assert got == [(793, 100), (910, 100), (1027, 100)] and warnings == []
    assert got[0][0] - 0 == 1920 - (got[2][0] + got[2][1])  # centred


@pytest.mark.parametrize(("offset", "expected"), [(100, (810, 500)), (-100, (610, 500))])
def test_a_max_length_fill_in_the_centre_still_moves_with_its_offset(offset, expected):
    assert placed(req("f", "top", length="fill", max_length=500, offset=offset, depth=46)) == (
        [expected],
        [],
    )
