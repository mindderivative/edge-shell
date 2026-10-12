# Shape canvas spike: findings and go/no-go (2026-10-12)

Branch `spike/shape-canvas` (local only, not pushed). Spec: `docs/superpowers/specs/2026-10-11-edge-shell-design.md` section 18. Plan: `docs/superpowers/plans/2026-10-12-shape-canvas-spike.md`. Code: `spikes/canvas/` (`outline.py`, `effects.py`, `bench.py`, `live.py`), tests in `spikes/tests/`. Images are in the git-ignored `spikes/out/` and were sent to Phil; they are referred to by file name only.

Convention in this note: **Measured** = a number a script printed. **Observed** = said by the human tester. **Inferred** = my reading, not directly measured.

## 1. Question and targets

Question: can one click-through, monitor-sized shape canvas (option B) draw the frame, corners and all panels as one outline, plus a border and a shadow, and animate with the panels, well enough to replace per-window drawing?

| Target (agreed with Phil) | Bar |
|---|---|
| Damaged-region redraw | <= 8 ms |
| Live animation | >= 60 fps (floor 55) |
| Banding | none visible |
| Live runs | <= 10 s each |

What the spike decided to build:

- One click-through canvas per monitor; the frame, screen corners and every panel form **one union outline**.
- **Border** = the outline stroked at twice the width and clipped to the mass side. Controls: width and RGBA colour.
- **Shadow** = stacked round-join strokes of the same outline, drawn under the mass, uniform (no offset, no second layer). Controls: `elevation` 0-100% and RGBA colour. `reach_px = round(48 * pct / 100)`. Profile: half-Gaussian tail, `C(k) = a * 0.5 * erfc(k / (sigma * sqrt2))`, `sigma = reach / 2.5`, with per-layer alphas solved for 8-bit rounding.
- Calibrated defaults (Phil): reasonable reach up to 32 px, `MAX_REACH_PX` = 48, shadow alpha 0.5 (`#00000080`), border 2 px in the accent (`#8fd3b6ff`). Both effects stay opt-in. Default elevation 50% (24 px) is the controller's choice, not yet confirmed by Phil.

## 2. Environment

| Item | Value |
|---|---|
| CPU | AMD Ryzen AI 9 HX 370 w/ Radeon 890M (24 threads), governor `performance` (amd-pstate-epp, EPP performance) |
| OS | Linux 7.2.9 (CachyOS) |
| Software | Python 3.14.7, pycairo 1.29.2, cairo 1.18.6 |
| Display | 1920x1080 at 60 Hz (HDMI-A-1), KWin Wayland, Plasma 6.7.5 |
| Headless backend | single-threaded cairo image surface (software), not the GTK stack |

## 3. Headless results

### 3.1 Damaged-region redraw

Setup (Task 3): 1080p, dock animating 0..64..0, 20 warm-up + 200 frames, `flush` inside the timing, two runs agree within 3.7%. Clip = the dock's bounding box at full depth plus the shadow reach plus the border, so it also covers the previous frame. Old profile (opacity 0.55, 8/16/24 layers):

| Layers | Damaged median / p95 / max (ms) | Clip px | Full redraw median (ms) |
|---|---|---|---|
| 8 | 0.33 / 0.36 / 0.38 | 51,072 | 2.49 |
| 16 | 0.67 / 0.70 / 0.71 | 57,408 | 5.09 |
| 24 | 1.13 / 1.17 / 1.70 | 64,000 | 7.75 (max 13.1) |

Final controls (Task 2c, half-Gaussian, alpha 0.35, 2 px border, 1080p):

| Elevation | Reach | Damaged median / p95 / max (ms) | Clip px |
|---|---|---|---|
| 25% | 12 px | 0.49 / 0.51 / 0.54 | 54,208 |
| 50% | 24 px | 0.98 / 1.00 / 1.06 | 64,000 |
| 75% | 36 px | 1.55 / 1.59 / 2.04 | 74,368 |
| 100% | 48 px | 2.07 / 2.13 / 2.15 | 85,312 |
| absolute | 64 px | 2.62 / 2.75 / 2.95 | 100,800 |
| absolute | 96 px | 3.41 / 3.68 / 3.72 | 134,848 |

