"""Corner panels in the layout resolver (spec 19): one per corner, shrink to fit, the free
spans of their two edges, and the overlap check."""

import pytest

from shell.panel_layout import (
    corner_clearance,
    free_span,
    layout_corners,
    layout_monitor,
)
from shell.panel_spec import CornerGeometry, CornerRequest, PanelRequest, default_edge

W, H, T, R, GAP = 1920, 1080, 10, 14, 8


def box(corner="bottom-left", edge=None, width=300, height=390, widget="box"):
    edge = edge or default_edge(corner)
    return CornerRequest(widget, corner, edge, width, height, "extended", widget)


def panel(edge="bottom", align="center", length=560, depth=64, widget="dock"):
    return PanelRequest(
        widget, edge, align, 0, None, 0, length, None, None, depth, "extended", widget, length
    )


def lay(*requests, width=W, height=H, thickness=T):
    return layout_monitor(list(requests), width, height, thickness, R, GAP, None, "monitors.X")


def where(geo):
    if geo is None:
        return None
    if isinstance(geo, CornerGeometry):
        return (geo.corner, geo.edge, geo.along, geo.depth)
    return (geo.edge, geo.pos, geo.length)


def placed(*requests, **kw):
    layout = lay(*requests, **kw)
    return [where(p) for p in layout.panels], layout.warnings


# ---- one corner panel -------------------------------------------------------------------


def test_the_default_box_is_placed_as_asked():
    layout = lay(box())
    assert layout.panels == [
        CornerGeometry("box", "bottom-left", "bottom", 300, 290, 380, "extended", "box")
    ]
    assert layout.warnings == []


@pytest.mark.parametrize(
    ("corner", "edge", "expected"),
    [
        ("bottom-left", "bottom", ("bottom-left", "bottom", 300, 380)),
        ("bottom-left", "left", ("bottom-left", "left", 390, 290)),
        ("top-right", "top", ("top-right", "top", 300, 380)),
        ("top-right", "right", ("top-right", "right", 390, 290)),
    ],
)
def test_along_and_depth_follow_the_opening_edge(corner, edge, expected):
    assert placed(box(corner, edge)) == ([expected], [])


def test_a_corner_panel_wider_than_the_edge_is_shrunk():
    assert placed(box(width=2000)) == (
        [("bottom-left", "bottom", 1882, 380)],
        ["monitors.X.panels.0 (box): width 2000 px does not fit the bottom edge; shrunk to 1882"],
    )


def test_a_corner_panel_taller_than_the_other_edge_is_shrunk():
    assert placed(box(height=1200)) == (
        [("bottom-left", "bottom", 300, 1032)],
        ["monitors.X.panels.0 (box): height 1200 px does not fit the left edge; shrunk to 1042"],
    )


def test_a_corner_panel_with_too_little_depth_is_not_shown():
    assert placed(box(height=70), thickness=64) == (
        [None],
        ["monitors.X.panels.0 (box): the bottom-left corner has no room for it; not shown"],
    )


def test_a_narrow_body_is_floored_to_the_minimum_length():
    assert placed(box(width=60)) == ([("bottom-left", "bottom", 70, 380)], [])


def test_a_large_radius_raises_the_minimum_along():
    # R = 40 (the theme allows up to 64): T + R + r = 10 + 40 + 40 = 90 > T + 60, so the side
    # from the lifted arc to the free corner never runs backwards (no folded outline)
    layout = layout_monitor([box(width=60)], W, H, T, 40, GAP, None, "monitors.X")
    assert [where(p) for p in layout.panels] == [("bottom-left", "bottom", 90, 380)]
    assert layout.warnings == []


# ---- several corner panels -----------------------------------------------------------------


def test_a_second_panel_in_the_same_corner_is_not_shown():
    assert placed(box(), box(edge="left", widget="other")) == (
        [("bottom-left", "bottom", 300, 380), None],
        [
            "monitors.X.panels.1 (other): the bottom-left corner already holds "
            "monitors.X.panels.0 (box); not shown"
        ],
    )


def test_two_corner_panels_facing_on_one_edge_keep_their_joins_and_the_gap():
    assert placed(box(), box("bottom-right", width=1700)) == (
        [("bottom-left", "bottom", 300, 380), ("bottom-right", "bottom", 1584, 380)],
        ["monitors.X.panels.1 (box): width 1700 px does not fit the bottom edge; shrunk to 1584"],
    )


def test_a_lifted_corner_arc_limits_the_next_corner_across():
    assert placed(box(), box("top-left", height=800)) == (
        [("bottom-left", "bottom", 300, 380), ("top-left", "top", 300, 652)],
        ["monitors.X.panels.1 (box): height 800 px does not fit the left edge; shrunk to 662"],
    )


def test_two_corner_panels_opening_from_the_same_side_edge():
    assert placed(box(edge="left"), box("top-left", "left", height=700)) == (
        [("bottom-left", "left", 390, 290), ("top-left", "left", 654, 290)],
        ["monitors.X.panels.1 (box): height 700 px does not fit the left edge; shrunk to 654"],
    )


def test_a_corner_squeezed_below_the_minimum_is_not_shown():
    got, warnings = placed(box(width=1840), box("bottom-right"))
    assert got == [("bottom-left", "bottom", 1840, 380), None]
    assert warnings == [  # only the outcome: no "shrunk to 44" for a panel that is not shown
        "monitors.X.panels.1 (box): the bottom-right corner has no room for it; not shown",
    ]


