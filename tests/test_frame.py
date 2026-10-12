"""Layer-shell setup of the invisible zone strips (no window is created)."""

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

from shell.frame import EDGES, STRIP_LAYER, strip_window  # noqa: E402


@pytest.mark.parametrize("edge", EDGES)
def test_strips_reserve_their_size_take_no_input_and_sit_below_the_canvas(edge):
    w = strip_window(edge)
    assert w["exclusivity"] == "auto"  # "normal" would reserve only 1 px
    assert w["pass_through"] is True
    assert w["layer"] == STRIP_LAYER == "bottom"
    assert edge in w["anchor"] and len(w["anchor"].split()) == 3
