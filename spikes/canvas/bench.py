"""Headless cost benchmark of the shape canvas: full vs damaged-region vs cached shadow.

Scene: ARGB32 layer surface with frame, corners, dock (bottom, 560x64, ANIMATED), clock (top,
168x46) and system bar (right, pos 600, length 300, depth 56), both static at full depth.
Every measured frame includes the drawing AND `surface.flush()` (cairo image operations may be
deferred) and is timed with `time.perf_counter`. 20 warm-up frames, then 200 measured frames;
the dock depth runs 0 -> 64 -> 0 twice over the 200 frames (the warm-up continues the sequence).

Run: scripts/py spikes/canvas/bench.py   (headless: image surfaces only, no window).
"""

from __future__ import annotations

import json
import math
import pathlib
import platform
import statistics
import time
from collections.abc import Callable

import cairo

from shell import geometry
from spikes.canvas.effects import draw_border, draw_shadow
from spikes.canvas.outline import _MATRICES, Panel, fill_mass, outline_path

T, R = 10, 14
MASS = (0.04, 0.05, 0.05, 1.0)
ACCENT = (0.56, 0.83, 0.71, 1.0)
OPACITY = 0.55
SHADOW_RGB = (0.0, 0.0, 0.0)
BORDER_W = 2
DOCK_LEN, DOCK_FULL = 560, 64
WARMUP, FRAMES = 20, 200
LAYERS = (8, 16, 24)
TARGET_MS = 8.0


def depth_at(i: int) -> float:
    """Dock depth for frame i: two 0 -> 64 -> 0 cycles per 200 frames (triangle wave)."""
    ph = (i % 100) / 100.0
    return DOCK_FULL * (1 - abs(2 * ph - 1))


class Scene:
    def __init__(self, w: int, h: int) -> None:
        self.w, self.h = w, h
        self.dock_pos = (w - DOCK_LEN) // 2

    def panels(self, dock_depth: float) -> list[Panel]:
        return [
            ("bottom", self.dock_pos, DOCK_LEN, DOCK_FULL, dock_depth),
            ("top", (self.w - 168) // 2, 168, 46, 46.0),
            ("right", 600, 300, 56, 56.0),
        ]

    def damage(self, reach: float) -> tuple[int, int, int, int]:
        """Dock bounding box at full depth + fillet radius, expanded by shadow reach + border.

        Even-aligned (so the half-res variant maps 1:1); clamped to the surface.
        """
        pad = math.ceil(reach) + BORDER_W
        x0 = self.dock_pos - R - pad
        x1 = self.dock_pos + DOCK_LEN + R + pad
        y0 = self.h - T - DOCK_FULL - pad
        x0, y0 = max(0, x0 - x0 % 2), max(0, y0 - y0 % 2)
        x1, y1 = min(self.w, x1 + x1 % 2), self.h
        return x0, y0, x1 - x0, y1 - y0


def new_surface(w: int, h: int) -> cairo.ImageSurface:
    return cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)


def clear_region(cr: cairo.Context, rect: tuple[int, int, int, int] | None) -> None:
    cr.save()
    cr.set_operator(cairo.OPERATOR_CLEAR)
    if rect is None:
        cr.paint()
    else:
        cr.rectangle(*rect)
        cr.fill()
    cr.restore()


def percentile(sorted_ms: list[float], p: float) -> float:
    return sorted_ms[min(len(sorted_ms) - 1, int(math.ceil(p * len(sorted_ms))) - 1)]


def measure(frame: Callable[[float], None]) -> dict:
    """Time `frame(depth)` (must include its own flush); WARMUP then FRAMES measured frames."""
    for i in range(WARMUP):
        frame(depth_at(i))
    ms = []
    for i in range(WARMUP, WARMUP + FRAMES):
        d = depth_at(i)
        t0 = time.perf_counter()
        frame(d)
        ms.append((time.perf_counter() - t0) * 1000)
    s = sorted(ms)
    return {
        "median_ms": statistics.median(ms),
        "p95_ms": percentile(s, 0.95),
        "max_ms": s[-1],
        "frames": len(ms),
    }


