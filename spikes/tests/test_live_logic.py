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
