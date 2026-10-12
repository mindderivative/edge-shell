import json

import pytest

from shell.outputs import Output, match_geometries, parse_kscreen


def out(name, x, y, w, h, scale=1, enabled=True):
    return {
        "name": name,
        "enabled": enabled,
        "pos": {"x": x, "y": y},
        "size": {"width": w, "height": h},
        "scale": scale,
    }


SAMPLE = json.dumps(
    {
        "outputs": [
            out("DP-1", 0, 1080, 1920, 1080),
            out("HDMI-A-1", 0, 0, 1920, 1080),
            out("DP-2", 0, 0, 800, 600, enabled=False),
        ]
    }
)


def test_parse_keeps_enabled_outputs_only():
    assert parse_kscreen(SAMPLE) == [
        Output("DP-1", 0, 1080, 1920, 1080),
        Output("HDMI-A-1", 0, 0, 1920, 1080),
    ]


def test_logical_size_divides_by_scale():
    text = json.dumps(
        {"outputs": [out("A", 0, 0, 3840, 2160, scale=2), out("B", 0, 0, 2880, 1620, scale=1.5)]}
    )
    a, b = parse_kscreen(text)
    assert (a.width, a.height) == (1920, 1080)
    assert (b.width, b.height) == (1920, 1080)


def test_match_by_geometry_regardless_of_gdk_order():
    outs = parse_kscreen(SAMPLE)
    assert match_geometries([(0, 0, 1920, 1080), (0, 1080, 1920, 1080)], outs) == [
        "HDMI-A-1",
        "DP-1",
    ]
    assert match_geometries([(0, 1080, 1920, 1080), (0, 0, 1920, 1080)], outs) == [
        "DP-1",
        "HDMI-A-1",
    ]


def test_match_falls_back_to_position():
    assert match_geometries([(0, 0, 1280, 720)], parse_kscreen(SAMPLE)) == ["HDMI-A-1"]


def test_unmatched_is_none():
    assert match_geometries([(5000, 5000, 100, 100)], parse_kscreen(SAMPLE)) == [None]


def test_invalid_json_is_a_value_error():
    with pytest.raises(ValueError):
        parse_kscreen("not json")