# ---- drawing building blocks -------------------------------------------------------------


def bump_path(cr: cairo.Context, scene: Scene, d: float) -> None:
    """Open path of the dock's S-shaped bump only (fillet, side, top, side, fillet)."""
    w, h = scene.w, scene.h
    u0 = w - scene.dock_pos - DOCK_LEN  # bottom edge: pos grows against the clockwise walk
    u1 = u0 + DOCK_LEN
    t = T
    r = geometry.join_radius(d, R)
    cr.save()
    cr.transform(_MATRICES["bottom"](w, h))
    cr.new_path()
    cr.move_to(u0 - r, t)
    cr.arc(u0 - r, t + r, r, -0.5 * math.pi, 0)
    cr.line_to(u0, t + d - r)
    cr.arc_negative(u0 + r, t + d - r, r, math.pi, 0.5 * math.pi)
    cr.line_to(u1 - r, t + d)
    cr.arc_negative(u1 - r, t + d - r, r, 0.5 * math.pi, 0)
    cr.line_to(u1, t + r)
    cr.arc(u1 + r, t + r, r, math.pi, 1.5 * math.pi)
    cr.restore()


def draw_dock_shadow_only(
    cr: cairo.Context, scene: Scene, panels: list[Panel], d: float, layers: int
) -> None:
    """Stacked-stroke shadow of the dock bump ALONE, clipped to the current desktop region."""
    from spikes.canvas.effects import shadow_alphas

    alphas = shadow_alphas(layers, OPACITY)
    cr.save()
    cr.new_path()
    outline_path(cr, scene.w, scene.h, T, R, panels)
    cr.clip()
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.set_line_cap(cairo.LINE_CAP_BUTT)
    for i in range(layers, 0, -1):
        bump_path(cr, scene, d)
        cr.set_line_width(2 * i)
        cr.set_source_rgba(*SHADOW_RGB, alphas[i - 1])
        cr.stroke()
    cr.restore()


def stack_strokes(
    cr: cairo.Context, scene: Scene, panels: list[Panel], layers: int, step: float
) -> None:
    """Same strokes as `draw_shadow` but WITHOUT its desktop-region clip (caller clips)."""
    from spikes.canvas.effects import shadow_alphas

    alphas = shadow_alphas(layers, OPACITY)
    cr.save()
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    for i in range(layers, 0, -1):
        cr.new_path()
        outline_path(cr, scene.w, scene.h, T, R, panels)
        cr.set_line_width(2 * i * step)
        cr.set_source_rgba(*SHADOW_RGB, alphas[i - 1])
        cr.stroke()
    cr.restore()


def full_scene(
    cr: cairo.Context, scene: Scene, panels: list[Panel], layers: int, step: float = 1.0
) -> None:
    if layers:
        draw_shadow(cr, scene.w, scene.h, T, R, panels, layers, OPACITY, SHADOW_RGB, step=step)
    fill_mass(cr, scene.w, scene.h, T, R, panels, MASS)
    draw_border(cr, scene.w, scene.h, T, R, panels, BORDER_W, ACCENT)


# ---- scenarios -----------------------------------------------------------------------------


def make_full(scene: Scene, layers: int, border: bool = True, step: float = 1.0):
    surf = new_surface(scene.w, scene.h)
    cr = cairo.Context(surf)

    def frame(d: float) -> None:
        panels = scene.panels(d)
        clear_region(cr, None)
        if layers:
            draw_shadow(cr, scene.w, scene.h, T, R, panels, layers, OPACITY, SHADOW_RGB, step=step)
        fill_mass(cr, scene.w, scene.h, T, R, panels, MASS)
        if border:
            draw_border(cr, scene.w, scene.h, T, R, panels, BORDER_W, ACCENT)
        surf.flush()

    return surf, frame


