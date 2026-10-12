# Shape Canvas Spike Plan

> **For agentic workers:** this is a **spike**: its output is an answer (numbers, images, a go/no-go), not code to keep. Build each probe as cheaply as correctness allows, in `spikes/canvas/` on the branch `spike/shape-canvas`. Use superpowers:subagent-driven-development to run it (implementer per task; the reviewer's job here is to check that the numbers and conclusions are trustworthy, not production quality). Steps use checkbox (`- [ ]`) syntax.

**Goal:** decide whether one click-through "shape canvas" layer surface per monitor (spec section 18, option B) can draw the frame, corners, panels, inner border and a stacked-stroke shadow smoothly enough, and stacks correctly on KWin.

**Question and targets (agreed with Phil):**
- Damaged-region redraw of the animating panel **<= 8 ms** per frame; live animation **>= 60 fps** (55 fps is the floor for "good enough").
- Shadow falloff without visible banding at 8-24 px elevation (alpha steps <= 2/255 between adjacent 1 px rows, monotonic).
- Live probe runs are capped at **10 seconds** each.

**Spec:** `docs/superpowers/specs/2026-10-11-edge-shell-design.md` section 18 (and 5.1 fallback). **Existing code to reuse:** `shell/geometry.py`, `shell/draw.py` (the per-panel renderer the canvas must match), `shell/theme.py` (`hex_to_rgba`).

## Global Constraints

- Python via `scripts/py` (shared venv: Fabric 0.0.2, PyGObject 3.50.0 `<3.52`, pycairo). Probe code lives under `spikes/canvas/` and `spikes/tests/`; do not modify `shell/`, `widgets/`, `services/` or the existing tests. Throwaway means no polish, but every probe states its inputs and prints its numbers.
- Never leave a process running. **Live probes (Task 4) draw on the user's screen: only on `HDMI-A-1`, each run under 10 seconds, and only when the task says so.** The auto-mode classifier may refuse to run them for subagents; if refused, stop and report (do not work around), and Phil runs the command himself.
- Geometry reference: 1920x1080 monitor, `T=10`, `R=14`, panel "bumps" grow inward from an edge by `depth`. The dark mass is everything outside the *inner desktop region*; the outline is the boundary of that region.
- Every commit ends with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` (second `-m`). Plain separate git commands. `ruff` excludes `docs/` but spikes are linted too: run `scripts/py -m ruff format spikes && scripts/py -m ruff check --fix spikes` before committing.
- **Do not push.** The spike branch stays local until Phil decides.

## File Structure

```
spikes/canvas/outline.py      # union outline path + mass fill (frame, corners, panel bumps)
spikes/canvas/effects.py      # inner border stroke + stacked-stroke shadow
spikes/canvas/render_frames.py# headless PNG renders at several depths
spikes/canvas/bench.py        # headless cost benchmark (full / damaged / cached)
spikes/canvas/live.py         # live layer-shell probe (Task 4)
spikes/tests/test_outline.py  # outline == existing per-window renderers
spikes/tests/test_effects.py  # banding / monotonicity / union checks
docs/superpowers/findings/2026-10-12-shape-canvas-spike.md  # the result
```

---

### Task 1: Union outline path that matches the existing renderers

**Files:** Create `spikes/canvas/__init__.py`, `spikes/canvas/outline.py`, `spikes/tests/test_outline.py`.

**Interfaces — Produces:**
- `Panel = tuple[str, int, int, int, float]` meaning `(edge, pos, length, depth_full, d_now)`: `edge` in top/bottom/left/right, `pos` the body start in px from the start of the edge (as in `geometry.anchor_and_margin`, the body starts at `pos`, the surface starts `R` earlier), `d_now` the current depth.
- `outline_path(cr, w, h, T, R, panels) -> None`: appends to `cr` ONE closed path: the boundary of the inner desktop region, walking clockwise from the top-left, with rounded inner screen corners of radius `R`, and for every panel on every edge the S-shaped bump: concave fillet of radius `r = min(R, d_now/2)` (use `shell.geometry.join_radius`), vertical side, convex corner radius `r`, flat top at depth `T + d_now` from the screen edge, convex corner, side, fillet. Panels on one edge are sorted by `pos`; assume they do not overlap.
- `fill_mass(cr, w, h, T, R, panels, rgba) -> None`: fills the dark mass = full-screen rectangle minus the inner region (build the screen rectangle and the outline in one path and fill with even-odd).

Algorithm hint: write `trace_edge(cr, length, T, R, panels_on_edge)` for the TOP edge in a canonical frame (moving along +x, desktop towards +y, edge at y = 0) and reuse it for the other three edges with `cr.save(); cr.translate(...); cr.rotate(...)`; paths keep their device-space points after `restore()`. The inner corner arcs join consecutive edges. The mass for one panel must equal what `shell.draw.draw_panel` + the frame strip + `draw_screen_corner` produce today (same radius rule `min(R, d/2)`), so the new outline is a drop-in.

- [ ] **Step 1: Write the failing contract test** (`spikes/tests/test_outline.py`) — pixel equality against the existing renderers for a single panel on each edge at depths 0, 5, 14, 28 and full (50), on a small 400x300 monitor with `T=10`, `R=14`:

```python
import cairo
import pytest

from shell import geometry as g
from shell.draw import draw_panel, draw_screen_corner
from spikes.canvas.outline import fill_mass

W, H, T, R = 400, 300, 10, 14
RGBA = (0.04, 0.05, 0.05, 1.0)
EDGES = ["top", "bottom", "left", "right"]


def alpha_bytes(surface):
    surface.flush()
    data = surface.get_data()
    stride = surface.get_stride()
    return [
        [data[y * stride + x * 4 + 3] for x in range(surface.get_width())]
        for y in range(surface.get_height())
    ]


def render_legacy(edge, pos, length, depth, d):
    """Frame strips + corner pieces + one panel, drawn the way the per-window code does today."""
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(s)
    cr.set_source_rgba(*RGBA)
    for rect in [(0, 0, W, T), (0, H - T, W, T), (0, 0, T, H), (W - T, 0, T, H)]:
        cr.rectangle(*rect)
    cr.fill()
    for corner, (ox, oy) in {
        "top-left": (T, T),
        "top-right": (W - T - R, T),
        "bottom-left": (T, H - T - R),
        "bottom-right": (W - T - R, H - T - R),
    }.items():
        cr.save()
        cr.translate(ox, oy)
        draw_screen_corner(cr, corner, R, RGBA)
        cr.restore()
    sw, sh = g.surface_size(edge, length, depth, T, R)
    horizontal = edge in ("top", "bottom")
    off = max(0, pos - R)
    if edge == "top":
        ox, oy = off, 0
    elif edge == "bottom":
        ox, oy = off, H - sh
    elif edge == "left":
        ox, oy = 0, off
    else:
        ox, oy = W - sw, off
    cr.save()
    cr.translate(ox, oy)
    draw_panel(cr, edge, length, depth, d, T, R, RGBA)
    cr.restore()
    return alpha_bytes(s)


def render_canvas(edge, pos, length, depth, d):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    fill_mass(cairo.Context(s), W, H, T, R, [(edge, pos, length, depth, d)], RGBA)
    return alpha_bytes(s)


@pytest.mark.parametrize("edge", EDGES)
@pytest.mark.parametrize("d", [0, 5, 14, 28, 50])
def test_canvas_matches_per_window_renderers(edge, d):
    pos, length, depth = 120, 140, 50
    a = render_legacy(edge, pos, length, depth, d)
    b = render_canvas(edge, pos, length, depth, d)
    bad = [
        (x, y, a[y][x], b[y][x])
        for y in range(H)
        for x in range(W)
        if abs(a[y][x] - b[y][x]) > 24  # antialiasing tolerance on edge pixels only
    ]
    assert len(bad) < 40, bad[:10]  # allow a few antialiased edge pixels, not shape errors
```

If the legacy composition above has a trivial transcription problem (surface placement of a panel on the left/right edge), fix the *test harness* to reproduce how `EdgePanel` places surfaces (`geometry.anchor_and_margin`), not the tolerance. Also add `spikes/__init__.py` and `spikes/tests/__init__.py` as needed so `from spikes.canvas...` imports work (pytest `pythonpath` is the repo root).

- [ ] **Step 2: Run to verify failure** — `scripts/py -m pytest spikes/tests/test_outline.py -q` — expected ImportError for `spikes.canvas.outline`.
- [ ] **Step 3: Implement `outline.py`** per the interface and hint above. Also add a second pure test `test_outline_is_one_closed_path` (count of `cr.copy_path()` MOVE_TO segments is 1 for the outline alone) and `test_multiple_panels_do_not_double_fill` (three panels on three edges: no pixel of the mass has alpha above the single-panel maximum).
- [ ] **Step 4: Run to verify pass** — `scripts/py -m pytest spikes/tests/test_outline.py -q` (all pass).
- [ ] **Step 5: Commit** — `git add spikes && git commit -m "spike: union outline path matching the per-window renderers" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"`.

---

### Task 2: Inner border and stacked-stroke shadow; headless look

**Files:** Create `spikes/canvas/effects.py`, `spikes/canvas/render_frames.py`, `spikes/tests/test_effects.py`.

**Interfaces — Consumes:** `outline_path`, `fill_mass` (Task 1). **Produces:**
- `draw_border(cr, w, h, T, R, panels, width, rgba)`: strokes the outline (`outline_path`) with `line_width = 2*width`, **clipped to the mass side** so exactly `width` px of border lies on the frame/panels and none on the desktop; the border therefore follows corners, joins and bumps as one line. (Clip: even-odd of the screen rectangle plus the outline path.)
- `shadow_alphas(layers, opacity, curve="smoothstep") -> list[float]`: per-layer alpha so the *cumulative* alpha at distance `k` (`1 - prod(1 - a_i)`) follows the falloff `opacity * (1 - smoothstep(k / layers))`.
- `draw_shadow(cr, w, h, T, R, panels, layers, opacity, rgba, offset=(0, 0))`: for `i` in `layers..1` (largest first) stroke the outline with `line_width = 2*i`, round joins, round caps, alpha `a_i`, translated by `offset`, **clipped to the desktop region** (inside the outline) so the shadow only falls on the desktop.

- [ ] **Step 1: Write failing tests** (`spikes/tests/test_effects.py`): (a) `shadow_alphas` cumulative alpha is monotonically non-increasing with distance and equals `opacity` at distance 0 within 1/255 and ~0 at `layers`; (b) rendering a single top panel at `layers in (8, 16, 24)`, sampling a vertical line through the middle of the panel and a vertical line through empty frame, the 8-bit alpha along each line is non-increasing away from the frame and adjacent-row steps are <= 2 (banding criterion; report the max step in the assertion message); (c) the shadow is symmetric left/right of a centred panel within 1/255; (d) no shadow pixel appears inside the mass (alpha under the mass from the shadow layer alone is irrelevant since the mass is painted on top, so instead assert that painting mass then shadow clipped to the desktop leaves the mass pixels at full alpha); (e) border pixels: along a vertical line through a bump the border colour appears exactly `width` px thick (+-1) on the mass side and 0 px on the desktop side.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement `effects.py`.** Prefer `cairo.LINE_JOIN_ROUND`/`LINE_CAP_ROUND`. Keep the code simple; no numpy (not installed). If the banding criterion fails at `layers=24`, use fractional line-width steps (0.5 px) and report it.
- [ ] **Step 4: `render_frames.py`:** renders to `spikes/out/` (git-ignored, create the directory) 1920x1080 PNGs of the full monitor (frame + dock bottom-centre 560x64 + clock top-centre 168x46 + system bar right pos 600 length 300 depth 56) at panel depths 0, 14, 32, 64 (all three panels at that fraction), and a composite "desktop" background (a vertical light-grey to mid-grey gradient plus some coloured blocks to show the shadow against content), with: no effects; border only (width 2, accent `#8fd3b6`); shadow only (16 layers, opacity 0.55, black); both. Also writes a 2x crop sheet of the dock-to-bottom-frame join, the top-left screen corner and the clock join. Add `spikes/out/` to `.gitignore` (the commit must include it).
- [ ] **Step 5: Run tests, run `render_frames.py`, open 3-4 PNGs with the Read tool and describe what you see (joins, corners, banding, border continuity).** Copy the best 4 images (one per effect combination at full depth, plus the join crop sheet) to the scratchpad dir `/tmp/claude-1000/-home-phil-Projects-pyDev-projects-myShell/ad21ced1-ce22-41f9-8c24-56b7b4005995/scratchpad/` and report their paths so the controller can send them to Phil.
- [ ] **Step 6: Commit** (`spike: border and stacked-stroke shadow, headless frames`).

---

### Task 3: Headless cost benchmark

**Files:** Create `spikes/canvas/bench.py`.

**Interfaces — Consumes:** Tasks 1-2. **Produces:** a printed table and `spikes/out/bench.json`.

Measure on a 1920x1080 ARGB32 `ImageSurface` with the full scene (frame, corners, dock/clock/bar) using `time.perf_counter` over at least 200 frames each (after 20 warm-up frames); report median, p95 and max in ms for each scenario while ONE panel (the dock) animates through depths 0 to 64 (other panels static):
1. **Mass only** (baseline): full redraw of the mass.
2. **Mass + border** (width 2), full redraw.
3. **Mass + shadow at 8 / 16 / 24 layers**, full redraw of everything.
4. Same as 3 but **damaged-region redraw only** (clip to the dock's bounding box expanded by the shadow reach `layers` + border; redraw background-free layer content inside the clip: clear region, shadow, mass, border). Report the clip area in px.
5. **Cached shadow**: render the shadow once into an `A8`/ARGB32 surface for the static part of the scene and composite it, redrawing only the animating panel's region (document what is cached and when it is invalidated).
6. The cost of the **blit of the damaged region to a destination surface** (`set_source_surface` + `paint` of the clip) as a stand-in for what GTK does per frame.

State the machine (CPU model from `/proc/cpuinfo`, Python and pycairo versions). Pass/fail against the targets: damaged-region redraw median **<= 8 ms** (scenario 4 or 5 at 16 layers); print which scenarios meet it. If scenario 4 at 16 layers misses the target, also try 2 optimisations (fewer layers with 1.5 px steps; strokes at half resolution into a cached surface scaled up) and report the effect.
- [ ] **Step 1: Implement and run** (`scripts/py spikes/canvas/bench.py`); paste the table in your report.
- [ ] **Step 2: Commit** (`spike: headless cost benchmark`).

---

### Task 4: Live probe on KWin — HUMAN GATE (Phil, HDMI-A-1)

**Files:** Create `spikes/canvas/live.py`.

**Behaviour:** a throwaway script, run by Phil, that for at most **10 seconds** (hard cap via a GLib timeout that quits the app):
1. Creates ONE `WaylandWindow` canvas on HDMI-A-1 (integer monitor index via `shell.gdk_util.monitor_index`; mapping by connector name via `shell.monitors.monitors_by_name`): layer `top`, anchored to all four edges, `exclusivity="none"` then `GtkLayerShell.set_exclusive_zone(self, -1)`, **empty input region** (re-applied in `do_size_allocate`, see `EdgePanel`), transparent background. It draws, with a `Gtk.DrawingArea`, the outline scene from Tasks 1-2 (frame + corners + dock at the bottom, clock at the top, system bar at the right, border width 2, shadow 16 layers opacity 0.55) and animates the dock's depth 0 -> 64 -> 0 repeatedly on the frame clock (sine ease, 2 s period) using **damaged-region redraws** (`queue_draw_area` of the dock box + reach).
2. Creates ONE dummy content window per panel (small `WaylandWindow`s placed over each panel body; a `Gtk.Label` "dock", "clock", "bar"; the dock one follows the animated depth) to test stacking: content windows must appear **above** the canvas.
3. Records frame timestamps from `add_tick_callback`; prints at exit: frames, mean/median/p95 frame interval, achieved fps, and process CPU time per second (`time.process_time`).
4. Prints a stacking/click-through checklist for Phil.
- [ ] **Step 1: Implement** and run ONLY the import check (`scripts/py -c "import spikes.canvas.live"`); do not start it.
- [ ] **Step 2: Commit** (`spike: live canvas probe`).
- [ ] **Step 3: GATE — Phil runs it** (`cd` to the worktree, `scripts/py spikes/canvas/live.py`, up to 10 s). He reports: (a) smoothness and flicker; (b) the printed fps and CPU line; (c) content windows above the canvas, dock label follows the animation; (d) click-through: clicking a window or desktop icon anywhere (including over the shadow and the animating dock region, except the dummy labels) reaches it; (e) the canvas stays below a fullscreen window if he cares to test (optional).

---

### Task 5: Findings and recommendation

**Files:** Create `docs/superpowers/findings/2026-10-12-shape-canvas-spike.md`.

- [ ] **Step 1: Write the note:** the question and targets; the environment; the Task 3 table; the Task 2 look results (with the image paths) and the banding numbers; the Task 4 results from Phil; a **go / no-go** for option B with reasons; recommended defaults for the real feature (layers, alpha curve, border width, opacity, whether to cache the shadow, the redraw strategy); surprises (anything that changed the design assumptions: stacking, input region, outline construction); and the follow-up plan outline (canvas refactor tasks).
- [ ] **Step 2: Commit** (`docs: shape canvas spike findings`). Do not push.

## Review Focus (for the final reviewer of the findings)

1. Do the benchmark scenarios measure what they claim (damaged region really clipped, cached shadow really not re-rendered, warm-up excluded, perf_counter around the draw AND the blit)?
2. Is the shadow's cumulative-alpha model implemented as stated, and does the banding test measure the right thing (adjacent-row steps on the final composite)?
3. Is the outline test strong (it compares against the existing per-window renderers, so a rotated or mirrored edge fails)?
4. Are the live probe's claims backed by the numbers it prints rather than by assertion?
5. Does the go/no-go follow from the numbers and Phil's observations?