- Every row is under 8 ms. One-time full redraw at 48 px: about 13.1 ms (startup, reload, hot-plug; not the animation path).
- At the chosen default alpha 0.5 the reviewer measured 2.36 ms at 100% (versus 2.07 ms at alpha 0.35).
- The damaged cost does not depend on monitor size (0.67 ms at 1080p and 1440p, 16 layers). A full redraw does scale (5.1 ms to 7.4 ms).
- The shadow strokes are about 90% of the cost; mass and border are negligible.
- Offset shadows (Task 2b variants, not chosen by Phil) cost 3-5 times more (damaged 4.3-6.8 ms, full redraw 56-85 ms). That is another reason the uniform model is the right one to build.

### 3.2 Cached static shadow: rejected

Caching the shadow of the static scene and stroking only the animating bump measured 0.26 / 0.53 / 0.96 ms (8 / 16 / 24 layers), a saving of about 0.15 ms. It is not a drop-in: the shadow of a union is a per-pixel max of the part shadows, but cairo composites with OVER, so the cached variant over-darkens the two concave fillets (max alpha error 63-64/255 over about 16-24 rows). Decision: no shadow cache.

### 3.3 Damaged vs full redraw

Task 3 reported a byte-identical result (max diff 0) and Task 2c called it "pixel-identical". The reviewer's independent check at 1080p disagrees: damaged and full redraws differ by <= 1/255 inside the clip and <= 3/255 outside it near the screen-corner arc, from cairo's arc tessellation. I trust the reviewer (a separate pass over the real surfaces). The difference is invisible, but "pixel-identical" overstates it.

### 3.4 Outline contract (Task 1)

The union outline was compared pixel for pixel with the existing per-window renderers (`pos=120, length=140`, 400x300, T=10, R=14) on all four edges at depths 0/5/14/28/50: **max alpha difference 5/255**, no pixel over 24 (at most 14 pixels differ at all). A rotated or mirrored edge would fail this test, so it is a real contract. Two self-intersection cases were found that the layout resolver must prevent (the legacy code merely overlaps fills):

1. A panel whose fillet lands inside a screen-corner arc: about 29 px differ. Rule: corner clearance `pos - r >= T + R`.
2. Neighbouring panels on one edge closer than `r1 + r2` (up to 28 px): their fillets overlap. Found by the reviewer; the multi-panel test only proved that the union never exceeds the single-panel alpha and was otherwise vacuous.

Spec section 17 now carries these minimum-geometry rules.

### 3.5 Banding criterion correction

The plan's "adjacent-row alpha step <= 2/255" is physically impossible: with opacity 0.55 the ideal 8-bit smooth falloff has steps of 26 / 13 / 9 per pixel at 8 / 16 / 24 layers. The criterion became: monotonic, and deviation from the ideal 8-bit model <= 2/255. Measured: max step deviation 1 at all three layer counts, max value deviation 1 / 3 / 7 (rounding accumulates), all columns monotonic. Visual check on the crops (2x/3x): no stair steps. Left/right symmetry: <= 1/255 on straight runs, up to 8/255 on arc pixels (tessellation).

## 4. The shadow look (design history)

1. The first prototype put full strength at the edge, 16 px reach, no offset; Phil judged it **embossing / a bevel**, not floating.
2. Diagnosis: a real drop shadow is about 50% at the edge (the rest is hidden under the shape); the prototype was a tight, fully dark halo.
3. Revision: half-Gaussian profile, 8-bit-aware per-layer alphas, a mirrored inside ramp under the bars so offsets leave no light gap.
4. Variants S1-S4 (offset, top-lit, two-layer contact + ambient) and borders B0-B4 were compared on light and dark sheets (`sheet_shadow_*`, `sheet_border_*`).
5. Phil chose a simpler model: a **uniform** shadow with only elevation and RGBA colour; a border with width and RGBA colour. Calibration sheets (`sheet_reach_calibration_*`) set the limits in section 1.
6. Observed weaknesses: a shadow cannot darken a near-black background, so it is faint on dark themes (the border carries the look there); 25% elevation is almost invisible; on light backgrounds the uniform shadow reads as a soft halo (heavy from about 64 px, unreasonable at 96 px).

## 5. Live results (Phil, HDMI-A-1, probe commit 872eff9)

Canvas allocation equalled the monitor geometry (1920x1080). The reports preserved the 7 runs as ranges and per-variant notes, not as seven separate printouts, so the table groups them by variant; the numbers are those recorded in the ledger.

