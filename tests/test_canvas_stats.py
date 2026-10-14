import pytest

from shell.canvas.simulate import FakeClock, default_shapes, main, simulate
from shell.canvas.stats import StatsRecorder, interval_stats, pct, ticks_between_draws


def test_pct():
    assert pct([3, 1, 2], 0.5) == 2
    assert pct([], 0.5) != pct([], 0.5)  # nan


def test_interval_stats_basic():
    s = interval_stats([0, 16000, 33000, 50000, 66000])
    assert s["frames"] == 5
    assert s["mean_ms"] == pytest.approx(16.5)
    assert s["median_ms"] == pytest.approx(16.5)
    assert s["p95_ms"] == pytest.approx(17.0)
    assert s["fps"] == pytest.approx(1000 / 16.5)


def test_interval_stats_skips_idle_gaps():
    s = interval_stats([0, 16667, 33334, 1_000_000, 1_016_667])
    assert s["median_ms"] == pytest.approx(16.667, abs=0.01)
    assert s["mean_ms"] == pytest.approx(16.667, abs=0.01)


@pytest.mark.parametrize("ts", [[], [123]])
def test_interval_stats_too_few_samples(ts):
    s = interval_stats(ts)
    assert s["frames"] == len(ts)
    assert s["mean_ms"] is None and s["fps"] is None


def test_ticks_between_draws():
    ticks = [10, 20, 30, 40, 50, 60]
    assert ticks_between_draws(ticks, [10, 20, 30, 40, 50, 60]) == [1, 1, 1, 1, 1]
    assert ticks_between_draws(ticks, [10, 30, 60]) == [2, 3]
    assert ticks_between_draws(ticks, []) == []
    assert ticks_between_draws([], [10, 20]) == [0]


def test_recorder_splits_full_and_damaged_draws():
    now = iter(range(0, 1000, 10))
    rec = StatsRecorder(lambda: next(now))
    rec.on_draw(5.0, True)
    rec.on_tick(1, 3.0)
    rec.on_draw(1.0, False)
    assert rec.full_draw_ms == [5.0] and rec.draw_ms == [1.0]
    assert rec.ticks[1] == [10] and rec.draw_ts == [0, 20]
    text = "\n".join(rec.report(2.0, 0.5))
    assert "canvas damaged draws: 1" in text and "canvas full draws: 1" in text
    assert "panel 1: 1 ticks; ticks between canvas draws {1: 1}" in text
    assert "0.25 of one core" in text


def test_report_without_ticks():
    assert "no panel animated" in "\n".join(StatsRecorder(lambda: 0).report(1.0, 0.0))


def test_simulation_draws_once_per_tick(make_config):
    clock = FakeClock()
    rec = StatsRecorder(clock.get_frame_time)
    theme = make_config(theme={"shadow": {"enabled": True}}).theme
    res = simulate(theme, (800, 600), default_shapes(800, 600)[:1], 40, recorder=rec, clock=clock)
    assert res.full_draws == 1 and len(rec.full_draw_ms) == 1
    assert len(rec.draw_ms) == res.draws - 1
    between = ticks_between_draws(rec.ticks[0], rec.draw_ts)
    assert set(between) <= {0, 1}  # never a skipped panel frame
    assert interval_stats(rec.ticks[0])["median_ms"] == pytest.approx(16.667, abs=0.01)


@pytest.mark.parametrize("size", [(1920, 1080), (640, 400)])
def test_default_shapes_fit_the_simulated_surface(size):
    from shell.panel_layout import layout_monitor
    from shell.panel_spec import PanelRequest

    w, h = size
    shapes = default_shapes(w, h)
    requests = [
        PanelRequest(
            "p", s.edge, "start", 0, s.pos, 0, s.length, None, None, s.depth, "extended", "p", 60
        )
        for s in shapes
    ]
    layout = layout_monitor(requests, w, h, 10, 14, 8)
    assert layout.warnings == []  # nothing clamped, shrunk or hidden
    assert [(p.pos, p.length) for p in layout.panels] == [(s.pos, s.length) for s in shapes]
    if size == (1920, 1080):  # the registered widget defaults
        assert [(s.pos, s.length) for s in shapes] == [(680, 560), (876, 168), (600, 300)]


def test_cli_prints_a_report(capsys):
    assert main(["--frames", "20", "--size", "640x400", "--elevation", "50", "--border", "2"]) == 0
    out = capsys.readouterr().out
    assert "=== edge-shell canvas stats ===" in out
    assert "panel 2:" in out  # all three panels animated
    assert "simulated 20 frames at 640x400" in out


@pytest.mark.parametrize("argv", [["--size", "10x"], ["--elevation", "101"], ["--border", "0"]])
def test_cli_rejects_bad_input(argv):
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 2


def test_config_shapes_lays_out_the_monitors_panels(fake_registry, make_config):
    from shell.canvas.simulate import config_shapes

    cfg = make_config(
        monitors={
            "HDMI-A-1": {
                "shell": "edge",
                "panels": [
                    {"panel": "edge", "name": "dock", "widget": "dock", "align": "end"},
                    {
                        "panel": "edge",
                        "name": "dock 2",
                        "widget": "dock",
                        "pos": 1300,
                    },  # dropped onto the first: not shown
                ],
            }
        }
    )
    shapes, warnings = config_shapes(cfg, "HDMI-A-1", 1920, 1080)
    assert [(s.edge, s.pos, s.length, s.depth) for s in shapes] == [("bottom", 1322, 560, 64)]
    assert warnings[0].startswith("monitors.HDMI-A-1.panels.1 (dock): overlaps")


def test_cli_simulates_a_config(tmp_path, capsys):
    pytest.importorskip("gi")
    pytest.importorskip("fabric")
    path = tmp_path / "layout.toml"
    path.write_text(
        '[theme.shadow]\nenabled = true\n[monitors.HDMI-A-1]\nshell = "edge"\n'
        '[[monitors.HDMI-A-1.panels]]\npanel = "edge"\nname = "dock"\nwidget = "dock"\n'
        'align = "end"\n'
        '[[monitors.HDMI-A-1.panels]]\npanel = "edge"\nname = "clock"\nwidget = "clock"\n'
        'length = "fill"\n'
    )
    assert main(["--config", str(path), "--frames", "20", "--size", "1280x720"]) == 0
    out = capsys.readouterr().out
    assert "panel 1:" in out and "panel 2:" not in out  # exactly the two configured panels
    assert "simulated 20 frames at 1280x720" in out and "layout:" not in out


def test_cli_reports_a_bad_config(tmp_path):
    pytest.importorskip("gi")
    pytest.importorskip("fabric")
    path = tmp_path / "bad.toml"
    path.write_text(
        '[[monitors.HDMI-A-1.panels]]\npanel = "edge"\nname = "dock"\nwidget = "dock"\n'
        'length = "half"\n'
    )
    with pytest.raises(SystemExit) as exc:
        main(["--config", str(path), "--frames", "1"])
    assert exc.value.code == 2


def test_cli_reports_an_unknown_widget(tmp_path, capsys):
    pytest.importorskip("gi")
    pytest.importorskip("fabric")
    path = tmp_path / "unknown.toml"
    path.write_text(
        '[monitors.HDMI-A-1]\nshell = "edge"\n[[monitors.HDMI-A-1.panels]]\n'
        'panel = "edge"\nname = "nope"\nwidget = "nope"\n'
    )
    with pytest.raises(SystemExit) as exc:  # a usage error, not a traceback
        main(["--config", str(path), "--frames", "1"])
    assert exc.value.code == 2
    assert "unknown widget 'nope'" in capsys.readouterr().err