def test_opposite_corner_panels_that_overlap_hide_the_later_one():
    got, warnings = placed(box(width=1200, height=700), box("top-right", width=1200, height=700))
    assert got == [("bottom-left", "bottom", 1200, 690), None]
    assert "monitors.X.panels.1 (box): overlaps monitors.X.panels.0 (box)" in warnings[0]


def test_a_hidden_corner_panel_takes_no_clearance():
    # the top-right panel overlaps the bottom-left one and is hidden: the top edge's end is a
    # plain screen corner again, so the bar sits at 1920 - 24 - 14 - 300 = 1582 (not 384)
    got, warnings = placed(
        box(width=1200, height=700),
        box("top-right", width=1200, height=700),
        panel("top", "end", 300, 56, "bar"),
    )
    assert got == [("bottom-left", "bottom", 1200, 690), None, ("top", 1582, 300)]
    assert len(warnings) == 1 and "panels.1 (box): overlaps monitors.X.panels.0" in warnings[0]


def test_a_hidden_corner_panel_does_not_take_its_corner():
    got, warnings = placed(
        box(width=1200, height=700),
        box("top-right", width=1200, height=700),
        box("top-right", width=300, height=240, widget="small"),
    )
    assert got == [("bottom-left", "bottom", 1200, 690), None, ("top-right", "top", 300, 230)]
    assert len(warnings) == 1


# ---- edge panels beside corner panels ----------------------------------------------------


def test_free_span_takes_the_corner_clearances():
    assert free_span(W, T, R, 64) == (38, 1882)  # unchanged without corner panels
    assert free_span(W, T, R, 64, start=322) == (336, 1882)
    assert free_span(H, T, R, 56, None, 404) == (38, 662)


def test_corner_clearance():
    same = CornerGeometry("box", "bottom-left", "bottom", 300, 290, 380, "extended", "box")
    other = CornerGeometry("box", "bottom-left", "left", 390, 380, 290, "extended", "box")
    assert corner_clearance("bottom", None, T, R, GAP) == 24
    assert corner_clearance("bottom", same, T, R, GAP) == 300 + 14 + 8
    assert corner_clearance("left", same, T, R, GAP) == 24 + 380
    assert corner_clearance("bottom", other, T, R, GAP) == 24 + 290


def test_an_edge_panel_starts_past_the_corner_panel_on_its_edge():
    got, warnings = placed(box(), panel(align="start"))
    assert got[1] == ("bottom", 336, 560) and warnings == []  # 300 + 14 + 8 + 14


def test_an_edge_panel_on_the_other_edge_stays_below_the_lifted_corner_arc():
    got, warnings = placed(box(), panel("left", "end", 300, 56, "bar"))
    assert got[1] == ("left", 362, 300) and warnings == []  # 1080 - (24 + 380) - 14 - 300
    assert placed(panel("left", "end", 300, 56, "bar"))[0] == [("left", 742, 300)]


def test_a_corner_panel_opening_from_the_side_edge_moves_the_other_edge():
    got, _ = placed(box(edge="left"), panel(align="start"), panel("left", "end", 200, 56, "bar"))
    assert got[1] == ("bottom", 328, 560)  # T + R + 290 + 14
    assert got[2] == ("left", 454, 200)  # 1080 - (390 + 14 + 8) - 14 - 200


def test_a_centred_edge_panel_does_not_move_for_a_corner_panel():
    assert placed(box(), panel())[0][1] == ("bottom", 680, 560)


def test_a_fill_panel_fills_up_to_the_corner_panel():
    req = panel(length="fill")
    got, _ = placed(box(), req)
    assert got[1] == ("bottom", 336, 1882 - 336)


def test_corner_panels_win_over_earlier_edge_panels_they_overlap():
    got, warnings = placed(panel("top", "start", 560, 700), box())
    assert got == [None, ("bottom-left", "bottom", 300, 380)]
    assert warnings == [
        "monitors.X.panels.0 (dock): overlaps monitors.X.panels.1 (box) or leaves less than "
        "the minimum gap between their joins; not shown"
    ]


def test_layout_corners_reports_by_config_index():
    got, notes = layout_corners([(4, box()), (9, box())], W, H, T, R, GAP, "monitors.X")
    assert got[4] is not None and got[9] is None and [i for i, _ in notes] == [9]


def test_the_state_is_kept():
    req = CornerRequest("box", "top-left", "top", 300, 390, "collapsed", "box")
    assert lay(req).panels[0].state == "collapsed"


def test_simulate_lays_out_corner_panels_from_a_config(corner_registry, make_config):
    from shell.canvas.scene import CornerShape, PanelShape
    from shell.canvas.simulate import config_shapes

    cfg = make_config(
        monitors={
            "HDMI-A-1": {
                "shell": "edge",
                "panels": [{"widget": "box"}, {"widget": "dock", "align": "start"}],
            }
        }
    )
    shapes, warnings = config_shapes(cfg, "HDMI-A-1", W, H)
    assert shapes == [
        CornerShape("bottom-left", "bottom", 300, 380),
        PanelShape("bottom", 336, 560, 64),
    ]
    assert warnings == []