| Variant (flags) | fps | Canvas draw ms median / p95 / max | Depth error max / mean (px) |
|---|---|---|---|
| default (`--raise-ms 500`, elevation 50%, border 2) | 59.9-60.6 | 1.90-2.07 / 2.33-2.55 / 7.9-13.6 | 1.3-1.8 / 0.01-1.01 |
| `--raise-ms 0` | 59.9-60.6 | within the default ranges | 0.14 / 0 |
| `--stack-order content-first` | 59.9-60.6 | within the default ranges | 1.01 / 0 |
| `--content-layer overlay` | 59.9-60.6 | within the default ranges | 0.88 / 0.01 |
| `--elevation 100` (48 px) | 59.9-60.6 | 3.92 / 4.45 / 22.58 | 1.75 / 1.02 |

Across all seven runs: frame interval median 16.67 ms, p95 <= 16.86 ms; content ticks versus canvas draws about 1:1, histogram of content ticks between consecutive draws `{1: ~590-597, 2: 1-9, 0: 0-2}`; CPU 0.32-0.43 of one core; 600 ticks after the 500 ms re-raise. The 22.58 ms max (and the 7.9-13.6 ms maxima elsewhere) is the one-time first full draw. Which flags the two remaining runs used is not recorded in the ledger (the five variants above account for five runs).

**Observed by the tester:**

