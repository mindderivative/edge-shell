import pytest

from spikes.canvas.effects import MAX_REACH_PX
from spikes.canvas.live import parse_args


def test_defaults():
    s = parse_args([])
    assert s.output == "HDMI-A-1"
    assert s.elevation == 50
    assert s.shadow_rgba == pytest.approx((0, 0, 0, 0x80 / 255))
    assert s.border_width == 2
    assert s.border_rgba[3] == 1.0
    assert s.content_layer == "top"
    assert s.raise_ms == 500
    assert s.seconds == 10
    assert s.selftest is False


def test_rejects_seconds_above_cap():
    with pytest.raises(SystemExit):
        parse_args(["--seconds", "11"])


def test_rejects_non_positive_seconds():
    with pytest.raises(SystemExit):
        parse_args(["--seconds", "0"])


def test_accepts_shorter_run():
    assert parse_args(["--seconds", "3"]).seconds == 3


def test_rejects_other_outputs():
    for out in ("DP-1", "eDP-1", ""):
        with pytest.raises(SystemExit):
            parse_args(["--output", out])


@pytest.mark.parametrize("value", ["-1", "101", "250"])
def test_rejects_elevation_out_of_range(value):
    with pytest.raises(SystemExit):
        parse_args(["--elevation", value])


def test_colours_rrggbb_and_rrggbbaa():
    s = parse_args(["--shadow-color", "#ff0000", "--border-color", "#00ff0080"])
    assert s.shadow_rgba == (1.0, 0.0, 0.0, 1.0)
    assert s.border_rgba == pytest.approx((0.0, 1.0, 0.0, 0x80 / 255))


def test_rejects_bad_colour():
    with pytest.raises(SystemExit):
        parse_args(["--shadow-color", "red"])


def test_rejects_bad_layer_and_negative_values():
    for args in (["--content-layer", "bottom"], ["--border-width", "-1"], ["--raise-ms", "-5"]):
        with pytest.raises(SystemExit):
            parse_args(args)


def test_reach_px_at_0_50_100():
    assert parse_args(["--elevation", "0"]).reach_px == 0
    assert parse_args(["--elevation", "50"]).reach_px == MAX_REACH_PX // 2
    assert parse_args(["--elevation", "100"]).reach_px == MAX_REACH_PX
