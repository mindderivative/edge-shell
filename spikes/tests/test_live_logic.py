import math

import pytest

from spikes.canvas.live import (
    AnimationState,
    dock_box,
    dock_depth_at,
    interval_stats,
    parse_args,
    simulate,
    union_boxes,
)

W, H = 1920, 1080


def contains(outer, inner):
    return (
        outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and outer[2] >= inner[2]
        and outer[3] >= inner[3]
    )


def test_union_none_safe_and_commutative():
    a, b = (10, 20, 30, 40), (5, 25, 50, 35)
    assert union_boxes(None, None) is None
    assert union_boxes(a, None) == a
    assert union_boxes(None, a) == a
    assert union_boxes(a, b) == union_boxes(b, a) == (5, 20, 50, 40)


def test_first_step_invalidates_whole_current_box():
    st = AnimationState(W, H, pad=26)
    step = st.step(0.0)
    assert step.invalidate == step.box
    assert step.box == dock_box(W, H, 0.0, 26)


def test_invalidate_contains_previous_and_current():
    st = AnimationState(W, H, pad=50)
    prev = None
    for i in range(240):
        s = st.step(i * 1 / 60)
        assert contains(s.invalidate, s.box)
        if prev is not None:
            assert contains(s.invalidate, prev)
        prev = s.box


@pytest.mark.parametrize("pad", [0, 2, 26, 50])
def test_box_stays_inside_monitor(pad):
    for i in range(0, 200):
        x0, y0, x1, y1 = dock_box(W, H, dock_depth_at(i / 50), pad)
        assert 0 <= x0 < x1 <= W
        assert 0 <= y0 < y1 <= H


def test_depth_sine_ease_period_2s():
    assert dock_depth_at(0) == pytest.approx(0)
    assert dock_depth_at(1.0) == pytest.approx(64)
    assert dock_depth_at(2.0) == pytest.approx(0, abs=1e-9)
    assert dock_depth_at(0.5) == pytest.approx(32)
    assert dock_depth_at(3.0) == pytest.approx(64)
    for i in range(400):
        assert -1e-9 <= dock_depth_at(i / 100) <= 64 + 1e-9
    assert dock_depth_at(0.3) == pytest.approx(dock_depth_at(2.3))
    assert math.isclose(dock_depth_at(0.25), 64 * (1 - math.cos(math.pi / 4)) / 2)


def test_interval_stats_basic():
    ts = [0, 16000, 33000, 50000, 66000]  # microseconds
    s = interval_stats(ts)
    assert s["frames"] == 5
    assert s["mean_ms"] == pytest.approx(16.5)
    assert s["median_ms"] == pytest.approx(16.5)
    assert s["p95_ms"] == pytest.approx(17.0)
    assert s["fps"] == pytest.approx(4 / 0.066)


@pytest.mark.parametrize("ts", [[], [123]])
def test_interval_stats_too_few_samples(ts):
    s = interval_stats(ts)
    assert s["frames"] == len(ts)
    assert s["mean_ms"] is None and s["median_ms"] is None
    assert s["p95_ms"] is None and s["fps"] is None


def test_simulate_30_frames_runs_headless():
    cfg = parse_args(["--simulate", "30"])
    res = simulate(cfg, 30, (W, H))
    assert res.error is None
    assert len(res.timestamps_us) == 30
    assert len(res.draws_ms) == 30
    assert interval_stats(res.timestamps_us)["mean_ms"] == pytest.approx(16.667, abs=0.01)


def test_simulate_flags_parse():
    cfg = parse_args(["--simulate", "5", "--sim-size", "800x600"])
    assert cfg.simulate == 5 and cfg.sim_size == (800, 600)
    for bad in (["--simulate", "0"], ["--sim-size", "10x"], ["--sim-size", "0x5"]):
        with pytest.raises(SystemExit):
            parse_args(bad)