def make_damaged(scene: Scene, layers: int, step: float = 1.0, half: bool = False, parts="smb"):
    """Clip = dock bbox + shadow reach + border; clear it; redraw shadow, mass, border inside.

    `half`: the shadow strokes are rendered at half resolution into a scratch surface and scaled
    up (bilinear) into the clip; mass and border stay full resolution.
    `parts`: which of s(hadow) m(ass) b(order) to draw (component breakdown only).
    """
    surf = new_surface(scene.w, scene.h)
    cr = cairo.Context(surf)
    rect = scene.damage(layers * step)
    x, y, cw, ch = rect
    scratch = new_surface(cw // 2, ch // 2) if half else None
    scr = cairo.Context(scratch) if half else None
    # prime the retained surface with the full scene so only the clip needs redrawing later
    clear_region(cr, None)
    full_scene(cr, scene, scene.panels(0), layers, step)

    def frame(d: float) -> None:
        panels = scene.panels(d)
        cr.save()
        cr.rectangle(*rect)
        cr.clip()
        clear_region(cr, None)  # CLEAR paint, limited by the clip
        if "s" in parts and layers:
            if half:
                clear_region(scr, None)
                scr.save()
                scr.scale(0.5, 0.5)
                scr.translate(-x, -y)
                stack_strokes(scr, scene, panels, layers, step)
                scr.restore()
                cr.save()
                # clip to the desktop region at FULL resolution (a half-res clip would bleed the
                # edge pixels towards transparent under bilinear scaling and dent the falloff)
                cr.new_path()
                outline_path(cr, scene.w, scene.h, T, R, panels)
                cr.clip()
                cr.translate(x, y)
                cr.scale(2, 2)
                cr.set_source_surface(scratch, 0, 0)
                pat = cr.get_source()
                pat.set_filter(cairo.FILTER_BILINEAR)
                pat.set_extend(cairo.EXTEND_PAD)
                cr.paint()
                cr.restore()
            else:
                draw_shadow(
                    cr, scene.w, scene.h, T, R, panels, layers, OPACITY, SHADOW_RGB, step=step
                )
        if "m" in parts:
            fill_mass(cr, scene.w, scene.h, T, R, panels, MASS)
        if "b" in parts:
            draw_border(cr, scene.w, scene.h, T, R, panels, BORDER_W, ACCENT)
        cr.restore()
        surf.flush()

    return surf, frame, rect


def make_cached(scene: Scene, layers: int):
    """Cached static shadow + per-frame damaged-region redraw of the animating panel only.

    CACHED (once): an ARGB32 W x H surface holding the stacked-stroke shadow of the scene with
    the dock at depth 0 (i.e. frame, corners, clock and bar: everything static). Mass and border
    are NOT cached.
    PER FRAME, clipped to the damaged rect: paint the cache with OPERATOR_SOURCE (replaces the
    clear + all static strokes), then stroke the stacked shadow of the dock bump ALONE (clipped
    to the current desktop region) over it, then fill the mass and stroke the border.
    Approximation: shadow(union) = max(shadow(parts)) (alpha is monotone in the distance to the
    nearest outline) but OVER gives 1-(1-a)(1-b) where the frame's and the dock's shadows overlap
    (only around the two concave fillets): a bit darker there; the error is measured in `check`.
    INVALIDATED when: monitor size, T/R, layers/opacity/colour/offset change, any static panel
    (clock, bar, other docks) changes geometry/depth, or the dock's edge/pos/length changes (the
    dock-only stroke follows depth for free). Theme (shadow colour) change also rebuilds it.
    """
    surf = new_surface(scene.w, scene.h)
    cr = cairo.Context(surf)
    cache = new_surface(scene.w, scene.h)
    t0 = time.perf_counter()
    ccr = cairo.Context(cache)
    draw_shadow(ccr, scene.w, scene.h, T, R, scene.panels(0), layers, OPACITY, SHADOW_RGB)
    cache.flush()
    build_ms = (time.perf_counter() - t0) * 1000
    rect = scene.damage(layers)
    clear_region(cr, None)
    full_scene(cr, scene, scene.panels(0), layers)

    def frame(d: float) -> None:
        panels = scene.panels(d)
        cr.save()
        cr.rectangle(*rect)
        cr.clip()
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_surface(cache, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        if d > 0.5:
            draw_dock_shadow_only(cr, scene, panels, d, layers)
        fill_mass(cr, scene.w, scene.h, T, R, panels, MASS)
        draw_border(cr, scene.w, scene.h, T, R, panels, BORDER_W, ACCENT)
        cr.restore()
        surf.flush()

    return surf, frame, rect, build_ms


def make_blit(scene: Scene, layers: int):
    """Blit the damaged rect of the layer surface to a destination surface (stand-in for GTK)."""
    src, _, rect = make_damaged(scene, layers)
    dst = new_surface(scene.w, scene.h)
    dcr = cairo.Context(dst)

    def frame(_d: float) -> None:
        dcr.save()
        dcr.rectangle(*rect)
        dcr.clip()
        dcr.set_operator(cairo.OPERATOR_SOURCE)
        dcr.set_source_surface(src, 0, 0)
        dcr.paint()
        dcr.restore()
        dst.flush()

    return frame


def make_damaged_plus_blit(scene: Scene, layers: int):
    surf, dmg, rect = make_damaged(scene, layers)
    dst = new_surface(scene.w, scene.h)
    dcr = cairo.Context(dst)

    def frame(d: float) -> None:
        dmg(d)
        dcr.save()
        dcr.rectangle(*rect)
        dcr.clip()
        dcr.set_operator(cairo.OPERATOR_SOURCE)
        dcr.set_source_surface(surf, 0, 0)
        dcr.paint()
        dcr.restore()
        dst.flush()

    return frame


# ---- correctness / banding checks ----------------------------------------------------------


def alpha_bytes(surf: cairo.ImageSurface) -> tuple[memoryview, int]:
    surf.flush()
    return surf.get_data(), surf.get_stride()


def reference_at(scene: Scene, layers: int, d: float, step: float = 1.0) -> cairo.ImageSurface:
    s = new_surface(scene.w, scene.h)
    cr = cairo.Context(s)
    full_scene(cr, scene, scene.panels(d), layers, step)
    s.flush()
    return s


def diff_stats(a: cairo.ImageSurface, b: cairo.ImageSurface, rect) -> dict:
    """Max / count of per-channel byte differences between two surfaces inside rect."""
    da, sa = alpha_bytes(a)
    db, sb = alpha_bytes(b)
    x, y, w, h = rect
    worst, over2, total = 0, 0, 0
    for row in range(y, y + h):
        ra = bytes(da[row * sa + x * 4 : row * sa + (x + w) * 4])
        rb = bytes(db[row * sb + x * 4 : row * sb + (x + w) * 4])
        if ra == rb:
            continue
        for p, q in zip(ra, rb, strict=True):
            e = abs(p - q)
            if e:
                worst = max(worst, e)
                over2 += e > 2
        total += 1
    return {"max_byte_diff": worst, "bytes_diff_gt2": over2, "rows_differing": total}


def banding(scene: Scene, surf: cairo.ImageSurface, layers: int, step: float) -> dict:
    """Alpha column going up from the dock's flat top (x = centre) at full depth."""
    data, stride = alpha_bytes(surf)
    x = scene.w // 2
    y_edge = scene.h - T - DOCK_FULL
    n = int(layers * step) + 3
    col = [data[(y_edge - 1 - k) * stride + x * 4 + 3] for k in range(n)]
    steps = [col[i] - col[i + 1] for i in range(n - 1)]
    span = layers * step

    def sm(v: float) -> float:
        v = min(1.0, max(0.0, v))
        return v * v * (3 - 2 * v)

    ideal = [round(255 * OPACITY * (1 - sm((k + 0.5) / span))) for k in range(n)]
    ideal_steps = [ideal[i] - ideal[i + 1] for i in range(n - 1)]
    return {
        "monotonic": all(s >= 0 for s in steps),
        "max_step": max(steps),
        "ideal_max_step": max(ideal_steps),
        "step_dev": max(abs(a - b) for a, b in zip(steps, ideal_steps, strict=True)),
        "value_dev": max(abs(a - b) for a, b in zip(col, ideal, strict=True)),
    }


# ---- run ------------------------------------------------------------------------------------


def machine() -> dict:
    cpu = "unknown"
    try:
        for line in pathlib.Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass

    def sysfs(name: str) -> str | None:
        try:
            return pathlib.Path(f"/sys/devices/system/cpu/cpu0/cpufreq/{name}").read_text().strip()
        except OSError:
            return None

    return {
        "cpu": cpu,
        "python": platform.python_version(),
        "pycairo": cairo.version,
        "cairo": cairo.cairo_version_string(),
        "governor": sysfs("scaling_governor"),
        "scaling_driver": sysfs("scaling_driver"),
        "epp": sysfs("energy_performance_preference"),
    }


def run_all() -> list[dict]:
    rows: list[dict] = []
    s1080, s1440 = Scene(1920, 1080), Scene(2560, 1440)

    def add(name: str, layers: int, scene: Scene, frame, rect=None, **extra) -> None:
        r = {"scenario": name, "layers": layers, "monitor": f"{scene.w}x{scene.h}", **extra}
        r.update(measure(frame))
        r["clip_px"] = rect[2] * rect[3] if rect else scene.w * scene.h
        r["clip_rect"] = list(rect) if rect else None
        rows.append(r)
        print(
            f"  {name:<34} L={layers:<2} {r['monitor']:<9} med {r['median_ms']:7.2f}  "
            f"p95 {r['p95_ms']:7.2f}  max {r['max_ms']:7.2f} ms",
            flush=True,
        )

    _, f = make_full(s1080, 0, border=False)
    add("1 mass only (full)", 0, s1080, f)
    _, f = make_full(s1080, 0)
    add("2 mass+border (full)", 0, s1080, f)
    for L in LAYERS:
        _, f = make_full(s1080, L)
        add("3 mass+shadow+border (full)", L, s1080, f)
    for L in LAYERS:
        _, f, rect = make_damaged(s1080, L)
        add("4 damaged-region redraw", L, s1080, f, rect)
    for L in LAYERS:
        _, f, rect, build = make_cached(s1080, L)
        add("5 cached static shadow + damaged", L, s1080, f, rect, cache_build_ms=build)
    for L in LAYERS:
        add("6 blit of damaged rect", L, s1080, make_blit(s1080, L), s1080.damage(L))
    for L in LAYERS:
        add(
            "4+6 damaged redraw + blit",
            L,
            s1080,
            make_damaged_plus_blit(s1080, L),
            s1080.damage(L),
        )
    # component breakdown of scenario 4 at 16 layers
    for parts, label in (("s", "shadow"), ("m", "mass"), ("b", "border")):
        _, f, rect = make_damaged(s1080, 16, parts=parts)
        add(f"4x clip+clear+{label} only", 16, s1080, f, rect)
    # 2560x1440 scaling
    _, f, rect = make_damaged(s1440, 16)
    add("7 damaged-region redraw", 16, s1440, f, rect)
    _, f, rect, build = make_cached(s1440, 16)
    add("7 cached static shadow + damaged", 16, s1440, f, rect, cache_build_ms=build)
    _, f = make_full(s1440, 16)
    add("7 mass+shadow+border (full)", 16, s1440, f)
    # optimisations on scenario 4 at the 16 px reach
    for name, L, st, half in (
        ("opt-a 8 layers x 2.0px step", 8, 2.0, False),
        ("opt-a 11 layers x 1.5px step", 11, 1.5, False),
        ("opt-b half-res strokes, 16 layers", 16, 1.0, True),
        ("opt-a+b half-res, 8 layers x 2.0", 8, 2.0, True),
    ):
        _, f, rect = make_damaged(s1080, L, step=st, half=half)
        add(name, L, s1080, f, rect, step=st, half=half)
    return rows


def checks() -> dict:
    """Pixel-level checks: damaged == full redraw; cached error; banding of each variant."""
    sc = Scene(1920, 1080)
    out: dict = {}
    for L in LAYERS:
        surf, f, rect = make_damaged(sc, L)
        for i in range(WARMUP + 37):  # arbitrary final depth, rising/falling
            f(depth_at(i))
        d = depth_at(WARMUP + 36)
        out[f"damaged_vs_full_L{L}"] = {
            "depth": d,
            **diff_stats(surf, reference_at(sc, L, d), (0, 0, sc.w, sc.h)),
        }
        csurf, cf, crect, _ = make_cached(sc, L)
        for dd in (10.0, 30.0, 64.0, 20.0):
            cf(dd)
            ref = reference_at(sc, L, dd)
            out[f"cached_vs_full_L{L}_d{int(dd)}"] = diff_stats(csurf, ref, (0, 0, sc.w, sc.h))
    for name, L, st, half in (
        ("L16 step1 (baseline)", 16, 1.0, False),
        ("L8 step2", 8, 2.0, False),
        ("L11 step1.5", 11, 1.5, False),
        ("L16 half-res", 16, 1.0, True),
        ("L8 step2 half-res", 8, 2.0, True),
    ):
        surf, f, _ = make_damaged(sc, L, step=st, half=half)
        f(64.0)
        out[f"banding {name}"] = banding(sc, surf, L, st)
    return out


def table(rows: list[dict], runs: list[list[dict]]) -> str:
    base = {(r["scenario"], r["layers"], r["monitor"]): r["median_ms"] for r in runs[0]}
    lines = [
        "| scenario | layers | monitor | median ms | p95 ms | max ms | clip px | vs 8 ms |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        applies = r["scenario"][0] in "4567o" and "full" not in r["scenario"]
        verdict = ("PASS" if r["median_ms"] <= TARGET_MS else "FAIL") if applies else "-"
        lines.append(
            f"| {r['scenario']} | {r['layers'] or '-'} | {r['monitor']} | {r['median_ms']:.3f} | "
            f"{r['p95_ms']:.3f} | {r['max_ms']:.3f} | {r['clip_px']} | {verdict} |"
        )
    del base
    return "\n".join(lines)


def main() -> None:
    m = machine()
    print("machine:", json.dumps(m))
    runs: list[list[dict]] = []
    for n in (1, 2):
        print(f"--- run {n} ---", flush=True)
        runs.append(run_all())
    print("--- checks ---", flush=True)
    chk = checks()
    for k, v in chk.items():
        print(" ", k, v)
    print("\n## run 1\n" + table(runs[0], runs))
    print("\n## run 2\n" + table(runs[1], runs))
    print("\n## noise (median run2 / run1)")
    worst = 0.0
    for a, b in zip(runs[0], runs[1], strict=True):
        ratio = b["median_ms"] / a["median_ms"]
        tiny = a["median_ms"] < 0.05  # sub-50us medians: ratio is quantisation noise
        if not tiny:
            worst = max(worst, abs(ratio - 1))
        flag = "" if abs(ratio - 1) <= 0.15 else ("  (<50us, ignored)" if tiny else "  <-- >15%")
        print(f"  {a['scenario']:<34} L={a['layers']:<2} {a['monitor']:<9} {ratio:5.2f}{flag}")
    print(f"worst deviation between runs: {worst * 100:.1f}%")
    meets = sorted(
        {
            f"{r['scenario']} L={r['layers']} {r['monitor']}"
            for run in runs
            for r in run
            if r["median_ms"] <= TARGET_MS
            and r["scenario"][0] in "457o"
            and "full" not in r["scenario"]
        }
    )
    print("\nmeeting <= 8 ms in some run:", *meets, sep="\n  ")
    out = pathlib.Path(__file__).resolve().parents[1] / "out"
    out.mkdir(exist_ok=True)
    (out / "bench.json").write_text(
        json.dumps({"machine": m, "runs": runs, "checks": chk, "target_ms": TARGET_MS}, indent=2)
    )
    print(f"\nwrote {out / 'bench.json'}")


if __name__ == "__main__":
    main()
