# Handle Customization and Interaction Toggles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every panel's handle can be customized (shape: dots, bar, chevron that morphs with depth, none; size; thickness; position along the edge; rest and hover colour) and its three interactions (click to toggle, hover to peek, drag to open) can be turned off one by one, per panel, with theme-wide and per-widget defaults, all live-reloadable without rebuilding a window.

**Architecture:** A pure core is built and tested headlessly first: config models (`shell/config/models.py`), handle choices carried in the `PanelRequest` but kept out of the layout (`shell/panel_spec.py`, `shell/registry.py`, `shell/config/diff.py`), handle rules (`shell/handle.py`: theme resolution, `auto` shape, highlight, labels, hit target, input region) and cairo drawing (`shell/handle_draw.py`: `draw_handle` with a morph parameter, plus a PNG review sheet). The GTK side changes in two places only: `EdgePanel`'s handle Button keeps its role as the hit target (click, keyboard, accessible name) but its child becomes a `Gtk.DrawingArea` that calls `draw_handle`, and `MonitorShell` updates live panels in place when only the handle or interactions change. The shape canvas is not touched.

**Tech Stack:** Python 3.14 (>=3.12), Fabric 0.0.2, PyGObject 3.50.0 (`<3.52`), pycairo, GtkLayerShell, Pydantic 2, pytest, ruff 0.17.0.

**Spec:** `docs/superpowers/specs/2026-10-11-edge-shell-design.md`, section 15 (this plan's scope, Phil's Gate D wishes), with sections 3 (handle tokens), 4 (interaction model), 6 (config, reload table), 16-17 (handle placement relative to the body, clip container, measurement) and 18 (the canvas draws the bodies; border outside the mass; "handle customization stays on the content windows"). Previous plans (style, gates, constraints): `docs/superpowers/plans/2026-10-13-shape-canvas-and-effects.md` (Gate 1 Fallback B: the delayed `raise_to_top` stays) and `docs/superpowers/plans/2026-10-13-layout-anchoring.md`. Findings: `docs/superpowers/findings/2026-10-12-shape-canvas-spike.md` (section 10, gate results).

**Phil's wishes (Gate D, quoted in spec 15):** "make sure we are planning for the ability to customize the 3 dots (color, size, location, shape) ... click to open, hover to peek, drag to open ... individually opt-in/opt-out ... thin bar ... arrow ... morphing".

**Scope (Plan 3).** In: config keys (`[theme.handle_style]`, per panel `handle` and `interaction` tables), widget defaults through the registry, the pure handle rules and drawing, the drawn handle in `EdgePanel`, the interaction flags, in-place reload, a headless review sheet, two gates, examples, README and spec. Out: the settings window (its models are made ready, decision 10), drawing the handle on the shape canvas (decision 1, the cost if wrong), removing the `raise_to_top` workaround (decision 1), a warning for panels with every interaction off (decision 7), per-panel border/shadow, HiDPI.

