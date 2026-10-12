"""Headless cost benchmark of the final effects: damaged-region redraw of the uniform shadow.

Scene: 1920x1080 ARGB32 layer surface with frame, corners, dock (bottom, 560x64, ANIMATED 0 ->
64 -> 0), clock (top, 168x46) and system bar (right, pos 600, length 300, depth 56), both static
at full depth. Border 2 px, shadow colour alpha 0.35. Every measured frame is `draw_scene` with
`clip` = dock bbox + reach + border, plus `surface.flush()`, timed with `time.perf_counter`.
20 warm-up frames, then 200 measured frames. The one-time FULL redraw is timed too.

Run: scripts/py -m spikes.canvas.bench   (headless: image surfaces only, no window).
"""

from __future__ import annotations

import json
import math
import pathlib
import statistics
import time

import cairo

from spikes.canvas import effects
from spikes.canvas.effects import draw_scene, reach_px
from spikes.canvas.outline import Panel

W, H, T, R = 1920, 1080, 10, 14
MASS = (0.04, 0.05, 0.05, 1.0)
BORDER = (2, (0.56, 0.83, 0.71, 1.0))
SHADOW_RGBA = (0.0, 0.0, 0.0, 0.35)
DOCK_LEN, DOCK_FULL = 560, 64
DOCK_POS = (W - DOCK_LEN) // 2
WARMUP, FRAMES = 20, 200
PERCENTS = (25, 50, 75, 100)
TARGET_MS = 8.0


def depth_at(i: int) -> float:
    """Dock depth for frame i: two 0 -> 64 -> 0 cycles per 200 frames (triangle wave)."""
    ph = (i % 100) / 100.0
    return DOCK_FULL * (1 - abs(2 * ph - 1))


def panels(dock_depth: float) -> list[Panel]:
    return [
        ("bottom", DOCK_POS, DOCK_LEN, DOCK_FULL, dock_depth),
        ("top", (W - 168) // 2, 168, 46, 46.0),
        ("right", 600, 300, 56, 56.0),
    ]


def damage(reach: int) -> tuple[int, int, int, int]:
    """Dock bbox at full depth + fillet radius, expanded by shadow reach + border; even-aligned."""
    pad = reach + BORDER[0]
    x0 = DOCK_POS - R - pad
    x1 = DOCK_POS + DOCK_LEN + R + pad
    y0 = H - T - DOCK_FULL - pad
    x0, y0 = max(0, x0 - x0 % 2), max(0, y0 - y0 % 2)
    x1 = min(W, x1 + x1 % 2)
    return x0, y0, x1 - x0, H - y0


def stats(ms: list[float]) -> dict:
    s = sorted(ms)
    return {
        "median_ms": statistics.median(ms),
        "p95_ms": s[min(len(s) - 1, math.ceil(0.95 * len(s)) - 1)],
        "max_ms": s[-1],
        "frames": len(ms),
    }


def bench_damaged(pct: int, max_px: int | None = None) -> dict:
    """`max_px`: temporarily set MAX_REACH_PX (to bench absolute reaches larger than 48 at 100%)."""
    saved = effects.MAX_REACH_PX
    if max_px is not None:
        effects.MAX_REACH_PX = max_px
    try:
        return _bench_damaged(pct)
    finally:
        effects.MAX_REACH_PX = saved


def _bench_damaged(pct: int) -> dict:
    reach = reach_px(pct)
    shadow = (pct, SHADOW_RGBA)
    rect = damage(reach)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(surf)
    draw_scene(cr, W, H, T, R, panels(0), MASS, border=BORDER, shadow=shadow)
    ms = []
    for i in range(WARMUP + FRAMES):
        t0 = time.perf_counter()
        draw_scene(cr, W, H, T, R, panels(depth_at(i)), MASS, BORDER, shadow, clip=rect)
        surf.flush()
        if i >= WARMUP:
            ms.append((time.perf_counter() - t0) * 1000)
    return {"elevation_pct": pct, "reach_px": reach, "clip_px": rect[2] * rect[3], **stats(ms)}


def bench_full(pct: int, repeats: int = 20) -> dict:
    shadow = (pct, SHADOW_RGBA)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(surf)
    ms = []
    for i in range(WARMUP // 2 + repeats):
        t0 = time.perf_counter()
        draw_scene(cr, W, H, T, R, panels(depth_at(i)), MASS, BORDER, shadow)
        surf.flush()
        if i >= WARMUP // 2:
            ms.append((time.perf_counter() - t0) * 1000)
    return {"elevation_pct": pct, "reach_px": reach_px(pct), "clip_px": W * H, **stats(ms)}


def main() -> None:
    rows = [bench_damaged(p) for p in PERCENTS]
    rows += [bench_damaged(100, max_px=px) for px in (64, 96)]  # absolute reaches (calibration)
    full = bench_full(100)
    print("| elevation | reach px | median ms | p95 ms | max ms | clip px | vs 8 ms |")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        verdict = "PASS" if r["median_ms"] <= TARGET_MS else "FAIL"
        print(
            f"| {r['elevation_pct']}% | {r['reach_px']} | {r['median_ms']:.3f} | "
            f"{r['p95_ms']:.3f} | {r['max_ms']:.3f} | {r['clip_px']} | {verdict} |"
        )
    print(
        f"full redraw at 100% (48 px), 1920x1080: median {full['median_ms']:.2f} ms, "
        f"p95 {full['p95_ms']:.2f}, max {full['max_ms']:.2f}"
    )
    out = pathlib.Path(__file__).resolve().parents[1] / "out"
    out.mkdir(exist_ok=True)
    (out / "bench_final.json").write_text(
        json.dumps({"damaged": rows, "full": full, "target_ms": TARGET_MS}, indent=2)
    )


if __name__ == "__main__":
    main()