# ---- content windows / canvas-vs-content sync -------------------------------------------------
from spikes.canvas import live  # noqa: E402
from spikes.canvas.live import (  # noqa: E402
    PanelSpec,
    content_geometry,
    lag_stats,
    marker_inset,
    panel_specs,
    sync_error,
    ticks_between_draws,
)


def test_marker_inset_matches_edgepanel_formula():
    # EdgePanel._place_handle: max(0, int(thickness + d - HANDLE_DEPTH)), HANDLE_DEPTH = 14
    for d in (0, 0.4, 3.9, 4.0, 17.5, 40, 64):
        assert marker_inset(d) == max(0, int(live.T + d - 14))
    assert marker_inset(0) == 0 and marker_inset(64) == 60


@pytest.mark.parametrize(
    ("edge", "size", "anchor"),
    [
        ("bottom", (560 + 28, 10 + 64), "bottom left"),
        ("top", (560 + 28, 10 + 64), "top left"),
        ("left", (10 + 64, 560 + 28), "left top"),
        ("right", (10 + 64, 560 + 28), "right top"),
    ],
)
def test_content_geometry_all_edges(edge, size, anchor):
    spec = PanelSpec("x", edge, 300, 560, 64)
    got_size, got_anchor, margin = content_geometry(spec, W, H)
    assert got_size == size
    assert got_anchor == anchor
    offset = 300 - live.R
    assert str(offset) in margin


def test_panel_specs_positions():
    dock, clock, bar = panel_specs(W)
    assert (dock.edge, dock.pos) == ("bottom", (W - 560) // 2)
    assert content_geometry(dock, W, H)[1:] == (
        "bottom left",
        f"0px 0px 0px {(W - 560) // 2 - live.R}px",
    )
    assert content_geometry(bar, W, H)[0] == (10 + 56, 300 + 28)
    assert content_geometry(clock, W, H)[0] == (168 + 28, 10 + 46)


def test_ticks_between_draws():
    ticks = [10, 20, 30, 40, 50, 60]
    assert ticks_between_draws(ticks, [10, 20, 30, 40, 50, 60]) == [1, 1, 1, 1, 1]
    assert ticks_between_draws(ticks, [10, 30, 60]) == [2, 3]
    assert ticks_between_draws(ticks, []) == []
    assert ticks_between_draws(ticks, [30]) == []
    assert ticks_between_draws([], [10, 20]) == [0]


def test_sync_error():
    assert sync_error([], [])["max_px"] is None
    assert sync_error([(5, 1.0)], [])["n"] == 0
    assert sync_error([(5, 1.0)], [(10, 2.0)])["n"] == 0  # tick before any draw
    ticks = [(10, 10.0), (20, 20.0), (30, 30.0)]
    draws = [(10, 10.0), (25, 20.0)]  # canvas stuck at 20 while the marker went to 30
    e = sync_error(ticks, draws)
    assert e["n"] == 3 and e["max_px"] == pytest.approx(10.0)
    assert e["mean_px"] == pytest.approx(20 / 3)
    assert sync_error([(10, 3.0)], [(10, 3.0)])["max_px"] == 0


def test_lag_stats_empty_and_single():
    s = lag_stats([], [])
    assert s["between_mean"] is None and s["sync"]["n"] == 0
    s = lag_stats([(1, 1.0)], [(1, 1.0)])
    assert s["between_min"] is None and s["sync"]["max_px"] == 0


def test_simulate_reports_zero_lag():
    cfg = parse_args(["--simulate", "40"])
    res = simulate(cfg, 40, (W, H))
    lag = lag_stats(res.ticks, res.draws)
    assert lag["content_ticks"] == lag["canvas_draws"] == 40
    assert lag["between_hist"] == {1: 39}
    assert lag["sync"]["max_px"] == 0


def test_stack_order_flag():
    assert parse_args([]).stack_order == "canvas-first"
    assert parse_args(["--stack-order", "content-first"]).stack_order == "content-first"
    with pytest.raises(SystemExit):
        parse_args(["--stack-order", "x"])