1. All labels and markers visible, in every variant (default, `--raise-ms 0`, `--stack-order content-first`, `--content-layer overlay`).
2. No flicker or tearing that he could see.
3. The border and shadow followed the bump. The marker looked glued to it (at the bottom it is pushed up by the screen edge, which is expected: a 14 px marker in a 10 px band).
4. Click-through worked, as far as he could test in 10 s.
5. Check (e), maximized window: the clock was correctly drawn above it, as designed (a maximized window stops at the frame's reserved zone; panels float over windows). This is a pass. **Fullscreen was not tested.** (The tester first reported this as a fullscreen window; he later clarified it was maximized.)

**Interpretation:**

- Pacing is 60 fps at 60 Hz, with no dropped frames visible in the interval statistics.
- Draw cost is about 2x the headless number (1.06 ms in `--simulate`, 1.9-2.1 ms live; the difference is inferred to be GTK overhead), but 2-4 ms is well under 8 ms.
- Sync between the content window and the canvas is 0-1 frame (<= 1.8 px at peak speed); the phase varies between runs. The probe notes that even a perfect pipeline shows up to about 1.7 px because the draw follows the tick within a frame.
- The delayed re-raise (`hide(); show_all()`) did not freeze the animation.
- CPU 0.32-0.43 of one core is while a loop animates continuously; normal use animates about 280 ms per interaction, so the average should be near zero (inferred, not measured). Before blaming the canvas, profile the content-tick / margin-relayout path and the 3-window setup; the headless draw is only about 1 ms of a 16.7 ms frame.

## 6. Reviewer findings and how they were handled

| Finding | Handling |
|---|---|
| Probe crashed on the first tick (`union(new, None)`); the report looked like a result with 0 frames (Phil's run 1). | Fix round 1 (717bffe): None-safe union, pure animation logic with headless tests, `PROBE FAILED` and exit 1 on any exception or 0 frames, `--simulate N` using the same code path. |
| Design flaw: static opaque content windows hid the bump and could not test canvas-vs-content sync (separate surfaces and frame clocks); the highest option-B risk. | Fix round 2 (872eff9): transparent full-depth content windows with a marker riding the bump, driven by the content window's tick as in `EdgePanel`; the canvas is invalidated cross-window; lag statistics and `--stack-order` added. |
| Multi-panel outline test was vacuous; neighbouring-panel fillet overlap not covered. | Rule recorded (min gap `r1 + r2`) and written into spec section 17; no code fix in a spike. |
| "Pixel-identical" overstated. | Corrected in 3.3. |
| The blit scenario was a memcpy stand-in (0.004 ms), so GTK commit and compositor cost were unknown headlessly. | Only the live runs (section 5) speak to it; the go/no-go does not rely on the blit number. |
| The go/no-go must not claim stacking or sync verified headlessly. | It does not; those claims rest on section 5. |

## 7. Go / no-go

**GO for option B (one click-through shape canvas per monitor)**, with the caveats in section 8.

| Claim | Evidence | Kind |
|---|---|---|
| Redraw cost is far inside the budget. | 0.5-2.1 ms headless at 12-48 px (up to 3.4 ms at 96 px) versus 8 ms; 1.9-4.5 ms live (p95) | Measured |
| 60 fps is held. | 59.9-60.6 fps, interval median 16.67 ms, p95 <= 16.86 ms | Measured |
| The canvas follows the panels. | 0-1 frame lag, <= 1.8 px at peak; border and shadow followed the bump | Measured + observed |
| No banding. | Monotonic, deviation from the ideal 8-bit model <= 1 | Measured |
| Seams are impossible by construction. | Union outline equals the per-window renderers within 5/255 on four edges and five depths | Measured |
| Content stays above the canvas. | Visible in all stacking variants | Observed (lone canvas, see section 8) |
| Click-through works. | Only tested in 10 s runs | Observed |

Recommended defaults for the real feature:

- Redraw only the damaged region every frame. No shadow cache. Keep full redraws for resize, theme, config and hot-plug (about 13 ms at 48 px).
- `elevation` 0-100% maps to `reach = round(MAX_REACH_PX * pct / 100)`; `MAX_REACH_PX = 48`; out-of-range values clamp; 0% draws nothing.
- Shadow default: black, alpha 0.5, elevation 50% (24 px; controller's choice, not confirmed by Phil).
- Border default: 2 px accent RGBA.
- Both effects are opt-in (`enabled = false`).
- 8-bit-aware per-layer alphas; round joins and caps.
- Draw only into the GTK clip rectangle (`Gdk.cairo_get_clip_rectangle`); the first draw is full.
- Keep the core plan's lessons: re-apply the empty input region in `do_size_allocate` (the probe does this after every allocate) and use the integer monitor index (`monitor_index(monitors_by_name()[name])`).

## 8. Not tested / open risks

- **Fullscreen behaviour: untested.** Planned test: open a fullscreen window and make it the ACTIVE window, then run the probe with a start delay so focus stays on it, e.g. `sleep 5; scripts/py -m spikes.canvas.live` from a terminal on DP-1 while clicking the fullscreen window on HDMI-A-1 during the delay. KWin differentiates maximized from fullscreen: fullscreen ignores the work area, and the active fullscreen window is normally raised above panels and docks. Only if an ACTIVE fullscreen window turns out to be covered is a configurable fullscreen-aware policy needed (hide or lower the shell while an active fullscreen window is on that output, via KWin scripting or D-Bus).
- **Stacking in the real design.** The canvas-first, content-first, overlay and `--raise-ms 0` variants all showed content above the canvas, but with a lone canvas and no frame strips. The real design still has four invisible zone-reserving strips; stacking must be re-tested with them before `raise_to_top` is removed.
- HiDPI and fractional scaling: the spec says reach scales by the display scale; untested, and 1 logical px is quantised at 2x.
- Multi-monitor (one canvas per monitor): untested; only HDMI-A-1 was used.
- Many panels animating at once: damage boxes would union and cost should be roughly additive per panel; not measured.
- Long runs (GC pauses, memory): runs were 10 s.
- Slower CPUs: all numbers come from one fast CPU with the performance governor. The 12x margin at 16 layers suggests room, but that is inferred.
- GPU and compositor cost beyond what the live frame times show.
- Shadow legibility on dark themes: weak by physics; a higher alpha or a tinted colour may be needed.
- Click-through beyond 10 s runs, and CPU cost during animation (see section 5).

## 9. Follow-up plan outline (build order)

1. Pure layout resolver: align, offset, length, gap, corner clearance (`pos - r >= T + R`), min gap `r1 + r2`, spec sections 16/17. Risk: many geometry edge cases.
2. Alpha-capable colour parsing (`#rrggbbaa`) and theme models for border and shadow with validation. Risk: existing `hex_to_rgba` callers.
3. Promote `outline.py` and `effects.py` into `shell/` with the same tests (outline vs legacy equality is the contract); then remove the legacy per-window drawing. Risk: regressions in the 255-test suite.
4. Canvas window per monitor plus invisible zone-reserving strips; panels become content / handle / input windows that read a shared depth. Risk: stacking and input regions change.
5. Remove the `raise_to_top` workaround if stacking holds with the strips (re-test). Risk: KWin ordering.
6. Damaged-region invalidation from each panel's depth changes. Risk: the clip must cover the previous footprint.
7. Config and reload hooks: border and shadow changes are redraws, not rebuilds. Risk: per-monitor overrides.
8. Conditional: run the fullscreen test from section 8 first; only if an active fullscreen window is covered, add a fullscreen-aware policy (hide or lower the shell). Risk: KWin D-Bus / scripting reliability.
9. Handle customization and interaction toggles (section 15) on the content windows. Risk: interplay with the markers and the empty input region.
10. Multi-monitor and scale handling (reach times scale). Risk: fractional scales.
11. Profile CPU during animation (content ticks, margin relayout, 3-window setup). Risk: may need a different animation path.
12. Human visual gates as in the core plan, including dark themes. Risk: subjective.