**Date:** 2026-10-13 (the plan's execution date, as in the file name).

**Size:** 10 tasks. 6 carry code and tests (1-4, 6-8), 2 human gates (Gate A = Task 5, a PNG review that needs no running shell; Gate B = Task 9, live on HDMI-A-1), Task 10 is docs. Riskiest: Task 6 (the drawn handle replaces the CSS dots: GTK allocation of the Button and its DrawingArea is only simulated by the tests; Gate B items 1-4 check it live), Task 7 (the input region without hover is new behaviour on the compositor: Gate B items 3 and 5 check that clicks reach the desktop and the hit target still answers), Task 8 (in-place updates must never rebuild: Gate B item 6 checks the log and the absence of flicker).

## Decisions (for Phil's review; each with the cost if Phil disagrees)

The spec leaves these open. They are the planner's choices; nothing below is implemented yet.

1. **The handle stays in the panel's own window, drawn with cairo (option a), not on the shape canvas (option b). The delayed `raise_to_top` workaround stays, unchanged.** `EdgePanel`'s handle remains a `Gtk.Button` (the hit target: click, keyboard activation, accessible name, `:hover`/focus state), and its child becomes a `Gtk.DrawingArea` whose draw handler calls the pure `draw_handle` (Task 6). Why not (b), drawing the shape on the canvas with an invisible hit target in the content window: Plan 1 Gate 1 (Run B, raise off) showed that without the re-raise the canvas lands ABOVE the panel windows, and the collapsed dots were hidden because they sit inside the frame band the canvas paints. Moving the handle to the canvas would make the collapsed handle visible without the raise, but every extended panel's content (clock text, dock icons, system bar labels) also lives in the panel windows above the canvas, so the raise would still be needed for the content: option (b) cannot retire the workaround, it only moves the one symptom that revealed it. Against (b) as well: the hover/focus highlight would have to be pushed from the panel window to the canvas (cross-window state), every hover change would damage the canvas (a full redraw path for a 3 px dot), keyboard focus and the accessible name would live in a different window from the drawing, and the canvas scene would gain per-panel handle state; Gate 2 of Plan 1 already showed the handle staying in step with the body without a shared frame clock. For (a): the change is local to `EdgePanel`, the canvas, scene and painter are untouched, the DrawingArea is about 44 x 14 px so a redraw per animation frame is negligible, the shape lives inside the 10 px band in the same window that takes the input, and the border (drawn outside the mass, on the canvas below) can never cover it. Gate B item 10 re-checks the collapsed handles after 10 s and records (information only) what `EDGE_SHELL_RAISE_MS=0` does now. *Cost if Phil prefers (b):* about 1.5 tasks: `PanelShape` gains a `HandleLook` and the panel's lit state, `draw_scene` draws the handle after `fill_mass` inside the panel's damage box (`panel_box` already covers the band and body), `ShapeCanvas.set_handle_lit(key, bool)` is called from the Button's `state-flags-changed`, and the Button's child becomes an empty box; the models, `shell/handle.py` and `draw_handle` are reused unchanged. It would still not remove the raise.
2. **Config surface: per panel `handle` and `interaction` tables, a theme-wide `[theme.handle_style]`, colours from the existing `handle` / `handle_hover` tokens.** Per panel entry: `handle.shape` (`auto | dots | bar | chevron | none`), `handle.size` (px along the edge, 4-40), `handle.weight` (px, 1-8: dot diameter, bar and chevron thickness; a key the spec did not list, needed for "thin bar"), `handle.offset` (px along the edge from the body centre, -2000..2000, negative towards the start of the edge; clamped to the body at run time without a warning, because the body length is only known after layout), `handle.color`, `handle.hover_color` (`#rrggbb` or `#rrggbbaa`); `interaction.click`, `interaction.hover`, `interaction.drag` (strict booleans, so `click = 1` or `"yes"` is rejected). Every key is optional; a missing key comes from the widget's registered default (`PanelDefaults.handle` / `.interaction`; no built-in widget sets any), then the monitor's theme (`[monitors.NAME.theme.handle_style]`), then `[theme.handle_style]` (`shape = "auto"`, `size = 15`, `weight = 3` in `config.default.toml`) and the colours `theme.handle` / `theme.handle_hover`. The name `handle_style` avoids a TOML clash: `[theme.handle]` cannot coexist with the existing `handle = "#7b7f84"` colour key. Unknown shapes and keys fail validation with the key path, as everywhere else. TOML may use dotted keys (`handle.shape = "bar"`) or an inline table. *Cost:* renaming keys before anyone depends on them is trivial; moving the colours into a `[theme.handle]` table would break every config that sets `handle = "..."` (needs a migration note); a widget default ranking below the theme instead of above it = swap two lookups in `shell/handle.py` (trivial).
3. **Shape `auto` (the default) follows the interactions; an explicit shape always wins.** `auto` = dots while click and drag are both on (today's look, so existing configs are unchanged), a bar for drag only, a chevron for click only, dots for hover only, nothing when all three are off (a handle would promise an interaction the panel does not answer). This is Phil's "thin bar when only drag, arrow when only click" as a default rather than a rule. *Cost:* explicit-only shapes (default `dots`, no `auto`) = drop `auto_shape` and one literal (small).
4. **Chevron morph: it folds through a flat bar, it does not rotate.** With `morph = d / depth`, the tip sits at `h/2 * (1 - 2 * morph)` across the edge: collapsed it points where the panel opens (into the screen), half-way it is a flat bar, extended it points back to the screen edge. A 180° rotation would point along the edge half-way, which reads as "slide sideways". `h = min(size / 2, (T - 2) - weight)`. *Cost:* a rotation instead is about 5 lines in `draw_handle` plus its test expectations.
5. **Across the edge the shape is centred in the last `T` px of the mass**: in the middle of the frame band while collapsed, `T / 2` px inside the body's inner edge while extended, never wider than `T - 2` px (1 px clear of the band's edges), with odd-width shapes snapped to pixel centres so dots stay crisp. Today's dots sit 7 px from the screen edge (an artefact of the 14 px button), so the collapsed dots move 2 px towards the screen edge, into the true middle of the 10 px band. *Cost:* keeping 7 px is one formula in `shape_centre` (trivial).
6. **Hit target separate from the shape and at least today's size.** The Button is `max(44, size + 16)` px along the edge (never longer than the body) by `max(14, T + 4)` px across, and rides the body's inner edge exactly as today (`inset = max(0, T + d - across)`). `offset` moves it and the shape together. Input region: with hover on it is unchanged (body plus the 16 px hover zone, which always contains the hit target); with hover off it is the body while it is out plus the hit target when click or drag is on; with all three off a collapsed panel takes no input at all (the frame band stays click-through there). *Cost:* other minimums are two constants.
7. **Interaction semantics.** Hover off: entering the strip never peeks and the handle does not light up for a peek. Drag off: a press never starts a drag (a press and release is still a click when click is on). Click off: `clicked` is ignored and the Button cannot take keyboard focus (keyboard activation follows click); the tooltip and accessible name become "Drag to expand clock" (drag on) or no tooltip and "clock handle" (drag off). The handle lights up (hover colour) while the pointer is on it or it has focus and click or drag is on, and while the panel peeks (spec 4: "Peek: handle dots brighten"; today the dots only brightened with the pointer on the handle itself). All three off is allowed: the panel then opens and closes only through `state` in the config (and later the settings window); no warning is logged. `state` keeps its meaning (the configured state, retargeted on reload) whatever the flags. Turning hover off by reload while the panel peeks drops the peek; turning drag off mid-drag lets that drag finish. *Cost:* a warning for all-off panels = one INFO line per config load (trivial); the old highlight rule = drop the peek clause of `is_highlighted` (trivial).
8. **Reload: handle and interaction changes are in-place updates.** `PanelRequest` gains `handle: HandleSpec` and `interaction: Interaction` (defaults, appended after `fallback_length`), but `PanelGeometry` and the layout never see them, so they can never cause a rebuild. The diff gains one kind, `panel-handle` (the entry changed only in `handle`, `interaction` and maybe `state`); `MonitorShell._sync_panels` keeps the last `(handle, interaction)` per index and calls the live panel's `set_handle(handle, interaction)` when it changed. Theme-level changes (`[theme.handle_style]`, `handle`, `handle_hover`) are an ordinary `restyle`: `apply_theme` re-resolves and redraws the handle (the canvas does its usual full redraw on a restyle). *Cost:* none structural.
9. **Draw errors never reach the main loop**: the handle's draw handler catches, logs with the traceback and draws nothing, like the canvas's. *Cost:* none.
10. **Settings-window readiness.** The Pydantic models stay the single source: `HandleConfig`, `InteractionConfig`, `HandleStyle` (+ per-monitor override) appear in `Config.model_json_schema()`, `HANDLE_SHAPES` lists the shape choices, and widget defaults come from the registry (`PanelDefaults.handle` / `.interaction`). A test pins the schema (Task 1). *Cost:* none.
11. **The `.handle-dot` CSS rules go** (the dots are no longer widgets); `#handle` keeps its reset rule. The `handle` / `handle_hover` theme tokens now feed cairo. *Cost:* none.

## Prerequisites

- Branch `feat/handle-customization` from `main` at `6cf17c1` (Plans 1 and 2 merged), in the worktree `/home/phil/Projects/pyDev/projects/myShell/.claude/worktrees/feat-edge-shell-core`.
- Baseline before Task 1: `scripts/py -m pytest -q` prints `645 passed` (2 GLib deprecation warnings are normal); `scripts/py -m ruff check .` prints `All checks passed!`.
- Always stage files by name, never `git add -A` or `git add .`.

## Global Constraints

- Python only through `scripts/py` (shared venv `/home/phil/Projects/pyDev/pyEnvs/global-base`). **PyGObject must stay `<3.52`** (Fabric 0.0.2 breaks on 3.52+).
- **Monitor is an INT.** Fabric 0.0.2's `WaylandWindow.monitor` is an int property; a `Gdk.Monitor` object is silently dropped. Always pass `monitor=monitor_index(monitor)` (`shell/gdk_util.py`). No new windows are created by this plan.
- **Input shape after allocate.** Fabric's `Window.do_size_allocate` resets the input shape on every allocate; `EdgePanel.do_size_allocate` re-applies the panel's region. Never drop that override; `_update_input_region` must stay callable from it (everything it reads, `_theme`, `_interaction`, `_look`, `_d`, is set before `_d` in `__init__`).
- **Exclusive zones** unchanged: panels and the canvas use `exclusivity="none"` then `GtkLayerShell.set_exclusive_zone(self, -1)`.
- **Keep the delayed `raise_to_top` workaround** (Plan 1 Gate 1, Fallback B): `RAISE_DELAY_MS` / `RAISE_FALLBACK_MS` in `shell/monitors.py`, the re-raise of rebuilt panels in `_new_panel`. This plan does not remove it (decision 1). An in-place handle update must not schedule a re-raise.
- **Pure modules import no GTK / `gi`:** `shell/handle.py`, `shell/handle_draw.py`, `shell/panel_spec.py`, `shell/registry.py`, `shell/panel_layout.py`, `shell/geometry.py`, `shell/config/*`, `shell/canvas/*` except `canvas.py`. pycairo is allowed (CI has it).
- **Colours** are `#rrggbb` or `#rrggbbaa` (`check_hex`, `hex_to_rgba`).
- **Tests.** CI has only pycairo, pydantic, pytest and ruff: any test importing `gi` or `fabric` starts with `pytest.importorskip("gi")` / `pytest.importorskip("fabric")`. Tests never create a window (that would draw on Phil's screen): GTK classes are tested by calling their methods on stand-ins (`SimpleNamespace`), as in `tests/test_edge_panel_drag.py`. A plain non-window widget may be created after `Gtk.init_check()` succeeds (skip otherwise).
- **Lint.** `ruff` 0.17.0, line length 100, rules E, F, I, UP, B (so no function calls in argument defaults: use the module-level `THEME_HANDLE` / `ALL_INTERACTIONS`), excludes `docs/` and `*.md`.
- **VERIFY** (before every commit): `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`. The suite must be green at the end of EVERY task (0 failed).
- **Git.** Plain separate git commands run from the worktree (no `cd … && git`, no command substitution around git). Stage files by name. **Never push.** Every commit message ends with a second `-m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"`.
- **Live runs.** Phil is the only visual tester, on `HDMI-A-1` only. **Never touch `DP-1`** (it holds the Plasma panel; never configure it as `edge`). Subagents executing tasks never launch the shell or any GUI (`main.py` without `--list-outputs`); headless commands are fine (`pytest`, `scripts/py -m shell.handle_draw --sheet …`, the `scripts/py -c` checks in Task 9, which import the widgets but create no window). Live probes are capped at 10 s (`main.py --stats` refuses more) and are run by Phil at the gates. If a live run is refused for a subagent, stop and report.

## Review Focus

The six input classes most likely to bite Phil that the spec implies but a happy-path test would not catch, each pinned by a test in the owning task:

1. **Existing configs must look and behave exactly as before** (no `handle` / `interaction` keys: dots, all three interactions, the same input region). Pinned by `test_defaults_change_nothing` (Task 1), `test_requests_default_to_the_theme_and_every_interaction` (Task 2), `test_the_theme_supplies_every_default` and `test_input_region_with_hover_is_unchanged` (Task 3), `test_dots_are_three_crisp_dots_along_the_edge` (Task 4), `test_the_handle_draws_the_rest_colour` (Task 6), `test_with_hover_the_input_region_is_unchanged` (Task 7); live by Gate B item 1.
2. **A handle that would leave the frame band or sit under the border** (big size, heavy weight, a deep chevron, a thin frame `thickness = 2`, the border on). Expect the shape clamped inside the band, 1 px clear, and nothing drawn when the band has no room. Pinned by `test_the_shape_never_leaves_its_band` and `test_nothing_is_drawn` (Task 4), `test_shape_centre` (Task 3); live by Gate A item 4 and Gate B item 9.
3. **An offset or a shape larger than the body** (offset 9999, a body shrunk to 60 px by the layout, `size = 40`). Expect the hit target and shape clamped inside the body, never off its end. Pinned by `test_offset_is_clamped_to_the_body` and `test_hit_size_has_a_minimum_and_grows_with_the_shape` (Task 3), `test_place_handle_offsets_along_and_rides_across` (the 9999 case, Task 6); live by Gate B item 4.
4. **A reload that changes only the handle or interactions, also while the panel peeks** must update in place: no rebuild, no re-raise, no stuck peek. Pinned by `test_handle_and_interaction_changes_update_in_place` (Task 2), `test_set_handle_updates_in_place_and_drops_a_peek` (Task 7), `test_a_handle_change_updates_the_live_panel` (Task 8); live by Gate B item 6.
5. **A panel with every interaction off** must draw no handle, take no input while collapsed (click-through) and still open from `state` in the config. Pinned by `test_auto_shape_follows_the_interactions` (Task 3), `test_with_every_interaction_off_a_collapsed_panel_is_click_through` and `test_labels_and_keyboard_follow_click` (Task 7); live by Gate B item 5.
6. **Bad values** (`shape = "star"`, `size = 3`, `color = "red"`, `click = "yes"`, a misspelt key) must be rejected with the key path, keeping the last good config. Pinned by `test_bad_values_name_the_key_path` and `test_an_unknown_shape_lists_the_known_ones` (Task 1); live by Gate B item 8.

## File Structure

```
shell/config/models.py        # + HandleShape, HANDLE_SHAPES, HandleStyle (+Override), Theme.handle_style,
                              #   HandleConfig, InteractionConfig, PanelConfig.handle / .interaction
config.default.toml           # + [theme.handle_style]
shell/panel_spec.py           # + HandleSpec, Interaction, THEME_HANDLE, ALL_INTERACTIONS;
                              #   PanelDefaults / PanelRequest gain handle + interaction
shell/registry.py             # request_for merges handle / interaction key by key (entry over widget)
shell/config/diff.py          # + "panel-handle" change kind
shell/handle.py               # NEW, PURE: HandleLook, resolve_handle, auto_shape, is_highlighted,
                              #   handle_label, morph, hit_size, clamp_offset, along_margins, hit_inset,
                              #   shape_centre, hit_rect, input_rects
shell/handle_draw.py          # NEW, PURE cairo: handle_matrix, snap, draw_handle, render_sheet, main
shell/edge_panel.py           # handle Button + DrawingArea, _size_handle, _on_handle_draw, offset placement,
                              #   apply_theme / set_handle in place, interaction flags, input region
shell/theme.py                # .handle-dot CSS rules removed
shell/monitors.py             # passes handle / interaction to panels; in-place set_handle on reload
examples/handles-test.toml    # Gate B
tests/test_config_handle.py   # NEW (Task 1)
tests/test_handle_requests.py # NEW (Task 2)
tests/test_handle.py          # NEW (Task 3)
tests/test_handle_draw.py     # NEW (Task 4)
tests/test_edge_panel_handle.py  # NEW (Tasks 6-7)
tests/test_theme.py           # one expectation adjusted (Task 6)
tests/test_monitor_shell.py   # FakeWindow.set_handle, bare_shell._handles, 5 new tests (Task 8)
README.md, docs/superpowers/specs/2026-10-11-edge-shell-design.md   # Task 10
```

| Task | Deliverable | Expected `pytest -q` | Keeps the suite green because |
| --- | --- | --- | --- |
| 1 | config models and defaults | 664 (+19) | new keys optional, defaults reproduce today |
| 2 | requests, registry merge, `panel-handle` diff | 678 (+14) | new fields have defaults; positional constructions unchanged |
| 3 | pure handle rules | 742 (+64) | new module |
| 4 | `draw_handle` + review sheet | 869 (+127) | new module |
| 5 | Gate A (PNG sheet, Phil) | 869 | no code |
| 6 | drawn handle in `EdgePanel`, CSS dots removed | 884 (+15) | `EdgePanel`'s new kwargs have defaults |
| 7 | interaction flags, `set_handle`, input region | 895 (+11) | stand-in tests |
| 8 | `MonitorShell` in-place updates | 900 (+5) | fakes gain `set_handle` |
| 9 | Gate B (live, Phil) + example | 900 | example only |
| 10 | README, spec | 900 | docs only |

Without a display, `test_the_handle_is_a_button_drawing_with_cairo` (Task 6) is skipped (one fewer passed, one skipped).

---

### Task 1: Config keys for handles and interactions

**Files:**
- Modify: `shell/config/models.py` (imports; new types before `class Theme`; `Theme.handle_style`; `ThemeOverride`; `HandleConfig` / `InteractionConfig` before `class PanelConfig`; two `PanelConfig` fields)
- Modify: `config.default.toml` (before the `# Panel layout (spec 16-17).` block)
- Test: `tests/test_config_handle.py` (new)

**Interfaces:**
- Consumes: `check_hex`, `_Strict`, `_override_of`, `deep_merge` (existing, `shell/config/models.py`); `load_config`, `parse_config` (`shell/config/loader.py`).
- Produces:
  - `shell.config.models.HandleShape = Literal["auto", "dots", "bar", "chevron", "none"]`, `HANDLE_SHAPES: tuple[str, ...]` (same order)
  - `HandleStyle(shape: HandleShape = "auto", size: int = 15 (4-40), weight: int = 3 (1-8))`, `HandleStyleOverride` (all optional)
  - `Theme.handle_style: HandleStyle`; `ThemeOverride.handle_style: HandleStyleOverride | None`
  - `HandleConfig(shape, size, weight, offset (-2000..2000), color, hover_color)`, every field `| None = None`; colours checked by `check_hex`
  - `InteractionConfig(click, hover, drag)`, each `StrictBool | None = None`
  - `PanelConfig.handle: HandleConfig`, `PanelConfig.interaction: InteractionConfig` (default empty tables)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_handle.py`:

```python
"""Config keys for handle customization and per-interaction toggles (spec 15)."""

import pytest
from pydantic import ValidationError

from shell.config.loader import load_config, parse_config
from shell.config.models import (
    HANDLE_SHAPES,
    Config,
    ConfigError,
    HandleConfig,
    InteractionConfig,
    PanelConfig,
)


def one_panel(**entry):
    return {"HDMI-A-1": {"shell": "edge", "panels": [{"widget": "dock", **entry}]}}


def test_defaults_change_nothing(make_config):
    cfg = make_config()
    style = cfg.theme.handle_style
    assert (style.shape, style.size, style.weight) == ("auto", 15, 3)
    panel = PanelConfig(widget="dock")
    assert panel.handle == HandleConfig() and panel.interaction == InteractionConfig()
    assert all(v is None for v in panel.handle.model_dump().values())
    assert all(v is None for v in panel.interaction.model_dump().values())


def test_shapes_offered_to_the_settings_window():
    assert HANDLE_SHAPES == ("auto", "dots", "bar", "chevron", "none")


def test_a_full_handle_and_interaction_entry(make_config):
    cfg = make_config(
        monitors=one_panel(
            handle={
                "shape": "chevron",
                "size": 24,
                "weight": 4,
                "offset": -120,
                "color": "#FF8800",
                "hover_color": "#ffffff80",
            },
            interaction={"click": True, "hover": False, "drag": False},
        )
    )
    panel = cfg.monitor("HDMI-A-1").panels[0]
    assert panel.handle.model_dump() == {
        "shape": "chevron",
        "size": 24,
        "weight": 4,
        "offset": -120,
        "color": "#ff8800",  # normalised like every theme colour
        "hover_color": "#ffffff80",
    }
    assert (panel.interaction.click, panel.interaction.hover, panel.interaction.drag) == (
        True,
        False,
        False,
    )


@pytest.mark.parametrize(
    ("table", "key", "value", "kind"),
    [
        ("handle", "shape", "star", "literal_error"),
        ("handle", "size", 3, "greater_than_equal"),
        ("handle", "size", 41, "less_than_equal"),
        ("handle", "weight", 0, "greater_than_equal"),
        ("handle", "weight", 9, "less_than_equal"),
        ("handle", "offset", 2001, "less_than_equal"),
        ("handle", "color", "red", "value_error"),
        ("handle", "hover_color", "#fff", "value_error"),
        ("handle", "colour", "#ffffff", "extra_forbidden"),
        ("interaction", "click", "yes", "bool_type"),
        ("interaction", "drag", 1, "bool_type"),
        ("interaction", "peek", True, "extra_forbidden"),
    ],
)
def test_bad_values_name_the_key_path(make_config, table, key, value, kind):
    with pytest.raises(ValidationError) as exc:
        make_config(monitors=one_panel(**{table: {key: value}}))
    (error,) = exc.value.errors()
    assert error["loc"] == ("monitors", "HDMI-A-1", "panels", 0, table, key)
    assert error["type"] == kind


def test_an_unknown_shape_lists_the_known_ones(make_config):
    data = make_config().model_dump()
    data["monitors"] = one_panel(handle={"shape": "star"})
    with pytest.raises(ConfigError) as exc:
        parse_config(data)
    assert str(exc.value) == (
        "monitors.HDMI-A-1.panels.0.handle.shape: "
        "Input should be 'auto', 'dots', 'bar', 'chevron' or 'none'"
    )


def test_theme_handle_style_per_monitor_merges_key_by_key(make_config):
    cfg = make_config(
        theme={"handle_style": {"shape": "bar", "size": 30}},
        monitors={"A": {"theme": {"handle_style": {"size": 20}}}},
    )
    a, other = cfg.theme_for("A").handle_style, cfg.theme_for("B").handle_style
    assert (a.shape, a.size, a.weight) == ("bar", 20, 3)
    assert (other.shape, other.size, other.weight) == ("bar", 30, 3)
    with pytest.raises(ValidationError, match=r"monitors\.A\.theme: handle_style\.size"):
        make_config(monitors={"A": {"theme": {"handle_style": {"size": 99}}}})


def test_toml_dotted_keys_and_the_default_file(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text(
        "[monitors.HDMI-A-1]\n"
        'shell = "edge"\n'
        "[[monitors.HDMI-A-1.panels]]\n"
        'widget = "dock"\n'
        'handle.shape = "bar"\n'
        'handle.color = "#8fd3b6"\n'
        "interaction.hover = false\n",
        encoding="utf-8",
    )
    cfg = load_config(user, required=True)
    panel = cfg.monitor("HDMI-A-1").panels[0]
    assert (panel.handle.shape, panel.handle.color, panel.handle.size) == ("bar", "#8fd3b6", None)
    assert (panel.interaction.hover, panel.interaction.click) == (False, None)
    style = cfg.theme.handle_style  # from config.default.toml
    assert (style.shape, style.size, style.weight) == ("auto", 15, 3)


def test_the_json_schema_describes_the_new_tables():
    schema = Config.model_json_schema()
    defs = schema["$defs"]
    assert set(defs["HandleConfig"]["properties"]) == {
        "shape",
        "size",
        "weight",
        "offset",
        "color",
        "hover_color",
    }
    assert set(defs["InteractionConfig"]["properties"]) == {"click", "hover", "drag"}
    assert defs["HandleStyle"]["properties"]["shape"]["enum"] == list(HANDLE_SHAPES)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/py -m pytest -q tests/test_config_handle.py`
Expected: FAIL at collection with `ImportError: cannot import name 'HANDLE_SHAPES'`.

- [ ] **Step 3: Implement in `shell/config/models.py`**

1. Change `from typing import Annotated, Any, Literal` to `from typing import Annotated, Any, Literal, get_args`, and add `StrictBool,` to the pydantic import list right after `Field,`.
2. Insert directly above `class Theme(_Strict):`

```python
HandleShape = Literal["auto", "dots", "bar", "chevron", "none"]
HANDLE_SHAPES: tuple[str, ...] = get_args(HandleShape)  # the settings window's choices
HandleSize = Annotated[int, Field(ge=4, le=40)]  # px along the edge
HandleWeight = Annotated[int, Field(ge=1, le=8)]  # px: dot diameter, bar and chevron stroke
HandleOffset = Annotated[int, Field(ge=-2000, le=2000)]  # px from the body centre


class HandleStyle(_Strict):
    """The handle look of every panel whose entry (or widget) does not say otherwise (spec 15).
    "auto" picks the shape from the panel's interactions (shell.handle.auto_shape). The colours
    are the theme's `handle` and `handle_hover` tokens."""

    shape: HandleShape = "auto"
    size: HandleSize = 15
    weight: HandleWeight = 3
```

3. In `class Theme`, after `shadow: Shadow = Field(default_factory=Shadow)` add

```python
    handle_style: HandleStyle = Field(default_factory=HandleStyle)
```

4. Replace

```python
ShadowOverride = _override_of("ShadowOverride", Shadow)
# Merged over the base theme (deep_merge) and re-validated by Theme.
ThemeOverride = _override_of(
    "ThemeOverride", Theme, {"border": BorderOverride, "shadow": ShadowOverride}
)
```

by

```python
ShadowOverride = _override_of("ShadowOverride", Shadow)
HandleStyleOverride = _override_of("HandleStyleOverride", HandleStyle)
# Merged over the base theme (deep_merge) and re-validated by Theme.
ThemeOverride = _override_of(
    "ThemeOverride",
    Theme,
    {"border": BorderOverride, "shadow": ShadowOverride, "handle_style": HandleStyleOverride},
)
```

5. Insert directly above `class PanelConfig(_Strict):`

```python
class HandleConfig(_Strict):
    """A panel's own handle (spec 15). Every key is optional: a missing one comes from the
    widget's default, then the theme ([theme.handle_style]; colours: the theme's handle and
    handle_hover). `offset` moves the handle along the edge from the body centre (negative:
    towards the start of the edge, left or top); it is clamped to the body."""

    shape: HandleShape | None = None
    size: HandleSize | None = None
    weight: HandleWeight | None = None
    offset: HandleOffset | None = None
    color: str | None = None
    hover_color: str | None = None

    @field_validator("color", "hover_color")
    @classmethod
    def _hex(cls, value: str | None) -> str | None:
        return None if value is None else check_hex(value)


class InteractionConfig(_Strict):
    """Which interactions open and close a panel (spec 15). A missing key comes from the
    widget's default, else true. Keyboard activation follows `click`."""

    click: StrictBool | None = None
    hover: StrictBool | None = None
    drag: StrictBool | None = None
```

6. In `class PanelConfig`, after `state: PanelState | None = None` add

```python
    handle: HandleConfig = Field(default_factory=HandleConfig)
    interaction: InteractionConfig = Field(default_factory=InteractionConfig)
```

- [ ] **Step 4: Add the defaults to `config.default.toml`**

Insert directly above the line `# Panel layout (spec 16-17). `gap` is the straight piece of frame left between two neighbouring`:

```toml
# Handle look of every panel (spec 15); a panel entry's `handle` table overrides it, and the
# colours are `handle` and `handle_hover` above. Per monitor: [monitors.NAME.theme.handle_style].
[theme.handle_style]
shape = "auto"          # auto | dots | bar | chevron | none; auto follows the interactions
size = 15               # px along the edge, 4-40
weight = 3              # px, 1-8: dot diameter, bar and chevron thickness

```

- [ ] **Step 5: Run the tests**

Run: `scripts/py -m pytest -q tests/test_config_handle.py`
Expected: `19 passed`.

- [ ] **Step 6: VERIFY and commit**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `664 passed`, ruff `All checks passed!`.

```bash
git add shell/config/models.py config.default.toml tests/test_config_handle.py
git commit -m "feat(config): handle style, per-panel handle and interaction tables" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Handle and interaction in requests; registry defaults; in-place diff kind

**Files:**
- Modify: `shell/panel_spec.py` (import; new dataclasses and constants before `PanelDefaults`; two fields on `PanelDefaults` and `PanelRequest`)
- Modify: `shell/registry.py` (import; `request_for`; two helpers)
- Modify: `shell/config/diff.py` (import; `Kind`; `_diff_panels`; `_in_place`)
- Test: `tests/test_handle_requests.py` (new)

**Interfaces:**
- Consumes: `HandleShape`, `PanelConfig.handle` / `.interaction` (Task 1).
- Produces:
  - `shell.panel_spec.HandleSpec(shape: HandleShape | None = None, size: int | None = None, weight: int | None = None, offset: int = 0, color: str | None = None, hover_color: str | None = None)` (frozen; None = the theme's value)
  - `shell.panel_spec.Interaction(click: bool = True, hover: bool = True, drag: bool = True)` (frozen)
  - `shell.panel_spec.THEME_HANDLE = HandleSpec()`, `ALL_INTERACTIONS = Interaction()`
  - `PanelDefaults.handle: HandleSpec = HandleSpec()`, `PanelDefaults.interaction: Interaction = Interaction()` (last fields)
  - `PanelRequest.handle: HandleSpec = HandleSpec()`, `PanelRequest.interaction: Interaction = Interaction()` (after `fallback_length`)
  - `shell.registry.request_for(cfg)` fills both, key by key: the entry's value, else the widget default
  - `shell.config.diff.Kind` gains `"panel-handle"`: emitted when two requests differ only in `handle`, `interaction` and maybe `state` (and not only in `state`)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_handle_requests.py`:

```python
"""Handle and interaction choices travel from the config entry (over the widget's defaults)
into the PanelRequest; changing them is an in-place reload, never a rebuild (spec 15)."""

import pytest

from shell.config.diff import Change, diff_configs
from shell.config.models import PanelConfig
from shell.panel_layout import layout_monitor
from shell.panel_spec import HandleSpec, Interaction, PanelDefaults


@pytest.fixture
def grip(fake_registry):
    """A widget whose defaults set a handle and turn hover off."""
    fake_registry.register(
        "grip",
        PanelDefaults(
            edge="left",
            length=200,
            depth=40,
            label="grip",
            handle=HandleSpec(shape="bar", size=30, color="#112233"),
            interaction=Interaction(hover=False),
        ),
    )(type("Grip", (), {}))
    return fake_registry


def test_requests_default_to_the_theme_and_every_interaction(fake_registry):
    req = fake_registry.request_for(PanelConfig(widget="dock"))
    assert req.handle == HandleSpec() and req.interaction == Interaction()
    assert (req.interaction.click, req.interaction.hover, req.interaction.drag) == (
        True,
        True,
        True,
    )


def test_entry_keys_win_over_the_widget_defaults_key_by_key(grip):
    req = grip.request_for(
        PanelConfig(
            widget="grip",
            handle={"size": 20, "offset": -30, "hover_color": "#ffffff"},
            interaction={"click": False},
        )
    )
    assert req.handle == HandleSpec(
        shape="bar", size=20, weight=None, offset=-30, color="#112233", hover_color="#ffffff"
    )
    assert req.interaction == Interaction(click=False, hover=False, drag=True)
    plain = grip.request_for(PanelConfig(widget="grip"))
    assert plain.handle == HandleSpec(shape="bar", size=30, color="#112233")
    assert plain.interaction == Interaction(hover=False)


def test_the_layout_ignores_the_handle(fake_registry):
    a = fake_registry.request_for(PanelConfig(widget="dock"))
    b = fake_registry.request_for(
        PanelConfig(widget="dock", handle={"shape": "chevron"}, interaction={"drag": False})
    )
    one = layout_monitor([a], 1920, 1080, 10, 14, 8).panels
    two = layout_monitor([b], 1920, 1080, 10, 14, 8).panels
    assert one == two


def mon(*panels, theme=None):
    return {"HDMI-A-1": {"shell": "edge", "panels": list(panels), "theme": theme or {}}}


@pytest.mark.parametrize(
    "entry",
    [
        {"handle": {"shape": "bar"}},
        {"handle": {"offset": 40}},
        {"handle": {"color": "#ff0000"}},
        {"interaction": {"hover": False}},
        {"interaction": {"click": False, "drag": False}},
        {"handle": {"size": 30}, "state": "collapsed"},
    ],
)
def test_handle_and_interaction_changes_update_in_place(fake_registry, make_config, entry):
    old = make_config(monitors=mon({"widget": "dock"}, {"widget": "clock"}))
    new = make_config(monitors=mon({"widget": "dock"}, {"widget": "clock", **entry}))
    assert diff_configs(old, new) == [Change("panel-handle", "HDMI-A-1", 1)]


def test_a_handle_change_with_a_geometry_change_rebuilds(fake_registry, make_config):
    old = make_config(monitors=mon({"widget": "dock"}))
    new = make_config(monitors=mon({"widget": "dock", "depth": 80, "handle": {"shape": "bar"}}))
    assert diff_configs(old, new) == [Change("panel-rebuild", "HDMI-A-1", 0)]


@pytest.mark.parametrize(
    "theme",
    [
        {"handle_style": {"shape": "chevron"}},
        {"handle_style": {"weight": 5}},
        {"handle": "#ff0000"},
        {"handle_hover": "#00ff00"},
    ],
)
def test_theme_handle_changes_are_a_restyle(fake_registry, make_config, theme):
    old = make_config(monitors=mon({"widget": "dock"}))
    new = make_config(monitors=mon({"widget": "dock"}), theme=theme)
    assert diff_configs(old, new) == [Change("restyle", "HDMI-A-1")]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/py -m pytest -q tests/test_handle_requests.py`
Expected: FAIL at collection with `ImportError: cannot import name 'HandleSpec'`.

- [ ] **Step 3: Implement `shell/panel_spec.py`**

Change the models import to `from shell.config.models import Align, Edge, HandleShape, PanelState` and insert directly above `@dataclass(frozen=True)` / `class PanelDefaults:`

```python
@dataclass(frozen=True)
class HandleSpec:
    """A panel's own handle choices (config entry over widget default). None = the theme's
    value ([theme.handle_style], colours `handle` / `handle_hover`), resolved by
    shell.handle.resolve_handle, so a theme change restyles without touching the request."""

    shape: HandleShape | None = None
    size: int | None = None
    weight: int | None = None
    offset: int = 0  # px along the edge from the body centre; clamped to the body
    color: str | None = None
    hover_color: str | None = None


@dataclass(frozen=True)
class Interaction:
    """Which interactions a panel answers (spec 15). Keyboard activation follows `click`."""

    click: bool = True
    hover: bool = True
    drag: bool = True


THEME_HANDLE = HandleSpec()  # every handle key from the theme
ALL_INTERACTIONS = Interaction()  # click, hover and drag on (spec 15 default)


```

At the end of `PanelDefaults` (after `offset: int = 0`) add

```python
    handle: HandleSpec = HandleSpec()
    interaction: Interaction = Interaction()
```

At the end of `PanelRequest` (after `fallback_length: int  # px for "content" until the widget has been measured`) add

```python
    # Not part of the layout (PanelGeometry): a change is applied to the live panel in place.
    handle: HandleSpec = HandleSpec()
    interaction: Interaction = Interaction()
```

- [ ] **Step 4: Implement `shell/registry.py`**

Change the import to `from shell.panel_spec import HandleSpec, Interaction, PanelDefaults, PanelRequest`. In `request_for`, replace the tail of the `PanelRequest(...)` call

```python
        label=d.label,
        fallback_length=d.length,
    )
```

by

```python
        label=d.label,
        fallback_length=d.length,
        handle=_handle(cfg, d.handle),
        interaction=_interaction(cfg, d.interaction),
    )


def _handle(cfg: PanelConfig, default: HandleSpec) -> HandleSpec:
    """Key by key: the entry's [handle] value, else the widget's default (None = the theme's)."""
    own = cfg.handle
    return HandleSpec(
        **{
            key: getattr(default, key) if getattr(own, key) is None else getattr(own, key)
            for key in ("shape", "size", "weight", "offset", "color", "hover_color")
        }
    )


def _interaction(cfg: PanelConfig, default: Interaction) -> Interaction:
    own = cfg.interaction
    return Interaction(
        **{
            key: getattr(default, key) if getattr(own, key) is None else getattr(own, key)
            for key in ("click", "hover", "drag")
        }
    )
```

- [ ] **Step 5: Implement `shell/config/diff.py`**

Add the import `from shell.panel_spec import HandleSpec, Interaction, PanelRequest` after `from shell.config.models import Config`. Add `"panel-handle",` as the last entry of `Kind` (after `"panel-state",`). In `_diff_panels` replace

```python
        elif replace(old[i], state=new[i].state) == new[i]:
            changes.append(Change("panel-state", name, i))
        else:
            changes.append(Change("panel-rebuild", name, i))
    return changes + removed[::-1]
```

by

```python
        elif replace(old[i], state=new[i].state) == new[i]:
            changes.append(Change("panel-state", name, i))
        elif _in_place(old[i]) == _in_place(new[i]):
            # handle / interaction (maybe with state): updated on the live panel, no rebuild
            changes.append(Change("panel-handle", name, i))
        else:
            changes.append(Change("panel-rebuild", name, i))
    return changes + removed[::-1]


def _in_place(req: PanelRequest) -> PanelRequest:
    """The request without what a live panel changes in place (state, handle, interaction)."""
    return replace(req, state="extended", handle=HandleSpec(), interaction=Interaction())
```

- [ ] **Step 6: Run the tests**

Run: `scripts/py -m pytest -q tests/test_handle_requests.py tests/test_registry.py tests/test_config_diff.py`
Expected: all pass (`tests/test_handle_requests.py` has 14; `test_request_uses_widget_defaults` still passes because the new fields default to `HandleSpec()` / `Interaction()`).

- [ ] **Step 7: VERIFY and commit**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `678 passed`.

```bash
git add shell/panel_spec.py shell/registry.py shell/config/diff.py tests/test_handle_requests.py
git commit -m "feat(registry): handle and interaction in panel requests; in-place panel-handle diff" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Pure handle rules (`shell/handle.py`)

**Files:**
- Create: `shell/handle.py`
- Test: `tests/test_handle.py` (new)

**Interfaces:**
- Consumes: `HandleSpec`, `Interaction` (Task 2); `Theme.handle_style`, `Theme.handle`, `Theme.handle_hover` (Task 1); `geometry.is_horizontal`, `geometry.to_canvas`, `geometry.input_rect`, `geometry.body_rect` (existing); `shell.theme.hex_to_rgba` (existing).
- Produces (all pure; `Rect = (x, y, width, height)` in panel-surface px):
  - `HIT_ALONG = 44`, `HIT_ACROSS = 14`, `HIT_PAD = 8`
  - `HandleLook(shape: str, size: int, weight: int, offset: int, rgba: RGBA, hover_rgba: RGBA)` (frozen; `shape` never `"auto"`)
  - `auto_shape(interaction: Interaction) -> str`
  - `resolve_handle(spec: HandleSpec, interaction: Interaction, theme: Theme) -> HandleLook`
  - `is_highlighted(prelight: bool, focused: bool, hovered: bool, extended: bool, interaction: Interaction) -> bool`
  - `handle_label(label: str, extended: bool, interaction: Interaction) -> str | None`
  - `morph(d: float, depth: int) -> float` (0..1)
  - `hit_size(thickness: int, size: int, length: int) -> tuple[int, int]` (along, across)
  - `clamp_offset(offset: int, length: int, hit_along: int) -> int`
  - `along_margins(offset: int) -> tuple[int, int]` (start, end)
  - `hit_inset(thickness: int, d: float, hit_across: int) -> int`
  - `shape_centre(edge, width, height, thickness, d) -> tuple[float, float]` (in the hit target's own px)
  - `hit_rect(edge, length, depth, d, thickness, radius, hit: tuple[int, int], offset) -> Rect`
  - `input_rects(edge, length, depth, d, thickness, radius, hover_zone, interaction, hit, offset) -> list[Rect]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_handle.py`:

```python
"""Pure handle rules (shell/handle.py): look, highlight, labels, hit target, input region."""

import pytest

from shell import geometry
from shell import handle as hd
from shell.panel_spec import HandleSpec, Interaction
from shell.theme import hex_to_rgba

ALL = Interaction()
EDGES = ["top", "bottom", "left", "right"]


@pytest.mark.parametrize(
    ("click", "hover", "drag", "shape"),
    [
        (True, True, True, "dots"),
        (True, False, True, "dots"),
        (False, True, True, "bar"),
        (False, False, True, "bar"),
        (True, True, False, "chevron"),
        (True, False, False, "chevron"),
        (False, True, False, "dots"),
        (False, False, False, "none"),
    ],
)
def test_auto_shape_follows_the_interactions(click, hover, drag, shape):
    assert hd.auto_shape(Interaction(click=click, hover=hover, drag=drag)) == shape


def test_the_theme_supplies_every_default(make_config):
    look = hd.resolve_handle(HandleSpec(), ALL, make_config().theme)
    assert look == hd.HandleLook(
        shape="dots",
        size=15,
        weight=3,
        offset=0,
        rgba=hex_to_rgba("#7b7f84"),
        hover_rgba=hex_to_rgba("#e6e8ea"),
    )


def test_panel_choices_win_over_the_theme(make_config):
    theme = make_config(theme={"handle_style": {"shape": "bar", "size": 30}}).theme
    look = hd.resolve_handle(
        HandleSpec(shape="chevron", weight=5, offset=-12, color="#ff000080"), ALL, theme
    )
    assert (look.shape, look.size, look.weight, look.offset) == ("chevron", 30, 5, -12)
    assert look.rgba == hex_to_rgba("#ff000080")
    assert look.hover_rgba == hex_to_rgba("#e6e8ea")  # theme handle_hover


def test_auto_from_the_panel_or_the_theme_follows_the_interactions(make_config):
    theme = make_config().theme  # handle_style.shape = "auto"
    click_only = Interaction(hover=False, drag=False)
    assert hd.resolve_handle(HandleSpec(), click_only, theme).shape == "chevron"
    assert hd.resolve_handle(HandleSpec(shape="auto"), click_only, theme).shape == "chevron"
    bar_theme = make_config(theme={"handle_style": {"shape": "bar"}}).theme
    assert hd.resolve_handle(HandleSpec(), click_only, bar_theme).shape == "bar"  # explicit


@pytest.mark.parametrize(
    ("prelight", "focused", "hovered", "extended", "interaction", "expected"),
    [
        (True, False, False, False, ALL, True),
        (False, True, False, True, ALL, True),
        (False, False, True, False, ALL, True),  # peeking
        (False, False, True, True, ALL, False),  # extended: only the handle itself lights up
        (False, False, False, False, ALL, False),
        (True, False, False, False, Interaction(click=False, drag=False), False),
        (False, False, True, False, Interaction(hover=False), False),
        (True, False, False, False, Interaction(click=False, hover=False), True),
    ],
)
def test_highlight(prelight, focused, hovered, extended, interaction, expected):
    assert hd.is_highlighted(prelight, focused, hovered, extended, interaction) is expected


@pytest.mark.parametrize(
    ("extended", "interaction", "label"),
    [
        (False, ALL, "Expand dock"),
        (True, ALL, "Collapse dock"),
        (False, Interaction(click=False), "Drag to expand dock"),
        (True, Interaction(click=False, hover=False), "Drag to collapse dock"),
        (False, Interaction(click=False, drag=False), None),
    ],
)
def test_handle_label(extended, interaction, label):
    assert hd.handle_label("dock", extended, interaction) == label


def test_morph_is_the_depth_fraction():
    assert [hd.morph(d, 64) for d in (-1, 0, 32, 64, 80)] == [0.0, 0.0, 0.5, 1.0, 1.0]
    assert hd.morph(5, 0) == 0.0


def test_hit_size_has_a_minimum_and_grows_with_the_shape():
    assert hd.hit_size(10, 15, 560) == (44, 14)  # today's handle button
    assert hd.hit_size(10, 40, 560) == (56, 14)  # 8 px past the shape on each side
    assert hd.hit_size(20, 15, 560) == (44, 24)  # thick frame: the band plus 4 px
    assert hd.hit_size(10, 40, 50) == (50, 14)  # never longer than the body


def test_offset_is_clamped_to_the_body():
    assert [hd.clamp_offset(o, 560, 44) for o in (300, -300, 10, 0)] == [258, -258, 10, 0]
    assert hd.clamp_offset(30, 44, 44) == 0
    assert hd.along_margins(12) == (24, 0)
    assert hd.along_margins(-5) == (0, 10)


def test_the_hit_target_rides_the_inner_edge():
    assert hd.hit_inset(10, 0, 14) == 0
    assert hd.hit_inset(10, 3.5, 14) == 0
    assert hd.hit_inset(10, 64, 14) == 60  # 10 + 64 - 14: ends at the body's inner edge


@pytest.mark.parametrize(
    ("edge", "size", "d", "centre"),
    [
        ("bottom", (44, 14), 0, (22, 9)),  # 5 px from the screen edge: mid-band
        ("bottom", (44, 14), 64, (22, 5)),  # 5 px inside the inner edge
        ("top", (44, 14), 0, (22, 5)),
        ("top", (44, 14), 64, (22, 9)),
        ("left", (14, 44), 0, (5, 22)),
        ("right", (14, 44), 0, (9, 22)),
        ("right", (14, 44), 2, (7, 22)),  # moves with the depth while the box is clamped
    ],
)
def test_shape_centre(edge, size, d, centre):
    assert hd.shape_centre(edge, *size, 10, d) == centre


@pytest.mark.parametrize(
    ("edge", "d", "offset", "rect"),
    [
        ("bottom", 0, 0, (272, 60, 44, 14)),
        ("bottom", 64, 0, (272, 0, 44, 14)),
        ("top", 0, 0, (272, 0, 44, 14)),
        ("left", 0, 0, (0, 272, 14, 44)),
        ("right", 0, 0, (60, 272, 14, 44)),
        ("bottom", 0, 300, (530, 60, 44, 14)),  # clamped to the body (258)
        ("left", 0, -20, (0, 252, 14, 44)),  # negative: towards the top
    ],
)
def test_hit_rect_in_surface_px(edge, d, offset, rect):
    assert hd.hit_rect(edge, 560, 64, d, 10, 14, (44, 14), offset) == rect


@pytest.mark.parametrize("edge", EDGES)
@pytest.mark.parametrize("d", [0, 8, 16, 40, 64])
def test_the_hover_input_region_contains_the_hit_target(edge, d):
    x, y, w, h = hd.hit_rect(edge, 560, 64, d, 10, 14, (44, 14), 0)
    ix, iy, iw, ih = geometry.input_rect(edge, 560, 64, d, 10, 14, 16)
    assert ix <= x and iy <= y and x + w <= ix + iw and y + h <= iy + ih


def rects(d, interaction, edge="bottom"):
    return hd.input_rects(edge, 560, 64, d, 10, 14, 16, interaction, (44, 14), 0)


def test_input_region_with_hover_is_unchanged():
    for d in (0, 30, 64):
        assert rects(d, ALL) == [geometry.input_rect("bottom", 560, 64, d, 10, 14, 16)]


def test_input_region_without_hover():
    click = Interaction(hover=False, drag=False)
    nothing = Interaction(click=False, hover=False, drag=False)
    body = geometry.body_rect("bottom", 560, 64, 64, 10, 14)
    assert rects(0, click) == [(272, 60, 44, 14)]  # collapsed: only the hit target
    assert rects(0, nothing) == []  # all off: the strip is click-through
    assert rects(64, nothing) == [body]  # the content still takes input
    assert rects(64, click) == [body, (272, 0, 44, 14)]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/py -m pytest -q tests/test_handle.py`
Expected: FAIL at collection with `ImportError: cannot import name 'handle' from 'shell'`.

- [ ] **Step 3: Create `shell/handle.py`**

```python
"""Panel handle (spec 15): what it looks like, where it sits and what takes input. Pure: no GTK.

The handle is drawn by the panel's own window (shell.edge_panel) with shell.handle_draw. Its
hit target is a separate, larger box than the drawn shape: at least HIT_ALONG x HIT_ACROSS px
(today's 44 x 14 handle button), growing with the shape size and the frame thickness.

Across the edge the shape is centred in the last `thickness` px of the panel's mass: in the
middle of the frame band while collapsed, `thickness / 2` px inside the body's inner edge
while extended, so it rides the inner edge and never leaves the mass (the border is drawn
outside the mass, so it never covers the handle).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from shell import geometry
from shell.config.models import Edge, Theme
from shell.panel_spec import HandleSpec, Interaction
from shell.theme import hex_to_rgba

RGBA = tuple[float, float, float, float]
Rect = tuple[int, int, int, int]  # x, y, width, height in panel-surface px

HIT_ALONG = 44  # minimum hit target along the edge
HIT_ACROSS = 14  # minimum hit target across the edge
HIT_PAD = 8  # the hit target reaches this far past the drawn shape along the edge


@dataclass(frozen=True)
class HandleLook:
    """A panel's handle with every theme default applied. `shape` is never "auto"."""

    shape: str  # "dots" | "bar" | "chevron" | "none"
    size: int
    weight: int
    offset: int
    rgba: RGBA
    hover_rgba: RGBA


def auto_shape(interaction: Interaction) -> str:
    """The shape "auto" stands for: dots while click and drag are both on (today's look), a
    bar for drag only, a chevron for click only, dots for hover only, nothing when all three
    are off (the handle would promise an interaction the panel does not answer)."""
    if interaction.click and interaction.drag:
        return "dots"
    if interaction.drag:
        return "bar"
    if interaction.click:
        return "chevron"
    return "dots" if interaction.hover else "none"


def resolve_handle(spec: HandleSpec, interaction: Interaction, theme: Theme) -> HandleLook:
    style = theme.handle_style
    shape = spec.shape or style.shape
    return HandleLook(
        shape=auto_shape(interaction) if shape == "auto" else shape,
        size=spec.size or style.size,
        weight=spec.weight or style.weight,
        offset=spec.offset,
        rgba=hex_to_rgba(spec.color or theme.handle),
        hover_rgba=hex_to_rgba(spec.hover_color or theme.handle_hover),
    )


def is_highlighted(
    prelight: bool, focused: bool, hovered: bool, extended: bool, interaction: Interaction
) -> bool:
    """Draw in the hover colour: pointer on (or keyboard focus in) the handle of a panel that
    answers a click or a drag, or the panel peeking (spec 4: the dots brighten on peek)."""
    if (interaction.click or interaction.drag) and (prelight or focused):
        return True
    return interaction.hover and hovered and not extended


def handle_label(label: str, extended: bool, interaction: Interaction) -> str | None:
    """Tooltip and accessible name; None when the handle answers neither click nor drag."""
    verb = "Collapse" if extended else "Expand"
    if interaction.click:
        return f"{verb} {label}"
    if interaction.drag:
        return f"Drag to {verb.lower()} {label}"
    return None


def morph(d: float, depth: int) -> float:
    """Chevron morph: 0 collapsed, 1 fully extended."""
    if depth <= 0:
        return 0.0
    return min(1.0, max(0.0, d / depth))


def hit_size(thickness: int, size: int, length: int) -> tuple[int, int]:
    """(along, across) px of the hit target; never longer than the body."""
    along = min(length, max(HIT_ALONG, size + 2 * HIT_PAD))
    return along, max(HIT_ACROSS, thickness + 4)


def clamp_offset(offset: int, length: int, hit_along: int) -> int:
    """Keep the hit target (and so the shape) inside the body."""
    room = max(0, (length - hit_along) // 2)
    return max(-room, min(room, offset))


def along_margins(offset: int) -> tuple[int, int]:
    """(start, end) margins that move a centred widget by `offset` px along the edge."""
    return max(0, 2 * offset), max(0, -2 * offset)


def hit_inset(thickness: int, d: float, hit_across: int) -> int:
    """Distance of the hit target from the screen edge: it rides the body's inner edge."""
    return max(0, int(thickness + d - hit_across))


def shape_centre(
    edge: Edge, width: float, height: float, thickness: int, d: float
) -> tuple[float, float]:
    """Centre of the drawn shape in the hit target's own coordinates (`width` x `height` is its
    allocation). Along the edge: the middle. Across: `thickness + d - thickness / 2` px from
    the screen edge."""
    across = height if geometry.is_horizontal(edge) else width
    local = thickness + d - thickness / 2 - hit_inset(thickness, d, round(across))
    if edge == "bottom":
        return width / 2, height - local
    if edge == "top":
        return width / 2, local
    if edge == "left":
        return local, height / 2
    return width - local, height / 2  # right


def hit_rect(
    edge: Edge,
    length: int,
    depth: int,
    d: float,
    thickness: int,
    radius: int,
    hit: tuple[int, int],
    offset: int,
) -> Rect:
    """The hit target in panel-surface px (the input region needs it when hover is off)."""
    along, across = length + 2 * radius, thickness + depth
    hit_along, hit_across = hit
    centre = radius + length / 2 + clamp_offset(offset, length, hit_along)
    u0, u1 = centre - hit_along / 2, centre + hit_along / 2
    inset = hit_inset(thickness, d, hit_across)
    v0, v1 = across - inset - hit_across, across - inset  # v: far side 0, screen edge `across`
    x1, y1 = geometry.to_canvas(edge, u0, v0, along, across)
    x2, y2 = geometry.to_canvas(edge, u1, v1, along, across)
    x, y = math.floor(min(x1, x2)), math.floor(min(y1, y2))
    return x, y, math.ceil(max(x1, x2)) - x, math.ceil(max(y1, y2)) - y


def input_rects(
    edge: Edge,
    length: int,
    depth: int,
    d: float,
    thickness: int,
    radius: int,
    hover_zone: int,
    interaction: Interaction,
    hit: tuple[int, int],
    offset: int,
) -> list[Rect]:
    """Where the panel takes input at depth `d`. With hover on: the body plus the invisible
    hover zone (as before; it contains the hit target). With hover off: the body while it is
    out, plus the hit target when click or drag is on; nothing at all while collapsed with
    every interaction off (the strip is click-through)."""
    if interaction.hover:
        return [geometry.input_rect(edge, length, depth, d, thickness, radius, hover_zone)]
    rects = []
    if d > 0:
        rects.append(geometry.body_rect(edge, length, depth, d, thickness, radius))
    if interaction.click or interaction.drag:
        rects.append(hit_rect(edge, length, depth, d, thickness, radius, hit, offset))
    return rects
```

- [ ] **Step 4: Run the tests**

Run: `scripts/py -m pytest -q tests/test_handle.py`
Expected: `64 passed`.

- [ ] **Step 5: VERIFY and commit**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `742 passed`.

```bash
git add shell/handle.py tests/test_handle.py
git commit -m "feat(handle): pure handle rules: theme resolution, auto shape, hit target, input region" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: `draw_handle` with morph, and a review sheet

**Files:**
- Create: `shell/handle_draw.py`
- Test: `tests/test_handle_draw.py` (new)

**Interfaces:**
- Consumes: `shell.theme.hex_to_rgba` (existing, only inside `render_sheet`).
- Produces (pure cairo):
  - `SHAPES = ("dots", "bar", "chevron", "none")`
  - `handle_matrix(edge, cx, cy) -> cairo.Matrix`: canonical (u along the edge, v towards where the panel opens) to device px around (cx, cy)
  - `snap(value: float, weight: float) -> float`
  - `draw_handle(cr, shape: str, size: int, weight: int, rgba: RGBA, morph: float, edge, cx: float, cy: float, max_across: float) -> None`
  - `render_sheet(path: str, thickness: int = 10, zoom: int = 6) -> tuple[int, int]`; `main(argv) -> int` (`python -m shell.handle_draw --sheet FILE.png`)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_handle_draw.py`:

```python
"""Headless pixel tests for draw_handle (shell/handle_draw.py)."""

import math

import cairo
import pytest

from shell import handle_draw as hdraw
from shell.theme import hex_to_rgba

W = H = 80
C = 40.5  # where an odd-weight shape centred near (40, 40) lands after snapping
WHITE = (1.0, 1.0, 1.0, 1.0)
EDGES = ["top", "bottom", "left", "right"]
FILLED, EMPTY = 128, 20


def render(shape, edge, morph=0.0, size=15, weight=3, rgba=WHITE, max_across=8):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(surface)
    hdraw.draw_handle(cr, shape, size, weight, rgba, morph, edge, 40, 40, max_across)
    surface.flush()
    return surface


def pixel(surface, x, y):
    """(b, g, r, a) bytes of the pixel containing device point (x, y)."""
    off = int(math.floor(y)) * surface.get_stride() + int(math.floor(x)) * 4
    return tuple(surface.get_data()[off : off + 4])


def alpha(surface, x, y):
    return pixel(surface, x, y)[3]


def at(edge, u, v):
    """Device point of canonical (u along, v towards the desktop) around the snapped centre."""
    return hdraw.handle_matrix(edge, C, C).transform_point(u, v)


def lit(surface):
    data, stride = surface.get_data(), surface.get_stride()
    return [(x, y) for y in range(H) for x in range(W) if data[y * stride + x * 4 + 3]]


@pytest.mark.parametrize("edge", EDGES)
def test_dots_are_three_crisp_dots_along_the_edge(edge):
    s = render("dots", edge)
    for u in (-6, 0, 6):  # 3 px dots, 3 px gaps: today's look
        assert alpha(s, *at(edge, u, 0)) == 255
    for u in (-3, 3, -9, 9):
        assert alpha(s, *at(edge, u, 0)) < EMPTY
    assert alpha(s, *at(edge, 0, 2)) < EMPTY and alpha(s, *at(edge, 0, -2)) < EMPTY


@pytest.mark.parametrize("edge", EDGES)
def test_bar_is_one_rounded_line(edge):
    s = render("bar", edge, size=20)
    for u in range(-8, 9):
        assert alpha(s, *at(edge, u, 0)) > FILLED
    assert alpha(s, *at(edge, -11, 0)) < EMPTY and alpha(s, *at(edge, 11, 0)) < EMPTY
    assert alpha(s, *at(edge, 0, 2)) < EMPTY and alpha(s, *at(edge, 0, -2)) < EMPTY


@pytest.mark.parametrize("edge", EDGES)
def test_chevron_points_where_the_panel_opens_then_morphs_back(edge):
    closed, flat, open_ = (render("chevron", edge, m) for m in (0.0, 0.5, 1.0))
    # height = min(15 / 2, 8 - 3) = 5: the tip is 2.5 px from the centre, the arm ends -2.5
    assert alpha(closed, *at(edge, 0, 2)) > FILLED  # tip towards the desktop
    assert alpha(closed, *at(edge, 0, -2)) < EMPTY
    assert alpha(closed, *at(edge, 6, -2.5)) > FILLED  # arm ends towards the screen edge
    assert alpha(flat, *at(edge, 0, 0)) > FILLED  # half way: a flat bar
    assert alpha(flat, *at(edge, 0, 2)) < EMPTY and alpha(flat, *at(edge, 0, -2)) < EMPTY
    assert alpha(open_, *at(edge, 0, -2)) > FILLED  # extended: points back to the edge
    assert alpha(open_, *at(edge, 0, 2)) < EMPTY


def test_the_tip_direction_matches_the_edge():
    # bottom panel collapsed: the chevron points up, into the screen
    s = render("chevron", "bottom", 0.0)
    assert alpha(s, C, C - 2) > FILLED and alpha(s, C, C + 2) < EMPTY
    s = render("chevron", "right", 0.0)
    assert alpha(s, C - 2, C) > FILLED and alpha(s, C + 2, C) < EMPTY


def test_colours_rest_hover_and_alpha():
    s = render("dots", "bottom", rgba=hex_to_rgba("#e6e8ea"))
    assert pixel(s, C, C) == (0xEA, 0xE8, 0xE6, 255)  # ARGB32 is BGRA in memory
    s = render("dots", "bottom", rgba=hex_to_rgba("#ffffff80"))
    assert pixel(s, C, C) == (128, 128, 128, 128)  # premultiplied


@pytest.mark.parametrize("shape", ["dots", "bar", "chevron"])
@pytest.mark.parametrize("edge", EDGES)
@pytest.mark.parametrize("morph", [0.0, 0.5, 1.0])
@pytest.mark.parametrize(("size", "weight"), [(4, 1), (15, 3), (40, 8)])
def test_the_shape_never_leaves_its_band(shape, edge, morph, size, weight):
    max_across = 8  # thickness 10 - 2
    s = render(shape, edge, morph, size, weight, max_across=max_across)
    w = min(weight, max_across)
    along_reach = max(size / 2, 1.5 * w if shape == "dots" else 0) + 1
    across_reach = max_across / 2 + 1
    pixels = lit(s)
    assert pixels
    for x, y in pixels:
        du, dv = (x + 0.5 - C, y + 0.5 - C)
        if edge in ("left", "right"):
            du, dv = dv, du
        assert abs(du) <= along_reach and abs(dv) <= across_reach, (x, y)


@pytest.mark.parametrize(
    ("shape", "rgba", "max_across"),
    [("none", WHITE, 8), ("dots", (1.0, 1.0, 1.0, 0.0), 8), ("bar", WHITE, 0)],
)
def test_nothing_is_drawn(shape, rgba, max_across):
    assert lit(render(shape, "bottom", rgba=rgba, max_across=max_across)) == []


def test_snap_keeps_odd_widths_on_pixel_centres():
    assert hdraw.snap(40, 3) == 40.5 and hdraw.snap(40.9, 3) == 40.5
    assert hdraw.snap(40.4, 2) == 40.0 and hdraw.snap(40.6, 4) == 41.0


def test_the_review_sheet(tmp_path, capsys):
    out = tmp_path / "handles.png"
    assert hdraw.main(["--sheet", str(out)]) == 0
    assert out.stat().st_size > 0
    assert "handles.png (3360x4032)" in capsys.readouterr().out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/py -m pytest -q tests/test_handle_draw.py`
Expected: FAIL at collection with `ImportError: cannot import name 'handle_draw' from 'shell'`.

- [ ] **Step 3: Create `shell/handle_draw.py`**

```python
"""Draw a panel handle with cairo (spec 15). Pure: no GTK.

Shapes are drawn in a canonical frame centred on the handle: u along the edge, v across it,
+v pointing where the panel opens (towards the desktop). `handle_matrix` rotates that frame
onto the real edge. The chevron morphs with the panel's depth (`morph` = d / depth): at 0 it
points where the panel opens, at 0.5 it is a flat bar, at 1 it points back to the screen edge.

`python -m shell.handle_draw --sheet FILE.png` renders every shape on every edge at several
morph values, enlarged, for a visual check without starting the shell.
"""

from __future__ import annotations

import math

import cairo

from shell.config.models import Edge

RGBA = tuple[float, float, float, float]
SHAPES = ("dots", "bar", "chevron", "none")


def handle_matrix(edge: Edge, cx: float, cy: float) -> cairo.Matrix:
    """Canonical (u, v) -> device px, centred on (cx, cy)."""
    if edge == "top":
        return cairo.Matrix(1, 0, 0, 1, cx, cy)
    if edge == "bottom":
        return cairo.Matrix(1, 0, 0, -1, cx, cy)
    if edge == "left":
        return cairo.Matrix(0, 1, 1, 0, cx, cy)
    return cairo.Matrix(0, 1, -1, 0, cx, cy)  # right


def snap(value: float, weight: float) -> float:
    """Pixel-align a centre so an odd-width shape covers whole pixels (crisp edges)."""
    if round(weight) % 2:
        return math.floor(value) + 0.5
    return float(round(value))


def draw_handle(
    cr: cairo.Context,
    shape: str,
    size: int,
    weight: int,
    rgba: RGBA,
    morph: float,
    edge: Edge,
    cx: float,
    cy: float,
    max_across: float,
) -> None:
    """Draw `shape` centred on (cx, cy): `size` px along the edge, `weight` px thick, never
    more than `max_across` px across (the caller passes thickness - 2, so the shape stays
    inside the frame band with 1 px to spare on each side)."""
    if shape == "none" or rgba[3] <= 0 or max_across <= 0:
        return
    w = max(1.0, min(float(weight), float(max_across)))
    cr.save()
    cr.transform(handle_matrix(edge, snap(cx, w), snap(cy, w)))
    cr.set_source_rgba(*rgba)
    if shape == "dots":
        r = w / 2
        reach = max(size / 2 - r, w)  # outer dot centres; the dots never overlap
        for u in (-reach, 0.0, reach):
            cr.new_sub_path()
            cr.arc(u, 0, r, 0, 2 * math.pi)
        cr.fill()
    else:
        half = max(0.0, (size - w) / 2)  # round caps add w / 2 at each end
        if shape == "bar":
            tip = 0.0
        else:  # chevron
            height = max(0.0, min(size / 2, max_across - w))  # arm ends to tip, across
            tip = height / 2 * (1 - 2 * min(1.0, max(0.0, morph)))
        cr.move_to(-half, -tip)
        cr.line_to(0, tip)
        cr.line_to(half, -tip)
        cr.set_line_width(w)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.stroke()
    cr.restore()


def render_sheet(path: str, thickness: int = 10, zoom: int = 6) -> tuple[int, int]:
    """Write a PNG: one row per shape and edge, columns at morph 0, 0.25, 0.5, 0.75, 1. Each
    cell is a `thickness` px frame band (frame colour) with the handle in the theme's rest
    colour, then the same in the hover colour; enlarged `zoom` times without smoothing."""
    from shell.theme import hex_to_rgba

    frame, rest, hover = (hex_to_rgba(c) for c in ("#0b0c0d", "#7b7f84", "#e6e8ea"))
    morphs = (0.0, 0.25, 0.5, 0.75, 1.0)
    cell, pad = 48, 4  # px per cell at 1x, and the white gap around it
    rows = [(s, e) for s in SHAPES[:3] for e in ("top", "bottom", "left", "right")]
    step = cell + 2 * pad
    width, height = step * len(morphs) * 2, step * len(rows)
    small = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(small)
    cr.set_source_rgb(1, 1, 1)
    cr.paint()
    for row, (shape, edge) in enumerate(rows):
        for col in range(len(morphs) * 2):
            x0, y0 = col * step + pad, row * step + pad
            cr.set_source_rgb(0.55, 0.6, 0.65)  # a mid-grey "desktop"
            cr.rectangle(x0, y0, cell, cell)
            cr.fill()
            colour = rest if col < len(morphs) else hover
            m = morphs[col % len(morphs)]
            # the frame band along the cell's own edge
            band = {
                "top": (x0, y0, cell, thickness),
                "bottom": (x0, y0 + cell - thickness, cell, thickness),
                "left": (x0, y0, thickness, cell),
                "right": (x0 + cell - thickness, y0, thickness, cell),
            }[edge]
            cr.set_source_rgba(*frame)
            cr.rectangle(*band)
            cr.fill()
            mid = thickness / 2
            cx, cy = {
                "top": (x0 + cell / 2, y0 + mid),
                "bottom": (x0 + cell / 2, y0 + cell - mid),
                "left": (x0 + mid, y0 + cell / 2),
                "right": (x0 + cell - mid, y0 + cell / 2),
            }[edge]
            draw_handle(cr, shape, 15, 3, colour, m, edge, cx, cy, thickness - 2)
    big = cairo.ImageSurface(cairo.FORMAT_ARGB32, width * zoom, height * zoom)
    out = cairo.Context(big)
    out.scale(zoom, zoom)
    out.set_source_surface(small, 0, 0)
    out.get_source().set_filter(cairo.FILTER_NEAREST)
    out.paint()
    big.write_to_png(path)
    return big.get_width(), big.get_height()


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Render every handle shape to a PNG sheet.")
    p.add_argument("--sheet", required=True, help="output PNG path")
    p.add_argument("--thickness", type=int, default=10, help="frame thickness (default 10)")
    args = p.parse_args(argv)
    w, h = render_sheet(args.sheet, args.thickness)
    print(f"wrote {args.sheet} ({w}x{h})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests**

Run: `scripts/py -m pytest -q tests/test_handle_draw.py`
Expected: `127 passed` (108 of them are the band check: 3 shapes x 4 edges x 3 morphs x 3 sizes).

- [ ] **Step 5: VERIFY and commit**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `869 passed`.

```bash
git add shell/handle_draw.py tests/test_handle_draw.py
git commit -m "feat(handle): draw_handle with a depth morph, and a PNG review sheet" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: GATE A (Phil): the shapes on a review sheet (no shell)

**Files:** none (the sheet is written to `/tmp`, never committed).

**Interfaces:**
- Consumes: `shell.handle_draw.main` (Task 4). No code changes.

This gate needs no running shell and no monitor choice: it is a PNG file. The implementer (a subagent may) runs Step 1; Phil looks at the picture.

- [ ] **Step 1: Render the sheet**

```bash
scripts/py -m shell.handle_draw --sheet /tmp/edge-handles.png
```
Expected: `wrote /tmp/edge-handles.png (3360x4032)`. Also render a thin frame: `scripts/py -m shell.handle_draw --sheet /tmp/edge-handles-t6.png --thickness 6`.

- [ ] **Step 2: GATE A (Phil)**

Open `/tmp/edge-handles.png` in any image viewer (for example `gwenview /tmp/edge-handles.png`). It is 6x enlarged without smoothing, so each visible square is one screen pixel. Rows, top to bottom: dots, bar, chevron, each on the top, bottom, left and right edge (the dark strip is a 10 px frame band, the grey is the desktop). Columns: morph 0, 0.25, 0.5, 0.75, 1 in the rest colour `#7b7f84`, then the same five in the hover colour `#e6e8ea`.

1. **Dots** look like today's three dots (3 px, 3 px gaps), crisp (whole pixels, no blurred half pixels), centred in the band, identical in every column (dots do not morph).
2. **Bar:** one rounded 15 px line, 3 px thick, crisp, centred in the band.
3. **Chevron morph:** column 1 (collapsed) points away from the screen edge into the desktop (top edge: down; bottom: up; left: right; right: left); column 3 is a flat bar; column 5 (extended) points back towards the screen edge; columns 2 and 4 are in between. Judge whether the fold reads as "open" / "close" (decision 4; the alternative is a rotation).
4. **Inside the band:** no shape touches the band's edges (1 px clear on both sides), also in `/tmp/edge-handles-t6.png` (6 px band: the shapes shrink across to fit, the dots get thinner).
5. **Defaults** (decision 2): size 15, weight 3 and the chevron's height look right at 1:1 (view the sheet at 1/6 zoom to see screen size). Say which numbers to change if not.
6. **Colours:** rest and hover are clearly different; the hover colour is the one the peeking and hovered handle will use.

**On failure:** a wrong direction or a fold that reads badly -> change `draw_handle`'s chevron branch (decision 4's rotation alternative) and the matching expectations in `test_chevron_points_where_the_panel_opens_then_morphs_back` / `test_the_tip_direction_matches_the_edge`, re-run Task 4's VERIFY, re-render. Blurry dots -> check `snap` with the failing weight and add a pixel test for it first. Other default numbers -> change them in `HandleStyle` and `config.default.toml` (Task 1) and in the tests that pin 15 / 3 (`tests/test_config_handle.py`, `tests/test_handle.py`). Record Phil's answers for Task 10.

---

### Task 6: The drawn handle in `EdgePanel`

`EdgePanel`'s handle Button keeps its role as the hit target; its child becomes a `Gtk.DrawingArea` drawing `draw_handle`. The look is resolved from the panel's `HandleSpec`, its `Interaction` and the theme; a restyle redraws it in place. The interaction flags themselves are wired in Task 7.

**Files:**
- Modify: `shell/edge_panel.py` (imports and module constants; `__init__`; `apply_theme`; `_sync_handle` + new `_restyle_handle`; the `# ---- layout` block's `_build_handle` becomes a `# ---- handle` block with `_hit`, `_size_handle`, `_on_handle_draw`; head of `_place_handle`)
- Modify: `shell/theme.py` (two CSS lines removed)
- Modify: `tests/test_theme.py` (`test_every_css_colour_parses_in_gtk3`)
- Test: `tests/test_edge_panel_handle.py` (new)

**Interfaces:**
- Consumes: `HandleSpec`, `Interaction`, `THEME_HANDLE`, `ALL_INTERACTIONS` (Task 2); `shell.handle` as `hd`: `resolve_handle`, `hit_size`, `hit_inset`, `clamp_offset`, `along_margins`, `shape_centre`, `is_highlighted`, `morph` (Task 3); `draw_handle` (Task 4).
- Produces:
  - `EdgePanel(spec, theme, monitor, index, scope, on_depth=None, handle: HandleSpec = THEME_HANDLE, interaction: Interaction = ALL_INTERACTIONS)`
  - attributes `_handle_spec`, `_interaction`, `_look: HandleLook` (set before `_d`), `_handle` (Button), `_handle_area` (DrawingArea)
  - `EdgePanel.apply_theme(theme)` re-resolves and redraws the handle (`_restyle_handle`)
  - `EdgePanel._restyle_handle()`: resolve -> `_size_handle()` -> `_sync_handle()` -> `_place_handle(_d)` -> `_last_rect = None` -> `_update_input_region(_d)`
  - `EdgePanel._hit() -> (along, across)`; `_size_handle()`; `_on_handle_draw(area, cr) -> False`
  - `HANDLE_DEPTH` / `HANDLE_LENGTH` are removed (no other module uses them)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_edge_panel_handle.py`:

```python
"""EdgePanel's drawn handle and interaction flags, called on stand-in objects (no window)."""

from types import SimpleNamespace

import cairo
import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

from gi.repository import Gtk  # noqa: E402

import shell.edge_panel as ep  # noqa: E402
from shell import handle as hd  # noqa: E402
from shell.panel_spec import HandleSpec, Interaction  # noqa: E402
from shell.theme import to_css  # noqa: E402

ALL = Interaction()


class FakeHandleWidget:
    """Records what EdgePanel sets on its handle Button."""

    def __init__(self, flags=Gtk.StateFlags.NORMAL):
        self.flags = flags
        self.set = {}
        self.name = None
        accessible = SimpleNamespace(set_name=lambda n: setattr(self, "name", n))
        self.get_accessible = lambda: accessible

    def __getattr__(self, attr):
        if attr.startswith("set_"):
            return lambda *values: self.set.__setitem__(attr[4:], values)
        raise AttributeError(attr)

    def get_state_flags(self):
        return self.flags


def stub(make_config, edge="bottom", interaction=ALL, handle=None, **extra):
    theme = make_config().theme
    handle = handle or HandleSpec()
    s = SimpleNamespace(
        spec=SimpleNamespace(edge=edge, length=560, depth=64, label="dock"),
        _theme=theme,
        _interaction=interaction,
        _handle_spec=handle,
        _look=hd.resolve_handle(handle, interaction, theme),
        _d=0.0,
        _hovered=False,
        _extended=False,
        _last_rect=None,
        _handle=FakeHandleWidget(),
        _handle_area=SimpleNamespace(draws=0),
        _content=SimpleNamespace(set_sensitive=lambda v: None),
        regions=[],
        calls=[],
    )
    s._handle_area.queue_draw = lambda: setattr(s._handle_area, "draws", s._handle_area.draws + 1)
    s.input_shape_combine_region = s.regions.append
    s._hit = lambda: ep.EdgePanel._hit(s)
    for key, value in extra.items():
        setattr(s, key, value)
    return s


def rects_of(region):
    out = []
    for i in range(region.num_rectangles()):
        r = region.get_rectangle(i)
        out.append((r.x, r.y, r.width, r.height))
    return out


# ---- in-place restyle -----------------------------------------------------------------


def test_apply_theme_restyles_the_handle(make_config):
    s = stub(make_config)
    s._restyle_handle = lambda: s.calls.append(("restyle", s._theme))
    theme = make_config(theme={"handle_style": {"shape": "bar"}}).theme
    ep.EdgePanel.apply_theme(s, theme)
    assert s.calls == [("restyle", theme)]


def test_restyle_resolves_then_resizes_relabels_replaces_and_reregions(make_config):
    s = stub(make_config, interaction=Interaction(drag=False), _last_rect=((1, 2, 3, 4),))
    s._theme = make_config(theme={"handle_style": {"size": 40}}).theme
    for name in ("_size_handle", "_sync_handle"):
        setattr(s, name, lambda name=name: s.calls.append(name))
    s._place_handle = lambda d: s.calls.append(("place", d))
    s._update_input_region = lambda d: s.calls.append(("region", d, s._last_rect))
    ep.EdgePanel._restyle_handle(s)
    assert (s._look.shape, s._look.size) == ("chevron", 40)  # auto: click only
    assert s.calls == ["_size_handle", "_sync_handle", ("place", 0.0), ("region", 0.0, None)]


@pytest.mark.parametrize(
    ("edge", "size"), [("bottom", (56, 14)), ("top", (56, 14)), ("left", (14, 56))]
)
def test_the_hit_target_size(make_config, edge, size):
    s = stub(make_config, edge=edge, handle=HandleSpec(size=40))
    ep.EdgePanel._size_handle(s)
    assert s._handle.set["size_request"] == size


@pytest.mark.parametrize(
    ("edge", "offset", "d", "expected"),
    [
        ("bottom", 30, 64.0, {"margin_start": (60,), "margin_end": (0,), "margin_bottom": (60,)}),
        ("top", 0, 0.0, {"margin_start": (0,), "margin_end": (0,), "margin_top": (0,)}),
        ("left", -20, 0.0, {"margin_top": (0,), "margin_bottom": (40,), "margin_start": (0,)}),
        ("right", 9999, 64.0, {"margin_top": (516,), "margin_bottom": (0,), "margin_end": (60,)}),
    ],
)
def test_place_handle_offsets_along_and_rides_across(make_config, edge, offset, d, expected):
    s = stub(make_config, edge=edge, handle=HandleSpec(offset=offset))
    ep.EdgePanel._place_handle(s, d)
    for key, value in expected.items():
        assert s._handle.set[key] == value, key
    assert s._handle_area.draws == 1


# ---- drawing ------------------------------------------------------------------------


def draw(s, w=44, h=14):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    area = SimpleNamespace(get_allocation=lambda: SimpleNamespace(width=w, height=h))
    assert ep.EdgePanel._on_handle_draw(s, area, cairo.Context(surface)) is False
    surface.flush()
    return surface


def centre_pixel(surface):
    # bottom edge, collapsed, T = 10: the middle dot covers pixel (22, 9) (snapped to 22.5, 9.5)
    off = 9 * surface.get_stride() + 22 * 4
    return tuple(surface.get_data()[off : off + 4])


def test_the_handle_draws_the_rest_colour(make_config):
    assert centre_pixel(draw(stub(make_config))) == (0x84, 0x7F, 0x7B, 255)  # #7b7f84


def test_pointer_on_the_handle_draws_the_hover_colour(make_config):
    s = stub(make_config)
    s._handle.flags = Gtk.StateFlags.PRELIGHT
    assert centre_pixel(draw(s)) == (0xEA, 0xE8, 0xE6, 255)  # #e6e8ea


def test_a_peek_draws_the_hover_colour(make_config):
    s = stub(make_config, _hovered=True)
    assert centre_pixel(draw(s)) == (0xEA, 0xE8, 0xE6, 255)


def test_a_draw_error_is_logged_not_raised(make_config, caplog):
    s = stub(make_config)
    s._look = None
    draw(s)
    assert "drawing the handle of dock failed" in caplog.text


def test_the_handle_is_a_button_drawing_with_cairo(make_config):
    if not Gtk.init_check()[0]:
        pytest.skip("no display")
    s = stub(make_config)
    for name in ("_on_clicked", "_on_press", "_on_motion", "_on_release", "_on_handle_draw"):
        setattr(s, name, lambda *a: False)
    button = ep.EdgePanel._build_handle(s)
    assert isinstance(button, Gtk.Button) and button.get_name() == "handle"
    assert isinstance(button.get_child(), Gtk.DrawingArea)
    assert s._handle_area is button.get_child()


def test_css_no_longer_styles_handle_dots(make_config):
    css = to_css(make_config().theme, "mon-x")
    assert "handle-dot" not in css
    assert ".mon-x #handle { min-width: 0; min-height: 0; padding: 0; }" in css
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/py -m pytest -q tests/test_edge_panel_handle.py`
Expected: FAIL (for example `AttributeError: type object 'EdgePanel' has no attribute '_hit'`, `_restyle_handle`, `_on_handle_draw`; the CSS test fails on `handle-dot`).

- [ ] **Step 3: Imports and constants in `shell/edge_panel.py`**

Add `import logging` above `import math`. Replace

```python
from shell import geometry, panel_state
from shell.anim import Tween
from shell.config.models import Theme
from shell.gdk_util import monitor_index
from shell.panel_layout import content_length
from shell.panel_spec import PanelGeometry

HANDLE_DEPTH = 14  # handle size across the depth axis
HANDLE_LENGTH = 44  # handle size along the edge
```

by

```python
from shell import geometry, panel_state
from shell import handle as hd
from shell.anim import Tween
from shell.config.models import Theme
from shell.gdk_util import monitor_index
from shell.handle_draw import draw_handle
from shell.panel_layout import content_length
from shell.panel_spec import (
    ALL_INTERACTIONS,
    THEME_HANDLE,
    HandleSpec,
    Interaction,
    PanelGeometry,
)

log = logging.getLogger(__name__)
```

- [ ] **Step 4: `__init__`**

Replace the end of the signature and the docstring

```python
        on_depth: Callable[[float], None] | None = None,
    ):
        """`spec` is resolved by shell.panel_layout (exact pos and length in px); `on_depth(d)`
        is called on every animation frame with the current depth (MonitorShell forwards it to
        the canvas)."""
```

by

```python
        on_depth: Callable[[float], None] | None = None,
        handle: HandleSpec = THEME_HANDLE,
        interaction: Interaction = ALL_INTERACTIONS,
    ):
        """`spec` is resolved by shell.panel_layout (exact pos and length in px); `on_depth(d)`
        is called on every animation frame with the current depth (MonitorShell forwards it to
        the canvas). `handle` and `interaction` come from the PanelRequest (spec 15); both can
        change later in place (set_handle)."""
```

After `self._on_depth = on_depth` insert (these must come before `self._d = 0.0`: `do_size_allocate` reads them once `_d` exists)

```python
        self._handle_spec = handle
        self._interaction = interaction
        self._look = hd.resolve_handle(handle, interaction, theme)
```

After `self._handle = self._build_handle()` insert `self._size_handle()`.

- [ ] **Step 5: `apply_theme`, `_sync_handle`, `_restyle_handle`**

Replace

```python
    def apply_theme(self, theme: Theme) -> None:
        """Colors only (CSS and the canvas repaint them); geometry changes rebuild the panel."""
        self._theme = theme
```

by

```python
    def apply_theme(self, theme: Theme) -> None:
        """A restyle: colours and the theme's handle style are redrawn in place (CSS and the
        canvas repaint the rest); geometry changes rebuild the panel."""
        self._theme = theme
        self._restyle_handle()
```

Replace `_sync_handle` by

```python
    def _sync_handle(self) -> None:
        self._content.set_sensitive(self._extended)
        name = ("Collapse " if self._extended else "Expand ") + self.spec.label
        self._handle.set_tooltip_text(name)
        self._handle.get_accessible().set_name(name)
        self._handle_area.queue_draw()  # the peek highlight may have changed

    def _restyle_handle(self) -> None:
        self._look = hd.resolve_handle(self._handle_spec, self._interaction, self._theme)
        self._size_handle()
        self._sync_handle()
        self._place_handle(self._d)
        self._last_rect = None
        self._update_input_region(self._d)
```

- [ ] **Step 6: The handle block**

Replace the whole `# ---- layout ---` comment line and `_build_handle` (from `    # ---- layout ---` down to its `        return handle`) by

```python
    # ---- handle ----------------------------------------------------------------
    def _build_handle(self) -> Button:
        """The hit target: a Button (click, keyboard, accessible name) whose child draws the
        shape with cairo. Sized by _size_handle."""
        area = Gtk.DrawingArea()
        area.connect("draw", self._on_handle_draw)
        self._handle_area = area
        handle = Button(name="handle", child=area, on_clicked=self._on_clicked)
        handle.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        handle.connect("button-press-event", self._on_press)
        handle.connect("motion-notify-event", self._on_motion)
        handle.connect("button-release-event", self._on_release)
        handle.connect("state-flags-changed", lambda *_args: area.queue_draw())  # hover, focus
        return handle

    def _hit(self) -> tuple[int, int]:
        return hd.hit_size(self._theme.thickness, self._look.size, self.spec.length)

    def _size_handle(self) -> None:
        along, across = self._hit()
        if geometry.is_horizontal(self.spec.edge):
            self._handle.set_size_request(along, across)
        else:
            self._handle.set_size_request(across, along)

    def _on_handle_draw(self, area, cr) -> bool:
        try:
            look, t = self._look, self._theme
            alloc = area.get_allocation()
            cx, cy = hd.shape_centre(
                self.spec.edge, alloc.width, alloc.height, t.thickness, self._d
            )
            flags = self._handle.get_state_flags()
            lit = hd.is_highlighted(
                bool(flags & Gtk.StateFlags.PRELIGHT),
                bool(flags & Gtk.StateFlags.FOCUSED),
                self._hovered,
                self._extended,
                self._interaction,
            )
            draw_handle(
                cr,
                look.shape,
                look.size,
                look.weight,
                look.hover_rgba if lit else look.rgba,
                hd.morph(self._d, self.spec.depth),
                self.spec.edge,
                cx,
                cy,
                t.thickness - 2,
            )
        except Exception:  # never let a draw error escape into GTK's main loop
            log.exception("drawing the handle of %s failed", self.spec.label)
        return False
```

- [ ] **Step 7: `_place_handle`**

Replace its first three lines

```python
    def _place_handle(self, d: float) -> None:
        inset = max(0, int(self._theme.thickness + d - HANDLE_DEPTH))  # rides the inner edge
        h, edge = self._handle, self.spec.edge
```

by

```python
    def _place_handle(self, d: float) -> None:
        along, across = self._hit()
        inset = hd.hit_inset(self._theme.thickness, d, across)  # rides the inner edge
        offset = hd.clamp_offset(self._look.offset, self.spec.length, along)
        before, after = hd.along_margins(offset)
        h, edge = self._handle, self.spec.edge
        if geometry.is_horizontal(edge):
            h.set_margin_start(before)
            h.set_margin_end(after)
        else:
            h.set_margin_top(before)
            h.set_margin_bottom(after)
        self._handle_area.queue_draw()  # the shape moves inside the box while it is clamped
```

The `if edge == "bottom": … else: …` alignment and inset block below it stays as it is (the centred axis plus the start/end margins moves the handle by `offset`; the inset margin on the other axis is today's).

- [ ] **Step 8: CSS in `shell/theme.py`**

Delete the two lines

```
{s} .handle-dot {{ min-width: 3px; min-height: 3px; border-radius: 50%; background-color: {c["handle"]}; }}
{s} #handle:hover .handle-dot, {s} #handle:focus .handle-dot {{ background-color: {c["handle_hover"]}; }}
```

and keep `{s} #handle {{ min-width: 0; min-height: 0; padding: 0; }}`. In `tests/test_theme.py`, `test_every_css_colour_parses_in_gtk3`, replace

```python
    theme = make_config(theme={"accent": "#8fd3b680", "handle": "#7b7f84ff"}).theme
    values = re.findall(r"(?:color|background-color): ([^;]+);", to_css(theme, "mon-x"))
    assert len(values) >= 6
```

by

```python
    theme = make_config(theme={"accent": "#8fd3b680", "text": "#e6e8eaff"}).theme
    values = re.findall(r"(?:color|background-color): ([^;]+);", to_css(theme, "mon-x"))
    assert len(values) >= 5  # the handle colours are drawn with cairo, not CSS
```

- [ ] **Step 9: Run the tests**

Run: `scripts/py -m pytest -q tests/test_edge_panel_handle.py tests/test_edge_panel_drag.py tests/test_monitor_shell.py tests/test_theme.py`
Expected: all pass (`tests/test_edge_panel_handle.py` has 15).

- [ ] **Step 10: VERIFY and commit**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `884 passed`.

```bash
git add shell/edge_panel.py shell/theme.py tests/test_theme.py tests/test_edge_panel_handle.py
git commit -m "feat(panel): draw the handle with cairo in the panel window; restyle in place" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Interaction flags, `set_handle` and the input region

**Files:**
- Modify: `shell/edge_panel.py` (`_last_rect` annotation; `set_handle` after `apply_theme`; `_on_enter`; `_sync_handle`; `_on_clicked`; `_update_input_region`; `_on_press`)
- Test: `tests/test_edge_panel_handle.py` (append)

**Interfaces:**
- Consumes: `hd.handle_label`, `hd.input_rects` (Task 3); Task 6's `_restyle_handle`, `_hit`, `_handle_area`.
- Produces:
  - `EdgePanel.set_handle(handle: HandleSpec, interaction: Interaction) -> None` (in place: restyle, then drop a peek that hover no longer allows)
  - hover off: `_on_enter` never peeks; drag off: `_on_press` never records a press; click off: `_on_clicked` never toggles, the Button is not focusable, the tooltip/accessible name follow `handle_label`
  - `_update_input_region(d)` applies `hd.input_rects(...)` as one `cairo.Region`; `_last_rect` is the tuple of rects

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_edge_panel_handle.py`:

```python


# ---- input region -------------------------------------------------------------------


def test_with_hover_the_input_region_is_unchanged(make_config):
    s = stub(make_config)
    ep.EdgePanel._update_input_region(s, 0.0)
    assert [rects_of(r) for r in s.regions] == [[(14, 48, 560, 26)]]  # body + hover zone
    ep.EdgePanel._update_input_region(s, 0.0)
    assert len(s.regions) == 1  # unchanged: not re-applied


def test_without_hover_only_the_hit_target_takes_input(make_config):
    s = stub(make_config, interaction=Interaction(hover=False))
    ep.EdgePanel._update_input_region(s, 0.0)
    assert rects_of(s.regions[-1]) == [(272, 60, 44, 14)]


def test_with_every_interaction_off_a_collapsed_panel_is_click_through(make_config):
    s = stub(make_config, interaction=Interaction(click=False, hover=False, drag=False))
    ep.EdgePanel._update_input_region(s, 0.0)
    assert rects_of(s.regions[-1]) == []
    ep.EdgePanel._update_input_region(s, 64.0)
    assert rects_of(s.regions[-1]) == [(14, 0, 560, 74)]  # the content still takes input


# ---- interaction flags --------------------------------------------------------------


def test_a_press_starts_no_drag_without_drag(make_config):
    s = stub(make_config, interaction=Interaction(drag=False), _press=None)
    event = SimpleNamespace(button=1, x_root=5.0, y_root=5.0)
    assert ep.EdgePanel._on_press(s, None, event) is False
    assert s._press is None
    s._interaction = ALL
    s._dragging = s._suppress_click = False
    ep.EdgePanel._on_press(s, None, event)
    assert s._press == (5.0, 5.0)


def test_a_click_toggles_only_with_click(make_config):
    toggles = []
    s = stub(make_config, interaction=Interaction(click=False), _suppress_click=False)
    s.toggle = lambda: toggles.append(1)
    ep.EdgePanel._on_clicked(s)
    assert toggles == []
    s._interaction = ALL
    ep.EdgePanel._on_clicked(s)
    assert toggles == [1]


def test_entering_does_not_peek_without_hover(make_config):
    s = stub(make_config, interaction=Interaction(hover=False), _dragging=False)
    s._retarget = lambda: s.calls.append("retarget")
    ep.EdgePanel._on_enter(s)
    assert s._hovered is False and s.calls == []
    s._interaction = ALL
    ep.EdgePanel._on_enter(s)
    assert s._hovered is True and s.calls == ["retarget"]


# ---- in-place updates ---------------------------------------------------------------


def test_set_handle_updates_in_place_and_drops_a_peek(make_config):
    s = stub(make_config, _hovered=True)
    s._restyle_handle = lambda: s.calls.append("restyle")
    s._retarget = lambda: s.calls.append(("retarget", s._hovered))
    new = (HandleSpec(shape="bar"), Interaction(hover=False))
    ep.EdgePanel.set_handle(s, *new)
    assert (s._handle_spec, s._interaction) == new
    assert s.calls == ["restyle", ("retarget", False)]


def test_set_handle_keeps_a_peek_that_hover_still_allows(make_config):
    s = stub(make_config, _hovered=True)
    s._restyle_handle = lambda: s.calls.append("restyle")
    s._retarget = lambda: s.calls.append("retarget")
    ep.EdgePanel.set_handle(s, HandleSpec(shape="bar"), ALL)
    assert s.calls == ["restyle"] and s._hovered is True


@pytest.mark.parametrize(
    ("interaction", "tooltip", "name", "focus"),
    [
        (ALL, "Expand dock", "Expand dock", True),
        (Interaction(click=False), "Drag to expand dock", "Drag to expand dock", False),
        (Interaction(click=False, drag=False), None, "dock handle", False),
    ],
)
def test_labels_and_keyboard_follow_click(make_config, interaction, tooltip, name, focus):
    s = stub(make_config, interaction=interaction)
    ep.EdgePanel._sync_handle(s)
    assert s._handle.set["tooltip_text"] == (tooltip,)
    assert s._handle.name == name
    assert s._handle.set["can_focus"] == (focus,)
    assert s._handle_area.draws == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/py -m pytest -q tests/test_edge_panel_handle.py`
Expected: 10 of the 11 new tests FAIL (for example `AttributeError: type object 'EdgePanel' has no attribute 'set_handle'`; the hover-off region tests get the old single hover rect; the label tests find no `can_focus`). `test_with_hover_the_input_region_is_unchanged` already passes: it pins the behaviour that must not change.

- [ ] **Step 3: Implement in `shell/edge_panel.py`**

1. Change `self._last_rect: tuple[int, int, int, int] | None = None` to `self._last_rect: tuple[tuple[int, int, int, int], ...] | None = None`.
2. Directly after `apply_theme` add

```python
    def set_handle(self, handle: HandleSpec, interaction: Interaction) -> None:
        """A reload changed this panel's handle or interactions: update in place, no rebuild."""
        self._handle_spec, self._interaction = handle, interaction
        self._restyle_handle()
        if self._hovered and not interaction.hover:
            self._hovered = False
            self._retarget()  # drop a peek that hover no longer allows
```

3. In `_on_enter`, after the `if self._dragging: … return` lines add

```python
        if not self._interaction.hover:  # no peek; the handle still lights up on its own
            return
```

4. Replace `_sync_handle` by

```python
    def _sync_handle(self) -> None:
        self._content.set_sensitive(self._extended)
        label = hd.handle_label(self.spec.label, self._extended, self._interaction)
        self._handle.set_tooltip_text(label)  # None: no tooltip
        self._handle.get_accessible().set_name(label or f"{self.spec.label} handle")
        self._handle.set_can_focus(self._interaction.click)  # keyboard follows click
        self._handle_area.queue_draw()  # the peek highlight may have changed
```

5. In `_on_clicked`, insert before `self.toggle()`

```python
        if not self._interaction.click:
            return
```

6. Replace `_update_input_region` by

```python
    def _update_input_region(self, d: float) -> None:
        # The body (plus an invisible hover zone while collapsed, or only the handle's hit
        # target when hover is off) takes input: shell.handle.input_rects.
        t, s = self._theme, self.spec
        rects = tuple(
            hd.input_rects(
                s.edge,
                s.length,
                s.depth,
                d,
                t.thickness,
                t.radius,
                t.hover_zone,
                self._interaction,
                self._hit(),
                self._look.offset,
            )
        )
        if rects == self._last_rect:
            return
        self._last_rect = rects
        self.input_shape_combine_region(cairo.Region([cairo.RectangleInt(*r) for r in rects]))
```

7. In `_on_press`, replace

```python
        if event.button != 1:
            return False
```

by

```python
        if event.button != 1 or not self._interaction.drag:
            return False  # without drag a press is only ever a click
```

(`_on_release` and `_on_motion` need no change: without a recorded press `_on_motion` returns at once and `_finish_drag` only clears.)

- [ ] **Step 4: Run the tests**

Run: `scripts/py -m pytest -q tests/test_edge_panel_handle.py tests/test_edge_panel_drag.py tests/test_monitor_shell.py`
Expected: all pass (`tests/test_edge_panel_handle.py` has 26).

- [ ] **Step 5: VERIFY and commit**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `895 passed`.

```bash
git add shell/edge_panel.py tests/test_edge_panel_handle.py
git commit -m "feat(panel): per-panel click, hover and drag toggles; input region follows them" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: `MonitorShell` passes the handle and updates it in place

**Files:**
- Modify: `shell/monitors.py` (import; `__init__` list `_handles`; `_sync_panels`; `_new_panel`; `close`)
- Modify: `tests/test_monitor_shell.py` (`FakeWindow.handles` + `set_handle`; `bare_shell._handles`; 5 tests appended)

**Interfaces:**
- Consumes: `PanelRequest.handle` / `.interaction` (Task 2), `EdgePanel(..., handle=, interaction=)` and `EdgePanel.set_handle` (Tasks 6-7), `Change("panel-handle", …)` (Task 2).
- Produces: `MonitorShell._handles: list[tuple[HandleSpec, Interaction] | None]` parallel to `panels` / `_resolved`. A panel is built with `handle=req.handle, interaction=req.interaction`; a live panel whose geometry did not change gets `set_handle(handle, interaction)` only when that pair changed, before `set_state`; never a rebuild or a re-raise.

- [ ] **Step 1: Update the fakes and write the failing tests**

In `tests/test_monitor_shell.py`:

1. In `FakeWindow.__init__` add `self.handles = []` after `self.states = []`, and after `set_state` add

```python
    def set_handle(self, handle, interaction):
        self.handles.append((handle, interaction))
```

2. In `bare_shell`, after `shell._resolved = [None] * len(shell.panels)` add `shell._handles = [None] * len(shell.panels)`.
3. Append at the end of the file:

```python


# ---- handle and interaction (spec 15): in place, never a rebuild ---------------------


def test_panels_get_their_handle_and_interaction(build):
    from shell.panel_spec import HandleSpec, Interaction

    shell, _, _ = build(
        edge(
            {"widget": "dock", "handle": {"shape": "bar", "offset": 20}},
            {"widget": "clock", "interaction": {"hover": False}},
        )
    )
    dock, clock = shell.panels
    assert dock.kwargs["handle"] == HandleSpec(shape="bar", offset=20)
    assert dock.kwargs["interaction"] == Interaction()
    assert clock.kwargs["handle"] == HandleSpec()
    assert clock.kwargs["interaction"] == Interaction(hover=False)


def test_a_handle_change_updates_the_live_panel(build, make_config):
    from shell.panel_spec import HandleSpec, Interaction

    shell, _, timers = build(edge({"widget": "dock"}, {"widget": "clock"}))
    dock, clock = shell.panels
    before = len(timers)
    new = make_config(
        monitors=edge(
            {"widget": "dock", "handle": {"shape": "chevron"}, "interaction": {"drag": False}},
            {"widget": "clock"},
        )
    )
    shell.apply(new, [Change("panel-handle", "HDMI-A-1", 0)])
    assert shell.panels == [dock, clock] and not dock.destroyed
    assert dock.handles == [(HandleSpec(shape="chevron"), Interaction(drag=False))]
    assert clock.handles == []  # unchanged panels are not touched
    assert len(timers) == before  # no rebuild, so no re-raise
    shell.apply(new, [])  # the same config again: nothing to do
    assert len(dock.handles) == 1


def test_a_handle_and_state_change_does_both_in_place(build, make_config):
    shell, _, _ = build(edge({"widget": "dock"}))
    dock = shell.panels[0]
    new = make_config(
        monitors=edge({"widget": "dock", "state": "collapsed", "handle": {"size": 30}})
    )
    shell.apply(new, [Change("panel-handle", "HDMI-A-1", 0)])
    assert shell.panels[0] is dock and dock.states == ["collapsed"]
    assert dock.handles[0][0].size == 30


def test_a_rebuilt_panel_gets_the_new_handle(build, make_config):
    shell, _, _ = build(edge({"widget": "dock"}))
    old = shell.panels[0]
    shell.apply(
        make_config(monitors=edge({"widget": "dock", "depth": 80, "handle": {"shape": "bar"}})),
        [Change("panel-rebuild", "HDMI-A-1", 0)],
    )
    new = shell.panels[0]
    assert old.destroyed and new is not old
    assert new.kwargs["handle"].shape == "bar" and new.handles == []


def test_a_theme_handle_style_change_restyles_in_place(build, make_config):
    shell, _, _ = build(edge({"widget": "dock"}))
    dock = shell.panels[0]
    new = make_config(theme={"handle_style": {"shape": "bar"}}, monitors=edge({"widget": "dock"}))
    shell.apply(new, [Change("restyle", "HDMI-A-1")])
    assert shell.panels[0] is dock and not dock.destroyed
    assert dock.themes[0].handle_style.shape == "bar" and dock.handles == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/py -m pytest -q tests/test_monitor_shell.py`
Expected: the new tests FAIL (`KeyError: 'handle'` in `dock.kwargs`; `dock.handles == []` after the handle change); the existing ones pass.

- [ ] **Step 3: Implement in `shell/monitors.py`**

1. Change the import to `from shell.panel_spec import HandleSpec, Interaction, PanelGeometry, PanelRequest`.
2. In `__init__`, after `self._resolved: list[PanelGeometry | None] = []` add

```python
        # Each index's (handle, interaction) as last given to its panel (changed in place).
        self._handles: list[tuple[HandleSpec, Interaction] | None] = []
```

3. In `_sync_panels`, replace

```python
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
```

by

```python
            self.panels.pop()
            self._resolved.pop()
            self._handles.pop()
        for i, geo in enumerate(wanted):
            if i == len(self.panels):
                self.panels.append(None)
                self._resolved.append(None)
                self._handles.append(None)
            old, panel = self._resolved[i], self.panels[i]
            req = self._requests[i]
            handles = (req.handle, req.interaction)
            if geo is None:
                if panel is not None:
                    self._destroy_panel(i)
            elif panel is None or old is None or replace(old, state=geo.state) != geo:
                if panel is not None:
                    self._destroy_panel(i)
                self.panels[i] = self._new_panel(i, geo, theme, raise_later=not startup)
            else:  # same geometry: the live panel changes in place (spec 15: never a rebuild)
                if self._handles[i] != handles:
                    panel.set_handle(*handles)
                if old.state != geo.state:
                    panel.set_state(geo.state)
            self._resolved[i] = geo
            self._handles[i] = handles
```

4. In `_new_panel`, after `self.canvas.add_panel(key, PanelShape(geo.edge, geo.pos, geo.length, geo.depth))` add `req = self._requests[index]`, and pass two more keyword arguments after `on_depth=lambda d, k=key: self.canvas.set_depth(k, d),`:

```python
                handle=req.handle,
                interaction=req.interaction,
```

5. In `close`, after `self._resolved.clear()` add `self._handles.clear()`.

- [ ] **Step 4: Run the tests**

Run: `scripts/py -m pytest -q tests/test_monitor_shell.py tests/test_app_sync.py`
Expected: all pass.

- [ ] **Step 5: VERIFY and commit**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `900 passed`.

```bash
git add shell/monitors.py tests/test_monitor_shell.py
git commit -m "feat(monitors): pass handle and interaction to panels; update them in place on reload" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: GATE B (Phil, HDMI-A-1): handles live

**Files:**
- Create: `examples/handles-test.toml`

**Interfaces:**
- Consumes: Tasks 1-8; no code changes.

- [ ] **Step 1: Create the example config**

```toml
# Gate B (handle plan): handle shapes, colours, offsets and per-interaction toggles, on
# HDMI-A-1 only (DP-1 is left alone).
#   cp examples/handles-test.toml /tmp/edge-handles.toml
#   scripts/py main.py --config /tmp/edge-handles.toml -v      (edit the copy while it runs)
[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]    # 0: dock, bottom centre: today's dots, every interaction
widget = "dock"

[[monitors.HDMI-A-1.panels]]    # 1: top left, click only: "auto" draws a chevron
widget = "clock"
align = "start"
interaction.hover = false
interaction.drag = false

[[monitors.HDMI-A-1.panels]]    # 2: top right, hover + drag (no click): "auto" draws a bar
widget = "clock"
align = "end"
state = "collapsed"
interaction.click = false
handle.size = 28
handle.color = "#8fd3b6"
handle.hover_color = "#ffffff"

[[monitors.HDMI-A-1.panels]]    # 3: right edge: an explicit chevron, thinner, 100 px up
widget = "system_bar"
handle.shape = "chevron"
handle.size = 24
handle.weight = 2
handle.offset = -100

[[monitors.HDMI-A-1.panels]]    # 4: bottom left, every interaction off: only `state` opens it
widget = "clock"
edge = "bottom"
align = "start"
state = "collapsed"
interaction.click = false
interaction.hover = false
interaction.drag = false
```

Check it loads, lays out without warnings and resolves the expected handles (headless; imports the widgets, creates no window):

`scripts/py -c "import widgets; from pathlib import Path; from shell.config.loader import load_config; from shell.registry import requests_for; from shell.panel_layout import layout_monitor; from shell.handle import resolve_handle; c = load_config(Path('examples/handles-test.toml'), required=True); t = c.theme_for('HDMI-A-1'); R = requests_for(c, 'HDMI-A-1'); L = layout_monitor(R, 1920, 1080, 10, 14, c.layout_for('HDMI-A-1').gap); print([(p.edge, p.pos, p.length) for p in L.panels], L.warnings); print([(lk.shape, lk.size, lk.weight, lk.offset) for lk in (resolve_handle(r.handle, r.interaction, t) for r in R)])"`

Expected:
```
[('bottom', 680, 560), ('top', 38, 168), ('top', 1714, 168), ('right', 600, 300), ('bottom', 38, 168)] []
[('dots', 15, 3, 0), ('chevron', 15, 3, 0), ('bar', 28, 3, 0), ('chevron', 24, 2, -100), ('none', 15, 3, 0)]
```

- [ ] **Step 2: Commit**

```bash
git add examples/handles-test.toml
git commit -m "docs(examples): handle gate config with shapes, colours, offsets and toggles" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 3: GATE B (Phil)**

```bash
cp examples/handles-test.toml /tmp/edge-handles.toml
scripts/py main.py --config /tmp/edge-handles.toml -v
```
Edit `/tmp/edge-handles.toml` while it runs; each save applies within about a second. Ctrl+C quits.

1. **Dock (defaults, regression):** three dots at the dock's inner (top) edge while extended, in the middle of the frame band once collapsed (2 px nearer the screen edge than before, decision 5), crisp. Pointer on the handle: the dots turn light; hover peek, click toggle and drag (50 % snap) work exactly as before; the tooltip says "Collapse dock" / "Expand dock".
2. **Top-left clock (click only, chevron):** extended, the chevron near the clock's lower edge points up (back to the screen edge). Click it: the clock collapses and the chevron folds smoothly through a flat bar to point down while it rides into the band. Hover the strip below the collapsed clock: no peek. Press on the handle, move 30 px down, release: no drag (the clock only toggles if the release lands on the handle).
3. **Top-right clock (hover + drag, mint bar):** collapsed: a 28 px mint bar in the band. Hover the strip: it peeks and the bar turns white. Click the bar: nothing happens. Drag down from the bar: the clock follows and snaps open past half depth. Tooltip "Drag to expand clock" (after it opened: "Drag to collapse clock").
4. **System bar (explicit chevron, offset -100):** a thinner 24 px chevron, 100 px above the bar's middle (about y = 650 instead of 750), pointing right (to the screen edge) while extended and left once collapsed. The clickable area reaches about 10 px past each end of the chevron (hit target 44 px). Set `handle.offset = 9999` and save: the chevron moves to the bottom end of the bar's body and stops there (clamped), never past the join. Undo.
5. **Bottom-left clock (all off):** nothing is drawn in the band at x 38..206; hovering there does nothing and a click on the frame band there reaches the desktop (click-through). Set its `state = "extended"` and save: the clock opens (config is the only way). Set `"collapsed"` again.
6. **In place, no rebuild:** change panel 3's `handle.shape` to `"dots"` and save: only the handle changes; the system bar's labels do not blink and the log shows `config reloaded: 1 change(s)` without the panel being rebuilt (no new window title in the log, no delayed re-raise). Set panel 0's `interaction.hover = false` and save while the dock is collapsed and peeking: the peek drops at once and hovering no longer peeks. Undo both.
7. **Theme level:** add `[theme.handle_style]` with `shape = "bar"` and `handle = "#ff8800"` under `[theme]` (both new tables at the top of the file: `[theme]` / `handle = "#ff8800"` then `[theme.handle_style]` / `shape = "bar"`) and save: every handle without its own shape becomes a bar (panel 4 stays invisible: its own interactions are all off but its shape is now the theme's explicit bar, so a bar appears there - note whether that is what you expect, decision 3), panel 3 keeps its chevron, panel 2 keeps its mint colour, the others turn orange. No panel rebuilds. Remove both again and save.
8. **Invalid value:** set panel 3's `handle.shape = "star"` and save: a "Config not applied" notification names `monitors.HDMI-A-1.panels.3.handle.shape` and lists the valid shapes; the previous look stays. Undo.
9. **Border:** add `[theme.border]` with `enabled = true` and `width = 4` and save: every handle stays inside the dark band, fully visible; the border runs outside it and never covers a handle. Remove and save.
10. **Stacking (decision 1):** quit, start again, wait 10 s: every collapsed handle is visible (the delayed re-raise still does its job). For the record only: quit and start once with `env EDGE_SHELL_RAISE_MS=0 scripts/py main.py --config /tmp/edge-handles.toml -v`, wait 10 s and note whether the collapsed handles are hidden (expected: hidden, as at Plan 1 Gate 1); this does not change the plan.
11. **Measurement:** `scripts/py main.py --config /tmp/edge-handles.toml --stats 10` (10 s, every panel toggling): fps while animating >= 55 and canvas damaged-draw p95 <= 8 ms (Plan 1/2 targets). Copy the printed report.
12. The `-v` logs have no errors (the warning of item 8 is expected).

**On failure:**
- Items 1-4 wrong position or size of the handle: compare `hd.shape_centre` / `hd.hit_size` / `_place_handle` with `test_shape_centre` and `test_place_handle_offsets_along_and_rides_across`; reproduce the failing edge/depth in a new test first. A handle that does not repaint while the panel animates: check that `_place_handle` and `_sync_handle` queue a draw (`_handle_area.draws` tests).
- Item 2/3 interaction wrong: the matching Task 7 test (`test_a_press_starts_no_drag_without_drag`, `test_a_click_toggles_only_with_click`, `test_entering_does_not_peek_without_hover`); add a failing case before fixing.
- Item 5 not click-through: print the region (`-v` plus a temporary `log.debug` of `rects` in `_update_input_region`) and compare with `test_with_every_interaction_off_a_collapsed_panel_is_click_through`.
- Item 6 shows a rebuild: check `diff_configs` (`test_handle_and_interaction_changes_update_in_place`) and `_sync_panels` (`test_a_handle_change_updates_the_live_panel`).
- Item 10 collapsed handles hidden even WITH the raise: stop and report (this would be a regression in stacking, not a handle bug); option (b) of decision 1 does not fix content stacking.
- Item 11 below target: run `--stats 10` on `examples/panels-test.toml` for comparison; if only the handle example is slower, profile `_on_handle_draw` (it should be well under 0.1 ms).

Write down each item's result; Task 10 records them.

---

### Task 10: Docs: README and spec

**Files:**
- Modify: `README.md` (configuration section; Known limitations)
- Modify: `docs/superpowers/specs/2026-10-11-edge-shell-design.md` (sections 4, 6, 15)

**Interfaces:**
- Consumes: Gate A and Gate B results. No code.

- [ ] **Step 1: README**

1. After the paragraph that starts `The border adds to the overall size:` (it ends `… while the border is enabled.`) and before `## Develop`, insert:

````markdown
### Handles and interactions

Each panel's handle and its three interactions can be set per panel entry; every key is
optional (a missing one comes from the theme):

```toml
[[monitors.HDMI-A-1.panels]]
widget = "clock"
handle.shape = "chevron"     # auto | dots | bar | chevron | none
handle.size = 24             # px along the edge, 4-40
handle.weight = 2            # px, 1-8: dot diameter, bar and chevron thickness
handle.offset = -100         # px along the edge from the body centre (clamped to the body)
handle.color = "#8fd3b6"     # rest colour (default: theme handle)
handle.hover_color = "#ffffff"  # pointer on the handle, or peeking (default: theme handle_hover)
interaction.click = true     # click (and keyboard) toggles
interaction.hover = false    # hovering the strip peeks
interaction.drag = true      # dragging the handle opens and closes

[theme.handle_style]         # the default for every panel; per monitor:
shape = "auto"               # [monitors.NAME.theme.handle_style]
size = 15
weight = 3
```

`auto` picks the shape from the interactions: dots (click and drag), a bar (drag only), a
chevron (click only), dots (hover only), nothing (all off). The chevron points where the
panel opens while it is collapsed and folds through a flat bar to point back as it extends.
A panel with all three interactions off opens and closes only through `state`. Handle and
interaction changes apply in place on reload. `scripts/py -m shell.handle_draw --sheet
/tmp/handles.png` renders every shape for a look without starting the shell.
````

2. In `## Develop`, after the `scripts/py -m shell.canvas.simulate --config …` line inside the code block, add the line `scripts/py -m shell.handle_draw --sheet /tmp/handles.png        # every handle shape, enlarged`.
3. In `## Known limitations / planned`, delete the two lines

```
- Handle customization (shape, color, size, position) and per-interaction opt-in/out
  (click, hover, drag) are planned, see spec section 15.
```

and change the re-raise item's second sentence to `Live testing showed it is still needed: without it the collapsed handles are hidden behind the canvas (the handle is drawn in the panel's own window, like the content).`

- [ ] **Step 2: Spec**

1. Section 4, after the **Hover target.** paragraph, add: `**Per-panel toggles (section 15, implemented).** Each of click, hover and drag can be turned off per panel (`interaction` table). Hover off: no peek; drag off: a press never drags; click off: the handle ignores clicks and takes no keyboard focus. With hover off the collapsed input region is only the handle's hit target; with all three off a collapsed panel takes no input.`
2. Section 6, in the example config, after `state = "extended"            # collapsed | extended` add the two lines `handle.shape = "auto"         # auto | dots | bar | chevron | none (section 15)` and `interaction.hover = true      # click / hover / drag, each optional`. In the reload table, change the first row's change cell to `Theme colour, border, shadow or handle style` and add the row `| Panel `handle` or `interaction` | Update the live panel in place (no rebuild) |` after the `Panel `state`` row.
3. Section 15, after the **Design implications** list, append:

```markdown
**Implemented (2026-10-13, plan `docs/superpowers/plans/2026-10-13-handle-customization.md`):** the handle stays in the panel's own window: its Button is the hit target (click, keyboard, accessible name) and a `Gtk.DrawingArea` child draws it with the pure `draw_handle` (`shell/handle_draw.py`); the shape canvas is unchanged and the delayed re-raise stays (the content windows need it anyway, so drawing the handle on the canvas would not retire it). Config: per panel `handle` (`shape` auto/dots/bar/chevron/none, `size` 4-40, `weight` 1-8, `offset`, `color`, `hover_color`) and `interaction` (`click`, `hover`, `drag`); theme-wide `[theme.handle_style]` (`shape`, `size`, `weight`, per monitor through the theme override; colours from `handle` / `handle_hover`); widget defaults through `PanelDefaults.handle` / `.interaction`. `auto` follows the interactions (dots; bar for drag only; chevron for click only; none when all are off). The chevron folds through a flat bar as `d / depth` goes from 0 to 1. The shape is centred in the last `T` px of the mass, at most `T - 2` px across; the hit target is at least 44 x 14 px and rides the inner edge. Reload: a `panel-handle` change kind, applied in place (`EdgePanel.set_handle`); theme handle changes are a restyle. Gate A (sheet) and Gate B (live, HDMI-A-1): RESULTS.
```

Replace `RESULTS` with Phil's Gate A answers (items 3 and 5) and the Gate B item results, including the `--stats 10` numbers (fps while animating, damaged-draw median / p95) and item 10's record.

- [ ] **Step 3: Commit**

```bash
git add README.md docs/superpowers/specs/2026-10-11-edge-shell-design.md
git commit -m "docs: handle customization and interaction toggles in README and spec" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage**

| Requirement (spec 15, Phil's Gate D wishes, the planner brief) | Task |
| --- | --- |
| Handle shape per panel: dots, thin bar, chevron/arrow, none | 1, 3, 4, 6 (decisions 2-3) |
| Colour (rest and hover), size, location (offset) per panel; RGBA colours | 1, 2, 3, 6 |
| Chevron morph with depth, pure `draw_handle(..., morph)` with `morph = d / depth` | 3 (`morph`), 4, 6 (decision 4) |
| Click / hover / drag individually opt-in/out, defaults all on | 1, 2, 7 (decision 7) |
| Style by interaction (thin bar for drag only, arrow for click only) | 3 (`auto_shape`, decision 3) |
| Theme-level default with per-monitor override; widget defaults through the registry | 1, 2 (decision 2) |
| Unknown shapes and bad values fail with the key path | 1 |
| Hit area separate from and larger than the shape; minimum hit size | 3, 6, 7 (decision 6) |
| Keyboard activation follows click; accessible names | 3 (`handle_label`), 7 |
| All three off: behaviour and how the panel still opens | 3, 7, 9 item 5 (decision 7) |
| Handle and interaction changes are in-place (no rebuild); diff kind; PanelRequest equality | 2, 8 (decision 8) |
| Where the handle is drawn; the raise workaround | decision 1, Global Constraints, 9 item 10 |
| Handle inside the band, never under the border | 3 (`shape_centre`), 4 (band test), 9 item 9 (decision 5) |
| Clip container and content measurement unaffected | the handle is its own overlay child, not in the clip container; `natural_length` reads `_inner` only (unchanged code) |
| Headless pixel tests: morph 0 / 0.5 / 1, four edges, hover colour | 4, 6 |
| Settings-window readiness: models single source, JSON schema | 1 (`test_the_json_schema_describes_the_new_tables`, decision 10) |
| CSS `.handle-dot` and the theme tokens | 6 (decision 11) |
| Human gates on HDMI-A-1 only, with commands and checklists | 5 (no shell), 9 |
| README and spec | 10 |

Not covered by design: drawing on the canvas (decision 1, the cost if wrong), removing the raise, per-panel border/shadow, a settings window, HiDPI.

**2. Placeholder scan:** every code step carries the code, every test step the tests, every gate exact values. The one fill-in is Task 10's `RESULTS`, which is the gate outcome by definition, with an exact instruction of what to write.

**3. Type consistency:** `HandleSpec(shape, size, weight, offset, color, hover_color)` and `Interaction(click, hover, drag)` (Task 2) are used with these names in Tasks 3, 6, 7, 8 and the tests. `resolve_handle(spec, interaction, theme) -> HandleLook(shape, size, weight, offset, rgba, hover_rgba)` (Task 3) is what `EdgePanel._look` holds (Task 6). `hit_size(thickness, size, length)`, `hit_inset(thickness, d, hit_across)`, `clamp_offset(offset, length, hit_along)`, `along_margins(offset)`, `shape_centre(edge, width, height, thickness, d)`, `input_rects(edge, length, depth, d, thickness, radius, hover_zone, interaction, hit, offset)` (Task 3) are called with that order in Tasks 6-7. `draw_handle(cr, shape, size, weight, rgba, morph, edge, cx, cy, max_across)` (Task 4) is called with that order in `_on_handle_draw` (Task 6) and `render_sheet`. `EdgePanel(..., on_depth=None, handle=THEME_HANDLE, interaction=ALL_INTERACTIONS)` (Task 6) matches `MonitorShell._new_panel`'s keywords (Task 8) and `FakeWindow`'s `kwargs`. `set_handle(handle, interaction)` (Task 7) matches `FakeWindow.set_handle` and `_sync_panels` (Task 8). `Change("panel-handle", monitor, index)` (Task 2) is the kind the Task 8 tests pass to `apply`.

**4. Review Focus:** each of the six lines names its pinning tests in Tasks 1-8 and a gate item.

**5. Test counts (expected):** baseline 645. Task 1: 664 (+19). Task 2: 678 (+14). Task 3: 742 (+64). Task 4: 869 (+127). Task 6: 884 (+15). Task 7: 895 (+11). Task 8: 900 (+5). Without a display one Task 6 test is skipped. A different total is not a failure by itself, but check which test it is.

**Verification while planning:** Tasks 1-4 and 6-8 were prototyped in a scratch copy of this worktree (not committed): the final state passed the full suite (900 passed) and ruff (`All checks passed!`); Task 1 alone gave 19, Tasks 1-2 gave 678, and `tests/test_handle.py` (64), `tests/test_handle_draw.py` (127) and `tests/test_edge_panel_handle.py` (26, including the GTK Button/DrawingArea check) passed as written here. The review sheet was rendered and looked at: the dots are crisp, the bar is centred, the chevron points into the screen at morph 0, is flat at 0.5 and points back at 1 on all four edges. The Task 9 example resolved to the expected lines above. Not run separately: the intermediate state between Tasks 6 and 7 (Task 6's `_sync_handle` and `_update_input_region` are the pre-plan versions plus one `queue_draw`, and Task 6's 15 tests do not touch the Task 7 behaviour), and anything on screen (Gates A-B are Phil's).

## Open questions for Phil

1. **Decision 1:** handle in the panel window (planned) or on the shape canvas? The plan argues the canvas would not retire the raise because the content windows need it too.
2. **Decision 3:** keep `auto` (shape follows the interactions) as the default, or always dots unless set?
3. **Decision 4:** chevron folds through a flat bar (planned) or rotates 180°? Gate A item 3 is the place to judge.
4. **Decision 5:** the collapsed dots move 2 px towards the screen edge (true centre of the band). Keep, or keep today's 7 px?
5. **Decision 7:** should the handle also light up while the panel peeks (planned; spec 4 says the dots brighten on peek) - and is "all three off, no warning" right?
6. **Gate B item 7:** a theme-wide explicit shape (`shape = "bar"`) also draws a bar on a panel whose interactions are all off (only `auto` turns into `none`). Should an all-off panel never draw a handle regardless of shape?
