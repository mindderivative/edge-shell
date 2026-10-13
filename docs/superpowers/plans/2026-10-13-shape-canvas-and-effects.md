# Shape Canvas and Effects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status (2026-10-13):** complete. Gates 1-5 passed with Phil on HDMI-A-1. Fallback B applied (the delayed panel re-raise is kept); Task 11 fallbacks A, C, D were not needed. After Gate 4 the border moved outside the mass (Task 13b, `514573f`). Results: `docs/superpowers/findings/2026-10-12-shape-canvas-spike.md` section 10.

**Goal:** Replace the per-window panel drawing with one click-through shape canvas per monitor that draws the frame, the screen corners and every panel as one outline, and add the opt-in inner border and uniform shadow, without regressing any existing behaviour.

**Architecture:** Spec 18 option B, as proven by the shape-canvas spike. A pure core (`shell/canvas/`: outline, effects, style, scene, painter, simulation, stats; `shell/panel_layout.py`) is built and tested headlessly first. A thin GTK window (`ShapeCanvas`) wraps the pure `CanvasPainter`; each panel keeps a transparent full-depth `EdgePanel` window for content, handle and input, and reports its animated depth to the canvas, which redraws only the damaged box. Frame strips become invisible, input-less, zone-reserving surfaces on the `bottom` layer; the screen-corner windows disappear. Every on-screen step ends in a human gate on `HDMI-A-1`.

**Tech Stack:** Python 3.14 (>=3.12), Fabric 0.0.2, PyGObject 3.50.0 (`<3.52`), pycairo, GtkLayerShell, Pydantic 2, pytest, ruff 0.17.0.

**Spec:** `docs/superpowers/specs/2026-10-11-edge-shell-design.md` (sections 3-7, 17 "Minimum geometry rules", 18). Spike evidence: `docs/superpowers/findings/2026-10-12-shape-canvas-spike.md`, spike plan `docs/superpowers/plans/2026-10-12-shape-canvas-spike.md`, spike code `spikes/canvas/` (commit `872eff9`).

