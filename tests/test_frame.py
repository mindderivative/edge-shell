"""Layer-shell setup of the invisible zone strips (no window is created)."""

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

from shell.frame import EDGES, STRIP_LAYER, strip_size, strip_window  # noqa: E402


@pytest.mark.parametrize("edge", EDGES)
def test_strips_reserve_their_size_take_no_input_and_sit_below_the_canvas(edge):
    w = strip_window(edge)
    assert w["exclusivity"] == "auto"  # "normal" would reserve only 1 px
    assert w["pass_through"] is True
    assert w["layer"] == STRIP_LAYER == "bottom"
    assert edge in w["anchor"] and len(w["anchor"].split()) == 3


@pytest.mark.parametrize("edge", EDGES)
def test_strip_size_is_thickness_plus_the_outer_border(edge, make_config):
    off = make_config().theme
    on = make_config(theme={"border": {"enabled": True, "width": 4}}).theme
    across = 1 if edge in ("top", "bottom") else 0
    along = 1 - across
    assert strip_size(edge, off)[across] == 10 and strip_size(edge, off)[along] == -1
    assert strip_size(edge, on)[across] == 14 and strip_size(edge, on)[along] == -1
