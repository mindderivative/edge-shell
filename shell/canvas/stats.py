"""Frame pacing, canvas draw cost and canvas-vs-panel cadence, for `main.py --stats` and
`python -m shell.canvas.simulate`. Pure. `pct`, `interval_stats` and `ticks_between_draws` are
the shape-canvas spike's (spikes/canvas/live.py at 872eff9), so live numbers compare with
docs/superpowers/findings/2026-10-12-shape-canvas-spike.md."""

from __future__ import annotations

import statistics
from bisect import bisect_right
from collections import Counter, defaultdict
from collections.abc import Callable, Hashable

GAP_US = 100_000  # tick intervals longer than this are idle time between animations


def pct(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(q * (len(s) - 1) + 0.5))] if s else float("nan")


def interval_stats(timestamps_us: list[int]) -> dict:
    """Frame-interval stats from per-frame timestamps (us); None values when there is no
    interval. Gaps longer than GAP_US (no animation running) are left out."""
    iv = [
        (b - a) / 1000
        for a, b in zip(timestamps_us, timestamps_us[1:], strict=False)
        if 0 < b - a <= GAP_US
    ]
    out = {"frames": len(timestamps_us), "mean_ms": None, "median_ms": None, "p95_ms": None}
    out["fps"] = None
    if iv:
        out["mean_ms"] = statistics.fmean(iv)
        out["median_ms"] = statistics.median(iv)
        out["p95_ms"] = pct(iv, 0.95)
        out["fps"] = 1000 / out["mean_ms"]
    return out


def ticks_between_draws(tick_ts: list[int], draw_ts: list[int]) -> list[int]:
    """For each pair of consecutive canvas draws, the number of panel ticks in (prev, cur]."""
    ticks, draws = sorted(tick_ts), sorted(draw_ts)
    return [
        bisect_right(ticks, cur) - bisect_right(ticks, prev)
        for prev, cur in zip(draws, draws[1:], strict=False)
    ]


class StatsRecorder:
    """Implements shell.canvas.painter.Recorder. `now_us` is the clock: GLib.get_monotonic_time
    live, the fake frame clock in the simulation."""

    def __init__(self, now_us: Callable[[], int]):
        self.now_us = now_us
        self.ticks: dict[Hashable, list[int]] = defaultdict(list)
        self.draw_ts: list[int] = []
        self.draw_ms: list[float] = []  # damaged-region draws
        self.full_draw_ms: list[float] = []  # first draw, theme changes, resizes

    def on_tick(self, key: Hashable, depth: float) -> None:
        self.ticks[key].append(self.now_us())

    def on_draw(self, duration_ms: float, full: bool) -> None:
        (self.full_draw_ms if full else self.draw_ms).append(duration_ms)
        self.draw_ts.append(self.now_us())

    def report(self, wall_s: float, cpu_s: float) -> list[str]:
        lines = ["=== edge-shell canvas stats ==="]
        busiest = max(self.ticks, key=lambda k: len(self.ticks[k]), default=None)
        if busiest is None:
            lines.append("no panel animated (no ticks recorded)")
        else:
            st = interval_stats(self.ticks[busiest])
            lines.append(
                f"panel ticks (busiest panel): {st['frames']}; frame interval ms: mean "
                f"{_fmt(st['mean_ms'])} median {_fmt(st['median_ms'])} p95 {_fmt(st['p95_ms'])}"
                f"; fps while animating {_fmt(st['fps'], '.1f')}"
            )
        for label, values in (("damaged", self.draw_ms), ("full", self.full_draw_ms)):
            if values:
                lines.append(
                    f"canvas {label} draws: {len(values)}; ms median "
                    f"{statistics.median(values):.2f} p95 {pct(values, 0.95):.2f} "
                    f"max {max(values):.2f}"
                )
            else:
                lines.append(f"canvas {label} draws: 0")
        for key in sorted(self.ticks, key=str):
            hist = Counter(ticks_between_draws(self.ticks[key], self.draw_ts))
            lines.append(
                f"panel {key}: {len(self.ticks[key])} ticks; ticks between canvas draws "
                f"{dict(sorted(hist.items()))} (0 = idle redraw, 1 = in step, 2+ = skipped)"
            )
        load = cpu_s / wall_s if wall_s > 0 else None
        lines.append(f"CPU: {cpu_s:.2f} s over {wall_s:.2f} s wall = {_fmt(load)} of one core")
        return lines


def _fmt(v, spec: str = ".2f") -> str:
    return "n/a" if v is None else format(v, spec)