**Scope (Plan 1 of 3, fixed by Phil).** In: the canvas, invisible strips, content windows, border and shadow with config, reload and per-monitor overrides, the smallest safe geometry rules, a `--stats` measurement mode, gates, cleanup, docs. Out (separate plans): the align/offset/length/gap layout model (spec 16/17; today's `pos` placement through `geometry.anchor_and_margin` stays), handle customization (spec 15), the settings window, Plasma integration, HiDPI/fractional scale (the code stays scale-ready and warns), a multi-panel layout resolver.

**Date:** 2026-10-13 (the plan's execution date, as in the file name).

**Size:** 16 tasks. 11 carry code and tests (1-9, 12, 14), 5 gates (Gate 1 in Task 7, Gate 2 in Task 8, Gate 3 = Task 10, Gate 4 = Task 13, Gate 5 = Task 15), Task 11 is a set of conditional fallbacks, Task 16 is docs. Riskiest: Task 7 (strips on the `bottom` layer must still reserve the zone), Task 8 (canvas/content stacking and depth sync), Task 12 (removing the raise workaround depends on the gates).

## Decisions recorded (DECIDED with Phil; do not reopen)

1. **Branch base:** merge PR #1 first, then branch from `main` (details under Prerequisites).
2. **Overlapping or too-close panels:** the later panel (config order) is hidden and a notification names it (Task 5 rules, Task 9 notification). No shifting.
3. **Frame band click-through:** accepted. The invisible strips take no input, so clicks on the frame band reach the desktop (spec updated in Task 16).
4. **Default shadow elevation 50 % (24 px):** confirmed by Phil. (The controller updated the sentence in spec section 18 separately, commit `3f1d311`; Task 16 only verifies it.)
5. **Spike folder removal:** Task 12 deletes `spikes/canvas/` (including the live probe `spikes/canvas/live.py`) and `spikes/tests/`; git history keeps them at `872eff9`. Recorded as decided unless Phil objects before Task 12.

## Prerequisites

- Merge order (decision 1): (1) PR #1 (core shell, https://github.com/mindderivative/edge-shell/pull/1) is merged into `main`; (2) the spike branch `spike/shape-canvas` (it holds `spikes/`, the findings note, the spec 17/18 updates and both plan documents: the spike plan and this plan) is rebased onto `main` and merged as a second PR, **PR #2**; (3) the work branch `feat/shape-canvas` is then created from `main` in its own worktree (superpowers:using-git-worktrees). Task 3 copies code from `spikes/canvas/`, so PR #2 must be in. Check: `git log --oneline main -- spikes/canvas/outline.py docs/superpowers/findings/2026-10-12-shape-canvas-spike.md` shows commits for both paths.
- Fallback: if PR #2 has not been merged, branch from `spike/shape-canvas`.
- Baseline before Task 1: `scripts/py -m pytest -q` prints `255 passed` (2 GLib deprecation warnings are normal); `scripts/py -m ruff check .` prints `All checks passed!`.
- Do not carry over local uncommitted edits (for example a local change to `examples/panels-test.toml`): always stage files by name, never `git add -A` or `git add .`.

## Global Constraints

- Python only through `scripts/py` (shared venv `/home/phil/Projects/pyDev/pyEnvs/global-base`). **PyGObject must stay `<3.52`** (Fabric 0.0.2 breaks on 3.52+).
- Wayland + `wlr-layer-shell` only; windows are `fabric.widgets.wayland.WaylandWindow`.
- **Monitor is an INT.** Fabric's `WaylandWindow.monitor` is an int property; a `Gdk.Monitor` object is silently dropped and KWin uses its default output. Always pass `monitor=monitor_index(monitor)` (`shell/gdk_util.py:16`). `MonitorShell._check_monitor` (`shell/monitors.py:130-139`) logs an error when a window lands on the wrong output: every new window goes through `MonitorShell._track`.
- **Input shape after allocate.** Fabric's `Window.do_size_allocate` re-applies the `pass_through` state on every allocate (`fabric/widgets/window.py:219-222` in the venv): `pass_through=True` windows (canvas, strips) stay click-through by themselves; a window with a NARROW region must re-apply it after the parent allocate, as `EdgePanel.do_size_allocate` does (`shell/edge_panel.py:115-122`). Never drop that override.
- **Exclusive zones.** Strips use `exclusivity="auto"` (never `"normal"`, which reserves 1 px). Non-reserving windows (canvas, panels) use `exclusivity="none"` and then `GtkLayerShell.set_exclusive_zone(self, -1)` immediately after `super().__init__()` (`shell/edge_panel.py:56-58`); zone 0 would make KWin push them clear of the frame.
- **Stacking within a layer is not guaranteed by creation order** (the core build needed a delayed `hide()/show_all()` re-raise, `shell/monitors.py:25-31`, `shell/edge_panel.py:124-137`). The canvas is created first, panels after; the raise stays until Gates 1-2 prove it is no longer needed (Tasks 7, 8, 12).
- **Window references.** Fabric's `Application.add_window` keeps every window: unregister before destroy (`EdgeShellApp.unregister_window`, `shell/app.py:56-61`; `MonitorShell._release`, `shell/monitors.py:153-162`).
- **Timers.** Repeating timers must be cancelled on destroy (`widgets/clock.py:32-37`, `widgets/system_bar.py:37-42`). The canvas adds no timers.
- **One instance.** `_already_running()` is checked before any window exists (`shell/app.py:32-34`, `shell/app.py:183-189`); keep that order in `run()`.
- **Hot-plug guard.** `sync_monitors` keeps the current shells when the monitor mapping is empty (`shell/app.py:66-69`); do not change it.
- **Tests.** Any test importing `gi` or `fabric` starts with `pytest.importorskip("gi")` and `pytest.importorskip("fabric")` (CI has no GTK, only pycairo). Tests never create a window (that would draw on Phil's screen): GTK classes are tested by calling their methods on stand-ins, as `tests/test_edge_panel_drag.py` and `tests/test_canvas_window.py` do.
- **Lint.** `ruff` 0.17.0, line length 100, excludes `docs/` and `*.md` (`pyproject.toml`).
- **VERIFY** (before every commit): `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`. The suite must be green at the end of EVERY task (0 failed).
- **Git.** Plain separate git commands run from the worktree (no `cd … && git`, no command substitution around git). Stage files by name. **Never push.** Every commit message ends with a second `-m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"`.
- **Live runs.** Phil is the only visual tester, on `HDMI-A-1` only. **Never touch `DP-1`** (it holds the Plasma panel; never disable it, never configure it as `edge`). Live probes are capped at 10 s (`main.py --stats` refuses more). If the auto-mode classifier refuses a live run for a subagent, stop and report; do not work around it: Phil runs the gate command himself.
- **Shape canvas facts (spec 18 + findings, do not reopen):** one outline for frame + corners + panels (`outline_path` / `fill_mass`); border = outline stroked at 2x width clipped to the mass side; shadow = uniform stacked round-join strokes under the mass, clipped to the desktop region, half-Gaussian `C(k) = a*0.5*erfc(k/(sigma*sqrt2))`, `sigma = reach/2.5`, 8-bit-aware layer alphas; `reach_px = round(48 * pct / 100)`, `MAX_REACH_PX = 48`; the drawing clamps, validation rejects out-of-range values with the key path; defaults when enabled: shadow `#00000080` elevation 50 (24 px, confirmed by Phil), border 2 px `#8fd3b6ff`; both `enabled = false` by default. **No shadow cache.** First draw full; then redraw the damaged box = union of the previous and current panel box grown by reach + border width.
- **Colours** accept `#rrggbb` or `#rrggbbaa` everywhere in the theme. GTK3's CSS parser rejects `#rrggbbaa` (checked: `Gdk.RGBA().parse("#8fd3b680")` is False), so CSS always goes through `shell.theme.css_color`.
- **HiDPI:** scale 1 is assumed. The canvas logs a warning when a monitor's scale factor is not 1; shadow reach is not multiplied by the scale yet (later plan).
- Pure modules import no GTK/`gi`: everything in `shell/canvas/` except `canvas.py`, plus `shell/panel_layout.py` and the existing pure modules.

## Review Focus

The five failure modes most likely to bite Phil that no single happy-path test would catch, each pinned by a test in the owning task:

1. **Stale pixels after animation or drag:** a damage box that misses a changed region leaves ghost shadow, border or body pixels. Expect every frame to equal a full redraw. Pinned by `test_damaged_redraws_equal_a_full_redraw` and `test_random_depth_jumps_never_leave_stale_pixels` (Task 4), and by mutation-checked boxes in `test_panel_box_on_every_edge` (Task 4).
2. **Wrong window setup:** the canvas or a strip taking input, a strip not reserving its zone, or a strip stacked above panels. Expect click-through everywhere except panel bodies and handles. Pinned by `test_canvas_window_setup` (Task 6) and `test_strips_reserve_their_size_take_no_input_and_sit_below_the_canvas` (Task 7); the compositor side by Gates 1-2.
3. **Canvas and panel out of step:** the body drawn at a different depth from the handle, or a ghost body left by a removed/rebuilt/failed panel. Expect the body to follow the handle every frame and disappear with its panel. Pinned by `test_apply_depth_moves_handle_and_region_then_reports_to_the_canvas` and `test_on_depth_is_stored_before_the_tweens_exist` (Task 8), `test_add_and_remove_keep_canvas_and_panels_in_step`, `test_failed_panel_construction_leaves_no_scene_shape` (Task 8) and `test_simulation_draws_once_per_tick` (Task 14).
4. **Theme regressions:** a partial per-monitor `[theme.shadow]` override resetting the other shadow keys, or an alpha colour reaching GTK CSS as `#rrggbbaa` (silently ignored by GTK3). Expect key-by-key merging and every CSS colour parseable. Pinned by `test_monitor_override_merges_nested_tables_key_by_key` (Task 2) and `test_every_css_colour_parses_in_gtk3` (Task 1).
5. **Self-intersecting outline from user geometry:** `pos = 0` or two panels close together on one edge breaks the single path (wrong fills). Expect the panel clamped or hidden with a warning, never a broken frame. Pinned by `test_without_the_clamp_the_outline_breaks_inside_the_corner_arc`, `test_panel_clamped_to_the_corner_renders_like_legacy`, `test_neighbours_need_a_gap_of_r1_plus_r2` (Task 5) and `test_a_neighbour_change_rebuilds_the_panel_it_unhides` (Task 8); the live clamp and its notification by Gate 3 item 6 (Task 10).

## File Structure

```
shell/canvas/__init__.py      # package marker (empty)
shell/canvas/outline.py       # PURE: union outline path + mass fill (moved from spikes/canvas)
shell/canvas/effects.py       # PURE: border, uniform shadow, draw_scene (moved from spikes/canvas)
shell/canvas/style.py         # PURE: Theme -> CanvasStyle (mass rgba, border, shadow, pad)
shell/canvas/scene.py         # PURE: per-monitor scene model + damage boxes
shell/canvas/painter.py       # PURE: CanvasPainter = everything the canvas window does
shell/canvas/simulate.py      # PURE: headless Tween -> painter -> clipped-draw loop (+ CLI)
shell/canvas/stats.py         # PURE: frame pacing / draw cost / cadence + StatsRecorder
shell/canvas/canvas.py        # GTK: ShapeCanvas window (thin shell over CanvasPainter)
shell/panel_layout.py         # PURE: resolved pos per panel + minimum geometry rules
shell/frame.py                # GTK: invisible zone-reserving FrameEdge strips (ScreenCorner removed)
shell/edge_panel.py           # GTK: content/handle/input window, reports depth (no drawing)
shell/monitors.py             # GTK: MonitorShell = canvas + strips + panels, layout reconcile
shell/app.py                  # wiring; layout warnings; --stats run
shell/theme.py                # hex_to_rgba (alpha), css_color, to_css
shell/config/models.py        # Border, Shadow, overrides, deep_merge, alpha colours
shell/config/loader.py        # uses models.deep_merge
shell/draw.py                 # DELETED in Task 12 (moved to tests/legacy_draw.py)
tests/legacy_draw.py          # TEST-ONLY reference renderers (the outline contract)
examples/effects-test.toml    # Gate 4 config
spikes/canvas/, spikes/tests/ # DELETED in Task 12 (kept in git history at 872eff9)
```

| Task | Deliverable | Keeps the suite green because |
| --- | --- | --- |
| 1 | `#rrggbbaa` colours, `css_color` | 6-digit behaviour unchanged; old tests untouched |
| 2 | `[theme.border]`, `[theme.shadow]`, deep merge | new fields have defaults; default file matches them |
| 3 | `shell/canvas/{outline,effects,style}.py` + contract tests | new modules only; `shell/draw.py` still used by the shell |
| 4 | scene, painter, simulation | new modules only |
| 5 | `shell/panel_layout.py` | new module only |
| 6 | `ShapeCanvas` window | new module, not wired yet |
| 7 | canvas per monitor, invisible strips, no corner windows; Gate 1 | tests for corners/raise updated in the same task |
| 8 | panels through the canvas (EdgePanel depth, MonitorShell layout + reconcile); Gate 2 | `test_monitor_shell.py` rewritten with the code; the app does not read the new attributes yet |
| 9 | layout notifications in the app (only when a monitor's warnings change) | new app method + tests |
| 10 | Gate 3 (clock, system bar, corner clamp) | no code |
| 11 | conditional fallbacks | only if a gate failed |
| 12 | cleanup (raise, `shell/draw.py`, spikes) | tests removed together with the code they test |
| 13 | Gate 4 (effects) + example | example file only |
| 14 | `--stats`, simulate CLI | new code + tests |
| 15 | Gate 5 (regression) | no code |
| 16 | README, spec, findings | docs only |

---

### Task 1: Alpha-capable theme colours

**Files:**
- Modify: `shell/config/models.py:22-32` (colour regex, `COLOR_FIELDS`), `shell/config/models.py:58-63` (`Theme._hex`)
- Modify: `shell/theme.py:12-15` (`hex_to_rgba`), `shell/theme.py:27-41` (`to_css`)
- Test: `tests/test_theme.py`, `tests/test_config_models.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `shell.config.models.COLOR_FIELDS: tuple[str, ...]` (renamed from `_COLOR_FIELDS`, same seven names).
  - `shell.config.models.check_hex(value: str) -> str` (lower-cased value; `ValueError("must be a #rrggbb or #rrggbbaa hex color")` otherwise).
  - `shell.theme.hex_to_rgba(value: str, alpha: float = 1.0) -> tuple[float, float, float, float]`: 8-digit colours carry their own alpha, multiplied by `alpha`; 6-digit colours behave exactly as before; any other length raises `ValueError`.
  - `shell.theme.css_color(value: str) -> str`: `#rrggbb` unchanged, `#rrggbbaa` -> `rgba(r, g, b, a.aaa)`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_theme.py` change the imports at the top to:

```python
import re

import pytest

from shell.theme import css_color, hex_to_rgba, scope_class, to_css
```

and append:

```python
# ---- alpha colours (#rrggbbaa) ----------------------------------------------------


def test_hex_to_rgba_reads_the_alpha_digits():
    expected = (0x8F / 255, 0xD3 / 255, 0xB6 / 255, 0x80 / 255)
    assert hex_to_rgba("#8fd3b680") == pytest.approx(expected)
    assert hex_to_rgba("#000000ff") == (0.0, 0.0, 0.0, 1.0)
    assert hex_to_rgba("#ffffff80", 0.5) == pytest.approx((1.0, 1.0, 1.0, 0x80 / 255 * 0.5))


@pytest.mark.parametrize("bad", ["", "#fff", "#8fd3b", "#8fd3b6800"])
def test_hex_to_rgba_rejects_other_lengths(bad):
    with pytest.raises(ValueError):
        hex_to_rgba(bad)


def test_css_color_keeps_six_digits_and_converts_eight():
    assert css_color("#8fd3b6") == "#8fd3b6"
    assert css_color("#8fd3b680") == "rgba(143, 211, 182, 0.502)"
    assert css_color("#000000ff") == "rgba(0, 0, 0, 1.000)"


def test_css_never_contains_eight_digit_hex(make_config):
    css = to_css(make_config(theme={"accent": "#8fd3b680", "text": "#e6e8eaff"}).theme, "mon-x")
    assert ".mon-x .active { color: rgba(143, 211, 182, 0.502); }" in css
    assert re.search(r"#[0-9a-fA-F]{8}\b", css) is None


def test_every_css_colour_parses_in_gtk3(make_config):
    gi = pytest.importorskip("gi")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk

    theme = make_config(theme={"accent": "#8fd3b680", "handle": "#7b7f84ff"}).theme
    values = re.findall(r"(?:color|background-color): ([^;]+);", to_css(theme, "mon-x"))
    assert len(values) >= 6
    for value in (v for v in values if v != "transparent"):
        assert Gdk.RGBA().parse(value), value
```

Append to `tests/test_config_models.py`:

```python
def test_eight_digit_colour_accepted_and_lowercased(make_config):
    assert make_config(theme={"frame": "#0B0C0D80"}).theme.frame == "#0b0c0d80"


@pytest.mark.parametrize("bad", ["#0b0c0d8", "#0b0c0d800", "0b0c0d80", "#0b0c0g80"])
def test_bad_alpha_colour_rejected_with_key_path(make_config, bad):
    with pytest.raises(ValidationError) as exc:
        make_config(theme={"frame": bad})
    assert exc.value.errors()[0]["loc"] == ("theme", "frame")
    assert "#rrggbbaa" in str(exc.value)
```

- [ ] **Step 2: Run them to see them fail**

Run: `scripts/py -m pytest -q tests/test_theme.py tests/test_config_models.py`
Expected: collection error `ImportError: cannot import name 'css_color' from 'shell.theme'`, and after that is fixed the model tests fail with `must be a #rrggbb hex color` for 8-digit values.

- [ ] **Step 3: Implement the model change**

In `shell/config/models.py` replace

```python
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_FONT_FORBIDDEN = re.compile(r'["\\{};]')  # font names go unescaped into generated CSS
_COLOR_FIELDS = (
```

with

```python
_HEX = re.compile(r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")  # #rrggbb or #rrggbbaa
_FONT_FORBIDDEN = re.compile(r'["\\{};]')  # font names go unescaped into generated CSS
COLOR_FIELDS = (
```

Add after `class _Strict` (before `class Theme`):

```python
def check_hex(value: str) -> str:
    if not _HEX.match(value):
        raise ValueError("must be a #rrggbb or #rrggbbaa hex color")
    return value.lower()
```

and replace the colour validator inside `Theme`:

```python
    @field_validator(*COLOR_FIELDS)
    @classmethod
    def _hex(cls, value: str) -> str:
        return check_hex(value)
```

- [ ] **Step 4: Implement the theme change**

In `shell/theme.py` change the import to `from shell.config.models import COLOR_FIELDS, Theme`, replace `hex_to_rgba` with:

```python
def hex_to_rgba(value: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    """'#rrggbb' or '#rrggbbaa' -> (r, g, b, a) in 0..1. The colour's own alpha (ff when
    absent) is multiplied by `alpha`, so 6-digit colours behave exactly as before."""
    h = value.lstrip("#")
    if len(h) not in (6, 8):
        raise ValueError(f"invalid colour {value!r}: expected #rrggbb or #rrggbbaa")
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    own = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
    return (r, g, b, own * alpha)


def css_color(value: str) -> str:
    """A theme colour as GTK3 CSS: '#rrggbb' unchanged, '#rrggbbaa' as rgba() (GTK3's CSS
    parser rejects 8-digit hex)."""
    h = value.lstrip("#")
    if len(h) != 8:
        return value
    r, g, b, a = (int(h[i : i + 2], 16) for i in (0, 2, 4, 6))
    return f"rgba({r}, {g}, {b}, {a / 255:.3f})"
```

and replace `to_css` with (same rules, every colour through `css_color`):

```python
def to_css(theme: Theme, scope: str) -> str:
    s = f".{scope}"
    c = {name: css_color(getattr(theme, name)) for name in COLOR_FIELDS}
    return f"""\
window{s}, {s} * {{ all: unset; font-family: {_font_stack(theme.font)}; color: {c["text"]}; }}
window{s} {{ background-color: transparent; }}
{s} #frame-strip {{ background-color: {c["frame"]}; }}
{s} #handle {{ min-width: 0; min-height: 0; padding: 0; }}
{s} .handle-dot {{ min-width: 3px; min-height: 3px; border-radius: 50%; background-color: {c["handle"]}; }}
{s} #handle:hover .handle-dot, {s} #handle:focus .handle-dot {{ background-color: {c["handle_hover"]}; }}
{s} .icon-button {{ min-width: 44px; min-height: 44px; border-radius: 10px; }}
{s} .icon-button:hover {{ background-color: {c["surface_hover"]}; }}
{s} .secondary {{ color: {c["text_secondary"]}; }}
{s} .active {{ color: {c["accent"]}; }}
{s} #clock-time {{ font-size: 20px; font-weight: 500; }}
"""  # noqa: E501
```

(Same-quote nesting inside the f-string needs Python 3.12+, which `pyproject.toml` requires.)

- [ ] **Step 5: Run the tests**

Run: `scripts/py -m pytest -q tests/test_theme.py tests/test_config_models.py`
Expected: all pass (15 in `test_theme.py`, 30 in `test_config_models.py`).

- [ ] **Step 6: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell/config/models.py shell/theme.py tests/test_theme.py tests/test_config_models.py
git commit -m "feat(theme): #rrggbbaa colours; CSS gets rgba() for GTK3" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
Expected VERIFY tail: no failures (the full count rises by 13).

---

### Task 2: Border and shadow theme tables with per-monitor deep merge

**Files:**
- Modify: `shell/config/models.py` (imports; new `deep_merge`, `Border`, `Shadow`; `Theme` fields; override models; `Config.theme_for`)
- Modify: `shell/config/loader.py:17-24` (drop `_deep_merge`, use `models.deep_merge`)
- Modify: `config.default.toml` (append two tables)
- Test: `tests/test_config_effects.py` (new)

**Interfaces:**
- Consumes: `check_hex` (Task 1).
- Produces:
  - `shell.config.models.deep_merge(base: dict, over: dict) -> dict` (nested dicts merge key by key; scalars and lists replace; inputs not mutated).
  - `shell.config.models.Border` (frozen): `enabled: bool = False`, `width: int = 2` (1..16), `color: str = "#8fd3b6ff"`.
  - `shell.config.models.Shadow` (frozen): `enabled: bool = False`, `elevation: int = 50` (0..100), `color: str = "#00000080"`.
  - `Theme.border: Border`, `Theme.shadow: Shadow` (defaults when absent).
  - `BorderOverride`, `ShadowOverride`, `ThemeOverride` (all fields optional, nested tables partial).
  - `Config.theme_for(name) -> Theme` now deep-merges the monitor override.
  - Diff behaviour (unchanged code, pinned by tests): any border/shadow change, including `enabled`, is `Change("restyle", monitor)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_effects.py`:

```python
"""[theme.border] / [theme.shadow]: validation, defaults, per-monitor deep merge, diff."""

import pytest
from pydantic import ValidationError

from shell.config.diff import Change, diff_configs
from shell.config.loader import load_config
from shell.config.models import Border, Shadow, deep_merge


def test_defaults_are_opt_in_and_calibrated(make_config):
    theme = make_config().theme
    assert theme.border == Border(enabled=False, width=2, color="#8fd3b6ff")
    assert theme.shadow == Shadow(enabled=False, elevation=50, color="#00000080")


def test_partial_table_keeps_the_other_defaults(make_config):
    shadow = make_config(theme={"shadow": {"enabled": True}}).theme.shadow
    assert shadow == Shadow(enabled=True, elevation=50, color="#00000080")


@pytest.mark.parametrize("elevation", [0, 100])
def test_elevation_bounds_inclusive(make_config, elevation):
    assert make_config(theme={"shadow": {"elevation": elevation}}).theme.shadow.elevation == (
        elevation
    )


@pytest.mark.parametrize(
    ("table", "loc"),
    [
        ({"shadow": {"elevation": -1}}, ("theme", "shadow", "elevation")),
        ({"shadow": {"elevation": 101}}, ("theme", "shadow", "elevation")),
        ({"shadow": {"color": "black"}}, ("theme", "shadow", "color")),
        ({"shadow": {"offset": 3}}, ("theme", "shadow", "offset")),
        ({"border": {"width": 0}}, ("theme", "border", "width")),
        ({"border": {"color": "#8fd3b6f"}}, ("theme", "border", "color")),
    ],
)
def test_bad_effect_values_report_the_key_path(make_config, table, loc):
    with pytest.raises(ValidationError) as exc:
        make_config(theme=table)
    assert exc.value.errors()[0]["loc"] == loc


def test_monitor_override_merges_nested_tables_key_by_key(make_config):
    cfg = make_config(
        theme={"shadow": {"enabled": True, "color": "#11223380"}},
        monitors={"HDMI-A-1": {"shell": "edge", "theme": {"shadow": {"elevation": 80}}}},
    )
    assert cfg.theme_for("HDMI-A-1").shadow == Shadow(enabled=True, elevation=80, color="#11223380")
    assert cfg.theme_for("DP-1").shadow == Shadow(enabled=True, elevation=50, color="#11223380")


def test_monitor_override_can_switch_an_effect_off(make_config):
    cfg = make_config(
        theme={"border": {"enabled": True}},
        monitors={"HDMI-A-1": {"theme": {"border": {"enabled": False}}}},
    )
    assert cfg.theme_for("HDMI-A-1").border.enabled is False
    assert cfg.theme_for("DP-1").border.enabled is True


def test_out_of_range_override_fails_at_load_with_its_path(make_config):
    with pytest.raises(ValidationError) as exc:
        make_config(monitors={"HDMI-A-1": {"theme": {"shadow": {"elevation": 150}}}})
    assert "monitors.HDMI-A-1.theme" in str(exc.value)
    assert "shadow.elevation" in str(exc.value)


def test_deep_merge_merges_tables_replaces_lists_and_copies():
    base = {"a": {"x": 1, "y": 2}, "l": [1, 2], "s": 1}
    out = deep_merge(base, {"a": {"y": 3}, "l": [9]})
    assert out == {"a": {"x": 1, "y": 3}, "l": [9], "s": 1}
    assert base == {"a": {"x": 1, "y": 2}, "l": [1, 2], "s": 1}  # not mutated


# ---- loader -----------------------------------------------------------------------


def test_default_file_defines_the_effect_tables():
    theme = load_config(None).theme
    assert theme.border == Border() and theme.shadow == Shadow()


def test_user_file_enables_shadow_and_keeps_defaults(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text("[theme.shadow]\nenabled = true\n")
    assert load_config(path).theme.shadow == Shadow(enabled=True)


def test_user_file_monitor_border_override(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text(
        '[monitors.HDMI-A-1]\nshell = "edge"\n[monitors.HDMI-A-1.theme.border]\nwidth = 4\n'
    )
    border = load_config(path).theme_for("HDMI-A-1").border
    assert border == Border(width=4)


# ---- diff -------------------------------------------------------------------------


def _mon(theme=None):
    return {"shell": "edge", "panels": [], "theme": theme or {}}


@pytest.mark.parametrize(
    "theme",
    [
        {"shadow": {"enabled": True}},
        {"shadow": {"elevation": 90}},
        {"shadow": {"color": "#ff000080"}},
        {"border": {"enabled": True}},
        {"border": {"width": 5, "color": "#ffffff40"}},
    ],
)
def test_effect_changes_are_a_restyle_not_a_rebuild(fake_registry, make_config, theme):
    old = make_config(monitors={"HDMI-A-1": _mon()})
    new = make_config(theme=theme, monitors={"HDMI-A-1": _mon()})
    assert diff_configs(old, new) == [Change("restyle", "HDMI-A-1")]


def test_per_monitor_effect_override_restyles_only_that_monitor(fake_registry, make_config):
    old = make_config(monitors={"HDMI-A-1": _mon(), "DP-2": _mon()})
    new = make_config(monitors={"HDMI-A-1": _mon({"border": {"enabled": True}}), "DP-2": _mon()})
    assert diff_configs(old, new) == [Change("restyle", "HDMI-A-1")]
```

- [ ] **Step 2: Run it to see it fail**

Run: `scripts/py -m pytest -q tests/test_config_effects.py`
Expected: `ImportError: cannot import name 'Border' from 'shell.config.models'`.

- [ ] **Step 3: Implement the models**

In `shell/config/models.py`:

1. Change `from typing import Annotated, Literal` to `from typing import Annotated, Any, Literal`.
2. After `check_hex` (Task 1) add:

```python
def deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    """`over` on top of `base`; nested tables merge key by key, scalars and lists replace."""
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class Border(_Strict):
    """Inner border along the outline of the frame and panels (spec 18). Opt-in."""

    enabled: bool = False
    width: Annotated[int, Field(ge=1, le=16)] = 2
    color: str = "#8fd3b6ff"

    @field_validator("color")
    @classmethod
    def _hex(cls, value: str) -> str:
        return check_hex(value)


class Shadow(_Strict):
    """Uniform shadow of the frame and panels (spec 18). Opt-in. `elevation` is 0-100 %."""

    enabled: bool = False
    elevation: Annotated[int, Field(ge=0, le=100)] = 50
    color: str = "#00000080"

    @field_validator("color")
    @classmethod
    def _hex(cls, value: str) -> str:
        return check_hex(value)
```

3. In `class Theme`, after `font: Annotated[list[str], Field(min_length=1)]` add:

```python
    border: Border = Field(default_factory=Border)
    shadow: Shadow = Field(default_factory=Shadow)
```

4. Replace the `ThemeOverride = create_model(...)` block (with its comment) by:

```python
def _override_of(name: str, model: type[BaseModel], nested: dict[str, type] | None = None):
    """Same fields as `model`, all optional (None = not set). Nested tables use the override
    model given in `nested`, so a partial `[monitors.X.theme.shadow]` table stays partial."""
    nested = nested or {}
    fields = {
        fname: (nested.get(fname, field.annotation) | None, None)
        for fname, field in model.model_fields.items()
    }
    return create_model(name, __base__=_Strict, **fields)


BorderOverride = _override_of("BorderOverride", Border)
ShadowOverride = _override_of("ShadowOverride", Shadow)
# Merged over the base theme (deep_merge) and re-validated by Theme.
ThemeOverride = _override_of(
    "ThemeOverride", Theme, {"border": BorderOverride, "shadow": ShadowOverride}
)
```

5. In `Config.theme_for` replace `return Theme.model_validate({**self.theme.model_dump(), **override})` by:

```python
        return Theme.model_validate(deep_merge(self.theme.model_dump(), override))
```

- [ ] **Step 4: Use the shared merge in the loader**

In `shell/config/loader.py` change the import to `from shell.config.models import Config, ConfigError, deep_merge`, delete the whole `_deep_merge` function, and in `load_config` replace `_deep_merge(data, ...)` by `deep_merge(data, ...)`.

- [ ] **Step 5: Add the defaults to `config.default.toml`**

Append at the end of the file (after `font = [...]`):

```toml

# Inner border along the frame and panel outline (spec section 18). Opt-in.
[theme.border]
enabled = false
width = 2               # px, drawn on the frame side of the outline
color = "#8fd3b6ff"     # #rrggbb or #rrggbbaa (the alpha makes it translucent)

# Uniform shadow of the frame and panels onto the desktop. Opt-in.
[theme.shadow]
enabled = false
elevation = 50          # 0-100 %; 100 % reaches 48 px
color = "#00000080"     # #rrggbb or #rrggbbaa; the alpha is the shadow's strength
```

- [ ] **Step 6: Run the tests**

Run: `scripts/py -m pytest -q tests/test_config_effects.py tests/test_config_loader.py tests/test_config_models.py tests/test_config_diff.py`
Expected: all pass (23 new; `test_defaults_only_matches_test_theme` still passes because the file's values equal the model defaults).

- [ ] **Step 7: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell/config/models.py shell/config/loader.py config.default.toml tests/test_config_effects.py
git commit -m "feat(config): opt-in [theme.border] and [theme.shadow], deep per-monitor merge" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Move the spike's outline and effects into `shell/canvas/`, with the legacy contract

**Files:**
- Create: `shell/canvas/__init__.py` (empty), `shell/canvas/outline.py`, `shell/canvas/effects.py` (copied from `spikes/canvas/`, edits below), `shell/canvas/style.py`
- Create: `tests/legacy_draw.py` (copy of `shell/draw.py`), `tests/test_canvas_outline.py`, `tests/test_canvas_effects.py` (copied from `spikes/tests/`, edits below), `tests/test_canvas_style.py`
- Leave untouched: `shell/draw.py` (the panels still draw with it until Task 8) and `spikes/` (removed in Task 12).

**Interfaces:**
- Consumes: `shell.geometry.join_radius`, `is_horizontal`; `shell.theme.hex_to_rgba` (Task 1); `Theme.border/.shadow` (Task 2).
- Produces:
  - `shell.canvas.outline.Panel = tuple[str, int, int, int, float]` = `(edge, pos, length, depth_full, d_now)` where `pos` is the body start in screen px from the left (top/bottom) or top (left/right).
  - `outline_path(cr, w, h, T, R, panels: list[Panel]) -> None`, `fill_mass(cr, w, h, T, R, panels, rgba) -> None` (unchanged from the spike).
  - `shell.canvas.effects`: `RGBA`, `MAX_REACH_PX = 48`, `reach_px(elevation_pct: float) -> int`, `shadow_levels(elevation: int, alpha: float) -> tuple[float, ...]`, `draw_border(cr, w, h, T, R, panels, width, rgba)`, `draw_shadow_uniform(cr, w, h, T, R, panels, elevation_pct, rgba)`, `draw_shadow_reach(...)`, `draw_scene(cr, w, h, T, R, panels, mass_rgba, border: tuple[float, RGBA] | None = None, shadow: tuple[float, RGBA] | None = None, clip: tuple[int, int, int, int] | None = None)`. `parse_rgba_hex` is NOT migrated (use `shell.theme.hex_to_rgba`).
  - `shell.canvas.style.CanvasStyle(mass: RGBA, border: tuple[float, RGBA] | None, shadow: tuple[float, RGBA] | None)` with property `pad -> int` (= `reach_px(elevation)` if shadow + `ceil(width)` if border), and `style_for(theme: Theme) -> CanvasStyle` (`shadow` is None when disabled or elevation 0).
  - `tests/legacy_draw.py`: `draw_panel`, `draw_screen_corner` (verbatim copies; test-only).

- [ ] **Step 1: Copy the files**

```bash
mkdir -p shell/canvas
touch shell/canvas/__init__.py
cp spikes/canvas/outline.py shell/canvas/outline.py
cp spikes/canvas/effects.py shell/canvas/effects.py
cp shell/draw.py tests/legacy_draw.py
cp spikes/tests/test_outline.py tests/test_canvas_outline.py
cp spikes/tests/test_effects.py tests/test_canvas_effects.py
```

- [ ] **Step 2: Point the copied tests at the new modules (they fail until Step 4)**

In `tests/test_canvas_outline.py` insert a first line `"""Contract: the one union outline equals the legacy per-window renderers (tests/legacy_draw.py)."""` plus a blank line, and replace the two imports

```python
from shell.draw import draw_panel, draw_screen_corner
from spikes.canvas.outline import fill_mass, outline_path
```

with

```python
from shell.canvas.outline import fill_mass, outline_path
from tests.legacy_draw import draw_panel, draw_screen_corner
```

In `tests/test_canvas_effects.py`: replace `from spikes.canvas import effects` by `from shell.canvas import effects`; replace `from spikes.canvas.effects import (` by `from shell.canvas.effects import (`; delete the line `    parse_rgba_hex,` from that import list; replace `from spikes.canvas.outline import fill_mass` by `from shell.canvas.outline import fill_mass`; delete everything from the line `# ---- parse_rgba_hex ---…` to the end of the file (the two `parse_rgba_hex` tests; `hex_to_rgba` is covered by Task 1); rename

```python
def test_default_max_reach_placeholder():
    assert MAX_REACH_PX == 48  # the only place the default is pinned
```

to

```python
def test_max_reach_is_48_px():
    assert MAX_REACH_PX == 48  # calibrated with Phil (spec 18); the only place it is pinned
```

In `tests/legacy_draw.py` replace the first line (module docstring) by:

```python
"""TEST-ONLY reference: the per-window renderers the core shell used before the shape canvas.

Kept verbatim from shell/draw.py so tests/test_canvas_outline.py can prove the union outline
draws the same shapes. Not imported by shell code."""
```

Create `tests/test_canvas_style.py`:

```python
import pytest

from shell.canvas.style import CanvasStyle, style_for


def test_effects_off_by_default(make_config):
    style = style_for(make_config().theme)
    assert style == CanvasStyle(mass=(11 / 255, 12 / 255, 13 / 255, 1.0), border=None, shadow=None)
    assert style.pad == 0


def test_enabled_effects_carry_width_elevation_and_rgba(make_config):
    theme = make_config(
        theme={"border": {"enabled": True}, "shadow": {"enabled": True, "elevation": 100}}
    ).theme
    style = style_for(theme)
    assert style.border[0] == 2
    assert style.border[1] == pytest.approx((0x8F / 255, 0xD3 / 255, 0xB6 / 255, 1.0))
    assert style.shadow[0] == 100
    assert style.shadow[1] == pytest.approx((0.0, 0.0, 0.0, 0x80 / 255))
    assert style.pad == 48 + 2


def test_zero_elevation_means_no_shadow(make_config):
    theme = make_config(theme={"shadow": {"enabled": True, "elevation": 0}}).theme
    assert style_for(theme).shadow is None


def test_translucent_frame_colour_reaches_the_mass(make_config):
    style = style_for(make_config(theme={"frame": "#0b0c0d80"}).theme)
    assert style.mass[3] == pytest.approx(0x80 / 255)


def test_pad_at_default_elevation(make_config):
    theme = make_config(theme={"shadow": {"enabled": True}}).theme
    assert style_for(theme).pad == 24  # 50 % of 48 px
```

Run: `scripts/py -m pytest -q tests/test_canvas_outline.py tests/test_canvas_effects.py tests/test_canvas_style.py`
Expected (verified in a scratch copy): collection stops with `ERROR tests/test_canvas_style.py` / `ModuleNotFoundError: No module named 'shell.canvas.style'` / `Interrupted: 1 error during collection`. The two copied test files would already pass at this point, because `spikes` is importable from the repo root and the copied `shell/canvas/effects.py` still imports `spikes.canvas.outline`; Step 3 removes that dependency.

- [ ] **Step 3: Edit the copied modules**

`shell/canvas/outline.py`: replace the module docstring (line 1) with

```python
"""Union outline of the desktop region: one closed path for frame + corners + all panels.

Pure cairo. Migrated from the shape-canvas spike (spikes/canvas/outline.py at 872eff9).
`tests/test_canvas_outline.py` pins it to the legacy per-window renderers (tests/legacy_draw.py).
"""
```

The rest of the file is unchanged.

`shell/canvas/effects.py`:
1. Replace the module docstring with

```python
"""Border and uniform shadow driven by the one union outline path (spec section 18). Pure cairo.

Controls: border = (width px, RGBA); shadow = (elevation %, RGBA) where the colour's alpha is
the strength. No offset, no top/bottom bias, no second layer. Migrated from the shape-canvas
spike (spikes/canvas/effects.py at 872eff9) without behaviour changes.
"""
```

2. Delete `import re`; replace `from spikes.canvas.outline import Panel, fill_mass, outline_path` by `from shell.canvas.outline import Panel, fill_mass, outline_path`.
3. Change the `MAX_REACH_PX` comment to `# shadow reach at elevation 100 % (logical px), calibrated with Phil`.
4. Delete the `_HEX_RE = re.compile(...)` line and the whole `parse_rgba_hex` function (they sit between `reach_px` and `_mul_un8`).

Everything else (`reach_px`, `_mul_un8`, `_over`, `shadow_levels`, `draw_border`, `draw_shadow_uniform`, `draw_shadow_reach`, `draw_scene`) stays byte-identical.

- [ ] **Step 4: Create `shell/canvas/style.py`**

```python
"""Theme -> what the shape canvas paints (mass colour, border, shadow). Pure."""

from __future__ import annotations

import math
from dataclasses import dataclass

from shell.canvas.effects import RGBA, reach_px
from shell.config.models import Theme
from shell.theme import hex_to_rgba


@dataclass(frozen=True)
class CanvasStyle:
    mass: RGBA
    border: tuple[float, RGBA] | None  # (width px, rgba) or None when disabled
    shadow: tuple[float, RGBA] | None  # (elevation %, rgba) or None when disabled / 0 %

    @property
    def pad(self) -> int:
        """How far past a panel's box a depth change can alter pixels: reach + border width."""
        reach = reach_px(self.shadow[0]) if self.shadow is not None else 0
        width = math.ceil(self.border[0]) if self.border is not None else 0
        return reach + width


def style_for(theme: Theme) -> CanvasStyle:
    border, shadow = theme.border, theme.shadow
    return CanvasStyle(
        mass=hex_to_rgba(theme.frame),
        border=(border.width, hex_to_rgba(border.color)) if border.enabled else None,
        shadow=(
            (shadow.elevation, hex_to_rgba(shadow.color))
            if shadow.enabled and shadow.elevation > 0
            else None
        ),
    )
```

- [ ] **Step 5: Run the tests**

Run: `scripts/py -m pytest -q tests/test_canvas_outline.py tests/test_canvas_effects.py tests/test_canvas_style.py`
Expected: all pass (22 + 26 + 5). The outline-vs-legacy contract (`test_canvas_matches_per_window_renderers`, 4 edges x 5 depths) is the migration's proof.

- [ ] **Step 6: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell/canvas/__init__.py shell/canvas/outline.py shell/canvas/effects.py shell/canvas/style.py tests/legacy_draw.py tests/test_canvas_outline.py tests/test_canvas_effects.py tests/test_canvas_style.py
git commit -m "feat(canvas): outline and effects move from the spike into shell/canvas" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 4: Scene model, damage boxes, CanvasPainter and the headless simulation

**Files:**
- Create: `shell/canvas/scene.py`, `shell/canvas/painter.py`, `shell/canvas/simulate.py`
- Test: `tests/test_canvas_scene.py`

**Interfaces:**
- Consumes: `shell.canvas.outline.Panel`, `shell.canvas.effects.draw_scene`, `shell.canvas.style.CanvasStyle` / `style_for` (Task 3), `shell.anim.Tween` (existing: `Tween(widget, on_value, duration_ms=280, delay_ms=0)` with `jump_to(target)`, `animate_to(target)`; it calls `widget.add_tick_callback(fn)` / `widget.remove_tick_callback(id)` and `clock.get_frame_time()`), `shell.config.models.Edge`, `Theme`.
- Produces:
  - `shell.canvas.scene.Box = tuple[int, int, int, int]` = `(x0, y0, x1, y1)`, x1/y1 exclusive.
  - `PanelShape(edge: Edge, pos: int, length: int, depth: int)` (frozen dataclass; `pos` = body start, as in `Panel`).
  - `union_boxes(a: Box | None, b: Box | None) -> Box | None`; `box_to_rect(box) -> (x, y, w, h)`.
  - `panel_box(shape, d, width, height, thickness, radius, pad) -> Box`.
  - `Scene(width, height, thickness, radius, pad=0)` with `resize(w, h)`, `set_pad(pad)`, `full_box() -> Box`, `add_panel(key, shape, depth=0.0) -> Box`, `remove_panel(key) -> Box | None`, `set_depth(key, d) -> Box | None` (None if unknown key or unchanged depth), `depth(key)`, `depths() -> dict`, `keys()`, `outline_panels() -> list[Panel]`; attributes `width`, `height`, `thickness`, `radius`, `pad`.
  - `shell.canvas.painter.Recorder` protocol: `on_tick(key, depth) -> None`, `on_draw(duration_ms: float, full: bool) -> None`.
  - `CanvasPainter(scene, style, invalidate: Callable[[Box | None], None])` with attributes `scene`, `style`, `recorder: Recorder | None`; property `needs_full`; methods `set_style(style)`, `resize(w, h) -> bool`, `add_panel(key, shape)`, `remove_panel(key)`, `set_depth(key, d)`, `draw(cr, clip: tuple[int, int, int, int] | None)`. `invalidate(None)` means "everything".
  - `shell.canvas.simulate`: `FRAME_US = 16_667`, `NOISE = 3`, `FakeClock`, `FakeTicker`, `SimResult`, `compare(a: bytes, b: bytes) -> tuple[int, int]`, `simulate(theme, size, shapes, frames, toggle_every=18, check_every=0, recorder=None, clock=None) -> SimResult`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_canvas_scene.py`:

```python
"""Scene model, damage boxes, CanvasPainter and the headless tick/draw simulation."""

import random

import cairo
import pytest

from shell.canvas.painter import CanvasPainter
from shell.canvas.scene import PanelShape, Scene, box_to_rect, panel_box, union_boxes
from shell.canvas.simulate import FRAME_US, FakeClock, FakeTicker, compare, simulate
from shell.canvas.style import style_for

W, H, T, R = 1920, 1080, 10, 14
DOCK = PanelShape("bottom", 680, 560, 64)


def contains(outer, inner):
    return (
        outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and outer[2] >= inner[2]
        and outer[3] >= inner[3]
    )


# ---- boxes --------------------------------------------------------------------------


def test_union_is_none_safe_and_commutative():
    a, b = (10, 20, 30, 40), (5, 25, 50, 35)
    assert union_boxes(None, None) is None
    assert union_boxes(a, None) == union_boxes(None, a) == a
    assert union_boxes(a, b) == union_boxes(b, a) == (5, 20, 50, 40)


def test_box_to_rect():
    assert box_to_rect((5, 6, 15, 26)) == (5, 6, 10, 20)


@pytest.mark.parametrize(
    ("edge", "expected"),
    [
        ("bottom", (680 - 14 - 3, 1080 - 10 - 64 - 3, 680 + 560 + 14 + 3, 1080)),
        ("top", (680 - 14 - 3, 0, 680 + 560 + 14 + 3, 10 + 64 + 3)),
        ("left", (0, 680 - 14 - 3, 10 + 64 + 3, 680 + 560 + 14 + 3)),
        ("right", (1920 - 10 - 64 - 3, 680 - 14 - 3, 1920, 680 + 560 + 14 + 3)),
    ],
)
def test_panel_box_on_every_edge(edge, expected):
    shape = PanelShape(edge, 680, 560, 64)
    got = panel_box(shape, 64.0, W, H, T, R, 3)
    assert got == (expected[0], expected[1], min(W, expected[2]), min(H, expected[3]))


def test_panel_box_rounds_fractional_depth_outward_and_clamps():
    assert panel_box(DOCK, 3.2, W, H, T, R, 0)[1] == 1080 - 10 - 4
    near = PanelShape("top", 5, 100, 40)
    x0, y0, x1, y1 = panel_box(near, 40, W, H, T, R, 48)
    assert (x0, y0) == (0, 0) and x1 == 5 + 100 + 14 + 48 and y1 == 10 + 40 + 48


# ---- scene --------------------------------------------------------------------------


def test_set_depth_damages_old_and_new_footprint():
    scene = Scene(W, H, T, R, pad=26)
    scene.add_panel("dock", DOCK)
    prev = panel_box(DOCK, 0.0, W, H, T, R, 26)
    for d in (5.0, 30.5, 64.0, 12.0, 0.0):
        box = scene.set_depth("dock", d)
        now = panel_box(DOCK, d, W, H, T, R, 26)
        assert contains(box, prev) and contains(box, now)
        prev = now


def test_set_depth_unchanged_or_unknown_is_none():
    scene = Scene(W, H, T, R)
    scene.add_panel(1, DOCK, depth=10.0)
    assert scene.set_depth(1, 10.0) is None
    assert scene.set_depth("nope", 5.0) is None


def test_add_and_remove_return_the_footprint():
    scene = Scene(W, H, T, R, pad=4)
    box = scene.add_panel(1, DOCK, depth=64.0)
    assert box == panel_box(DOCK, 64.0, W, H, T, R, 4)
    assert scene.remove_panel(1) == box
    assert scene.remove_panel(1) is None
    assert scene.outline_panels() == []


def test_outline_panels_carry_current_depth():
    scene = Scene(W, H, T, R)
    scene.add_panel("a", DOCK)
    scene.add_panel("b", PanelShape("top", 876, 168, 46), depth=46.0)
    scene.set_depth("a", 12.5)
    assert sorted(scene.outline_panels()) == [
        ("bottom", 680, 560, 64, 12.5),
        ("top", 876, 168, 46, 46.0),
    ]
    assert scene.depths() == {"a": 12.5, "b": 46.0}


# ---- painter ------------------------------------------------------------------------


def make_painter(make_config, theme=None):
    seen = []
    scene = Scene(W, H, T, R)
    painter = CanvasPainter(scene, style_for(make_config(theme=theme).theme), seen.append)
    return painter, scene, seen


def test_painter_invalidates_damage_and_full_on_style(make_config):
    painter, scene, seen = make_painter(make_config)
    painter.add_panel(1, DOCK)
    painter.set_depth(1, 20.0)
    painter.set_depth(1, 20.0)  # unchanged: nothing
    assert len(seen) == 2 and all(box is not None for box in seen)
    painter.set_style(style_for(make_config(theme={"shadow": {"enabled": True}}).theme))
    assert seen[-1] is None and scene.pad == 24 and painter.needs_full


def test_painter_resize_only_when_different(make_config):
    painter, scene, seen = make_painter(make_config)
    assert painter.resize(W, H) is False and seen == []
    assert painter.resize(1280, 720) is True and seen == [None]
    assert (scene.width, scene.height) == (1280, 720)


def test_first_draw_is_full_even_with_a_clip(make_config):
    painter, _, _ = make_painter(make_config)
    calls = []

    class Rec:
        def on_tick(self, key, depth):
            calls.append(("tick", key, depth))

        def on_draw(self, ms, full):
            calls.append(("draw", full))

    painter.recorder = Rec()
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    painter.draw(cairo.Context(surface), (0, 0, 10, 10))
    painter.add_panel(1, DOCK)
    painter.set_depth(1, 3.0)
    painter.draw(cairo.Context(surface), (600, 1000, 700, 80))
    assert calls == [("draw", True), ("tick", 1, 3.0), ("draw", False)]


# ---- simulation: the real Tween -> painter -> clipped draw loop ---------------------


def test_fake_ticker_runs_and_drops_finished_callbacks():
    ticker, clock = FakeTicker(), FakeClock()
    seen = []
    ticker.add_tick_callback(lambda w, c: seen.append(c.get_frame_time()) or len(seen) < 2)
    for t in (0, FRAME_US, 2 * FRAME_US):
        clock.now_us = t
        ticker.run(clock)
    assert seen == [0, FRAME_US]


THEMES = [
    {},
    {"border": {"enabled": True, "width": 3, "color": "#ffffff80"}},
    {"shadow": {"enabled": True, "elevation": 50}},
    {"shadow": {"enabled": True, "elevation": 100}, "border": {"enabled": True}},
]


@pytest.mark.parametrize("theme", THEMES)
def test_damaged_redraws_equal_a_full_redraw(make_config, theme):
    """The core damage contract: after many clipped redraws of an animating scene the retained
    surface matches a fresh full redraw, up to cairo's arc tessellation noise (a few pixels)."""
    shapes = [
        PanelShape("bottom", 170, 260, 64),
        PanelShape("top", 300, 120, 46),
        PanelShape("right", 100, 120, 56),
        PanelShape("left", 140, 90, 40),
    ]
    res = simulate(make_config(theme=theme).theme, (640, 400), shapes, 80, check_every=7)
    assert res.checked == 12
    assert res.max_noisy <= 40 and res.max_diff <= 32, res
    assert res.full_draws == 1  # only the first draw
    assert res.draws > 60


def test_random_depth_jumps_never_leave_stale_pixels(make_config):
    """Drag-like arbitrary depth changes on several panels, several per frame."""
    theme = make_config(theme={"shadow": {"enabled": True}, "border": {"enabled": True}}).theme
    w, h = 500, 360
    shapes = {
        0: PanelShape("bottom", 140, 200, 60),
        1: PanelShape("bottom", 400, 50, 30),  # gap 60 >= 14 + 14
        2: PanelShape("top", 200, 100, 50),
        3: PanelShape("left", 120, 80, 70),
    }
    pending = []
    scene = Scene(w, h, theme.thickness, theme.radius)
    painter = CanvasPainter(scene, style_for(theme), pending.append)
    for key, shape in shapes.items():
        painter.add_panel(key, shape)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    painter.draw(cairo.Context(surface), None)
    pending.clear()
    rng = random.Random(7)
    for _ in range(40):
        for key in rng.sample(sorted(shapes), 2):
            painter.set_depth(key, rng.uniform(0, shapes[key].depth))
        cr = cairo.Context(surface)
        for box in pending:
            cr.rectangle(*box_to_rect(box))
        cr.clip()
        extents = None
        for box in pending:
            extents = union_boxes(extents, box)
        painter.draw(cr, box_to_rect(extents))
        pending.clear()
    fresh = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    CanvasPainter(scene, painter.style, lambda _b: None).draw(cairo.Context(fresh), None)
    surface.flush()
    fresh.flush()
    worst, noisy = compare(bytes(surface.get_data()), bytes(fresh.get_data()))
    assert noisy <= 40 and worst <= 32, (worst, noisy)


def test_simulation_at_1080p_keeps_damage_small(make_config):
    theme = make_config(theme={"shadow": {"enabled": True}}).theme
    res = simulate(theme, (W, H), [DOCK], 40)
    assert res.full_draws == 1
    assert max(res.damage_px[1:]) < 0.05 * W * H  # never a full-surface redraw while animating
```

- [ ] **Step 2: Run it to see it fail**

Run: `scripts/py -m pytest -q tests/test_canvas_scene.py`
Expected: `ModuleNotFoundError: No module named 'shell.canvas.painter'`.

- [ ] **Step 3: Create `shell/canvas/scene.py`**

```python
"""Per-monitor scene model for the shape canvas: monitor size, T, R, every panel's shape and
current depth, and the damaged box a depth change invalidates. Pure: no GTK, no cairo."""

from __future__ import annotations

import math
from collections.abc import Hashable
from dataclasses import dataclass

from shell.canvas.outline import Panel
from shell.config.models import Edge

Box = tuple[int, int, int, int]  # (x0, y0, x1, y1) in surface px; x1 / y1 exclusive


@dataclass(frozen=True)
class PanelShape:
    """A panel as the canvas draws it. `pos` is where the body starts along the edge, in px
    from the left (top/bottom edges) or from the top (left/right edges)."""

    edge: Edge
    pos: int
    length: int
    depth: int  # full depth past the frame


def union_boxes(a: Box | None, b: Box | None) -> Box | None:
    """Bounding union; None means 'no box' and is neutral."""
    if a is None:
        return b
    if b is None:
        return a
    return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])


def box_to_rect(box: Box) -> tuple[int, int, int, int]:
    """(x0, y0, x1, y1) -> (x, y, width, height), as queue_draw_area and draw_scene take it."""
    return box[0], box[1], box[2] - box[0], box[3] - box[1]


def panel_box(
    shape: PanelShape, d: float, width: int, height: int, thickness: int, radius: int, pad: int
) -> Box:
    """Every pixel the panel can affect at depth `d`: the body plus both fillets (radius <= R),
    from the screen edge to the body's inner edge, grown by `pad`, clamped to the surface."""
    a0 = shape.pos - radius - pad
    a1 = shape.pos + shape.length + radius + pad
    across = thickness + math.ceil(max(0.0, d)) + pad
    if shape.edge == "top":
        box = (a0, 0, a1, across)
    elif shape.edge == "bottom":
        box = (a0, height - across, a1, height)
    elif shape.edge == "left":
        box = (0, a0, across, a1)
    else:  # right
        box = (width - across, a0, width, a1)
    return max(0, box[0]), max(0, box[1]), min(width, box[2]), min(height, box[3])


class Scene:
    """What one monitor's canvas draws. Panels are keyed by any hashable (MonitorShell uses ints).

    `pad` is how far the effects reach past the outline (CanvasStyle.pad); damage boxes grow by it.
    """

    def __init__(self, width: int, height: int, thickness: int, radius: int, pad: int = 0):
        self.width, self.height = width, height
        self.thickness, self.radius = thickness, radius
        self.pad = pad
        self._shapes: dict[Hashable, PanelShape] = {}
        self._depths: dict[Hashable, float] = {}

    # ---- whole-surface changes (callers redraw everything) ----------------------------
    def resize(self, width: int, height: int) -> None:
        self.width, self.height = width, height

    def set_pad(self, pad: int) -> None:
        self.pad = pad

    def full_box(self) -> Box:
        return 0, 0, self.width, self.height

    # ---- panels -------------------------------------------------------------------------
    def add_panel(self, key: Hashable, shape: PanelShape, depth: float = 0.0) -> Box:
        """Add (or replace) a panel; returns the box to redraw."""
        old = self._box(key)
        self._shapes[key] = shape
        self._depths[key] = float(depth)
        return union_boxes(old, self._box(key))

    def remove_panel(self, key: Hashable) -> Box | None:
        """Forget a panel; returns the box it covered (None if it was unknown)."""
        box = self._box(key)
        self._shapes.pop(key, None)
        self._depths.pop(key, None)
        return box

    def set_depth(self, key: Hashable, d: float) -> Box | None:
        """Move a panel to depth `d`. Returns the damaged box (old and new footprint, grown by
        pad), or None when the key is unknown or the depth did not change."""
        if key not in self._shapes:
            return None
        d = float(d)
        if d == self._depths[key]:
            return None
        old = self._box(key)
        self._depths[key] = d
        return union_boxes(old, self._box(key))

    def depth(self, key: Hashable) -> float:
        return self._depths[key]

    def depths(self) -> dict[Hashable, float]:
        return dict(self._depths)

    def keys(self) -> list[Hashable]:
        return list(self._shapes)

    def outline_panels(self) -> list[Panel]:
        """Panels in the form shell.canvas.outline expects: (edge, pos, length, depth, d)."""
        return [
            (s.edge, s.pos, s.length, s.depth, self._depths[k]) for k, s in self._shapes.items()
        ]

    def _box(self, key: Hashable) -> Box | None:
        shape = self._shapes.get(key)
        if shape is None:
            return None
        return panel_box(
            shape,
            self._depths[key],
            self.width,
            self.height,
            self.thickness,
            self.radius,
            self.pad,
        )
```

- [ ] **Step 4: Create `shell/canvas/painter.py`**

```python
"""Everything the shape canvas window does except being a window. Pure: the GTK window passes
an `invalidate` callback (queue_draw_area / queue_draw) and calls draw() from its draw handler,
and shell.canvas.simulate drives the same object headlessly."""

from __future__ import annotations

import time
from collections.abc import Callable, Hashable
from typing import Protocol

import cairo

from shell.canvas.effects import draw_scene
from shell.canvas.scene import Box, PanelShape, Scene
from shell.canvas.style import CanvasStyle

Rect = tuple[int, int, int, int]  # (x, y, width, height)


class Recorder(Protocol):
    """Optional measurement hook (shell.canvas.stats.StatsRecorder implements it)."""

    def on_tick(self, key: Hashable, depth: float) -> None: ...

    def on_draw(self, duration_ms: float, full: bool) -> None: ...


class CanvasPainter:
    def __init__(self, scene: Scene, style: CanvasStyle, invalidate: Callable[[Box | None], None]):
        """`invalidate(box)` schedules a redraw of `box`; `invalidate(None)` of everything."""
        self.scene = scene
        self.style = style
        self.recorder: Recorder | None = None
        self._invalidate = invalidate
        self._needs_full = True  # the first draw is always a full redraw
        scene.set_pad(style.pad)

    @property
    def needs_full(self) -> bool:
        """True until the next draw() when a full redraw is pending (start, theme, resize)."""
        return self._needs_full

    # ---- changes ------------------------------------------------------------------------
    def set_style(self, style: CanvasStyle) -> None:
        """Theme change (colour, border, shadow): new pad, full redraw."""
        self.style = style
        self.scene.set_pad(style.pad)
        self._full()

    def resize(self, width: int, height: int) -> bool:
        """Adopt the real surface size; True (and a full redraw) when it changed."""
        if (width, height) == (self.scene.width, self.scene.height):
            return False
        self.scene.resize(width, height)
        self._full()
        return True

    def add_panel(self, key: Hashable, shape: PanelShape) -> None:
        self._damage(self.scene.add_panel(key, shape))

    def remove_panel(self, key: Hashable) -> None:
        self._damage(self.scene.remove_panel(key))

    def set_depth(self, key: Hashable, d: float) -> None:
        """Called from a panel's Tween on every frame; redraws only the damaged box."""
        box = self.scene.set_depth(key, d)
        if box is not None and self.recorder is not None:  # count only real depth changes
            self.recorder.on_tick(key, d)
        self._damage(box)

    # ---- drawing ------------------------------------------------------------------------
    def draw(self, cr: cairo.Context, clip: Rect | None) -> None:
        """Paint into `cr`. `clip` is the bounding rectangle of the region being redrawn (GTK:
        Gdk.cairo_get_clip_rectangle); None, or a pending full redraw, repaints everything."""
        full = self._needs_full or clip is None
        self._needs_full = False
        start = time.perf_counter()
        s, st = self.scene, self.style
        draw_scene(
            cr,
            s.width,
            s.height,
            s.thickness,
            s.radius,
            s.outline_panels(),
            st.mass,
            border=st.border,
            shadow=st.shadow,
            clip=None if full else clip,
        )
        if self.recorder is not None:
            self.recorder.on_draw((time.perf_counter() - start) * 1000, full)

    def _full(self) -> None:
        self._needs_full = True
        self._invalidate(None)

    def _damage(self, box: Box | None) -> None:
        if box is not None and box[2] > box[0] and box[3] > box[1]:
            self._invalidate(box)
```

- [ ] **Step 5: Create `shell/canvas/simulate.py`**

```python
"""Headless run of the real animation/draw loop: shell.anim.Tween on a fake frame clock drives
CanvasPainter.set_depth exactly as EdgePanel does, and the canvas "draw" happens once per frame
with the cairo clip set to the union of the invalidated boxes, the way GTK clips a draw handler.
Pure (cairo image surfaces)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import cairo

from shell.anim import Tween
from shell.canvas.painter import CanvasPainter
from shell.canvas.scene import Box, PanelShape, Scene, box_to_rect, union_boxes
from shell.canvas.style import style_for
from shell.config.models import Theme

FRAME_US = 16_667  # 60 Hz
# cairo's arc tessellation differs by a few levels between a clipped and a full redraw on a
# handful of anti-aliased pixels (measured: <= 15/255 on <= 10 channels at 640x400). A missed
# damaged region shows as hundreds of channels off by tens of levels.
NOISE = 3


class FakeClock:
    def __init__(self) -> None:
        self.now_us = 0

    def get_frame_time(self) -> int:
        return self.now_us


class FakeTicker:
    """The two methods of a Gtk.Widget that shell.anim.Tween uses, run by hand per frame."""

    def __init__(self) -> None:
        self._callbacks: dict[int, Callable] = {}
        self._next_id = 1

    def add_tick_callback(self, fn: Callable) -> int:
        tick_id, self._next_id = self._next_id, self._next_id + 1
        self._callbacks[tick_id] = fn
        return tick_id

    def remove_tick_callback(self, tick_id: int) -> None:
        self._callbacks.pop(tick_id, None)

    def run(self, clock: FakeClock) -> None:
        for tick_id, fn in list(self._callbacks.items()):
            if tick_id in self._callbacks and not fn(self, clock):
                self._callbacks.pop(tick_id, None)


@dataclass
class SimResult:
    frames: int = 0
    draws: int = 0
    full_draws: int = 0
    max_diff: int = 0  # worst channel difference vs a fresh full redraw, over checked frames
    max_noisy: int = 0  # most channels differing by more than NOISE in one checked frame
    checked: int = 0
    damage_px: list[int] = field(default_factory=list)  # summed box area per draw (approx.)


def _snapshot(surface: cairo.ImageSurface) -> bytes:
    surface.flush()
    return bytes(surface.get_data())


def compare(a: bytes, b: bytes) -> tuple[int, int]:
    """(largest channel difference, number of channels differing by more than NOISE)."""
    diffs = [abs(x - y) for x, y in zip(a, b, strict=True)]
    return max(diffs, default=0), sum(d > NOISE for d in diffs)


def simulate(
    theme: Theme,
    size: tuple[int, int],
    shapes: list[PanelShape],
    frames: int,
    toggle_every: int = 18,
    check_every: int = 0,
    recorder=None,
    clock: FakeClock | None = None,
) -> SimResult:
    """Run `frames` frames. Every `toggle_every` frames every panel flips between collapsed and
    extended (280 ms tweens at 60 Hz take 17 frames, so 18 keeps them moving). With
    `check_every` > 0, every n-th frame the retained surface is compared with a fresh full
    redraw (max channel difference recorded in `max_diff`)."""
    w, h = size
    clock = clock or FakeClock()
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    pending: list[Box | None] = [None]  # the window's first expose covers everything
    scene = Scene(w, h, theme.thickness, theme.radius)
    painter = CanvasPainter(scene, style_for(theme), pending.append)
    painter.recorder = recorder
    ticker = FakeTicker()
    tweens: list[tuple[Tween, PanelShape]] = []
    for key, shape in enumerate(shapes):
        painter.add_panel(key, shape)
        tween = Tween(ticker, lambda d, k=key: painter.set_depth(k, d), theme.duration_ms)
        tween.jump_to(0.0)
        tweens.append((tween, shape))
    result = SimResult()
    extended = False
    for i in range(frames):
        clock.now_us = i * FRAME_US
        if toggle_every and i % toggle_every == 0:
            extended = not extended
            for tween, shape in tweens:
                tween.animate_to(shape.depth if extended else 0.0)
        ticker.run(clock)
        result.frames += 1
        if pending:
            _draw_like_gtk(surface, painter, pending, result)
            pending.clear()
        if check_every and i % check_every == 0:
            fresh = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
            check = CanvasPainter(scene, painter.style, lambda _box: None)
            check.draw(cairo.Context(fresh), None)
            worst, noisy = compare(_snapshot(surface), _snapshot(fresh))
            result.max_diff = max(result.max_diff, worst)
            result.max_noisy = max(result.max_noisy, noisy)
            result.checked += 1
    return result


def _draw_like_gtk(
    surface: cairo.ImageSurface,
    painter: CanvasPainter,
    pending: list[Box | None],
    result: SimResult,
) -> None:
    """One draw handler call: cr clipped to the invalid region, clip rect = its extents."""
    cr = cairo.Context(surface)
    scene = painter.scene
    if any(box is None for box in pending):
        boxes = [scene.full_box()]
    else:
        boxes = [box for box in pending if box is not None]
    for box in boxes:
        cr.rectangle(*box_to_rect(box))
    cr.clip()
    extents = None
    for box in boxes:
        extents = union_boxes(extents, box)
    result.full_draws += painter.needs_full
    painter.draw(cr, box_to_rect(extents))
    result.draws += 1
    result.damage_px.append(sum((b[2] - b[0]) * (b[3] - b[1]) for b in boxes))
```

- [ ] **Step 6: Run the tests**

Run: `scripts/py -m pytest -q tests/test_canvas_scene.py`
Expected: 21 passed (about 3 s; the simulations compare full surfaces).

- [ ] **Step 7: Prove the damage tests bite (mutation check, then revert)**

Temporarily change `across = thickness + math.ceil(max(0.0, d)) + pad` to `across = thickness + math.ceil(max(0.0, d))` in `scene.py`, run `scripts/py -m pytest -q tests/test_canvas_scene.py`: expect failures in `test_damaged_redraws_equal_a_full_redraw[theme2]`/`[theme3]` and `test_random_depth_jumps_never_leave_stale_pixels`. Then temporarily make `set_depth` return `self._box(key)` instead of the union: expect `test_damaged_redraws_equal_a_full_redraw` failures for every theme. Undo both edits so `scene.py` again matches Step 3 exactly, and re-run: 21 passed.

- [ ] **Step 8: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell/canvas/scene.py shell/canvas/painter.py shell/canvas/simulate.py tests/test_canvas_scene.py
git commit -m "feat(canvas): scene model, damage boxes, painter and headless simulation" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Panel positions and the minimum geometry rules

**Files:**
- Create: `shell/panel_layout.py`
- Test: `tests/test_panel_layout.py`

**Interfaces:**
- Consumes: `shell.geometry.join_radius(d, radius) -> float`, `is_horizontal(edge)`; `shell.panel_spec.PanelGeometry(widget, edge, pos, length, depth, state, label)` (frozen dataclass; `pos: int | None`, None = centred); `shell.canvas.outline.fill_mass` and `tests/legacy_draw.py` (Task 3) in the tests.
- Produces:
  - `shell.panel_layout.MIN_LENGTH = 60`.
  - `Layout(panels: list[PanelGeometry | None], warnings: list[str])` (frozen). Same order as the input; every non-None entry has an **int** `pos` (body start) and possibly a shrunk `length`; None = not shown.
  - `resolve_layout(geos: list[PanelGeometry], width: int, height: int, thickness: int, radius: int, where: str = "monitor") -> Layout`. Warning texts start with `f"{where}.panels.{i} ({widget}): "`.
  - The rules (spec 17 minimum geometry, smallest safe version): with `r = join_radius(depth, R)` at full depth, clamp `pos` into `[ceil(T + R + r), floor(extent - T - R - r) - length]`; shrink `length` to the free span when it is longer; hide a panel whose span is under `MIN_LENGTH`; hide a later panel whose body box (full depth, from the screen edge) grown by its `r` overlaps an earlier accepted panel's grown box (same edge: gap `< r1 + r2`). Touching is allowed. Centred panels get `pos = (extent - length) // 2`, which equals the old compositor centring of the `(length + 2R)` surface plus `R`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_panel_layout.py`:

```python
"""Minimum geometry rules (spec 17): corner clearance and separation, so the outline never
self-intersects. Pixel tests pin the boundary cases to the legacy per-window renderers."""

import cairo
import pytest

from shell import geometry as g
from shell.canvas.outline import fill_mass
from shell.panel_layout import resolve_layout
from shell.panel_spec import PanelGeometry
from tests.legacy_draw import draw_panel, draw_screen_corner

W, H, T, R = 1920, 1080, 10, 14


def geo(widget="dock", edge="bottom", pos=None, length=560, depth=64, state="extended"):
    return PanelGeometry(widget, edge, pos, length, depth, state, widget)


def test_defaults_are_untouched_and_centred_panels_get_an_exact_pos():
    layout = resolve_layout(
        [geo(), geo("clock", "top", None, 168, 46), geo("bar", "right", 600, 300, 56)],
        W,
        H,
        T,
        R,
    )
    assert layout.warnings == []
    assert [(p.edge, p.pos, p.length) for p in layout.panels] == [
        ("bottom", 680, 560),
        ("top", 876, 168),
        ("right", 600, 300),
    ]


def test_centred_pos_matches_the_layer_shell_centring_of_the_old_surface():
    # the old window was (length + 2R) wide and centred by the compositor; body = surface + R
    for length in (168, 560, 561):
        p = resolve_layout([geo(length=length)], W, H, T, R).panels[0]
        assert p.pos == (W - (length + 2 * R)) // 2 + R


@pytest.mark.parametrize(
    ("pos", "expected"), [(0, 38), (37, 38), (38, 38), (5000, 1920 - 38 - 560)]
)
def test_pos_is_clamped_to_the_corner_clearance(pos, expected):
    layout = resolve_layout([geo(pos=pos)], W, H, T, R, where="monitors.HDMI-A-1")
    assert layout.panels[0].pos == expected
    if pos == expected:
        assert layout.warnings == []
    else:
        assert layout.warnings == [
            f"monitors.HDMI-A-1.panels.0 (dock): pos {pos} would run into a screen corner; "
            f"moved to {expected}"
        ]


def test_clearance_uses_the_join_radius_of_a_shallow_panel():
    # depth 16 -> r = 8: clearance 10 + 14 + 8 = 32
    assert resolve_layout([geo(pos=0, depth=16)], W, H, T, R).panels[0].pos == 32
    # depth 27 -> r = 13.5: clearance 37.5, rounded up so it is never violated
    assert resolve_layout([geo(pos=0, depth=27)], W, H, T, R).panels[0].pos == 38


def test_too_long_is_shrunk_to_the_free_span():
    layout = resolve_layout([geo("bar", "right", 100, 1500, 56)], W, H, T, R)
    p = layout.panels[0]
    assert (p.pos, p.length) == (38, 1080 - 2 * 38)
    assert "shrunk to 1004" in layout.warnings[0]


def test_no_room_at_all_hides_the_panel():
    layout = resolve_layout([geo("bar", "right", 0, 300, 56)], W, 130, T, R)
    assert layout.panels == [None]
    assert "has no room for it; not shown" in layout.warnings[0]


def test_neighbours_need_a_gap_of_r1_plus_r2():
    a = geo("dock", pos=400, length=300)  # ends at 700, r = 14
    ok = geo("clock", pos=700 + 14 + 8, length=100, depth=16)  # r = 8: gap exactly 22
    tight = geo("clock", pos=700 + 14 + 7, length=100, depth=16)
    assert resolve_layout([a, ok], W, H, T, R).warnings == []
    layout = resolve_layout([a, tight], W, H, T, R, where="monitors.X")
    assert layout.panels[1] is None and layout.panels[0] is not None
    assert layout.warnings[0].startswith(
        "monitors.X.panels.1 (clock): overlaps monitors.X.panels.0"
    )


def test_two_centred_panels_on_one_edge_keep_the_first():
    layout = resolve_layout([geo(), geo("clock", "bottom", None, 168, 46)], W, H, T, R)
    assert layout.panels[1] is None and len(layout.warnings) == 1


def test_deep_panels_on_neighbouring_edges_must_not_cross():
    top = geo("a", "top", 40, 300, 400)  # body x 40..340, y 0..410
    left = geo("b", "left", 40, 300, 400)  # body x 0..410, y 40..340
    layout = resolve_layout([top, left], W, H, T, R)
    assert layout.panels[1] is None
    far = geo("b", "left", 600, 300, 400)
    assert resolve_layout([top, far], W, H, T, R).warnings == []


def test_panels_on_different_edges_far_apart_are_fine():
    layout = resolve_layout(
        [geo("a", "bottom", None), geo("b", "top", None), geo("c", "left", None, 300, 50)],
        W,
        H,
        T,
        R,
    )
    assert layout.warnings == [] and None not in layout.panels


# ---- the rule boundaries render like the legacy per-window code --------------------

SW, SH = 400, 300
RGBA = (0.04, 0.05, 0.05, 1.0)


def alpha_rows(surface):
    surface.flush()
    data, stride = surface.get_data(), surface.get_stride()
    return [[data[y * stride + x * 4 + 3] for x in range(SW)] for y in range(SH)]


def legacy(panels):
    """Strips + corner pieces + each panel at its EdgePanel surface origin (union of fills)."""
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, SW, SH)
    cr = cairo.Context(s)
    cr.set_source_rgba(*RGBA)
    for rect in [(0, 0, SW, T), (0, SH - T, SW, T), (0, 0, T, SH), (SW - T, 0, T, SH)]:
        cr.rectangle(*rect)
    cr.fill()
    for corner, (ox, oy) in {
        "top-left": (T, T),
        "top-right": (SW - T - R, T),
        "bottom-left": (T, SH - T - R),
        "bottom-right": (SW - T - R, SH - T - R),
    }.items():
        cr.save()
        cr.translate(ox, oy)
        draw_screen_corner(cr, corner, R, RGBA)
        cr.restore()
    for edge, pos, length, depth, d in panels:
        sw, sh = g.surface_size(edge, length, depth, T, R)
        along = sw if g.is_horizontal(edge) else sh
        _, margin = g.anchor_and_margin(edge, pos, along, R, SW if g.is_horizontal(edge) else SH)
        top_m, _, _, left_m = (int(m[:-2]) for m in margin.split())
        origin = {
            "top": (left_m, 0),
            "bottom": (left_m, SH - sh),
            "left": (0, top_m),
            "right": (SW - sw, top_m),
        }[edge]
        cr.save()
        cr.translate(*origin)
        draw_panel(cr, edge, length, depth, d, T, R, RGBA)
        cr.restore()
    return alpha_rows(s)


def outline(panels):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, SW, SH)
    fill_mass(cairo.Context(s), SW, SH, T, R, panels, RGBA)
    return alpha_rows(s)


def bad_pixels(a, b):
    return sum(1 for y in range(SH) for x in range(SW) if abs(a[y][x] - b[y][x]) > 24)


def as_outline(layout, d_fraction=1.0):
    return [(p.edge, p.pos, p.length, p.depth, p.depth * d_fraction) for p in layout.panels if p]


@pytest.mark.parametrize("edge", ["top", "bottom", "left", "right"])
@pytest.mark.parametrize("fraction", [1.0, 0.5, 0.2])
def test_panel_clamped_to_the_corner_renders_like_legacy(edge, fraction):
    layout = resolve_layout([geo("p", edge, 0, 120, 50)], SW, SH, T, R)
    assert layout.panels[0].pos == T + R + 14
    panels = as_outline(layout, fraction)
    assert bad_pixels(legacy(panels), outline(panels)) <= 2


def test_without_the_clamp_the_outline_breaks_inside_the_corner_arc():
    panels = [("top", 20, 120, 50, 50.0)]  # pos - r = 6 < T + R: the fillet hits the arc
    assert bad_pixels(legacy(panels), outline(panels)) > 20


@pytest.mark.parametrize("fraction", [1.0, 0.6, 0.3])
def test_neighbours_at_the_minimum_gap_render_like_legacy(fraction):
    layout = resolve_layout(
        [geo("a", "top", 60, 100, 50), geo("b", "top", 60 + 100 + 28, 80, 50)], SW, SH, T, R
    )
    assert None not in layout.panels and layout.warnings == []
    panels = as_outline(layout, fraction)
    assert bad_pixels(legacy(panels), outline(panels)) <= 2
```

- [ ] **Step 2: Run it to see it fail**

Run: `scripts/py -m pytest -q tests/test_panel_layout.py`
Expected: `ModuleNotFoundError: No module named 'shell.panel_layout'`.

- [ ] **Step 3: Create `shell/panel_layout.py`**

```python
"""Resolve every panel of one monitor to an exact position, enforcing the minimum geometry the
single-outline canvas needs (spec 17, "Minimum geometry rules"). Pure: no GTK.

The full align/offset/gap layout resolver is a later plan; this is the smallest safe rule set:

1. Corner clearance: a panel's fillet must not reach into a screen-corner arc, so
   `pos - r >= T + R` at both ends of the edge, with `r = join_radius(depth, R)` (the join
   radius at full depth, the widest it gets). Positions are clamped into that free span; a
   panel longer than the span is shrunk to fit; one that cannot keep MIN_LENGTH is not shown.
2. Separation: the body boxes (full depth, from the screen edge), each grown by its own `r`,
   must not overlap. On one edge that is the minimum gap `r1 + r2`; it also catches deep panels
   on neighbouring or opposite edges that would cross. A later panel (config order) that
   breaks it is not shown.

Every adjustment produces a warning naming the key path. Touching (gap exactly `r1 + r2`,
pos exactly at the clearance) is allowed: the outline renders it correctly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from shell import geometry
from shell.panel_spec import PanelGeometry

MIN_LENGTH = 60  # same floor as the config model's Length

Box = tuple[float, float, float, float]  # x0, y0, x1, y1


@dataclass(frozen=True)
class Layout:
    panels: list[PanelGeometry | None]  # input order; pos is always an int; None = not shown
    warnings: list[str]


def _grown_body(geo: PanelGeometry, width: int, height: int, thickness: int, r: float) -> Box:
    a0, a1 = geo.pos - r, geo.pos + geo.length + r
    across = thickness + geo.depth + r
    if geo.edge == "top":
        return (a0, -r, a1, across)
    if geo.edge == "bottom":
        return (a0, height - across, a1, height + r)
    if geo.edge == "left":
        return (-r, a0, across, a1)
    return (width - across, a0, width + r, a1)


def _overlap(a: Box, b: Box) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def resolve_layout(
    geos: list[PanelGeometry],
    width: int,
    height: int,
    thickness: int,
    radius: int,
    where: str = "monitor",
) -> Layout:
    """`where` prefixes warnings, e.g. "monitors.HDMI-A-1"."""
    out: list[PanelGeometry | None] = []
    warnings: list[str] = []
    placed: list[tuple[int, PanelGeometry, Box]] = []
    for i, geo in enumerate(geos):
        name = f"{where}.panels.{i} ({geo.widget})"
        extent = width if geometry.is_horizontal(geo.edge) else height
        r = geometry.join_radius(geo.depth, radius)
        clearance = thickness + radius + r  # corner clearance at each end of the edge
        lo, hi = math.ceil(clearance), math.floor(extent - clearance)  # body start / end limits
        span = hi - lo
        length = geo.length
        if length > span:
            if span < MIN_LENGTH:
                warnings.append(
                    f"{name}: the {geo.edge} edge ({extent} px) has no room for it; not shown"
                )
                out.append(None)
                continue
            warnings.append(
                f"{name}: length {length} px does not fit the {geo.edge} edge; shrunk to {span}"
            )
            length = span
        wanted = (extent - length) // 2 if geo.pos is None else geo.pos
        pos = min(max(wanted, lo), hi - length)
        if geo.pos is not None and pos != geo.pos:
            warnings.append(f"{name}: pos {geo.pos} would run into a screen corner; moved to {pos}")
        resolved = replace(geo, pos=pos, length=length)
        box = _grown_body(resolved, width, height, thickness, r)
        clash = next((j for j, _g, other in placed if _overlap(box, other)), None)
        if clash is not None:
            other = next(g for j, g, _b in placed if j == clash)
            warnings.append(
                f"{name}: overlaps {where}.panels.{clash} ({other.widget}) or leaves less than "
                f"the minimum gap between their joins; not shown"
            )
            out.append(None)
            continue
        placed.append((i, resolved, box))
        out.append(resolved)
    return Layout(out, warnings)
```

- [ ] **Step 4: Run the tests**

Run: `scripts/py -m pytest -q tests/test_panel_layout.py`
Expected: 29 passed. (Measured while planning: the clamped and minimum-gap cases differ from the legacy renderers in 0 pixels; an unclamped panel at `pos = 20` differs in 29.)

- [ ] **Step 5: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell/panel_layout.py tests/test_panel_layout.py
git commit -m "feat(layout): exact panel positions with corner clearance and minimum gap" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: The ShapeCanvas window

**Files:**
- Create: `shell/canvas/canvas.py`
- Test: `tests/test_canvas_window.py`; Modify: `tests/test_gtk_imports.py` (import smoke)

**Interfaces:**
- Consumes: `CanvasPainter`, `Scene`, `PanelShape`, `Box`, `box_to_rect` (Task 4), `style_for` (Task 3), `shell.gdk_util.monitor_index`, `Theme`.
- Produces:
  - `shell.canvas.canvas.CANVAS_WINDOW: dict` = `{"layer": "top", "anchor": "top left bottom right", "exclusivity": "none", "keyboard_mode": "none", "pass_through": True}`.
  - `ShapeCanvas(monitor: Gdk.Monitor, theme: Theme, scope: str)` (a `WaylandWindow`, title `edge-shell-canvas`, shown on creation) with attributes `area: Gtk.DrawingArea`, `painter: CanvasPainter` and methods `set_theme(theme)`, `add_panel(key, shape: PanelShape)`, `remove_panel(key)`, `set_depth(key, d)`. Exactly the canvas surface Task 7 creates per monitor.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_canvas_window.py`:

```python
"""ShapeCanvas methods called on stand-ins: no window is ever created (that would draw)."""

from types import SimpleNamespace

import cairo
import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

from shell.canvas.canvas import ShapeCanvas  # noqa: E402
from shell.canvas.painter import CanvasPainter  # noqa: E402
from shell.canvas.scene import PanelShape, Scene  # noqa: E402
from shell.canvas.style import style_for  # noqa: E402


class FakeArea:
    def __init__(self):
        self.calls = []

    def queue_draw(self):
        self.calls.append("all")

    def queue_draw_area(self, x, y, w, h):
        self.calls.append((x, y, w, h))


def stand_in(make_config, size=(400, 300), monitor_size=None):
    area = FakeArea()
    s = SimpleNamespace(area=area, _size_warned=False)
    s._monitor_size = monitor_size or size
    s._invalidate = lambda box: ShapeCanvas._invalidate(s, box)
    s._check_size = lambda: ShapeCanvas._check_size(s)
    s.painter = CanvasPainter(Scene(*size, 10, 14), style_for(make_config().theme), s._invalidate)
    return s


def test_invalidate_maps_boxes_to_queue_draw_area(make_config):
    s = stand_in(make_config)
    ShapeCanvas._invalidate(s, None)
    ShapeCanvas._invalidate(s, (10, 20, 110, 70))
    assert s.area.calls == ["all", (10, 20, 100, 50)]


def test_depth_change_queues_only_the_damaged_box(make_config):
    s = stand_in(make_config)
    ShapeCanvas.add_panel(s, 1, PanelShape("bottom", 100, 200, 64))
    s.area.calls.clear()
    ShapeCanvas.set_depth(s, 1, 30.0)
    assert s.area.calls == [(100 - 14, 300 - 10 - 30, 200 + 28, 10 + 30)]


def test_set_theme_queues_a_full_redraw_and_grows_the_pad(make_config):
    s = stand_in(make_config)
    ShapeCanvas.set_theme(s, make_config(theme={"shadow": {"enabled": True}}).theme)
    assert s.area.calls == ["all"] and s.painter.scene.pad == 24


def test_remove_panel_queues_its_footprint(make_config):
    s = stand_in(make_config)
    ShapeCanvas.add_panel(s, "k", PanelShape("top", 100, 100, 40))
    s.area.calls.clear()
    ShapeCanvas.remove_panel(s, "k")
    assert s.area.calls == [(86, 0, 128, 10)]  # collapsed footprint (depth 0)


def test_allocation_resizes_the_scene(make_config):
    s = stand_in(make_config)
    ShapeCanvas._on_allocate(s, None, SimpleNamespace(width=640, height=480))
    assert (s.painter.scene.width, s.painter.scene.height) == (640, 480)


def test_draw_handler_uses_the_cairo_clip_and_survives_errors(make_config, caplog):
    s = stand_in(make_config)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 400, 300)
    cr = cairo.Context(surface)
    assert ShapeCanvas._on_draw(s, None, cr) is False  # first draw: full
    surface.flush()
    assert surface.get_data()[3] == 255  # top-left pixel is frame

    def boom(_cr, _clip):
        raise RuntimeError("draw broke")

    s.painter.draw = boom
    assert ShapeCanvas._on_draw(s, None, cr) is False
    assert "shape canvas draw failed" in caplog.text


def test_size_mismatch_is_warned_once(make_config, caplog):
    s = stand_in(make_config, size=(400, 300), monitor_size=(1920, 1080))
    ShapeCanvas._check_size(s)
    ShapeCanvas._check_size(s)
    assert caplog.text.count("panels may be misaligned") == 1


def test_canvas_window_setup():
    from shell.canvas.canvas import CANVAS_WINDOW

    assert CANVAS_WINDOW == {
        "layer": "top",
        "anchor": "top left bottom right",
        "exclusivity": "none",  # then set_exclusive_zone(-1) in __init__
        "keyboard_mode": "none",
        "pass_through": True,
    }
```

In `tests/test_gtk_imports.py` add `    import shell.canvas.canvas  # noqa: F401` as the first line of `test_gtk_modules_import`.

- [ ] **Step 2: Run them to see them fail**

Run: `scripts/py -m pytest -q tests/test_canvas_window.py tests/test_gtk_imports.py`
Expected: `ModuleNotFoundError: No module named 'shell.canvas.canvas'`.

- [ ] **Step 3: Create `shell/canvas/canvas.py`**

Adapted from the spike's `Canvas`/`ClickThrough` (`spikes/canvas/live.py:441-464`, draw handler `:535-553`): Fabric's `pass_through=True` replaces the spike's manual empty-region re-apply (Fabric re-applies it after every allocate), and the drawing lives in `CanvasPainter`.

```python
"""The shape canvas window: one click-through, monitor-sized layer surface per monitor that
draws the frame, the screen corners and every panel shape as one outline, plus the border and
the shadow (spec 18, option B). A thin GTK shell over shell.canvas.painter.CanvasPainter."""

from __future__ import annotations

import logging
from collections.abc import Hashable

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from fabric.widgets.wayland import WaylandWindow
from gi.repository import Gdk, Gtk, GtkLayerShell

from shell.canvas.painter import CanvasPainter
from shell.canvas.scene import Box, PanelShape, Scene, box_to_rect
from shell.canvas.style import style_for
from shell.config.models import Theme
from shell.gdk_util import monitor_index

log = logging.getLogger(__name__)

# Layer-shell setup of the canvas. pass_through=True: Fabric's Window.do_size_allocate
# re-applies the EMPTY input region after every allocate (fabric/widgets/window.py), so the
# canvas never takes input. Same layer as the panels, created before them (MonitorShell).
CANVAS_WINDOW = {
    "layer": "top",
    "anchor": "top left bottom right",
    "exclusivity": "none",
    "keyboard_mode": "none",
    "pass_through": True,
}


class ShapeCanvas(WaylandWindow):
    def __init__(self, monitor, theme: Theme, scope: str):
        geo = monitor.get_geometry()
        if monitor.get_scale_factor() != 1:  # HiDPI is a later plan (reach x scale, clip area)
            log.warning(
                "scale %d is not supported yet: drawing at scale 1", monitor.get_scale_factor()
            )
        # Fabric's monitor property is an int: a Gdk.Monitor object is silently ignored.
        super().__init__(
            **CANVAS_WINDOW,
            monitor=monitor_index(monitor),
            title="edge-shell-canvas",
            name="shape-canvas",
            style_classes=[scope],
            visible=False,
        )
        # "none" alone is zone 0, which makes KWin shift us clear of other zones; -1 = cover all.
        GtkLayerShell.set_exclusive_zone(self, -1)
        self._monitor_size = (geo.width, geo.height)
        self._size_warned = False
        self.area = Gtk.DrawingArea()
        self.add(self.area)
        scene = Scene(geo.width, geo.height, theme.thickness, theme.radius)
        self.painter = CanvasPainter(scene, style_for(theme), self._invalidate)
        self.area.connect("size-allocate", self._on_allocate)
        self.area.connect("draw", self._on_draw)
        self.show_all()

    # ---- used by MonitorShell -----------------------------------------------------------
    def set_theme(self, theme: Theme) -> None:
        """Colour / border / shadow change (a restyle): full redraw, no rebuild."""
        self.painter.set_style(style_for(theme))

    def add_panel(self, key: Hashable, shape: PanelShape) -> None:
        self.painter.add_panel(key, shape)

    def remove_panel(self, key: Hashable) -> None:
        self.painter.remove_panel(key)

    def set_depth(self, key: Hashable, d: float) -> None:
        self.painter.set_depth(key, d)

    # ---- GTK ----------------------------------------------------------------------------
    def _invalidate(self, box: Box | None) -> None:
        if box is None:
            self.area.queue_draw()
        else:
            self.area.queue_draw_area(*box_to_rect(box))

    def _on_allocate(self, _area, alloc) -> None:
        self.painter.resize(alloc.width, alloc.height)

    def _on_draw(self, _area, cr) -> bool:
        try:
            self._check_size()
            ok, rect = Gdk.cairo_get_clip_rectangle(cr)
            self.painter.draw(cr, (rect.x, rect.y, rect.width, rect.height) if ok else None)
        except Exception:  # never let a draw error escape into GTK's main loop
            log.exception("shape canvas draw failed")
        return False

    def _check_size(self) -> None:
        size = (self.painter.scene.width, self.painter.scene.height)
        if size != self._monitor_size and not self._size_warned:
            self._size_warned = True
            log.warning(
                "shape canvas is %dx%d but the monitor is %dx%d: panels may be misaligned",
                *size,
                *self._monitor_size,
            )
```

- [ ] **Step 4: Run the tests**

Run: `scripts/py -m pytest -q tests/test_canvas_window.py tests/test_gtk_imports.py`
Expected: 9 passed (no window is created; `Gdk.cairo_get_clip_rectangle` works on an image-surface context without a display).

- [ ] **Step 5: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell/canvas/canvas.py tests/test_canvas_window.py tests/test_gtk_imports.py
git commit -m "feat(canvas): ShapeCanvas layer-shell window over the painter" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 7: One canvas per monitor, invisible zone strips, no corner windows (Gate 1)

The canvas now draws the frame and the four screen corners; the strips stop drawing and move to the `bottom` layer. Panels still draw their own bodies in this task (same colour on top of the canvas, so the look is unchanged); Task 8 moves them onto the canvas. Border and shadow config exists since Task 2 but must not be enabled before Task 8 (the panel bodies are not in the canvas yet).

**Files:**
- Modify: `shell/frame.py` (whole file: `ScreenCorner` and `CORNERS` removed, strips invisible on the `bottom` layer)
- Modify: `shell/monitors.py:5-31` (imports, raise switch), `shell/monitors.py:80-118` (`MonitorShell.__init__`, `_raise_panels` docstring), `shell/monitors.py:147-151` (`_add_panel`), `shell/monitors.py:175-179` (`apply` restyle)
- Modify: `shell/theme.py` (drop the `#frame-strip` rule)
- Test: `tests/test_frame.py` (new), `tests/test_monitor_shell.py`, `tests/test_theme.py`

**Interfaces:**
- Consumes: `ShapeCanvas(monitor, theme, scope)` with `set_theme(theme)` (Task 6).
- Produces:
  - `shell.frame.EDGES`, `shell.frame.STRIP_LAYER = "bottom"`, `shell.frame.strip_window(edge: str) -> dict` (`layer`, `anchor`, `exclusivity="auto"`, `keyboard_mode="none"`, `pass_through=True`), `FrameEdge(edge, monitor, theme, scope)` (same signature as before). `ScreenCorner` and `CORNERS` no longer exist.
  - `shell.monitors.raise_delays(env=os.environ) -> tuple[int, ...]`: `(RAISE_DELAY_MS, RAISE_FALLBACK_MS)` normally, `()` when `EDGE_SHELL_RAISE_MS=0` (temporary gate switch, removed in Task 12).
  - `MonitorShell.canvas: ShapeCanvas` (created and tracked first, before the strips); `MonitorShell.corners` no longer exists.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_frame.py`:

```python
"""Layer-shell setup of the invisible zone strips (no window is created)."""

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

from shell.frame import EDGES, STRIP_LAYER, strip_window  # noqa: E402


@pytest.mark.parametrize("edge", EDGES)
def test_strips_reserve_their_size_take_no_input_and_sit_below_the_canvas(edge):
    w = strip_window(edge)
    assert w["exclusivity"] == "auto"  # "normal" would reserve only 1 px
    assert w["pass_through"] is True
    assert w["layer"] == STRIP_LAYER == "bottom"
    assert edge in w["anchor"] and len(w["anchor"].split()) == 3
```

In `tests/test_monitor_shell.py`:
1. In `FakeWindow.__init__` add `self.themes = []`, and add the methods

```python
    def set_theme(self, theme):
        self.themes.append(theme)

    def apply_theme(self, theme):
        self.themes.append(theme)
```

2. In `bare_shell` replace `shell.corners = []` by `shell.canvas = FakeWindow()`.
3. In `test_init_schedules_primary_and_fallback_raise` add `monkeypatch.delenv("EDGE_SHELL_RAISE_MS", raising=False)` as the first line, and in it and in `test_init_without_panels_schedules_no_raise` replace `monkeypatch.setattr(mon_mod, "ScreenCorner", FakeWindow)` by `monkeypatch.setattr(mon_mod, "ShapeCanvas", FakeWindow)`.
4. Insert before the `# ---- EdgePanel.raise_to_top` section:

```python
# ---- shape canvas -------------------------------------------------------------------


class Built(FakeWindow):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.kind = kwargs.get("kind")


def build(monkeypatch, make_config, monitors):
    monkeypatch.setattr(mon_mod, "ShapeCanvas", lambda *a, **k: Built(kind="canvas"))
    monkeypatch.setattr(mon_mod, "FrameEdge", lambda *a, **k: Built(kind="strip"))
    monkeypatch.setattr(mon_mod, "widget_class", lambda _w: lambda *a, **k: Built(kind="panel"))
    monkeypatch.setattr(mon_mod.MonitorShell, "_check_monitor", lambda self, w: None)
    monkeypatch.setattr(mon_mod.GLib, "timeout_add", lambda *a: 1)
    cfg = make_config(monitors=monitors)
    tracked = []
    shell = mon_mod.MonitorShell("HDMI-A-1", object(), cfg, tracked.append)
    return shell, cfg, tracked


def test_canvas_is_created_first_then_strips_then_panels(monkeypatch, make_config, fake_registry):
    _, _, tracked = build(
        monkeypatch, make_config, {"HDMI-A-1": {"shell": "edge", "panels": [{"widget": "dock"}]}}
    )
    assert [w.kind for w in tracked] == ["canvas"] + ["strip"] * 4 + ["panel"]


def test_restyle_redraws_the_canvas_with_the_monitor_theme(monkeypatch, make_config):
    from shell.config.diff import Change

    shell, _, _ = build(monkeypatch, make_config, {"HDMI-A-1": {"shell": "edge"}})
    new = make_config(
        theme={"shadow": {"enabled": True}},
        monitors={"HDMI-A-1": {"shell": "edge", "theme": {"shadow": {"elevation": 90}}}},
    )
    shell.apply(new, [Change("restyle", "HDMI-A-1")])
    (theme,) = shell.canvas.themes
    assert theme.shadow.enabled and theme.shadow.elevation == 90


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, (500, 2000)),
        ({"EDGE_SHELL_RAISE_MS": "0"}, ()),
        ({"EDGE_SHELL_RAISE_MS": "x"}, (500, 2000)),
    ],
)
def test_raise_delays_switch(env, expected):
    assert mon_mod.raise_delays(env) == expected
```

In `tests/test_theme.py` replace the body of `test_css_is_scoped_and_uses_theme_colors` up to the `for line` loop:

```python
    css = to_css(make_config(theme={"accent": "#112233"}).theme, "mon-x")
    assert ".mon-x .active { color: #112233; }" in css
    assert "frame-strip" not in css  # the strips are invisible; the canvas draws the frame
    assert "window.mon-x" in css
```

and in `test_two_monitors_do_not_share_rules` replace `{"frame": "#111111"}` by `{"accent": "#111111"}` (the frame colour is no longer in the CSS).

Run: `scripts/py -m pytest -q tests/test_frame.py tests/test_monitor_shell.py tests/test_theme.py`
Expected: FAIL (`ImportError: cannot import name 'STRIP_LAYER'`, `AttributeError: ... has no attribute 'ShapeCanvas'`, `frame-strip` still in the CSS).

- [ ] **Step 2: Replace `shell/frame.py`**

```python
"""Zone-reserving frame strips (GTK / Fabric windows). The frame itself is drawn by the shape
canvas (shell/canvas/canvas.py); these strips are invisible and take no input."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from fabric.widgets.box import Box
from fabric.widgets.wayland import WaylandWindow

from shell.config.models import Theme
from shell.gdk_util import monitor_index

EDGES = ("top", "bottom", "left", "right")

# Below the canvas and the panels (both on "top"): an invisible strip can then never cover a
# panel, whatever order KWin stacks same-layer surfaces in. Exclusive zones count on every
# layer (verified at Gate 1; the fallback, plan Task 11 A, moves them back to "top").
STRIP_LAYER = "bottom"

_STRIP_ANCHOR = {
    "top": "top left right",
    "bottom": "bottom left right",
    "left": "left top bottom",
    "right": "right top bottom",
}


def strip_window(edge: str) -> dict:
    """Layer-shell setup of one strip: reserves its size ("auto"; NOT "normal", which reserves
    1 px) and takes no input (pass_through: Fabric re-applies it after every allocate)."""
    return {
        "layer": STRIP_LAYER,
        "anchor": _STRIP_ANCHOR[edge],
        "exclusivity": "auto",
        "keyboard_mode": "none",
        "pass_through": True,
    }


class FrameEdge(WaylandWindow):
    """One side of the frame: reserves T px so maximized windows stop at the frame."""

    def __init__(self, edge: str, monitor, theme: Theme, scope: str):
        horizontal = edge in ("top", "bottom")
        t = theme.thickness
        # Fabric's `monitor` property is an int; a Gdk.Monitor object is silently ignored.
        super().__init__(
            **strip_window(edge),
            monitor=monitor_index(monitor),
            title=f"edge-shell-frame-{edge}",
            style_classes=[scope],
            child=Box(name="frame-strip", size=(-1, t) if horizontal else (t, -1)),
            all_visible=True,
        )
```

- [ ] **Step 3: Edit `shell/monitors.py`**

1. Imports: change `import logging\nimport subprocess` to `import logging\nimport os\nimport subprocess`; add `from shell.canvas.canvas import ShapeCanvas` as the first `shell.` import; replace `from shell.frame import CORNERS, EDGES, FrameEdge, ScreenCorner` by `from shell.frame import EDGES, FrameEdge`.
2. Replace the comment above `RAISE_DELAY_MS` and add the switch after `RAISE_FALLBACK_MS = 2000`:

```python
# Timing workaround, not an event-driven fix (core build): KWin restacks same-layer surfaces
# when it first configures them, which put the old frame strips above the panels. The strips
# now live on the bottom layer, but the canvas shares the panels' layer, so the re-map stays
# until Gates 1-2 show it is not needed. Empirical: 50 ms was too early, 500 ms reliable; the
# second raise is a safety net for a slow compositor; both are no-ops after close().
RAISE_DELAY_MS = 500
RAISE_FALLBACK_MS = 2000


def raise_delays(env=os.environ) -> tuple[int, ...]:
    """Re-raise delays. EDGE_SHELL_RAISE_MS=0 turns the re-raise off, so Gates 1-2 can test
    whether the canvas design still needs it (temporary switch, removed with the raise)."""
    if env.get("EDGE_SHELL_RAISE_MS", "").strip() == "0":
        return ()
    return (RAISE_DELAY_MS, RAISE_FALLBACK_MS)
```

3. In `class MonitorShell`: docstring becomes `"""Every Edge Shell window for one monitor: the shape canvas, 4 zone strips, N panels."""`; in `__init__` replace everything from `self.windows: list = []` to the end of `__init__` by:

```python
        self.windows: list = []
        self.panels: list[EdgePanel] = []
        theme = config.theme_for(name)
        # The canvas first: it draws the frame and corners and must stay below every panel.
        self.canvas = ShapeCanvas(monitor, theme, self._scope)
        self._track(self.canvas)
        for edge in EDGES:
            self._track(FrameEdge(edge, monitor, theme, self._scope))
        for index, geo in enumerate(panels_for(config, name)):
            self.panels.append(self._make_panel(index, geo, theme))
        if self.panels:
            for delay in raise_delays():
                GLib.timeout_add(delay, self._raise_panels)
```

   `_raise_panels` docstring: `"""Re-map the live panels so they stack above the canvas (see RAISE_DELAY_MS)."""`.
4. In `_add_panel` replace `GLib.timeout_add(RAISE_DELAY_MS, self._raise_one, panel)` by

```python
        for delay in raise_delays()[:1]:
            GLib.timeout_add(delay, self._raise_one, panel)
```

5. In `apply`, the `restyle` branch becomes

```python
            if change.kind == "restyle":
                self.canvas.set_theme(theme)
                for panel in self.panels:
                    panel.apply_theme(theme)
```

- [ ] **Step 4: Drop the strip colour from the CSS**

In `shell/theme.py` delete the line `{s} #frame-strip {{ background-color: {c["frame"]}; }}` from `to_css`.

- [ ] **Step 5: Run the tests**

Run: `scripts/py -m pytest -q tests/test_frame.py tests/test_monitor_shell.py tests/test_theme.py tests/test_gtk_imports.py`
Expected: all pass. `grep -rn "ScreenCorner\|CORNERS" shell tests` prints nothing.

- [ ] **Step 6: VERIFY and commit (before the gate)**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell/frame.py shell/monitors.py shell/theme.py tests/test_frame.py tests/test_monitor_shell.py tests/test_theme.py
git commit -m "feat(canvas): one shape canvas per monitor; invisible zone strips; corners drawn by the canvas" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7: GATE 1 (Phil, HDMI-A-1): canvas + invisible strips, frame only**

This draws on Phil's screen. If the auto-mode classifier refuses the run, stop and hand the commands to Phil. Start each run from a terminal; Ctrl+C quits.

Run A (frame only, re-raise OFF):
```bash
env EDGE_SHELL_RAISE_MS=0 scripts/py main.py --config examples/hdmi-test.toml -v
```
1. A 10 px dark frame on all four edges of **HDMI-A-1** only; the inner desktop corners are rounded; it looks identical to the core build (a `spectacle` screenshot helps). DP-1 and its Plasma panel are untouched.
2. **Maximize a window** (e.g. Dolphin) on HDMI-A-1: it stops at the frame on all four sides. (This proves the zone strips still reserve space from the `bottom` layer.)
3. **Click-through:** clicks on the frame band itself and at the rounded corners reach what is underneath (new: the frame band no longer swallows clicks).
4. The `-v` log shows no `is not on the requested monitor`, no `panels may be misaligned`, no `scale … not supported`.
5. Ctrl+C removes everything.

Run B (dock, still drawn by its own window in this task, re-raise OFF):
```bash
env EDGE_SHELL_RAISE_MS=0 scripts/py main.py --config examples/dock-test.toml -v
```
6. The dock is fused with the frame: no seam or hairline at its joins.
7. Click the handle to collapse the dock, wait 3 s: the three handle dots are visible in the frame band (the panel window is above the canvas). Check again after 10 s.
8. Hover peek, click toggle and drag still work.

**On failure:**
- Item 2 fails (windows ignore the frame) -> Task 11 Fallback A, then repeat Gate 1.
- Item 7 fails -> repeat Run B without `env EDGE_SHELL_RAISE_MS=0`. If the dots are visible then, note "raise still needed" (Task 11 Fallback B applies; continue). If not -> Task 11 Fallback C (stop).
- Items 1 or 4 fail -> stop; collect the `-v` log and a screenshot; fix before Task 8.

Write down each item's result; Task 16 records them in the findings note.

---

### Task 8: Panels draw through the canvas (Gate 2)

`EdgePanel` stops drawing; it becomes the transparent content/handle/input window and reports its depth through `on_depth`. `MonitorShell` resolves the layout (Task 5), registers each panel's shape on the canvas, wires the depth callback, and reconciles panels against the resolved layout on reload. Layout warnings are logged here; the app's notification follows in Task 9 (split out to keep this task reviewable; the suite is green in between because the app does not read `layout_warnings` yet).

Positions are now resolved once, to an explicit `pos`, when a panel is built: a centred panel therefore no longer re-centres by itself if the monitor's resolution changes while the shell runs (the compositor used to centre the old single-edge-anchored surface). This joins the existing limitation for explicit `pos` (README "Known limitations"; a config save or restart re-resolves).

**Files:**
- Modify: `shell/edge_panel.py` (constructor `on_depth`; delete `_canvas`, `_on_draw`; `_apply_depth`; `apply_theme`; imports)
- Modify: `shell/monitors.py` (imports; whole `MonitorShell` class)
- Test: `tests/test_monitor_shell.py` (rewritten), `tests/test_edge_panel_drag.py`

**Interfaces:**
- Consumes: `resolve_layout`, `Layout` (Task 5); `PanelShape` (Task 4); `ShapeCanvas.add_panel/remove_panel/set_depth/set_theme` (Task 6); `raise_delays`, `RAISE_DELAY_MS`, `RAISE_FALLBACK_MS` (Task 7); `panels_for`, `widget_class` (registry).
- Produces:
  - `EdgePanel(spec, theme, monitor, index, scope, on_depth: Callable[[float], None] | None = None)`. `spec.pos` must be an int (resolved). `_apply_depth(d)` sets `_d`, places the handle, updates the input region, then calls `on_depth(d)`. No `_on_draw`, no `_canvas`. Widgets (`widgets/*.py`) do not override `__init__`, so they need no change.
  - `MonitorShell.panels: list[EdgePanel | None]` (config order; None = hidden by the layout rules), `MonitorShell.layout_warnings: list[str]`, `MonitorShell.live_panels() -> list[EdgePanel]`, `panel.scene_key: int` (set on every panel MonitorShell creates). `apply(config, changes)` restyles on a `restyle` change, then always reconciles panels with the resolved layout (rebuild when resolved geometry other than `state` changed, `set_state` when only `state` changed, add/remove to match). Warnings are logged with `log.warning`.

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_monitor_shell.py` completely with:

```python
"""Display-free tests for MonitorShell bookkeeping (windows are fakes)."""

from types import SimpleNamespace

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import shell.monitors as mon_mod  # noqa: E402
from shell.config.diff import Change  # noqa: E402


class FakeWindow:
    def __init__(self, *args, raises=False, **kwargs):
        self.args, self.kwargs = args, kwargs
        self.destroyed = False
        self.raises = raises
        self.raised = 0
        self.title = "w"
        self.themes = []
        self.states = []

    def destroy(self):
        self.destroyed = True
        if self.raises:
            raise RuntimeError("already gone")

    def raise_to_top(self):
        self.raised += 1

    def apply_theme(self, theme):
        self.themes.append(theme)

    def set_state(self, state):
        self.states.append(state)

    def get_title(self):
        return self.title


class FakeCanvas(FakeWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.shapes = {}
        self.depths = []

    def set_theme(self, theme):
        self.themes.append(theme)

    def add_panel(self, key, shape):
        self.shapes[key] = shape

    def remove_panel(self, key):
        self.shapes.pop(key, None)

    def set_depth(self, key, d):
        self.depths.append((key, d))


MONITOR = SimpleNamespace(get_geometry=lambda: SimpleNamespace(x=0, y=0, width=1920, height=1080))


def bare_shell(windows, panels=(), unregister=None):
    shell = mon_mod.MonitorShell.__new__(mon_mod.MonitorShell)
    shell.name = "HDMI-A-1"
    shell.windows = list(windows)
    shell.panels = list(panels)
    shell._resolved = [None] * len(shell.panels)
    shell.canvas = FakeCanvas()
    shell._closed = False
    shell._unregister = unregister or (lambda _w: None)
    return shell


def test_close_unregisters_then_destroys_every_window():
    seen = []
    wins = [FakeWindow(), FakeWindow()]

    def unregister(w):
        seen.append((w, w.destroyed))

    shell = bare_shell(wins, unregister=unregister)
    shell.close()
    assert [w for w, _ in seen] == wins
    assert all(not destroyed for _, destroyed in seen)  # unregistered before destroy
    assert all(w.destroyed for w in wins)
    assert shell.windows == [] and shell.panels == []


def test_destroy_panel_unregisters_it():
    panel = FakeWindow()
    gone = []
    shell = bare_shell([panel], [panel], unregister=gone.append)
    shell._destroy(panel)
    assert gone == [panel] and panel.destroyed
    assert shell.windows == []


def test_unregister_failure_does_not_block_destroy():
    def boom(_w):
        raise ValueError("not in list")

    win = FakeWindow()
    shell = bare_shell([win], unregister=boom)
    shell.close()
    assert win.destroyed


def test_destroy_error_is_contained():
    shell = bare_shell([FakeWindow(raises=True), FakeWindow()])
    shell.close()  # must not raise
    assert shell.windows == []


def test_raise_panels_raises_only_live_panels():
    a, b = FakeWindow(), FakeWindow()
    shell = bare_shell([a, b], [a, None, b])  # None = a panel hidden by the layout rules
    assert shell._raise_panels() is False  # one-shot GLib source
    assert (a.raised, b.raised) == (1, 1)


def test_raise_one_skips_a_panel_that_was_removed():
    a, b = FakeWindow(), FakeWindow()
    shell = bare_shell([a, b], [a])  # b was rebuilt or removed during the delay
    assert shell._raise_one(b) is False and b.raised == 0
    assert shell._raise_one(a) is False and a.raised == 1


# ---- building a monitor (fakes for every window) ------------------------------------


@pytest.fixture
def build(monkeypatch, make_config, fake_registry):
    """build(monitors, theme=None) -> (shell, tracked windows, timers)."""
    monkeypatch.delenv("EDGE_SHELL_RAISE_MS", raising=False)
    monkeypatch.setattr(mon_mod, "ShapeCanvas", FakeCanvas)
    monkeypatch.setattr(mon_mod, "FrameEdge", FakeWindow)
    monkeypatch.setattr(mon_mod, "widget_class", lambda _w: FakeWindow)
    monkeypatch.setattr(mon_mod.MonitorShell, "_check_monitor", lambda self, w: None)
    timers = []
    monkeypatch.setattr(
        mon_mod.GLib, "timeout_add", lambda ms, fn, *a: timers.append((ms, fn, a)) or len(timers)
    )

    def _build(monitors, theme=None):
        tracked = []
        cfg = make_config(monitors=monitors, theme=theme)
        shell = mon_mod.MonitorShell("HDMI-A-1", MONITOR, cfg, tracked.append)
        return shell, tracked, timers

    return _build


def edge(*panels, theme=None):
    return {"HDMI-A-1": {"shell": "edge", "panels": list(panels), "theme": theme or {}}}


def test_canvas_first_then_strips_then_panels(build):
    shell, tracked, _ = build(edge({"widget": "dock"}))
    assert tracked[0] is shell.canvas
    assert [type(w) for w in tracked[1:5]] == [FakeWindow] * 4
    assert tracked[5] is shell.panels[0]


def test_panels_get_a_resolved_pos_a_scene_shape_and_a_depth_callback(build):
    shell, _, _ = build(edge({"widget": "dock"}, {"widget": "bar"}))
    dock, bar = shell.panels
    assert dock.args[0].pos == 680 and bar.args[0].pos == 600  # centred dock resolved to 680
    assert {s.edge for s in shell.canvas.shapes.values()} == {"bottom", "right"}
    dock.kwargs["on_depth"](12.5)
    assert shell.canvas.depths == [(dock.scene_key, 12.5)]


def test_panel_that_breaks_the_layout_rules_is_hidden_and_reported(build):
    shell, _, _ = build(edge({"widget": "dock"}, {"widget": "dock"}))
    assert shell.panels[1] is None and len(shell.canvas.shapes) == 1
    assert "monitors.HDMI-A-1.panels.1 (dock): overlaps" in shell.layout_warnings[0]


def test_init_schedules_primary_and_fallback_raise(build):
    shell, _, timers = build(edge({"widget": "dock"}))
    assert [ms for ms, _, _ in timers] == [mon_mod.RAISE_DELAY_MS, mon_mod.RAISE_FALLBACK_MS]
    panel = shell.panels[0]
    for _, fn, a in timers:
        assert fn(*a) is False
    assert panel.raised == 2
    shell.close()
    for _, fn, a in timers:
        fn(*a)
    assert panel.raised == 2  # no work after close


def test_init_without_panels_schedules_no_raise(build):
    _, _, timers = build(edge())
    assert timers == []


def test_raise_switch_off_schedules_nothing(build, monkeypatch):
    monkeypatch.setenv("EDGE_SHELL_RAISE_MS", "0")
    _, _, timers = build(edge({"widget": "dock"}))
    assert timers == []


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, (500, 2000)),
        ({"EDGE_SHELL_RAISE_MS": "0"}, ()),
        ({"EDGE_SHELL_RAISE_MS": "x"}, (500, 2000)),
    ],
)
def test_raise_delays_switch(env, expected):
    assert mon_mod.raise_delays(env) == expected


# ---- reload ------------------------------------------------------------------------


def test_restyle_redraws_the_canvas_with_the_monitor_theme(build, make_config):
    shell, _, _ = build(edge({"widget": "dock"}))
    new = make_config(
        theme={"shadow": {"enabled": True}},
        monitors=edge({"widget": "dock"}, theme={"shadow": {"elevation": 90}}),
    )
    shell.apply(new, [Change("restyle", "HDMI-A-1")])
    (theme,) = shell.canvas.themes
    assert theme.shadow.enabled and theme.shadow.elevation == 90
    assert shell.panels[0].themes == [theme]


def test_state_change_retargets_without_rebuilding(build, make_config):
    shell, _, _ = build(edge({"widget": "dock"}))
    dock = shell.panels[0]
    shell.apply(
        make_config(monitors=edge({"widget": "dock", "state": "collapsed"})),
        [Change("panel-state", "HDMI-A-1", 0)],
    )
    assert shell.panels[0] is dock and dock.states == ["collapsed"] and not dock.destroyed


def test_geometry_change_rebuilds_and_moves_the_scene_shape(build, make_config):
    shell, _, timers = build(edge({"widget": "dock"}))
    old = shell.panels[0]
    shell.apply(
        make_config(monitors=edge({"widget": "dock", "length": 300})),
        [Change("panel-rebuild", "HDMI-A-1", 0)],
    )
    new = shell.panels[0]
    assert old.destroyed and new is not old
    assert list(shell.canvas.shapes) == [new.scene_key]
    assert shell.canvas.shapes[new.scene_key].length == 300
    assert timers[-1][0] == mon_mod.RAISE_DELAY_MS  # the rebuilt panel is re-raised once


def test_add_and_remove_keep_canvas_and_panels_in_step(build, make_config):
    shell, _, _ = build(edge({"widget": "dock"}))
    shell.apply(make_config(monitors=edge({"widget": "dock"}, {"widget": "clock"})), [])
    assert [p.args[0].widget for p in shell.panels] == ["dock", "clock"]
    assert len(shell.canvas.shapes) == 2
    clock = shell.panels[1]
    shell.apply(make_config(monitors=edge({"widget": "dock"})), [])
    assert clock.destroyed and len(shell.panels) == 1 and len(shell.canvas.shapes) == 1


def test_a_neighbour_change_rebuilds_the_panel_it_unhides(build, make_config):
    shell, _, _ = build(edge({"widget": "dock"}, {"widget": "dock"}))
    assert shell.panels[1] is None
    shell.apply(
        make_config(
            monitors=edge({"widget": "dock", "pos": 100, "length": 300}, {"widget": "dock"})
        ),
        [Change("panel-rebuild", "HDMI-A-1", 0)],
    )
    assert shell.panels[1] is not None and shell.layout_warnings == []
    assert len(shell.canvas.shapes) == 2


def test_failed_panel_construction_leaves_no_scene_shape(build, make_config, monkeypatch):
    shell, _, _ = build(edge())

    def explode(*a, **k):
        raise RuntimeError("widget broke")

    monkeypatch.setattr(mon_mod, "widget_class", lambda _w: explode)
    with pytest.raises(RuntimeError):
        shell.apply(make_config(monitors=edge({"widget": "dock"})), [])
    assert shell.canvas.shapes == {}


# ---- EdgePanel.raise_to_top (plain function called on a stand-in) --------------------


def _panel_stub(dragging=False, hovered=True):
    calls = []
    return SimpleNamespace(
        _dragging=dragging,
        _hovered=hovered,
        _d=3.0,
        _last_rect=(1, 2, 3, 4),
        hide=lambda: calls.append("hide"),
        show_all=lambda: calls.append("show_all"),
        _update_input_region=lambda d: calls.append(("region", d)),
        calls=calls,
    )


def test_raise_to_top_remaps_resets_hover_and_reapplies_region():
    from shell.edge_panel import EdgePanel

    p = _panel_stub()
    EdgePanel.raise_to_top(p)
    assert p.calls == ["hide", "show_all", ("region", 3.0)]
    assert p._hovered is False and p._last_rect is None


def test_raise_to_top_never_interrupts_a_drag():
    from shell.edge_panel import EdgePanel

    p = _panel_stub(dragging=True)
    EdgePanel.raise_to_top(p)
    assert p.calls == []
```

Append to `tests/test_edge_panel_drag.py`:

```python
def test_apply_depth_moves_handle_and_region_then_reports_to_the_canvas():
    calls = []
    s = SimpleNamespace(
        _place_handle=lambda d: calls.append(("handle", d)),
        _update_input_region=lambda d: calls.append(("region", d)),
        _on_depth=lambda d: calls.append(("canvas", d)),
    )
    ep.EdgePanel._apply_depth(s, 7.5)
    assert s._d == 7.5
    assert calls == [("handle", 7.5), ("region", 7.5), ("canvas", 7.5)]
    s._on_depth = None
    ep.EdgePanel._apply_depth(s, 1.0)  # no canvas callback: nothing breaks
    assert s._d == 1.0


def test_panels_no_longer_draw_their_own_body():
    assert not hasattr(ep.EdgePanel, "_on_draw")


def test_on_depth_is_stored_before_the_tweens_exist():
    # __init__ creates the depth Tween and calls jump_to, which runs _apply_depth and needs
    # self._on_depth. Building a real EdgePanel would map a window on Phil's screen, so this
    # display-free test checks the statement order in the source instead.
    import inspect

    src = inspect.getsource(ep.EdgePanel.__init__)
    assert src.index("self._on_depth = on_depth") < src.index("Tween(")
```

Run: `scripts/py -m pytest -q tests/test_monitor_shell.py tests/test_edge_panel_drag.py`
Expected: FAIL (no `on_depth` keyword, no `layout_warnings`, `_on_draw` still exists).

- [ ] **Step 2: Edit `shell/edge_panel.py`**

1. Module docstring:

```python
"""EdgePanel: the content, handle and input window of one panel. Its body is drawn by the
monitor's shape canvas; the panel reports its animated depth through `on_depth`."""
```

2. Add `from collections.abc import Callable` after `import math`; delete `from shell.draw import draw_panel` and `from shell.theme import hex_to_rgba` (keep `import cairo`: the input region uses it).
3. Replace the constructor signature line with:

```python
    def __init__(
        self,
        spec: PanelGeometry,
        theme: Theme,
        monitor,
        index: int,
        scope: str,
        on_depth: Callable[[float], None] | None = None,
    ):
        """`spec.pos` must be resolved (shell.panel_layout); `on_depth(d)` is called on every
        animation frame with the current depth (MonitorShell forwards it to the canvas)."""
```

4. After `self._theme = theme` add `self._on_depth = on_depth` (it must be set before the Tweens are created: `jump_to` already calls `_apply_depth`).
5. Delete the two lines creating `self._canvas` (`self._canvas = Gtk.DrawingArea()` and its `connect("draw", …)`), and replace `self.add(Overlay(child=self._canvas, overlays=[self._content, self._handle]))` by

```python
        # Transparent base: the body is painted by the shape canvas underneath this window.
        self.add(Overlay(child=Box(name="panel-base"), overlays=[self._content, self._handle]))
```

6. `apply_theme` becomes

```python
    def apply_theme(self, theme: Theme) -> None:
        """Colors only (CSS and the canvas repaint them); geometry changes rebuild the panel."""
        self._theme = theme
```

7. Replace `_apply_depth` and delete `_on_draw` entirely:

```python
    def _apply_depth(self, d: float) -> None:
        self._d = d
        self._place_handle(d)
        self._update_input_region(d)
        if self._on_depth is not None:
            self._on_depth(d)  # the canvas redraws the body's damaged box
```

`do_size_allocate` (input region after allocate), `raise_to_top`, the handle, drag and content code stay as they are. `anchor_and_margin` now always receives an int `pos`, so every panel is anchored by margin (centred panels included) and its body lands exactly on the canvas shape.

- [ ] **Step 3: Edit `shell/monitors.py`**

Imports: add `import itertools` before `import logging`, `from dataclasses import replace` after `import subprocess`, `from shell.canvas.scene import PanelShape` after the `ShapeCanvas` import, and `from shell.panel_layout import Layout, resolve_layout` after the `shell.outputs` import. Then replace the whole `class MonitorShell` with:

```python
class MonitorShell:
    """Every Edge Shell window for one monitor: the shape canvas, 4 zone strips, N panels."""

    def __init__(
        self,
        name: str,
        monitor: Gdk.Monitor,
        config: Config,
        register_window,
        unregister_window=None,
    ):
        self.name = name
        self.monitor = monitor
        self._register = register_window
        self._unregister = unregister_window or (lambda _window: None)
        self._scope = scope_class(name)
        self._closed = False
        self.windows: list = []
        # Config order; None = not shown (rejected by shell.panel_layout, see layout_warnings).
        self.panels: list[EdgePanel | None] = []
        self._resolved: list[PanelGeometry | None] = []
        self.layout_warnings: list[str] = []
        self._keys = itertools.count()  # scene keys for the canvas
        theme = config.theme_for(name)
        # The canvas first: it draws the frame and corners and must stay below every panel.
        self.canvas = ShapeCanvas(monitor, theme, self._scope)
        self._track(self.canvas)
        for edge in EDGES:
            self._track(FrameEdge(edge, monitor, theme, self._scope))
        self._sync_panels(config, theme, startup=True)
        if self.live_panels():
            for delay in raise_delays():
                GLib.timeout_add(delay, self._raise_panels)

    def live_panels(self) -> list[EdgePanel]:
        return [p for p in self.panels if p is not None]

    # ---- panels ---------------------------------------------------------------------------
    def _layout(self, config: Config, theme) -> Layout:
        g = self.monitor.get_geometry()
        return resolve_layout(
            panels_for(config, self.name),
            g.width,
            g.height,
            theme.thickness,
            theme.radius,
            where=f"monitors.{self.name}",
        )

    def _sync_panels(self, config: Config, theme, startup: bool) -> None:
        """Make the panels match the resolved layout: rebuild a panel whose resolved geometry
        changed (also when a neighbour's change moved or hid it), retarget a state change."""
        layout = self._layout(config, theme)
        self.layout_warnings = list(layout.warnings)
        for message in layout.warnings:
            log.warning("%s", message)
        wanted = layout.panels
        while len(self.panels) > len(wanted):  # removed at the end of the list
            if self.panels[-1] is not None:
                self._destroy_panel(len(self.panels) - 1)
            self.panels.pop()
            self._resolved.pop()
        for i, geo in enumerate(wanted):
            if i == len(self.panels):
                self.panels.append(None)
                self._resolved.append(None)
            old, panel = self._resolved[i], self.panels[i]
            if geo is None:
                if panel is not None:
                    self._destroy_panel(i)
            elif panel is None or old is None or replace(old, state=geo.state) != geo:
                if panel is not None:
                    self._destroy_panel(i)
                self.panels[i] = self._new_panel(i, geo, theme, raise_later=not startup)
            elif old.state != geo.state:
                panel.set_state(geo.state)
            self._resolved[i] = geo

    def _new_panel(self, index: int, geo: PanelGeometry, theme, raise_later: bool) -> EdgePanel:
        key = next(self._keys)
        self.canvas.add_panel(key, PanelShape(geo.edge, geo.pos, geo.length, geo.depth))
        try:
            panel = widget_class(geo.widget)(
                geo,
                theme,
                self.monitor,
                index,
                self._scope,
                on_depth=lambda d, k=key: self.canvas.set_depth(k, d),
            )
        except Exception:
            self.canvas.remove_panel(key)
            raise
        panel.scene_key = key
        self._track(panel)
        if raise_later:  # created after startup: re-raise it like the first ones
            for delay in raise_delays()[:1]:
                GLib.timeout_add(delay, self._raise_one, panel)
        return panel

    def _destroy_panel(self, index: int) -> None:
        panel = self.panels[index]
        self.panels[index] = None
        self.canvas.remove_panel(panel.scene_key)
        self._destroy(panel)

    def _raise_panels(self) -> bool:
        """Re-map the live panels so they stack above the canvas (see RAISE_DELAY_MS)."""
        if not self._closed:
            for panel in self.live_panels():
                panel.raise_to_top()
        return False

    def _raise_one(self, panel: EdgePanel) -> bool:
        # The panel may have been rebuilt or removed during the delay: only raise live ones.
        if panel in self.panels:
            panel.raise_to_top()
        return False

    # ---- windows --------------------------------------------------------------------------
    def _track(self, window) -> None:
        self.windows.append(window)
        self._register(window)
        self._check_monitor(window)

    def _check_monitor(self, window) -> None:
        got = GtkLayerShell.get_monitor(window)
        want = _geometry(self.monitor)
        if got is None or _geometry(got) != want:
            log.error(
                "window %s is not on the requested monitor: layer-shell has %s, wanted %s",
                window.get_title(),
                _geometry(got) if got else None,
                want,
            )

    def _release(self, window) -> None:
        """Drop the app's reference (Fabric keeps every added window) and destroy it."""
        try:
            self._unregister(window)
        except Exception:  # e.g. ValueError if the app never held it
            log.debug("could not unregister window on %s", self.name, exc_info=True)
        try:
            window.destroy()
        except Exception:  # the compositor may already have closed it (monitor unplugged)
            log.exception("failed to destroy window on %s", self.name)

    def _destroy(self, window) -> None:
        if window in self.windows:
            self.windows.remove(window)
        self._release(window)

    def apply(self, config: Config, changes: list[Change]) -> None:
        """Apply a reload in place: restyle the canvas and panels, then reconcile the panels
        against the newly resolved layout (the diff's panel kinds only say that it changed)."""
        theme = config.theme_for(self.name)
        if any(change.kind == "restyle" for change in changes):
            self.canvas.set_theme(theme)
            for panel in self.live_panels():
                panel.apply_theme(theme)
        self._sync_panels(config, theme, startup=False)

    def close(self) -> None:
        self._closed = True
        for window in self.windows:
            self._release(window)
        self.windows.clear()
        self.panels.clear()
        self._resolved.clear()
```

(`_make_panel` and `_add_panel` are gone: `_new_panel` replaces both.)

- [ ] **Step 4: Run the tests**

Run: `scripts/py -m pytest -q tests/test_monitor_shell.py tests/test_edge_panel_drag.py tests/test_gtk_imports.py`
Expected: all pass (23 in `test_monitor_shell.py`). Then `grep -n "draw_panel\|hex_to_rgba\|_canvas\b" shell/edge_panel.py` prints nothing.

- [ ] **Step 5: Headless loop check**

Run: `scripts/py -m pytest -q tests/test_canvas_scene.py -k "simulation or damaged"`
Expected: pass (the Tween -> canvas path the panels now use is the one the simulation drives).

- [ ] **Step 6: VERIFY and commit (before the gate)**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell/edge_panel.py shell/monitors.py tests/test_monitor_shell.py tests/test_edge_panel_drag.py
git commit -m "feat(canvas): panels draw through the shape canvas; layout rules applied" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7: GATE 2 (Phil, HDMI-A-1): the dock through the canvas**

```bash
env EDGE_SHELL_RAISE_MS=0 scripts/py main.py --config examples/dock-test.toml -v
```
1. **Fusion:** the extended dock and the frame are one shape: no seam, hairline or colour step at the joins or along the frame under the dock; the joins are smooth concave curves (zoom a `spectacle` screenshot).
2. **Content:** the three launcher buttons are centred in the dock and clickable (Terminal opens Konsole).
3. **Collapse / expand and handle-to-body sync:** click the handle: the body shrinks smoothly into the frame in about 0.3 s and grows back on the next click, and the handle rides the body's inner edge the whole time.
   *Why this needs a number.* The spike measured a canvas-vs-marker depth error of 0.14-1.80 px max (mean about 0-1 px), but its marker moved on a slow 2 s sine (peak about 1.7 px per frame), so one frame of lag could cost at most about 1.7 px. The real panel eases out with `cubic-bezier(.2,.8,.2,1)` over 280 ms: the dock moves 15.4, 14.3, 10.9 and 7.4 px in its first four frames (computed from `shell.anim.EASE_OUT`), so the same one-frame lag can open a gap of up to about 15 px for a frame at the start of a toggle. The spike data neither confirms nor rules this out, because whether the canvas draws in the same frame as the panel's tick varied from run to run (findings section 5).
   *Check.* First by eye at normal speed: any visible detach fails. Then record two collapses and two expands with Spectacle's screen recording of the dock region (60 fps) and step through the video frame by frame (e.g. `mpv`, key `.`). **Accepted:** the gap between the handle and the body's inner edge is at most 2 px, and only in at most one frame per toggle. **Anything larger or longer fails.**
4. **Collapsed handle visible:** after collapsing, the three dots are visible in the frame band; check again after 10 s (late restack).
5. **Click-through above the collapsed dock:** click the desktop about 40 px above the frame where the extended dock would be: the click reaches the desktop (only the 16 px hover zone above the frame belongs to the dock).
6. **Hover peek:** move the pointer onto the frame over the dock: it peeks out (about 14 px) and goes back when the pointer leaves.
7. **Drag:** press the handle and drag up: the depth follows the pointer, body and handle together; release above half depth extends, below half collapses.
8. **Maximized window:** maximize a window: it still stops at the frame; the extended dock floats over it.
9. The `-v` log has no errors.

**On failure:**
- Items 4 or 5 (stacking): repeat without `env EDGE_SHELL_RAISE_MS=0`. Fixed with the raise -> Fallback B (keep the raise). Not fixed -> Fallback C (stop).
- Item 3 (the numeric rule fails) -> Task 11 Fallback D, then repeat this gate. If D does not pass the rule either, Fallback D's decision step applies (Phil chooses).
- Item 1 (seams or wrong join shapes) -> stop: screenshot and compare with `tests/test_canvas_outline.py`; the pure contract says it cannot happen, so suspect a position mismatch between `EdgePanel` (`anchor_and_margin`) and the canvas shape (`PanelShape.pos`).

---

### Task 9: Notify layout adjustments, only when they change

The app tells Phil when the layout rules moved, shrank or hid a panel. It notifies when a monitor's warnings differ from the last ones it reported for that monitor, so an unrelated reload (say, an accent colour change) does not repeat the same notification.

**Files:**
- Modify: `shell/app.py:44-50` (`__init__`), `shell/app.py:63-84` (`sync_monitors`), `shell/app.py:153-167` (`_reload` apply loop), `shell/app.py:172-179` (`_report_error` -> `_notify`, new `_report_layout`)
- Test: `tests/test_app_sync.py`

**Interfaces:**
- Consumes: `MonitorShell.layout_warnings: list[str]` (Task 8).
- Produces: `EdgeShellApp._notify(title: str, message: str) -> None`; `EdgeShellApp._report_layout(name: str, shell) -> None` (notifies "Panels adjusted" with the joined warnings when they differ from the last reported list for `name`; an empty list is recorded silently); attribute `EdgeShellApp._layout_reported: dict[str, list[str]]`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_app_sync.py` add the class attribute `layout_warnings: list = []` to `FakeShell` (after `fail_apply: set = set()`), and append:

```python
def test_layout_warnings_are_notified_when_a_shell_opens(env, monkeypatch):
    app, mapping = env
    notes = []
    monkeypatch.setattr(
        app_mod.EdgeShellApp, "_notify", lambda self, title, msg: notes.append((title, msg))
    )
    monkeypatch.setattr(FakeShell, "layout_warnings", ["monitors.HDMI-A-1.panels.1 (dock): x"])
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    assert notes == [("Panels adjusted", "monitors.HDMI-A-1.panels.1 (dock): x")]


def test_no_notification_without_layout_warnings(env, monkeypatch):
    app, mapping = env
    notes = []
    monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, *a: notes.append(a))
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    assert notes == []


def test_layout_warnings_are_notified_only_when_they_change(renv, monkeypatch):
    app, _, _, _, _ = renv
    notes = []
    monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, title, msg: notes.append(msg))
    shell = app.shells["HDMI-A-1"]
    for warnings in (["w1"], ["w1"], ["w1", "w2"], [], ["w1"]):
        shell.layout_warnings = warnings
        app._report_layout("HDMI-A-1", shell)
    assert notes == ["w1", "w1\nw2", "w1"]  # unchanged: silent; cleared: silent; back: again


def test_unrelated_reload_does_not_repeat_the_layout_notification(renv, monkeypatch):
    app, store, _, _, make_config = renv
    notes = []
    monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, *a: notes.append(a))
    app.shells["HDMI-A-1"].layout_warnings = ["w"]
    app._report_layout("HDMI-A-1", app.shells["HDMI-A-1"])
    store.pending = make_config(
        theme={"accent": "#112233"}, monitors={"HDMI-A-1": mon(panels=[{"widget": "dock"}])}
    )
    app.reload()
    assert len(notes) == 1
```

Run: `scripts/py -m pytest -q tests/test_app_sync.py`
Expected: FAIL (`AttributeError: … has no attribute '_notify'` / `'_report_layout'`).

- [ ] **Step 2: Implement in `shell/app.py`**

1. In `__init__`, after `self._sync_timers: list[int] = []  # pending hot-plug sync timer ids` add
   `        self._layout_reported: dict[str, list[str]] = {}  # last notified warnings per monitor`.
2. In `sync_monitors`, right after the `self.shells[name] = MonitorShell(...)` statement inside the `for name in open_:` loop, add `self._report_layout(name, self.shells[name])`.
3. In `_reload`, inside the `try:` after `self.shells[name].apply(new, items)`, add `self._report_layout(name, self.shells[name])`.
4. Replace `_report_error` by:

```python
    def _report_layout(self, name: str, shell) -> None:
        """Notify panels moved, shrunk or hidden by the layout rules (shell.panel_layout), but
        only when that monitor's warnings changed, not on every unrelated reload."""
        warnings = list(shell.layout_warnings)
        if warnings == self._layout_reported.get(name, []):
            return
        self._layout_reported[name] = warnings
        if warnings:
            self._notify("Panels adjusted", "\n".join(warnings))

    def _notify(self, title: str, message: str) -> None:
        try:
            subprocess.Popen(["notify-send", "-a", "Edge Shell", "--", title, message[:400]])
        except OSError:
            pass  # no notify-send; the log line is enough

    def _report_error(self, message: str) -> None:
        log.error("config not applied (keeping the previous config):\n%s", message)
        self._notify("Config not applied", message)
```

(`test_notify_send_body_cannot_be_parsed_as_option` keeps passing: `--` still precedes the body.)

- [ ] **Step 3: Run the tests**

Run: `scripts/py -m pytest -q tests/test_app_sync.py`
Expected: all pass.

- [ ] **Step 4: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell/app.py tests/test_app_sync.py
git commit -m "feat(app): notify layout adjustments when they change" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 10: GATE 3 (Phil, HDMI-A-1): clock and system bar (top and right edges), corner clamp

No code. Prerequisite: Gate 2 passed (or its fallback applied) and Task 9 committed.

```bash
env EDGE_SHELL_RAISE_MS=0 scripts/py main.py --config examples/panels-test.toml -v
```
(`examples/panels-test.toml` as committed: dock, clock, system bar at their defaults.)

1. The clock sits centred on the **top** edge and shows the time (HH:MM, updates at the minute); the system bar sits on the **right** edge from y = 600 to 900 and shows CPU and RAM (update every 2 s).
2. Both are fused with the frame like the dock: correct concave joins on the top edge and on the vertical right edge (no flipped or missing fillets).
3. Click each handle: collapse/expand animate smoothly; handles ride the inner edges; the collapsed handles are visible in the top and right frame bands.
4. Hover peek works on both; drag works along each panel's own axis (down for the clock, left for the system bar).
5. Toggle all three panels quickly one after another: no stray frame pixels or leftover body ghosts anywhere when they settle.
6. **Corner clamp (live).** Quit, then `cp examples/panels-test.toml /tmp/edge-gate3.toml`, add `pos = 0` to the `system_bar` entry and run `env EDGE_SHELL_RAISE_MS=0 scripts/py main.py --config /tmp/edge-gate3.toml -v`: a "Panels adjusted" notification says `monitors.HDMI-A-1.panels.2 (system_bar): pos 0 would run into a screen corner; moved to 38`; the bar starts 38 px below the top of the screen and the top-right rounded corner of the frame stays intact (no notch, no stray fill). Then add an unrelated change at the top of the file (`[theme]` with `accent = "#d3a68f"`) and save: the accent changes, but no second notification. Remove `pos = 0` and save: the bar returns to y = 600, no notification.
7. The `-v` log has no errors (the clamp warning of item 6 is expected).

**On failure:** as in Gate 2 (stacking -> retry with the raise; handle-to-body rule fails -> Fallback D; wrong shape on one edge only -> stop and compare that edge in `tests/test_canvas_outline.py` and `tests/test_panel_layout.py`; item 6 wrong -> compare with `test_pos_is_clamped_to_the_corner_clearance` and the Task 9 tests).

---

### Task 11: Fallbacks (ONLY when a gate says so)

Skip this task entirely when Gates 1-3 passed with `EDGE_SHELL_RAISE_MS=0` and the Gate 2 handle-to-body rule passed. Each fallback is independent; apply only the ones a gate named, then repeat that gate.

**Fallback A: KWin ignores exclusive zones on the `bottom` layer (Gate 1 item 2).**
The strips go back to the `top` layer. They are invisible and input-less, so their stacking relative to panels no longer matters.

- [ ] In `shell/frame.py` set `STRIP_LAYER = "top"` and replace its comment with `# KWin did not honour exclusive zones on the bottom layer (Gate 1): same layer as the canvas. Harmless: the strips are invisible and take no input, so their stacking order does not matter.`
- [ ] In `tests/test_frame.py` change the assertion to `assert w["layer"] == STRIP_LAYER == "top"`.
- [ ] VERIFY, commit `fix(frame): zone strips on the top layer (KWin ignores bottom-layer zones)` with the trailer, repeat Gate 1.

**Fallback B: content windows still need the re-raise (Gate 1 item 7 / Gate 2 items 4-5 pass only without `EDGE_SHELL_RAISE_MS=0`).**
No code now. In Task 12 skip Steps 1-2 (raise removal) and keep the README limitation line about the re-raise; the `EDGE_SHELL_RAISE_MS` switch stays as a documented debug switch (add one line under README "Develop": `EDGE_SHELL_RAISE_MS=0 disables the startup re-raise (debugging stacking)`). Record the decision in the findings (Task 16).

**Fallback C: content windows are hidden under the canvas even with the re-raise.**
Stop. Do not improvise. Report to Phil with the `-v` log and a screenshot, and ask him to choose between: (1) content windows on the `overlay` layer (spike run 6 showed them visible, but overlay surfaces cover fullscreen windows, a visible regression), (2) the canvas on the `bottom` layer (panels stay above it, but normal windows would then cover the frame and the panel bodies while the handles stay on top), (3) going back to per-window drawing (spec 18 option A) for the panels. Each is a new decision for the spec.

**Fallback D: the handle-to-body rule of Gate 2 item 3 fails.**
The panel's depth Tween runs on the panel window's frame clock and the canvas redraws on its own; at the start of the 280 ms ease the body moves up to about 15 px per frame (see Gate 2 item 3), so a one-frame offset shows. Try driving the depth Tween from the canvas's frame clock. A Tween ticking on ANOTHER widget is not stopped by GTK when the panel is destroyed, so the panel must cancel it and ignore late ticks; `_place_handle` must never run on a destroyed widget. (Prototyped while planning: the suite stays green with these changes.)

- [ ] In `shell/anim.py`, add to `class Tween` (before `animate_to`):

```python
    def cancel(self) -> None:
        """Stop a running animation WITHOUT calling on_value (for a widget being destroyed)."""
        if self._tick_id:
            self._widget.remove_tick_callback(self._tick_id)
            self._tick_id = 0
```

- [ ] In `shell/edge_panel.py`: add the constructor parameter `tick_widget=None,` after `on_depth: Callable[[float], None] | None = None,`; after `self._on_depth = on_depth` add `self._gone = False  # set on destroy: the depth tween may tick on another widget`; replace `self._tween = Tween(self, self._apply_depth, theme.duration_ms)` by

```python
        # Fallback D: the depth tween ticks on `tick_widget` (the canvas) so body and handle
        # move in the canvas's frame; it must be stopped when this panel is destroyed.
        self._tween = Tween(tick_widget or self, self._apply_depth, theme.duration_ms)
        self.connect("destroy", self._stop_depth_ticks)
```

  (the fade tween stays on `self`), and put before `_apply_depth`, plus a guard as its first lines:

```python
    def _stop_depth_ticks(self, *_args) -> None:
        self._gone = True
        self._tween.cancel()

    def _apply_depth(self, d: float) -> None:
        if self._gone:  # never touch a destroyed panel's widgets
            return
        self._d = d
```

  (the rest of `_apply_depth` is unchanged; the name `_gone` avoids the widgets' own `_destroyed` flags and `_on_destroy` handlers in `widgets/clock.py` and `widgets/system_bar.py`).
- [ ] In `MonitorShell._new_panel` pass `tick_widget=self.canvas.area,` after `on_depth=…`.
- [ ] Tests: in `tests/test_monitor_shell.py` add `self.area = object()` to `FakeCanvas.__init__` and, in `test_panels_get_a_resolved_pos_a_scene_shape_and_a_depth_callback`, `assert dock.kwargs["tick_widget"] is shell.canvas.area` before the `on_depth` call. In `tests/test_edge_panel_drag.py` add `_gone=False,` to the `SimpleNamespace` in `test_apply_depth_moves_handle_and_region_then_reports_to_the_canvas` and append:

```python
def test_destroyed_panel_ignores_late_depth_ticks():
    calls = []
    s = SimpleNamespace(
        _gone=False,
        _tween=SimpleNamespace(cancel=lambda: calls.append("cancel")),
        _place_handle=lambda d: calls.append(("handle", d)),
        _update_input_region=lambda d: calls.append(("region", d)),
        _on_depth=lambda d: calls.append(("canvas", d)),
    )
    ep.EdgePanel._stop_depth_ticks(s)
    ep.EdgePanel._apply_depth(s, 5.0)  # a tick that was already queued on the canvas clock
    assert calls == ["cancel"] and s._gone is True
```

  and to `tests/test_anim.py`:

```python
def test_cancel_stops_without_reporting_a_value():
    w, seen = FakeWidget(), []
    t = Tween(w, seen.append, duration_ms=100)
    t.animate_to(10)
    w.frame(16)
    count = len(seen)
    t.cancel()
    assert not t.running and w.callbacks == {}
    w.frame(16)
    assert len(seen) == count  # no value after cancel
    t.cancel()  # idempotent
```

- [ ] VERIFY, commit `fix(canvas): drive panel depth from the canvas frame clock` with the trailer, repeat Gate 2 (including the numeric rule and a rebuild of the dock through a config save while it animates, to exercise the destroy guard).
- [ ] **Decision if D does not pass the rule (or only moves the lag to the handle): Phil chooses.** Undo D first (`git revert --no-commit HEAD`, then `git commit -m "revert: depth tween back on the panel frame clock" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"`), then stop and present these options with the Gate 2 recordings:
  1. **Draw the handle dots on the canvas** (the canvas paints the dots in the same frame as the body, so they can never drift apart; the content window keeps an invisible handle button for click, hover and drag). Overlaps spec 15 (handles drawn with cairo), so it would become a small task of its own, planned before Task 12.
  2. **Accept the measured lag** as is (record the measured gap and frame count in the findings, Task 16).
  3. **Soften the start of the ease** (a less steep first segment than `cubic-bezier(.2,.8,.2,1)` reduces the first-frame jump; changes the spec 4 timing, so it is Phil's call).
  4. Anything else Phil proposes.

---

### Task 12: Remove the replaced code (raise workaround, legacy renderers, spike scaffolding)

Prerequisite: Gates 1-3 passed. **Under Fallback B (raise still needed) skip Steps 1-2** and keep the README re-raise line in Step 5.

**Recorded decision (Decisions recorded, item 5; applies unless Phil objects before this task):** the spike code is deleted: `spikes/canvas/` (including the live probe `spikes/canvas/live.py`, `bench.py`, `render_frames.py`, `render_sheets.py`) and `spikes/tests/`. It stays in git history at `872eff9` and the findings note points there; `main.py --stats` and `python -m shell.canvas.simulate` replace the live probe and the benchmark. `spikes/__init__.py` stays for future probes. The spike tests import `shell.draw`, which this task deletes, so keeping them would leave broken code behind.

**Files:**
- Modify: `shell/monitors.py` (raise code), `shell/edge_panel.py` (`raise_to_top`), `tests/test_monitor_shell.py`, `tests/test_draw.py`, `README.md`
- Delete: `shell/draw.py`, `spikes/canvas/` (all files), `spikes/tests/` (all files)

**Interfaces:**
- Consumes: the Task 8 `MonitorShell`.
- Produces: `MonitorShell._sync_panels(config, theme)` and `MonitorShell._new_panel(index, geo, theme)` lose their `startup` / `raise_later` parameters; `RAISE_DELAY_MS`, `RAISE_FALLBACK_MS`, `raise_delays`, `_raise_panels`, `_raise_one`, `MonitorShell._closed`, `EdgePanel.raise_to_top` and `shell.draw` no longer exist. `tests/legacy_draw.py` is the only home of `draw_panel` / `draw_screen_corner`.

- [ ] **Step 1: Write the failing test and update the monitor tests (skip under Fallback B)**

In `tests/test_monitor_shell.py`:
1. `FakeWindow`: delete `self.raised = 0` and the `raise_to_top` method.
2. `bare_shell`: delete `shell._closed = False`.
3. `build` fixture: docstring `"""build(monitors, theme=None) -> (shell, tracked windows)."""`; delete the `monkeypatch.delenv("EDGE_SHELL_RAISE_MS", raising=False)` line, the `timers = []` line and the `monkeypatch.setattr(mon_mod.GLib, "timeout_add", …)` statement; `_build` returns `shell, tracked`.
4. Every `shell, tracked, _ = build(`, `shell, _, _ = build(` and `shell, _, timers = build(` becomes `shell, tracked = build(` / `shell, _ = build(` / `shell, _ = build(`.
5. Delete the tests `test_raise_panels_raises_only_live_panels`, `test_raise_one_skips_a_panel_that_was_removed`, `test_init_schedules_primary_and_fallback_raise`, `test_init_without_panels_schedules_no_raise`, `test_raise_switch_off_schedules_nothing`, `test_raise_delays_switch`, and in `test_geometry_change_rebuilds_and_moves_the_scene_shape` delete the line `assert timers[-1][0] == mon_mod.RAISE_DELAY_MS  # the rebuilt panel is re-raised once`.
6. Delete the whole `# ---- EdgePanel.raise_to_top …` section (`_panel_stub` and its two tests) and append:

```python
def test_the_raise_workaround_is_gone():
    from shell.edge_panel import EdgePanel

    assert not hasattr(EdgePanel, "raise_to_top")
    assert not hasattr(mon_mod, "raise_delays")
```

Run: `scripts/py -m pytest -q tests/test_monitor_shell.py`
Expected: FAIL only in `test_the_raise_workaround_is_gone`.

- [ ] **Step 2: Remove the raise code (skip under Fallback B)**

`shell/monitors.py`:
1. Delete `import os`; change `from gi.repository import Gdk, GLib, GtkLayerShell` to `from gi.repository import Gdk, GtkLayerShell`.
2. Delete the `# Timing workaround …` comment, `RAISE_DELAY_MS`, `RAISE_FALLBACK_MS` and the whole `raise_delays` function.
3. In `MonitorShell.__init__` delete `self._closed = False` and replace

```python
        self._sync_panels(config, theme, startup=True)
        if self.live_panels():
            for delay in raise_delays():
                GLib.timeout_add(delay, self._raise_panels)
```

by `        self._sync_panels(config, theme)`.
4. `def _sync_panels(self, config: Config, theme, startup: bool) -> None:` becomes `def _sync_panels(self, config: Config, theme) -> None:` and inside it `self._new_panel(i, geo, theme, raise_later=not startup)` becomes `self._new_panel(i, geo, theme)`.
5. `def _new_panel(self, index: int, geo: PanelGeometry, theme, raise_later: bool) -> EdgePanel:` becomes `def _new_panel(self, index: int, geo: PanelGeometry, theme) -> EdgePanel:` and the three lines starting at `if raise_later:` are deleted.
6. Delete the methods `_raise_panels` and `_raise_one`.
7. In `apply`, `self._sync_panels(config, theme, startup=False)` becomes `self._sync_panels(config, theme)`; in `close`, delete `self._closed = True`.

`shell/edge_panel.py`: delete the whole `raise_to_top` method.

Run: `scripts/py -m pytest -q tests/test_monitor_shell.py` -> all pass. `grep -rn "raise_to_top\|RAISE_\|EDGE_SHELL_RAISE_MS\|self\._closed" shell tests` prints only the `hasattr` line of the new test.

- [ ] **Step 3: Delete `shell/draw.py`; the legacy tests use the reference copy**

```bash
git rm shell/draw.py
```

In `tests/test_draw.py` replace `from shell.draw import draw_panel, draw_screen_corner` by `from tests.legacy_draw import draw_panel, draw_screen_corner` and insert as the first lines:

```python
"""Pins the legacy per-window renderers (tests/legacy_draw.py), the reference that
tests/test_canvas_outline.py compares the shape canvas with."""

```

Run: `grep -rn "from shell.draw\|import shell.draw\|from shell import draw" shell widgets tests main.py` -> no output.

- [ ] **Step 4: Delete the spike scaffolding**

```bash
git rm -r spikes/canvas spikes/tests
```

`spikes/__init__.py` stays. (`spikes/out/` is git-ignored local output; leave it to Phil.)

- [ ] **Step 5: README**

Delete the README line `- Panel startup includes a brief re-raise about half a second after launch, needed to stack panels above the frame strips.` together with its continuation line (skip under Fallback B).

- [ ] **Step 6: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell/monitors.py shell/edge_panel.py tests/test_monitor_shell.py tests/test_draw.py README.md
git commit -m "refactor: drop the raise workaround, per-window renderers and spike scaffolding" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
(The `git rm` deletions from Steps 3-4 are already staged.) Expected VERIFY: no failures; `tests/test_monitor_shell.py` goes from 23 to 14 tests (10 raise tests removed, 1 added).

- [ ] **Step 7: Quick re-check (Phil, 30 s)**

```bash
scripts/py main.py --config examples/panels-test.toml -v
```
No env var any more. Three panels as at Gate 3; the collapsed handles are visible after 10 s; Ctrl+C. If a handle is hidden now: `git revert --no-commit HEAD`, then `git commit -m "revert: keep the raise workaround" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"`, and redo this task under Fallback B (Steps 3-6 only).

---

### Task 13: GATE 4 (Phil, HDMI-A-1): border and shadow, live reload, per-monitor override

**Files:**
- Create: `examples/effects-test.toml`

**Interfaces:**
- Consumes: everything above; no code changes.

- [ ] **Step 1: Create the example config**

```toml
# Gate 4: shape canvas border and shadow on HDMI-A-1 only (DP-1 is left alone).
#   cp examples/effects-test.toml /tmp/edge-effects.toml
#   scripts/py main.py --config /tmp/edge-effects.toml -v      (edit the copy while it runs)
[theme.border]
enabled = true

[theme.shadow]
enabled = true
elevation = 50

[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]
widget = "dock"

[[monitors.HDMI-A-1.panels]]
widget = "clock"

[[monitors.HDMI-A-1.panels]]
widget = "system_bar"
```

Check it loads: `scripts/py -c "import widgets; from pathlib import Path; from shell.config.store import ConfigStore; print(ConfigStore(Path('examples/effects-test.toml'), required=True).config.theme_for('HDMI-A-1').shadow)"`
Expected: `enabled=True elevation=50 color='#00000080'`.

- [ ] **Step 2: Commit**

```bash
git add examples/effects-test.toml
git commit -m "docs(examples): border and shadow test config" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 3: GATE 4 (Phil)**

```bash
cp examples/effects-test.toml /tmp/edge-effects.toml
scripts/py main.py --config /tmp/edge-effects.toml -v
```
Edit `/tmp/edge-effects.toml` while it runs; each save applies within about a second.

1. **Border:** a 2 px accent line runs along the inner edge of the frame, around the rounded corners, into each panel's joins, along each panel body and back out, as one line: no gaps, no doubled or brighter spots at the joins.
2. **Shadow:** a soft dark shadow falls onto the desktop on every side, uniform, also into the joins; no seams, no darker spots where frame and panel meet. Check on a light and a dark wallpaper (on a near-black wallpaper the shadow is expected to be faint: the border carries the look there).
3. **Follows animation:** toggle and drag each panel: border and shadow follow every frame; when a panel collapses no shadow or border ghost stays behind.
4. `elevation = 0` -> no shadow at all; `elevation = 100` -> wider (48 px) shadow; back to `50`.
5. `color = "#ff000080"` under `[theme.shadow]` -> red-tinted shadow; `color = "#ffffff40"` under `[theme.border]` -> faint translucent border; `width = 4` -> thicker border on the frame side only (never on the desktop side).
6. `enabled = false` under `[theme.border]` -> border gone; under `[theme.shadow]` -> shadow gone; the panels do not flicker or rebuild (restyle only).
7. **Per-monitor override:** set the global `elevation = 20`, then add
   ```toml
   [monitors.HDMI-A-1.theme.shadow]
   elevation = 100
   ```
   (place it after the `[monitors.HDMI-A-1]` table, before the `[[monitors.HDMI-A-1.panels]]` entries): the wide shadow wins on HDMI-A-1 while `enabled` and `color` still come from the global table. Remove it -> narrow again.
8. **Invalid value:** `elevation = 150` -> a "Config not applied" notification naming `theme.shadow.elevation`, the previous look stays. Fix it -> applied.
9. **Alpha frame (optional):** `[theme]` `frame = "#0b0c0dc0"` -> translucent frame and panel bodies, no darker overlap at the joins.

**On failure:** ghosts after animation (item 3) -> stop, capture a screenshot and the config; the damage contract (Task 4) is wrong for that case: add a failing simulation test reproducing the config before fixing. Seams or double-darkening at joins -> screenshot + config; reproduce headlessly by painting the same theme and panel shapes with `CanvasPainter` onto a 1920x1080 `cairo.ImageSurface` and saving it with `write_to_png`, then add a failing pixel test before fixing. A reload that rebuilds panels (item 6) -> check `diff_configs` classification (Task 2 tests).

---

### Task 14: `--stats` measurement mode and the headless simulate command

**Files:**
- Create: `shell/canvas/stats.py`
- Modify: `shell/canvas/simulate.py` (append the command line), `shell/app.py` (stats run), `main.py` (`--stats`)
- Test: `tests/test_canvas_stats.py` (new), `tests/test_main.py`, `tests/test_app_sync.py`

**Interfaces:**
- Consumes: `CanvasPainter.recorder` / `Recorder` protocol (Task 4), `simulate`, `FakeClock` (Task 4), `MonitorShell.canvas.painter`, `MonitorShell.live_panels()` (Task 8), `EdgePanel.toggle()` (existing), `load_config`, `deep_merge`, `Theme`.
- Produces:
  - `shell.canvas.stats`: `GAP_US = 100_000`, `pct(values, q)`, `interval_stats(timestamps_us) -> dict` (keys `frames`, `mean_ms`, `median_ms`, `p95_ms`, `fps`; gaps > `GAP_US` ignored), `ticks_between_draws(tick_ts, draw_ts) -> list[int]`, `StatsRecorder(now_us: Callable[[], int])` with `ticks: dict[key, list[int]]`, `draw_ts`, `draw_ms`, `full_draw_ms`, `on_tick(key, depth)`, `on_draw(duration_ms, full)`, `report(wall_s, cpu_s) -> list[str]`. (`pct`, `interval_stats`, `ticks_between_draws` come from `spikes/canvas/live.py:217-234, 299-308` at `872eff9`.)
  - `shell.canvas.simulate.default_shapes(width, height) -> list[PanelShape]` (the registered widget defaults at 1920x1080; shrunk and moved on smaller sizes so no layout rule fires), `shell.canvas.simulate.main(argv=None) -> int` (`python -m shell.canvas.simulate [--frames N] [--size WxH] [--elevation P] [--border W]`).
  - `EdgeShellApp(store, stats_seconds: float | None = None)`, attributes `recorder`, methods `_exercise() -> bool` (toggles every live panel, repeats), `_stop() -> bool`; constant `shell.app.EXERCISE_MS = 300`.
  - `main.py --stats SECONDS` (`0 < SECONDS <= 10`, `main.MAX_STATS_SECONDS = 10`).
  - Why ticks are counted only on real depth changes and why there is no "sync error" number: in a live run the canvas draws later in the same frame than the panel's tick, so a timestamp comparison would always report one frame of error; the honest measure is the cadence (panel ticks between consecutive canvas draws: 1 = in step).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_canvas_stats.py`:

```python
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
    from shell.panel_layout import resolve_layout
    from shell.panel_spec import PanelGeometry

    w, h = size
    shapes = default_shapes(w, h)
    geos = [PanelGeometry("p", s.edge, s.pos, s.length, s.depth, "extended", "p") for s in shapes]
    layout = resolve_layout(geos, w, h, 10, 14)
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
```

In `tests/test_main.py` change both `def __init__(self, store):` of the existing `FakeApp` classes to `def __init__(self, store, **kwargs):` and append:

```python
def test_stats_seconds_reach_the_app(tmp_path, monkeypatch):
    cfg = tmp_path / "c.toml"
    cfg.write_text("")
    got = {}

    class FakeApp:
        def __init__(self, store, stats_seconds=None):
            got["stats"] = stats_seconds

        def run(self):
            return 0

    monkeypatch.setattr(app_mod, "EdgeShellApp", FakeApp)
    assert main_mod.main(["--config", str(cfg), "--stats", "7.5"]) == 0
    assert got["stats"] == 7.5
    assert main_mod.main(["--config", str(cfg)]) == 0
    assert got["stats"] is None


@pytest.mark.parametrize("value", ["0", "10.5", "-1", "abc"])
def test_stats_is_capped_at_ten_seconds(value):
    with pytest.raises(SystemExit) as exc:
        main_mod.main(["--stats", value])
    assert exc.value.code == 2
```

Append to `tests/test_app_sync.py`:

```python
# ---- --stats ---------------------------------------------------------------------


def test_exercise_toggles_every_live_panel_and_repeats(env):
    app, _ = env
    toggled = []
    panel = type("P", (), {"toggle": lambda self: toggled.append(self)})()
    app.shells["HDMI-A-1"] = type("S", (), {"live_panels": lambda self: [panel, panel]})()
    assert app._exercise() is True
    assert toggled == [panel, panel]


def test_stop_quits_once(env):
    app, _ = env
    quits = []
    app.app = type("A", (), {"quit": lambda self: quits.append(1)})()
    assert app._stop() is False and quits == [1]


def test_recorder_is_attached_to_every_opened_canvas(env, monkeypatch):
    app, mapping = env
    painter = type("Painter", (), {"recorder": None})()

    class WithCanvas(FakeShell):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.canvas = type("C", (), {"painter": painter})()

    monkeypatch.setattr(app_mod, "MonitorShell", WithCanvas)
    app.recorder = object()
    mapping["HDMI-A-1"] = object()
    app.sync_monitors()
    assert painter.recorder is app.recorder
```

Run: `scripts/py -m pytest -q tests/test_canvas_stats.py tests/test_main.py tests/test_app_sync.py`
Expected: FAIL (`No module named 'shell.canvas.stats'`, unknown `--stats`, no `_exercise`).

- [ ] **Step 2: Create `shell/canvas/stats.py`**

```python
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
```

- [ ] **Step 3: Append the command line to `shell/canvas/simulate.py`**

```python
# ---- command line: the headless twin of `main.py --stats` -------------------------------


def default_shapes(width: int, height: int) -> list[PanelShape]:
    """The built-in panels (widgets/: dock, clock, system_bar): their registered defaults at
    1920x1080, shrunk and moved on smaller sizes so that no layout rule (shell.panel_layout)
    would move, shrink or hide one on the simulated surface."""
    dock = min(560, width - 160)
    bar = min(300, height // 3)
    return [
        PanelShape("bottom", (width - dock) // 2, dock, 64),
        PanelShape("top", (width - 168) // 2, 168, 46),
        PanelShape("right", min(600, height - 110 - bar), bar, 56),  # clear of the dock
    ]


def main(argv: list[str] | None = None) -> int:
    import argparse
    import time

    from pydantic import ValidationError

    from shell.canvas.stats import StatsRecorder
    from shell.config.loader import load_config
    from shell.config.models import deep_merge

    p = argparse.ArgumentParser(
        prog="python -m shell.canvas.simulate",
        description="Headless run of the canvas animation loop with the default theme.",
    )
    p.add_argument("--frames", type=int, default=600, help="frames at 60 Hz (default 600)")
    p.add_argument("--size", default="1920x1080", help="WxH (default 1920x1080)")
    p.add_argument("--elevation", type=int, default=None, help="enable the shadow at 0-100 %%")
    p.add_argument("--border", type=int, default=None, help="enable the border, width in px")
    args = p.parse_args(argv)
    try:
        width, height = (int(v) for v in args.size.lower().split("x"))
    except ValueError:
        p.error(f"--size must be WxH, got {args.size!r}")
    theme = load_config(None).theme
    over: dict = {}
    if args.elevation is not None:
        over["shadow"] = {"enabled": True, "elevation": args.elevation}
    if args.border is not None:
        over["border"] = {"enabled": True, "width": args.border}
    try:
        theme = Theme.model_validate(deep_merge(theme.model_dump(), over))
    except ValidationError as exc:
        p.error(str(exc))
    clock = FakeClock()
    recorder = StatsRecorder(clock.get_frame_time)
    wall0, cpu0 = time.perf_counter(), time.process_time()
    res = simulate(
        theme,
        (width, height),
        default_shapes(width, height),
        args.frames,
        recorder=recorder,
        clock=clock,
    )
    print("\n".join(recorder.report(time.perf_counter() - wall0, time.process_time() - cpu0)))
    print(
        f"simulated {res.frames} frames at {width}x{height}: "
        f"{res.draws} draws, {res.full_draws} full"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Wire `--stats` into `main.py` and `shell/app.py`**

`main.py`: after the imports add

```python
MAX_STATS_SECONDS = 10  # live probes draw on the user's screen: keep them short


def _stats_seconds(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
    if not 0 < value <= MAX_STATS_SECONDS:
        raise argparse.ArgumentTypeError(f"must be in (0, {MAX_STATS_SECONDS}]")
    return value
```

add before the `-v/--verbose` argument

```python
    parser.add_argument(
        "--stats",
        type=_stats_seconds,
        default=None,
        metavar="SECONDS",
        help="measure for SECONDS (max 10): toggle every panel every 300 ms, then print frame "
        "pacing, canvas draw cost, canvas/panel cadence and CPU, and quit",
    )
```

and change the last line of `main` to `    return EdgeShellApp(store, stats_seconds=args.stats).run()`.

`shell/app.py`:
1. Add `import time` after `import sys`; add `from shell.canvas.stats import StatsRecorder` after `from shell import plan`; after `APP_NAME = "edge-shell"` add `EXERCISE_MS = 300  # --stats toggles every panel this often: a 280 ms tween plus a frame`.
2. Constructor:

```python
    def __init__(self, store: ConfigStore, stats_seconds: float | None = None):
        """`stats_seconds`: measure for that long (main.py --stats), print, then quit."""
        self.store = store
        self._stats_seconds = stats_seconds
        self.recorder: StatsRecorder | None = None
```

   (the remaining attribute lines stay).
3. In `sync_monitors`, after `self._report_layout(name, self.shells[name])` add

```python
            if self.recorder is not None:
                self.shells[name].canvas.painter.recorder = self.recorder
```

4. In `run()`: right after the `_already_running()` block add

```python
        if self._stats_seconds:
            self.recorder = StatsRecorder(GLib.get_monotonic_time)
```

   and replace the final `self.app.run()` / `return 0` with

```python
        if self.recorder is not None:
            GLib.timeout_add(EXERCISE_MS, self._exercise)
            GLib.timeout_add(int(self._stats_seconds * 1000), self._stop)
        wall0, cpu0 = time.perf_counter(), time.process_time()
        self.app.run()
        if self.recorder is not None:
            wall, cpu = time.perf_counter() - wall0, time.process_time() - cpu0
            print("\n".join(self.recorder.report(wall, cpu)))
        return 0

    def _exercise(self) -> bool:
        """--stats: keep every panel animating (collapse <-> extend)."""
        for shell in self.shells.values():
            for panel in shell.live_panels():
                panel.toggle()
        return True

    def _stop(self) -> bool:
        if self.app is not None:
            self.app.quit()
        return False
```

- [ ] **Step 5: Run the tests and the headless command**

Run: `scripts/py -m pytest -q tests/test_canvas_stats.py tests/test_main.py tests/test_app_sync.py`
Expected: all pass.

Run: `scripts/py -m shell.canvas.simulate --frames 300 --elevation 50 --border 2`
Expected (numbers vary by machine; measured while planning on Phil's machine):
```
=== edge-shell canvas stats ===
panel ticks (busiest panel): ...; frame interval ms: mean 16.67 median 16.67 p95 16.67; fps while animating 60.0
canvas damaged draws: ...; ms median ~3.7 p95 ~3.8 max ...
canvas full draws: 1; ms median ~6.5 ...
panel 0: ... ticks; ticks between canvas draws {1: ...} (0 = idle redraw, 1 = in step, 2+ = skipped)
...
simulated 300 frames at 1920x1080: ... draws, 1 full
```
(All three panels animate at once in this worst case; one animating panel costs about 1 ms headless, as in the findings.)

- [ ] **Step 6: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell/canvas/stats.py shell/canvas/simulate.py shell/app.py main.py tests/test_canvas_stats.py tests/test_main.py tests/test_app_sync.py
git commit -m "feat: --stats measurement mode and headless canvas simulation command" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 15: GATE 5 (Phil, HDMI-A-1): regression and measurement

No code. Prerequisite: Tasks 12-14 committed.

```bash
cp examples/effects-test.toml /tmp/edge-gate5.toml
scripts/py main.py --config /tmp/edge-gate5.toml -v
```

**Live reload** (edit `/tmp/edge-gate5.toml` while it runs):
1. Add `depth = 80` to the dock entry: only the dock is rebuilt at the new depth (clock and system bar do not flicker); the border and shadow follow.
2. Add `state = "collapsed"` to the clock entry: the clock collapses with its animation (no rebuild).
3. Add a fourth panel `[[monitors.HDMI-A-1.panels]]` `widget = "dock"`: a "Panels adjusted" notification says `monitors.HDMI-A-1.panels.3 (dock): overlaps …; not shown`; nothing else changes. Remove it: the next save shows no notification.
4. Save broken TOML (e.g. a lone `[theme`): "Config not applied", the look stays. Fix it: applied.
5. Set `thickness = 12` under `[theme]` (add a `[theme]` table at the top): the whole monitor rebuilds with a thicker frame; a maximized window re-snaps to the new frame. Remove it again.

**Hot-plug** (terminal on DP-1; never touch DP-1 itself):
6. `kscreen-doctor output.HDMI-A-1.disable`: no crash; the log shows `closing Edge Shell on HDMI-A-1`.
7. `kscreen-doctor output.HDMI-A-1.enable`: within about 3 s the frame, the three panels, border and shadow come back in the right places (`opening Edge Shell on HDMI-A-1`). If HDMI-A-1 stays off, enable it from System Settings > Display and report the log.

**Second instance:**
8. In another terminal: `scripts/py main.py --config /tmp/edge-gate5.toml; echo $status` (fish) prints `edge-shell is already running …` and `1`; no second frame flashes up.

**Maximized / fullscreen:**
9. A maximized window stops at the frame on all sides; panels float over it.
10. Make a window fullscreen (e.g. Firefox F11): it covers the shell completely; leave fullscreen: the shell is back intact. Repeat twice.

**Measurement** (quit the running shell first with Ctrl+C):
11. `scripts/py main.py --config /tmp/edge-gate5.toml --stats 10` toggles every panel every 300 ms for 10 s, quits by itself and prints the report. Acceptance (spike targets): `fps while animating` >= 55; `canvas damaged draws` p95 <= 8 ms; `ticks between canvas draws` mostly `1`. Record the CPU line (informative; the spike saw 0.32-0.43 of a core while animating continuously). For comparison run `scripts/py -m shell.canvas.simulate --frames 600 --elevation 50 --border 2`.
12. Optional: run normally for 10 minutes of ordinary use and compare `ps -o rss=,pcpu= -p (pgrep -f "main.py --config /tmp/edge-gate5.toml")` (fish syntax) at start and end: memory stays flat, CPU near 0 when idle.

**On failure:** reload/hot-plug/instance regressions -> stop and capture the `-v` log; they map to `tests/test_app_sync.py` and `tests/test_monitor_shell.py`, so first add a failing display-free test there. Draw p95 over 8 ms or fps under 55 -> record the report and the simulate output; do not tune blindly: compare with one panel (`--stats` with `examples/dock-test.toml`) and discuss with Phil (options: lower default elevation, profile the content-window tick path as findings section 9 item 11 suggests).

---

### Task 16: Docs: README, spec, findings

**Files:**
- Modify: `README.md`, `docs/superpowers/specs/2026-10-11-edge-shell-design.md`, `docs/superpowers/findings/2026-10-12-shape-canvas-spike.md`

**Interfaces:** none (docs only; ruff ignores Markdown).

- [ ] **Step 1: README**

1. Under the spec/plan links add `- [Shape canvas plan](docs/superpowers/plans/2026-10-13-shape-canvas-and-effects.md)`.
2. In **Features** add after the first bullet:
   ```markdown
   - One click-through shape canvas per monitor draws the frame, the rounded corners and every
     panel as one outline, so panels and frame join without seams.
   - Optional inner border and soft uniform shadow (`[theme.border]`, `[theme.shadow]`),
     live-reloadable and overridable per monitor.
   ```
3. In **Run** add
   ```bash
   scripts/py main.py --config examples/effects-test.toml -v  # with border and shadow
   scripts/py main.py --config examples/panels-test.toml --stats 10  # 10 s measurement, then quit
   ```
4. In **Configure**, after the existing TOML block add:
   ````markdown
   Colours are `#rrggbb` or `#rrggbbaa`. Border and shadow are off unless enabled:

   ```toml
   [theme.border]
   enabled = true
   width = 2                 # px, on the frame side of the outline
   color = "#8fd3b6ff"

   [theme.shadow]
   enabled = true
   elevation = 50            # 0-100 %; 100 % reaches 48 px
   color = "#00000080"       # the alpha is the strength

   [monitors.HDMI-A-1.theme.shadow]
   elevation = 80            # per monitor; the other shadow keys still come from [theme.shadow]
   ```
   ````
5. In **Develop** add `scripts/py -m shell.canvas.simulate --elevation 50 --border 2   # headless canvas benchmark` to the code block, and change "Pure logic lives in `shell/` (config, geometry, drawing, animation)" to "Pure logic lives in `shell/` (config, geometry, panel layout, animation) and `shell/canvas/` (outline, effects, scene, damage)".
6. In **Known limitations / planned** replace the "Several panels on one edge …" bullet by
   ```markdown
   - Several panels on one edge are not auto-arranged (use `edge` + `pos`). A panel too close
     to a screen corner is moved, one that overlaps an earlier panel (or leaves less than the
     minimum gap between their joins) is hidden; both send a notification. Planned: spec 16-17.
   ```
   replace the bullet "Changing a connected monitor's resolution or scale does not reflow panels with an explicit `pos`; restart the shell or save the config. Planned fix." (two lines) by
   ```markdown
   - Changing a connected monitor's resolution or scale does not reflow panels: neither those
     with an explicit `pos` nor, since the shape canvas, centred ones (every position is
     resolved once, when the panel is built). Restart the shell or save the config. Planned fix.
   ```
   and add
   ```markdown
   - The frame band is click-through: clicks on the frame reach the desktop.
   - HiDPI / fractional scaling: the canvas assumes scale 1 (it logs a warning otherwise).
   ```

- [ ] **Step 2: Spec (only where the implementation diverges)**

1. Section 3, after the token table: add the sentence `Colours accept `#rrggbb` or `#rrggbbaa` (the alpha form matters for the border and shadow).`
2. Section 5.1: replace the first sentence by `Each enabled monitor gets: one `ShapeCanvas`, 4 invisible `FrameEdge` strips, and one `EdgePanel` per configured panel (see section 18).` and replace the table rows by

   ```markdown
   | Window | Layer | Anchor | Exclusive zone | Input |
   | --- | --- | --- | --- | --- |
   | `ShapeCanvas` × 1 | top | 4 edges | −1 | None (`pass_through=True`) |
   | `FrameEdge` × 4 | bottom (invisible) | 3 edges | `auto` = T px | None (`pass_through=True`) |
   | `EdgePanel` × N | top | 1 edge + margin (resolved `pos`) | −1 | Panel body (+ hover zone) only, updated each frame |
   ```

   and replace the **Fallback.** paragraph by `**Implemented (2026-10-13):** the single-canvas design (section 18, option B) replaced per-window drawing. The strips only reserve space; panels are content, handle and input windows above the canvas.` (Under Fallback A write `top (invisible)` for the strips; under Fallback B add `The startup re-raise of panels is still needed.`)
3. Section 5.2: replace the paragraph by `The canvas draws one union outline of frame, corners and panels (`shell/canvas/outline.py`) in a canonical per-edge space rotated onto each edge, then the border and shadow (`shell/canvas/effects.py`). `shell/geometry.py` keeps the per-panel maths (join radius, input rects, anchors).`
4. Section 6, config example: in the TOML block, after the line `font = ["Hack Nerd Font Mono", "JetBrains Mono", "monospace"]` and before `[monitors.HDMI-A-1]`, insert

   ```toml

   [theme.border]                # opt-in inner border along the outline
   enabled = true
   width = 2                     # px, on the frame side
   color = "#8fd3b6ff"           # #rrggbb or #rrggbbaa

   [theme.shadow]                # opt-in uniform shadow onto the desktop
   enabled = true
   elevation = 50                # 0-100 %; 100 % reaches 48 px
   color = "#00000080"           # the alpha is the strength
   ```

   and after `theme.accent = "#d3a68f"      # optional per-monitor override` add the line `theme.shadow.elevation = 80   # nested tables merge key by key`.
   Then the live-reload table: the "Theme color" row becomes `| Theme colour, border or shadow | Regenerate CSS; redraw the canvas (no rebuild) |`; the "Panel `edge`, `pos`, `length` or `depth`" row becomes `| Panel `edge`, `pos`, `length` or `depth` | Rebuild that panel's window, and any panel whose resolved position or visibility changed with it (section 17 rules) |`.
5. Section 8 layout tree: add `│   ├── canvas/               # shape canvas: outline, effects, scene, painter, window` and `│   ├── panel_layout.py       # PURE: resolved positions, minimum geometry rules`, and change the `frame.py` comment to `# FrameEdge (invisible zone strips)`. In the module table below it, change the `shell/edge_panel.py` row to `| `shell/edge_panel.py` | Window setup, content placement, handle, input region, states; reports its depth to the canvas | Draw the panel body; contain widget content |` and add the rows

   ```markdown
   | `shell/canvas/*` (except `canvas.py`), `shell/panel_layout.py` | Pure logic: outline, border, shadow, scene, damage boxes, panel positions | Import GTK |
   | `shell/canvas/canvas.py` | The `ShapeCanvas` window: draws frame, corners, panel bodies, border, shadow | Take input; know widget content |
   ```

   and add `shell/canvas/*` (except `canvas.py`) and `shell/panel_layout.py` to the first row's pure-module list if that row is kept as is.
6. Section 17, after the "Minimum geometry rules" bullet add: `**Interim implementation (2026-10-13):** `shell/panel_layout.py` clamps `pos` into the free span (`T + R + r` from each end, `r` at full depth), shrinks over-long panels, and hides a later panel whose grown body box overlaps an earlier one (minimum gap `r1 + r2` on one edge), with a notification. The full resolver replaces it.`
7. Section 18, before "**Spike required before choosing B**" add: `**Status (2026-10-13):** spike done (`docs/superpowers/findings/2026-10-12-shape-canvas-spike.md`); option B implemented by `docs/superpowers/plans/2026-10-13-shape-canvas-and-effects.md`. The frame band is click-through now (the old strips took input).`
8. Section 18, default elevation: Phil confirmed 50 % (24 px) (Decisions recorded, item 4); the controller already updated that spec sentence (commit `3f1d311` on `spike/shape-canvas`, "confirmed by Phil"). Check: `grep -n "Phil has not set it yet" docs/superpowers/specs/2026-10-11-edge-shell-design.md` must print nothing. If it still prints the line, replace `(24 px, a controller choice inside the reasonable range; Phil has not set it yet)` by `(24 px, confirmed by Phil)`.

- [ ] **Step 3: Findings note**

Append to `docs/superpowers/findings/2026-10-12-shape-canvas-spike.md`:

```markdown
## 10. Follow-up status (plan 2026-10-13, shape canvas and effects)

| Section 9 item | Where |
|---|---|
| 1 Layout resolver | Plan 2; interim corner-clearance / minimum-gap rules in `shell/panel_layout.py` (plan Task 5) |
| 2 Alpha colours, theme models | Plan Tasks 1-2 |
| 3 Promote outline/effects | Plan Task 3 (contract: `tests/test_canvas_outline.py` vs `tests/legacy_draw.py`); legacy code removed in Task 12 |
| 4 Canvas, invisible strips, content windows | Plan Tasks 6-8 |
| 5 Remove `raise_to_top` | Plan Task 12 (or kept: Fallback B) |
| 6 Damaged-region invalidation | Plan Task 4 (`shell/canvas/scene.py`, simulation tests) |
| 7 Config and reload | Plan Tasks 2, 7, 8, 9 (layout notifications), Gate 4 |
| 8 Fullscreen | Gate 5 item 10 |
| 9 Handle customization | Later plan (spec 15) |
| 10 Multi-monitor and scale | Later; the canvas warns on scale != 1 |
| 11 CPU profile | `main.py --stats` (Gate 5); deeper profiling later |
| 12 Human gates | Gates 1-5 |

The spike code (`spikes/canvas/`, `spikes/tests/`) was removed in plan Task 12; it is in git history at `872eff9`.
```

Then add one line per gate below the table with the date, each item's pass/fail and any fallback applied, copied from the notes taken at Gates 1-5, plus the Gate 5 `--stats` report lines verbatim.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/superpowers/specs/2026-10-11-edge-shell-design.md docs/superpowers/findings/2026-10-12-shape-canvas-spike.md
git commit -m "docs: shape canvas, border and shadow; spec and findings follow-ups" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage**

| Requirement (spec / brief) | Task |
| --- | --- |
| One click-through canvas per monitor draws frame + corners + panels as one outline (18 option B) | 3, 4, 6, 7, 8 |
| Panels stop drawing bodies; transparent full-depth content windows report depth; damaged-box redraw | 4, 8 |
| Inner border: width px, RGBA, mass side only, opt-in | 2, 3 (`draw_border`), Gate 4 |
| Uniform shadow: elevation 0-100 -> `round(48*pct/100)`, RGBA, half-Gaussian, 8-bit levels, clipped to desktop, opt-in; clamp in drawing, reject in validation | 2, 3, Gate 4 |
| Defaults `#00000080` / 50 / 2 px `#8fd3b6ff`, `enabled = false` | 2 |
| `#rrggbbaa` in validator and `hex_to_rgba`, 6-digit unchanged; GTK3 CSS safety | 1 |
| Per-monitor override with deep merge | 2, Gate 4 item 7 |
| No shadow cache; first draw full; damage = union(prev, cur) grown by reach + border | 4 |
| Strips invisible, input-less, still reserving T; stacking risk + gate + fallback | 7, Gate 1, 11 A |
| Screen corners drawn by the canvas; `ScreenCorner` removed | 7 |
| Remove `raise_to_top` only after the gate | 7 (switch), Gates 1-2, 12, 11 B |
| Outline-vs-legacy contract kept via `tests/legacy_draw.py` | 3, 12 |
| Self-intersection rules clamped/rejected with warnings | 5, 8 (log), 9 (notification only when it changes), Gate 3 item 6 |
| Border/shadow changes and toggles are restyles; reload updates the canvas | 2 (diff tests), 7, 8 |
| Handle stays in step with the body (numeric rule), fallback and decision path | Gate 2 item 3, 11 D |
| Regression: frame, corners, dock/clock/system bar, animation, hover, click, drag, centring, reload, hot-plug, second instance, `sync_monitors` guard | 8, Gates 2, 3, 5 |
| Headless simulation of tick/draw loop | 4, 14 |
| `--stats` measurement | 14, Gate 5 |
| HiDPI noted, code scale-ready | 6 (warning), Global Constraints |
| Spike scaffolding decision (recorded) | 12 (deleted; history `872eff9`) |
| README, spec divergences (sections 3, 5, 6, 8, 17, 18), findings follow-ups | 16 |
| Decisions recorded (branch base, overlap rule, click-through band, elevation 50 %, spike removal) | Decisions recorded block, Prerequisites, 5, 9, 12, 16 |

Deliberately not covered (out of scope): spec 15 handles, spec 16/17 resolver, settings window, Plasma integration, scale-aware reach, multi-monitor visual testing (only HDMI-A-1 may be used).

**2. Placeholder scan:** no "TBD"/"TODO"/"similar to Task N"; every code step shows the code; edits to existing files quote the exact lines replaced. The Task 16 gate-results lines are data copied from the gates, specified field by field.

**3. Type and name consistency (checked against the code while writing, by grep):** existing names used: `geometry.join_radius/is_horizontal/anchor_and_margin/surface_size/input_rect`, `PanelGeometry`, `panels_for`, `widget_class`, `monitor_index`, `Tween.jump_to/animate_to`, `EdgePanel.toggle/set_state/apply_theme/_apply_depth/_place_handle/_update_input_region/do_size_allocate`, `MonitorShell._track/_check_monitor/_release/_destroy/apply/close`, `EdgeShellApp.sync_monitors/_reload/_report_error/register_window/unregister_window/run`, `diff_configs`, `Change`, `load_config`, `ConfigStore`. New names are defined once and reused with the same signatures: `PanelShape(edge, pos, length, depth)`, `Scene.add_panel/remove_panel/set_depth`, `CanvasPainter.draw(cr, clip)`, `Recorder.on_tick(key, depth)/on_draw(duration_ms, full)`, `ShapeCanvas.set_theme/add_panel/remove_panel/set_depth`, `resolve_layout(..., where=)`, `Layout.panels/warnings`, `MonitorShell.live_panels/layout_warnings/scene_key`, `EdgeShellApp._notify/_report_layout/_exercise/_stop/recorder`. Every task's code was run while planning in a scratch copy of the branch: after Task 14 the suite was 438 passed (from 255), ruff clean; the Task 8 state without Task 9 was green (416 passed), which is why the split is safe; Fallback D was prototyped on the Task 8 state and stayed green.

**4. Review Focus:** each of the five lines has its pinning test in the owning task (Tasks 1, 2, 4, 5, 6, 7, 8, 14) and Gate 3 item 6; mutation checks in Task 4 Step 7 show the damage tests fail when the pad or the previous-box union is dropped.
