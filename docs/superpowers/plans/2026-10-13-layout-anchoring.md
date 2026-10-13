# Layout and Anchoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Several panels per edge, placed by `align` / `offset` / `order` with a configurable `gap`, sized by px, `"fill"`, `"content"` or a percentage with optional `min_length` / `max_length`, clamped to the corner-free span of each edge, and re-laid out when the monitor's geometry changes.

**Architecture:** A pure resolver in `shell/panel_layout.py` (`layout_edge` per edge, `layout_monitor` per monitor) replaces the interim rules of the shape-canvas plan. Config entries become `PanelRequest`s (`shell/registry.py`), the resolver turns them into `PanelGeometry`s (exact body start and length), and `MonitorShell` keeps reconciling panels against the resolved layout as it does today (rebuild what moved, retarget state changes). "content" lengths are measured by the panel window after it is built and fed back into the resolver; a `notify::geometry` on the monitor triggers the same re-layout.

**Tech Stack:** Python 3.14 (>=3.12), Fabric 0.0.2, PyGObject 3.50.0 (`<3.52`), pycairo, GtkLayerShell, Pydantic 2, pytest, ruff 0.17.0.

**Spec:** `docs/superpowers/specs/2026-10-11-edge-shell-design.md`, sections 16 (several panels on one edge) and 17 (anchoring, sizing, corner behaviour; decisions 1-3 and the minimum geometry rules), with section 6 (config, reload table) and 18 (the canvas draws the resolved rectangles). Previous plan (style, gates, constraints): `docs/superpowers/plans/2026-10-13-shape-canvas-and-effects.md`. Findings: `docs/superpowers/findings/2026-10-12-shape-canvas-spike.md` (sections 3.4 and 10: corner clearance `pos - r >= T + R`, minimum gap `r1 + r2`).

**Scope (Plan 2).** In: config keys `align`, `offset`, `order`, `length` modes, `min_length`, `max_length`, `[layout] gap`; the pure resolver; `MonitorShell` / `EdgePanel` integration; reload semantics; re-layout on monitor geometry change; "content" measurement and content clipping; simulation and render tests; examples; README and spec. Out: handle customization (spec 15), the settings window, corner-spanning widget panels (spec 17, last bullet), HiDPI, a `panel-move` in-place move (see decision 7).

**Date:** 2026-10-13 (the plan's execution date, as in the file name).

**Size:** 11 tasks. 8 carry code and tests (1-5, 7-9), 2 human gates (Gate A = Task 6, Gate B = Task 10), Task 11 is docs. Riskiest: Task 5 (switching `MonitorShell` to the new resolver changes where existing configs put panels if a rule is wrong; Gate A item 9 checks the old examples look identical), Task 7 (the idle measurement and the clip container are GTK behaviour the unit tests only simulate; Gate B items 6-7 check clipping and that clicks, hover, drag and tooltips still reach the clipped content), Task 8 (whether KWin/GDK emit `notify::geometry` on a mode change is only provable live: Gate B item 10 is required, not optional).

## Decisions (for Phil's review; each marked with the cost if Phil disagrees)

The spec leaves these open. They are the planner's choices; nothing below has been implemented yet. Three of them (1, 2's deprecation logging, 5) were put to Phil and are not answered yet: they are marked **default pending Phil** and the plan is written for the default.

1. **Gap: one value per monitor, measured on top of the joins (default pending Phil: 8 px).** `[layout] gap = 8` (global default) with an optional `[monitors.NAME.layout] gap` override. Two neighbouring slotted panels on one edge are `r1 + r2 + gap` apart (body to body), so `gap` is the straight piece of frame between their curved joins and **any value >= 0 already satisfies the minimum gap `r1 + r2`**; no validation has to know the depths. Default 8 px. Per-edge gaps are not supported (one number covers the common case). *Cost if Phil disagrees:* another default = one number in `LayoutSettings` and `config.default.toml` plus the expected positions in the tests and gates (small); per-edge gap = an `edges` table in `LayoutSettings` and one lookup in `layout_monitor` (half a task); "gap = body-to-body distance" instead = change `space()` in the resolver plus a validation that compares it with the joins (small).
2. **`pos` vs `align` / `offset`: `pos` keeps its exact old meaning and wins, but cannot be mixed in one entry.** `pos` = the body starts `pos` px from the start of the screen edge, clamped to the corner clearance (so every existing config looks the same). A `pos` panel is placed on its own, outside the slots and outside the fill sharing. Setting `pos` together with `align` or `offset` in the same panel entry is a validation error naming the key path (ambiguous otherwise); the message gives the conversion: a lone `pos = N` equals `align = "start"`, `offset = N - (T + R + r)`, i.e. `N - 38` at the default theme for a panel at least 28 px deep (the clearance is 32-38 px depending on depth). Placement is taken as a whole: if an entry sets any of `pos` / `align` / `offset`, the widget's default placement is dropped and the missing keys are `align = "center"`, `offset = 0`. `pos = "center"` keeps working (= `align = "center"`). **Deprecation (default pending Phil): no notification** (it would repeat on every start); instead ONE INFO log line per config load and reload lists the key paths still using `pos` (pure helper `shell.registry.deprecated_pos_paths(config)`, called by `EdgeShellApp` at start and after each successful reload, never from `request_for`; Task 2). The README and spec call `pos` deprecated. *Cost:* making `pos` an offset from the free-span start instead would shift every existing `pos` panel by the clearance `T + R + r` (32-38 px depending on its depth, not a fixed 38 px) and needs a migration note (small code change); a notification instead of the log line = one `_notify` call (trivial).
3. **Order: per slot, default 0, ties keep config order.** A slot is (edge, align). The start slot packs from the start of the free span, the end slot from its end (order 0 nearest the end), the center slot is centred on the edge as one group. `offset` of the first panel in a slot counts from the slot's end; for center it shifts the whole group (may be negative) from where it would sit without the offset (centred, or pushed clear of the start/end groups). `offset` of a later panel is extra space before it; a negative offset there counts as 0 (negative offsets only mean something on the first panel of the center slot). Overlap handling is unchanged from the interim rule: panels are checked in **config order** and the later one is hidden with a notification. A hidden panel keeps the slot space it was given (its neighbours do not close up: a hole in the packing). Two panels meeting at a shared screen corner (an end-aligned bottom panel and an end-aligned right panel, or a start-aligned top panel and a start-aligned left panel, both at offset 0) always collide and the later is hidden: one of them needs an offset of at least the other's depth + r - R (its depth for a panel at least 2R = 28 px deep). *Cost:* ordering across the whole edge instead of per slot would be a rewrite of the slot packing (one task); closing up the holes = a second packing pass after the overlap check (half a task).
4. **Fill: equal shares of what is left.** All `"fill"` panels on one edge share the free span minus the fixed lengths, the spacing (`r1 + r2 + gap` between every pair of neighbours) and the offsets, equally (the first fill gets the odd pixels), then min/max and the 60 px floor apply. With a fill present the center group ends up against its neighbours. A fill that is the first center panel gives up `abs(offset)` px and moves that way (positive: the free space is before it), so its offset is never clamped away; an offset on a non-fill first center panel next to a fill has no room and is clamped with a warning. A fill that gets no room is floored at 60 px and the overlap rule hides the later colliding panel. *Cost:* weighted fills (`fill = 2`) later = a new key (small).
5. **"content": measured when the main loop is idle after each build, then laid out again (default pending Phil: the one-off startup rebuild is accepted).** Until measured a "content" panel has its widget's default px length. Each `_new_panel` records its index; after a `_sync_panels`, `MonitorShell` schedules one idle callback (by then the app's stylesheet is applied, so fonts have their real size) that measures only the live "content" panels built since the last measurement, those without a measurement for the widget now at their index, and, after a restyle, every "content" panel (fonts may have changed). It reads `EdgePanel.natural_length()` (the content's natural size along the edge plus 12 px padding each side) and, if a value changed, re-runs the layout (rebuilding that panel and any neighbour it moves) and reports warnings. So each "content" panel is built twice at startup. Measurements are kept per (index, widget, orientation). *Cost:* avoiding the startup rebuild needs an in-place resize of the layer surface (EdgePanel resizes its size request, margin, content placement and input region) - 1-2 tasks, planned only if Gate B item 2 shows a visible flash; it would also give decision 7's in-place move.
6. **Monitor shrink / resolution change: re-layout, same rules.** `MonitorShell` listens to the monitor's `notify::geometry` (250 ms debounce) and re-runs the layout: percentages and fills rescale, centred groups re-centre, px panels that no longer fit shrink (warning), panels that collide are hidden (notification). A zero or negative geometry (the monitor being unplugged) is ignored, so an unplug never produces a spurious "Panels adjusted"; the hot-plug sync closes the shell. When the monitor grows back they return; the notification fires only when the warnings change (existing `_report_layout`). This fixes the README limitation "centred panels do not re-centre on resolution change". *Cost:* none structural.
7. **Reload: no `panel-move` change kind.** A moved panel is rebuilt, as today (`MonitorShell._sync_panels` rebuilds every panel whose resolved geometry changed, including neighbours). The diff gains a `relayout` kind for a `gap` change only. *Cost:* if rebuild flicker on a move is annoying (Gate A item 5), add an in-place move (`EdgePanel` updates its layer-shell margin) - about one task.
8. **Content in a longer or shorter body: centred, never stretched, clipped when too long.** For `fill` / percent / long px the widget stays at its natural size, centred in the body (today's behaviour). The layer surface cannot grow either way (GTK3's `Gtk.Overlay` never measures its overlay children, and the content box is one); the real failure is content longer than the body drawing over the joins and the frame. So the content sits in a scroll-less `Gtk.ScrolledWindow` and is **clipped at the body edge instead of drawing over the joins and frame**, kept centred in the viewport (both adjustments re-centre on `changed`), so it is cut off equally at both ends; wheel events do not scroll it. *Cost:* a per-widget "stretch" flag later (small).
9. **Negative offsets only for `align = "center"`** (shift towards the start); for start/end they are a validation error, and on a later center panel they count as 0 (decision 3). *Cost:* trivial.
10. **The system bar's default moves from `pos = 600` to `align = "end"`, `offset = 142`**, so a smaller monitor no longer triggers a clamp warning for an untouched default. This is identical only on a 1080 px tall monitor (y = 600..900 with the default T/R). Elsewhere the bar keeps 142 px from the end of the free span: y = 960 at 1440 px (old: 600) and y = 240 at 720 px (old: 600 clamped to 382 with a warning). *Cost:* trivial revert.
11. **Re-layouts the shell starts by itself never raise into the main loop.** `MonitorShell._measure` (Task 7) and `_relayout` (Task 8) catch any exception, log it with its traceback and call `on_error(shell)`; `EdgeShellApp` then closes that shell and rebuilds it from the current config, as a failed reload does, but only once per monitor until the next successful reload (a second failure is logged and the shell is kept, so a widget that always fails cannot loop). *Cost:* none structural.

## Prerequisites

- Branch `feat/layout-anchoring` from `main` at `4b39efd` (Plan 1 merged), in the worktree `/home/phil/Projects/pyDev/projects/myShell/.claude/worktrees/feat-edge-shell-core`.
- Baseline before Task 1: `scripts/py -m pytest -q` prints `493 passed` (2 GLib deprecation warnings are normal); `scripts/py -m ruff check .` prints `All checks passed!`.
- Always stage files by name, never `git add -A` or `git add .`.

## Global Constraints

- Python only through `scripts/py` (shared venv `/home/phil/Projects/pyDev/pyEnvs/global-base`). **PyGObject must stay `<3.52`** (Fabric 0.0.2 breaks on 3.52+).
- **Monitor is an INT.** Fabric 0.0.2's `WaylandWindow.monitor` is an int property; a `Gdk.Monitor` object is silently dropped. Always pass `monitor=monitor_index(monitor)` (`shell/gdk_util.py`). Every new window goes through `MonitorShell._track` (which checks the output).
- **Input shape after allocate.** Fabric's `Window.do_size_allocate` resets the input shape on every allocate; `EdgePanel.do_size_allocate` re-applies the panel's region (`shell/edge_panel.py:125-132`). Never drop that override.
- **Exclusive zones.** Panels and the canvas use `exclusivity="none"` then `GtkLayerShell.set_exclusive_zone(self, -1)` right after `super().__init__()`; strips use `"auto"`.
- **Keep the delayed `raise_to_top` workaround** (Plan 1 Gate 1, Fallback B): `RAISE_DELAY_MS` / `RAISE_FALLBACK_MS` in `shell/monitors.py`, re-raise of rebuilt panels in `_new_panel`. Do not remove it.
- **Pure modules import no GTK / `gi`:** `shell/panel_layout.py`, `shell/panel_spec.py`, `shell/registry.py`, `shell/geometry.py`, `shell/config/*`, `shell/canvas/*` except `canvas.py`. `shell/canvas/simulate.py` may import `widgets` only inside `main()` behind `--config` (a CLI path), never at module level.
- **Tests.** CI has only pycairo, pydantic, pytest and ruff: any test importing `gi` or `fabric` starts with `pytest.importorskip("gi")` / `pytest.importorskip("fabric")` (or calls them inside the test). Tests never create a window (that would draw on Phil's screen): GTK classes are tested by calling their methods on stand-ins (`tests/test_edge_panel_drag.py`, `tests/test_canvas_window.py`, `tests/test_monitor_shell.py`). A plain non-window widget may be created after `Gtk.init_check()` succeeds.
- **Lint.** `ruff` 0.17.0, line length 100, excludes `docs/` and `*.md` (`pyproject.toml`).
- **VERIFY** (before every commit): `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`. The suite must be green at the end of EVERY task (0 failed).
- **Colours** are `#rrggbb` or `#rrggbbaa` (unchanged by this plan).
- **Layout warnings flow** stays: `MonitorShell.layout_warnings` -> `EdgeShellApp._report_layout` notifies "Panels adjusted" only when a monitor's warnings change. Every warning starts with the key path `monitors.NAME.panels.N (widget)`.
- **Git.** Plain separate git commands run from the worktree (no `cd … && git`, no command substitution around git). Stage files by name. **Never push.** Every commit message ends with a second `-m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"`.
- **Live runs.** Phil is the only visual tester, on `HDMI-A-1` only. **Never touch `DP-1`** (it holds the Plasma panel; never configure it as `edge`). Subagents executing tasks never launch the shell or any GUI (`main.py` without `--list-outputs`); headless commands are fine (`pytest`, `python -m shell.canvas.simulate`, the `scripts/py -c` checks in Tasks 6 and 10, which import the widgets but create no window). Live probes are capped at 10 s (`main.py --stats` refuses more) and are run by Phil at the gates. If a live run is refused for a subagent, stop and report.

## Review Focus

The six input classes most likely to bite Phil that the spec implies but a happy-path test would not catch, each pinned by a test in the owning task:

1. **A smaller (or hot-plugged smaller, or unplugged) monitor:** an untouched config must re-centre, rescale percentages and fills, shrink or clamp with a warning, and never crash, draw into a corner or report a spurious "Panels adjusted" while the monitor goes away. Pinned by `test_a_smaller_monitor_recentres_rescales_and_clamps` (Task 4), `test_the_system_bar_default_keeps_its_place` (Task 3), `test_a_resolution_change_relayouts_once_it_settles` and `test_a_zero_geometry_is_ignored` (Task 8); live by Gate B items 9-10.
2. **Existing configs (`pos`, centred defaults) must look exactly as before.** Pinned by `test_centred_panel_keeps_the_old_centring`, `test_pos_is_clamped_to_the_corner_clearance` (Task 3), `test_placement_is_taken_as_a_whole` (Task 2) and `test_pos_clamped_to_the_corner_renders_like_legacy` (Task 5); live by Gate A item 9.
3. **Ambiguous or invalid panel entries** (`pos` with `align`, a negative `offset` at an end, `min_length > max_length`, `length = "half"`, `"0%"`, `"560"` as a string, an unknown widget in the simulator) must be rejected with the key path, keeping the last good config. Pinned by `test_bad_length_names_the_key_path`, `test_placement_conflicts_name_the_panel` and `test_new_panel_keys_report_key_path` (Task 1) and `test_cli_reports_an_unknown_widget` (Task 9); live by Gate A item 7.
4. **A measured "content" length that belongs to a different widget** after a reorder, a measurement loop that never settles, or a re-layout the shell starts itself that raises. Pinned by `test_a_measurement_belongs_to_its_widget`, `test_content_panels_are_measured_when_idle_then_laid_out_again` (the second measurement changes nothing), `test_only_panels_built_since_the_last_measurement_are_measured`, `test_a_failing_measurement_is_logged_and_reported` (Task 7), `test_a_failed_relayout_rebuilds_the_shell_once` (Task 7) and `test_a_failing_relayout_is_logged_and_reported` (Task 8).
5. **Content longer than its body** (shrink to fit, `max_length`, a small percentage) must be clipped at the body edge, centred, never drawn over the joins and frame, and still take clicks, hover and drags. Pinned by `test_clip_container_never_asks_for_the_content_size` and `test_clipped_content_is_centred_in_the_body` (Task 7); live by Gate B items 6-7.
6. **Two panels meeting at a shared screen corner** (bottom end + right end, or top start + left start, at offset 0) always collide; the later one must be hidden with a notification naming both, never drawn crossed. Pinned by `test_corner_neighbours_on_adjacent_edges_collide` (Task 3); live by Gate A item 3.

## File Structure

```
shell/config/models.py        # + Align, check_length, LayoutSettings/LayoutOverride, PanelConfig keys,
                              #   Config.layout + layout_for, override check covers layout
config.default.toml           # + [layout] gap = 8
shell/panel_spec.py           # PanelDefaults (+ align, offset), PanelRequest (new), PanelGeometry (pos: int)
shell/registry.py             # request_for / requests_for (replace resolve_panel / panels_for in Task 5),
                              #   deprecated_pos_paths
shell/config/diff.py          # compares requests; + "relayout" kind for a gap change
shell/panel_layout.py         # PURE resolver: free_span, layout_edge, layout_monitor, content_length
shell/geometry.py             # anchor_and_margin takes a resolved pos (no None branch)
shell/monitors.py             # MonitorShell: layout_monitor, gap, "content" measurement, geometry re-layout,
                              #   on_layout / on_error callbacks
shell/edge_panel.py           # clip_container (centred), natural_length
shell/canvas/canvas.py        # ShapeCanvas.set_monitor_size
shell/canvas/simulate.py      # config_shapes + --config/--monitor
shell/app.py                  # pos deprecation log line; on_layout -> _report_layout; on_error -> _relayout_failed
widgets/system_bar.py         # default placement align = "end", offset = 142
examples/layout-test.toml     # Gate A
examples/layout-sizes-test.toml  # Gate B
tests/test_layout_resolver.py # NEW: resolver rules
tests/test_panel_layout.py    # REWRITTEN: pixel tests of resolved panels vs legacy renderers
```

| Task | Deliverable | Keeps the suite green because |
| --- | --- | --- |
| 1 | config keys, `[layout] gap`, validation | new keys optional with defaults; old keys unchanged |
| 2 | `PanelRequest`, `request_for`, diff on requests + `relayout`, `pos` deprecation log line | old `resolve_panel` / `panels_for` stay until Task 5 |
| 3 | resolver core: slots, order, gap, offset, pos, overlap | new functions beside the interim `resolve_layout` |
| 4 | length modes: percent, content, fill, min/max | additive edits; px behaviour unchanged |
| 5 | MonitorShell on the new resolver; old resolver removed | tests ported with the code |
| 6 | Gate A + `examples/layout-test.toml` | example only |
| 7 | "content" measurement, clip container, `on_layout`, `on_error` | new code + fakes |
| 8 | re-layout on monitor geometry change | new code + fakes |
| 9 | simulate `--config`, effects test at the corners | new code + tests |
| 10 | Gate B + `examples/layout-sizes-test.toml` | example only |
| 11 | README, spec | docs only |

---

### Task 1: Config keys for layout and anchoring

**Files:**
- Modify: `shell/config/models.py:18-20` (literals), `shell/config/models.py:138-155` (`Length` … `MonitorConfig`), `shell/config/models.py:158-179` (`Config`)
- Modify: `config.default.toml` (append)
- Test: `tests/test_config_models.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `shell.config.models.Align = Literal["start", "center", "end"]`
  - `shell.config.models.check_length(value: int | str) -> int | str` (px 60-4000, `"fill"`, `"content"`, `"N%"` / `"N.N%"` with 1 <= N <= 100; anything else `ValueError('must be a length in px (60-4000), "fill", "content" or a percentage from "1%" to "100%"')`)
  - `shell.config.models.LayoutSettings` (`gap: int`, 0-400, default 8), `LayoutOverride` (all fields optional)
  - `PanelConfig` fields: `align: Align | None`, `offset: int | None` (-20000..20000), `order: int | None` (0..1000), `length: int | str | None` (checked by `check_length`), `min_length: int | None`, `max_length: int | None` (both 60..4000); `pos` unchanged
  - `MonitorConfig.layout: LayoutOverride`; `Config.layout: LayoutSettings`; `Config.layout_for(name: str) -> LayoutSettings`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config_models.py` (it already imports `pytest`, `ValidationError` and `PanelConfig`):

```python
@pytest.mark.parametrize("length", [60, 4000, "fill", "content", "1%", "50%", "12.5%", "100%"])
def test_length_modes_accepted(length):
    assert PanelConfig(widget="dock", length=length).length == length


@pytest.mark.parametrize("length", [59, 4001, "0%", "101%", "half", "560", "50 %", True])
def test_bad_length_names_the_key_path(make_config, length):
    with pytest.raises(ValidationError) as exc:
        make_config(monitors={"HDMI-A-1": {"panels": [{"widget": "dock", "length": length}]}})
    (error,) = exc.value.errors()
    assert error["loc"] == ("monitors", "HDMI-A-1", "panels", 0, "length")
    assert '"fill", "content" or a percentage' in error["msg"]


def test_align_offset_order_and_bounds():
    p = PanelConfig(widget="dock", align="end", offset=12, order=3, min_length=100, max_length=900)
    assert (p.align, p.offset, p.order, p.min_length, p.max_length) == ("end", 12, 3, 100, 900)
    assert PanelConfig(widget="dock", offset=-40).offset == -40  # center may shift either way


@pytest.mark.parametrize(
    ("panel", "message"),
    [
        ({"pos": 10, "align": "end"}, "pos cannot be combined with align or offset"),
        ({"pos": "center", "offset": 3}, 'pos = N is align = "start", offset = N - 38'),
        ({"align": "end", "offset": -4}, 'a negative offset only works with align = "center"'),
        ({"min_length": 300, "max_length": 200}, "min_length must not be larger than max_length"),
    ],
)
def test_placement_conflicts_name_the_panel(make_config, panel, message):
    with pytest.raises(ValidationError) as exc:
        make_config(monitors={"HDMI-A-1": {"panels": [{"widget": "dock", **panel}]}})
    (error,) = exc.value.errors()
    assert error["loc"] == ("monitors", "HDMI-A-1", "panels", 0)
    assert message in error["msg"]


@pytest.mark.parametrize(
    ("panel", "field", "kind"),
    [
        ({"widget": "dock", "align": "middle"}, "align", "literal_error"),
        ({"widget": "dock", "order": -1}, "order", "greater_than_equal"),
        ({"widget": "dock", "offset": 20001}, "offset", "less_than_equal"),
        ({"widget": "dock", "min_length": 10}, "min_length", "greater_than_equal"),
    ],
)
def test_new_panel_keys_report_key_path(make_config, panel, field, kind):
    with pytest.raises(ValidationError) as exc:
        make_config(monitors={"HDMI-A-1": {"shell": "edge", "panels": [panel]}})
    (error,) = exc.value.errors()
    assert error["loc"] == ("monitors", "HDMI-A-1", "panels", 0, field)
    # the bound itself, not "extra_forbidden" (what every new key gives before this task)
    assert error["type"] == kind


def test_layout_gap_default_override_and_bounds(make_config):
    cfg = make_config(monitors={"A": {"layout": {"gap": 20}}, "B": {}})
    assert (cfg.layout.gap, cfg.layout_for("A").gap, cfg.layout_for("B").gap) == (8, 20, 8)
    assert cfg.layout_for("not-configured").gap == 8
    with pytest.raises(ValidationError, match=r"monitors\.A\.layout: gap"):
        make_config(monitors={"A": {"layout": {"gap": -1}}})
    with pytest.raises(ValidationError) as exc:
        make_config(monitors={"A": {"layout": {"gapp": 1}}})
    assert exc.value.errors()[0]["loc"] == ("monitors", "A", "layout", "gapp")
```

Run: `scripts/py -m pytest -q tests/test_config_models.py`
Expected: FAIL (`"fill"` rejected by the int `Length`; `align`, `order`, `offset` and `min_length` are extra keys, so `test_new_panel_keys_report_key_path` sees `extra_forbidden` instead of the bound; `Config` has no `layout`).

- [ ] **Step 2: Implement in `shell/config/models.py`**

1. After `ShellMode = Literal["edge", "plasma", "both", "none"]` add `Align = Literal["start", "center", "end"]`.
2. Replace the block from `Length = Annotated[int, Field(ge=60, le=4000)]` down to (and including) the `MonitorConfig` class with:

```python
Length = Annotated[int, Field(ge=60, le=4000)]
Depth = Annotated[int, Field(ge=16, le=2000)]
Offset = Annotated[int, Field(ge=0, le=20000)]
SignedOffset = Annotated[int, Field(ge=-20000, le=20000)]
Order = Annotated[int, Field(ge=0, le=1000)]
_PERCENT = re.compile(r"[0-9]{1,3}(\.[0-9]+)?%")


def check_length(value: int | str) -> int | str:
    """A panel length: px (60-4000), "fill" (the free span the neighbours leave), "content"
    (the widget's natural size) or a percentage of the free span such as "50%" (spec 17)."""
    if isinstance(value, int) and not isinstance(value, bool) and 60 <= value <= 4000:
        return value
    if value in ("fill", "content"):
        return value
    if isinstance(value, str) and _PERCENT.fullmatch(value) and 1 <= float(value[:-1]) <= 100:
        return value
    raise ValueError(
        'must be a length in px (60-4000), "fill", "content" or a percentage from "1%" to "100%"'
    )


class LayoutSettings(_Strict):
    """Per-monitor layout settings (spec 16). `gap` is the straight frame left between two
    neighbouring panels' joins on one edge, ON TOP of the joins (r1 + r2), so any value keeps
    the minimum gap the outline needs."""

    gap: Annotated[int, Field(ge=0, le=400)] = 8


LayoutOverride = _override_of("LayoutOverride", LayoutSettings)


class PanelConfig(_Strict):
    widget: str
    edge: Edge | None = None
    pos: Offset | Literal["center"] | None = None  # deprecated: align + offset
    align: Align | None = None
    offset: SignedOffset | None = None
    order: Order | None = None
    length: int | str | None = None
    min_length: Length | None = None
    max_length: Length | None = None
    depth: Depth | None = None
    state: PanelState | None = None

    @field_validator("length")
    @classmethod
    def _length(cls, value: int | str | None) -> int | str | None:
        return None if value is None else check_length(value)

    @model_validator(mode="after")
    def _placement(self) -> PanelConfig:
        if self.pos is not None and (self.align is not None or self.offset is not None):
            raise ValueError(
                "pos cannot be combined with align or offset (pos is deprecated): "
                'pos = N is align = "start", offset = N - 38 at the default theme '
                "(38 = thickness + radius + join radius; 32-38 depending on depth)"
            )
        if self.offset is not None and self.offset < 0 and (self.align or "center") != "center":
            raise ValueError('a negative offset only works with align = "center"')
        if (
            self.min_length is not None
            and self.max_length is not None
            and self.min_length > self.max_length
        ):
            raise ValueError("min_length must not be larger than max_length")
        return self


class MonitorConfig(_Strict):
    shell: ShellMode = "plasma"
    theme: ThemeOverride = Field(default_factory=ThemeOverride)
    layout: LayoutOverride = Field(default_factory=LayoutOverride)
    panels: list[PanelConfig] = Field(default_factory=list)
```

(`length` is a plain `int | str` checked by one validator so a bad value gives ONE error with the key path instead of one error per union member.)

3. In `class Config`, add `layout: LayoutSettings = Field(default_factory=LayoutSettings)` between `theme: Theme` and `monitors: …`; add after `theme_for`:

```python
    def layout_for(self, name: str) -> LayoutSettings:
        override = self.monitor(name).layout.model_dump(exclude_none=True)
        return LayoutSettings.model_validate({**self.layout.model_dump(), **override})
```

and replace the body of `_check_overrides` (the override models drop the field bounds, so both merged tables are re-validated here, as the theme already was):

```python
    @model_validator(mode="after")
    def _check_overrides(self) -> Config:
        for name in self.monitors:
            for table, resolve in (("theme", self.theme_for), ("layout", self.layout_for)):
                try:
                    resolve(name)
                except ValidationError as exc:
                    detail = "; ".join(
                        f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
                    )
                    raise ValueError(f"monitors.{name}.{table}: {detail}") from None
        return self
```

- [ ] **Step 3: Append to `config.default.toml`**

```toml

# Panel layout (spec 16-17). `gap` is the straight piece of frame left between two neighbouring
# panels on one edge, on top of their curved joins (so any value keeps the minimum the outline
# needs). Per monitor: [monitors.NAME.layout].
[layout]
gap = 8
```

- [ ] **Step 4: Run the tests**

Run: `scripts/py -m pytest -q tests/test_config_models.py tests/test_config_loader.py`
Expected: all pass (the existing `test_panel_bounds_report_key_path` still sees `length` 0 / 999999 rejected at `…panels.0.length`; `test_defaults_only_matches_test_theme` still passes because `[layout]` equals the model default).

- [ ] **Step 5: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell/config/models.py config.default.toml tests/test_config_models.py
git commit -m "feat(config): align, offset, order, length modes and layout gap" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Panel requests, registry and reload diff

**Files:**
- Modify: `shell/panel_spec.py` (whole file)
- Modify: `shell/registry.py:8` (import), add after `widget_class` (line 30) and before `validate_widgets`
- Modify: `shell/config/diff.py:10-14`, `shell/config/diff.py:42-44`
- Modify: `shell/app.py` (import, `__init__`, `_reload`, new `_log_deprecated`)
- Test: `tests/test_registry.py`, `tests/test_config_diff.py`, `tests/test_app_sync.py`

**Interfaces:**
- Consumes: Task 1 (`Align`, `PanelConfig` keys, `Config.layout_for`).
- Produces:
  - `shell.panel_spec.LengthSpec = int | str`
  - `PanelDefaults(edge, length: int, depth, label, pos: int | None = None, state = "extended", align: Align = "center", offset: int = 0)`
  - `PanelRequest(widget, edge, align, offset: int, pos: int | None, order: int, length: LengthSpec, min_length: int | None, max_length: int | None, depth: int, state, label: str, fallback_length: int)` (frozen dataclass, field order as listed; positional construction is used by tests)
  - `PanelGeometry` unchanged in this task (`pos: int | None`; Task 5 makes it `int`)
  - `shell.registry.request_for(cfg: PanelConfig) -> PanelRequest`, `shell.registry.requests_for(config: Config, monitor: str) -> list[PanelRequest]`; placement rule of decision 2; `order` None -> 0; `length` None -> the widget's default px; `fallback_length` = the widget's default px
  - `shell.config.diff.Kind` gains `"relayout"`; `diff_configs` emits `Change("relayout", name)` when `old.layout_for(name) != new.layout_for(name)` (after a `restyle`, before panel changes); panel changes compare `PanelRequest`s (state-only -> `panel-state`, anything else -> `panel-rebuild`)
  - `shell.registry.deprecated_pos_paths(config: Config) -> list[str]` (pure; `"monitors.NAME.panels.N.pos"` for every entry that sets `pos`, `"center"` included, in config order)
  - `EdgeShellApp._log_deprecated(config) -> None`: one INFO line on the `shell.app` logger starting `deprecated key pos` and listing the paths, nothing when there are none; called from `EdgeShellApp.__init__` (start) and from `_reload` after a successful load (decision 2)

- [ ] **Step 1: Write the failing tests**

In `tests/test_registry.py` change the import to `from shell.panel_spec import PanelDefaults, PanelGeometry, PanelRequest` and append:

```python
def test_request_uses_widget_defaults(fake_registry):
    assert registry.request_for(PanelConfig(widget="dock")) == PanelRequest(
        widget="dock",
        edge="bottom",
        align="center",
        offset=0,
        pos=None,
        order=0,
        length=560,
        min_length=None,
        max_length=None,
        depth=64,
        state="extended",
        label="dock",
        fallback_length=560,
    )


def test_request_overrides_win(fake_registry):
    got = registry.request_for(
        PanelConfig(widget="dock", depth=80, edge="top", state="collapsed", order=2)
    )
    assert (got.depth, got.edge, got.state, got.length, got.order) == (
        80,
        "top",
        "collapsed",
        560,
        2,
    )


def test_length_modes_and_bounds_pass_through(fake_registry):
    got = registry.request_for(
        PanelConfig(widget="dock", length="fill", min_length=100, max_length=900)
    )
    assert (got.length, got.min_length, got.max_length, got.fallback_length) == (
        "fill",
        100,
        900,
        560,
    )


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ({}, (600, "center", 0)),  # the bar's registered default: pos 600
        ({"pos": 100}, (100, "center", 0)),
        ({"pos": "center"}, (None, "center", 0)),
        ({"align": "end"}, (None, "end", 0)),  # the default pos is dropped
        ({"offset": 40}, (None, "center", 40)),
        ({"align": "start", "offset": 5}, (None, "start", 5)),
    ],
)
def test_placement_is_taken_as_a_whole(fake_registry, entry, expected):
    got = registry.request_for(PanelConfig(widget="bar", **entry))
    assert (got.pos, got.align, got.offset) == expected


def test_unknown_widget_request_lists_known(fake_registry):
    with pytest.raises(ConfigError, match="nope"):
        registry.request_for(PanelConfig(widget="nope"))


def test_requests_for_keeps_order_and_duplicates(fake_registry, make_config):
    cfg = make_config(
        monitors={
            "HDMI-A-1": {
                "panels": [{"widget": "dock"}, {"widget": "clock"}, {"widget": "dock", "order": 1}]
            }
        }
    )
    got = registry.requests_for(cfg, "HDMI-A-1")
    assert [(r.widget, r.order) for r in got] == [("dock", 0), ("clock", 0), ("dock", 1)]


def test_deprecated_pos_paths_lists_every_entry_using_pos(make_config):
    cfg = make_config(
        monitors={
            "A": {"panels": [{"widget": "dock"}, {"widget": "bar", "pos": 600}]},
            "B": {"panels": [{"widget": "clock", "pos": "center"}]},
        }
    )
    assert registry.deprecated_pos_paths(cfg) == [
        "monitors.A.panels.1.pos",
        "monitors.B.panels.0.pos",
    ]
    no_pos = make_config(monitors={"A": {"panels": [{"widget": "dock", "align": "end"}]}})
    assert registry.deprecated_pos_paths(no_pos) == []
```

In `tests/test_app_sync.py` append (the `renv` fixture is defined above in that file):

```python
# ---- pos deprecation ------------------------------------------------------------------


def test_deprecated_pos_is_logged_once_at_start(make_config, caplog):
    caplog.set_level("INFO", logger="shell.app")
    cfg = make_config(monitors={"HDMI-A-1": mon(panels=[{"widget": "dock", "pos": 100}])})
    app_mod.EdgeShellApp(SimpleNamespace(config=cfg))
    lines = [r.getMessage() for r in caplog.records if "deprecated key pos" in r.getMessage()]
    assert len(lines) == 1 and "monitors.HDMI-A-1.panels.0.pos" in lines[0]


def test_deprecated_pos_is_logged_once_per_reload(renv, caplog):
    app, store, _, _, make_config = renv
    caplog.set_level("INFO", logger="shell.app")
    store.pending = make_config(
        monitors={"HDMI-A-1": mon(panels=[{"widget": "dock", "pos": 100}, {"widget": "dock"}])}
    )
    app.reload()
    store.pending = make_config(monitors={"HDMI-A-1": mon(panels=[{"widget": "dock"}])})
    app.reload()  # no pos left: no line
    lines = [r.getMessage() for r in caplog.records if "deprecated key pos" in r.getMessage()]
    assert len(lines) == 1 and lines[0].endswith("monitors.HDMI-A-1.panels.0.pos")
```

In `tests/test_config_diff.py` insert `import pytest` and a blank line after the first line (`# tests/test_config_diff.py`), and append:

```python
def test_gap_change_relayouts_without_touching_panels(fake_registry, make_config):
    def cfg(gap):
        return make_config(
            monitors={"HDMI-A-1": {**mon(panels=[{"widget": "dock"}]), "layout": {"gap": gap}}}
        )

    assert diff_configs(cfg(8), cfg(20)) == [Change("relayout", "HDMI-A-1")]


def test_global_gap_change_relayouts_every_edge_monitor(fake_registry, make_config):
    monitors = {"HDMI-A-1": mon(), "DP-1": mon("plasma")}
    old = make_config(monitors=monitors)
    new = make_config(monitors=monitors)
    new = new.model_copy(update={"layout": new.layout.model_copy(update={"gap": 30})})
    assert diff_configs(old, new) == [Change("relayout", "HDMI-A-1")]


@pytest.mark.parametrize(
    "entry",
    [
        {"align": "end"},
        {"offset": 30},
        {"order": 2},
        {"length": "fill"},
        {"min_length": 100},
        {"max_length": 900},
    ],
)
def test_placement_and_length_changes_rebuild_that_panel(fake_registry, make_config, entry):
    old = make_config(monitors={"HDMI-A-1": mon(panels=[{"widget": "dock"}])})
    new = make_config(monitors={"HDMI-A-1": mon(panels=[{"widget": "dock", **entry}])})
    assert diff_configs(old, new) == [Change("panel-rebuild", "HDMI-A-1", 0)]
```

Run: `scripts/py -m pytest -q tests/test_registry.py tests/test_config_diff.py tests/test_app_sync.py`
Expected: FAIL (`ImportError: cannot import name 'PanelRequest'`; the two deprecation tests in `tests/test_app_sync.py` find no `deprecated key pos` line).

- [ ] **Step 2: Replace `shell/panel_spec.py`**

```python
"""Plain data describing a panel. Pure."""

from __future__ import annotations

from dataclasses import dataclass

from shell.config.models import Align, Edge, PanelState

LengthSpec = int | str  # px, "fill", "content" or "NN%" (validated by shell.config.models)


@dataclass(frozen=True)
class PanelDefaults:
    """A widget's registered defaults. `length` is px; it is also the length a "content" panel
    gets until the widget has been measured."""

    edge: Edge
    length: int
    depth: int
    label: str
    pos: int | None = None  # deprecated absolute start (see PanelRequest.pos)
    state: PanelState = "extended"
    align: Align = "center"
    offset: int = 0


@dataclass(frozen=True)
class PanelRequest:
    """What the config asks for (widget defaults + config overrides), before layout.

    `pos` is the deprecated alias: the body starts `pos` px from the start of the screen edge
    (left for top/bottom, top for left/right), clamped to the corner clearance. When it is set
    it wins: the panel is placed there on its own, outside the align slots."""

    widget: str
    edge: Edge
    align: Align
    offset: int
    pos: int | None
    order: int  # within its slot; ties keep config order
    length: LengthSpec
    min_length: int | None
    max_length: int | None
    depth: int
    state: PanelState
    label: str
    fallback_length: int  # px for "content" until the widget has been measured


@dataclass(frozen=True)
class PanelGeometry:
    """A panel with every value resolved (widget defaults + config overrides)."""

    widget: str
    edge: Edge
    pos: int | None
    length: int
    depth: int
    state: PanelState
    label: str
```

- [ ] **Step 3: Add the requests to `shell/registry.py`**

1. Import line: `from shell.panel_spec import PanelDefaults, PanelGeometry, PanelRequest`.
2. After `_DEFAULTS: dict[str, PanelDefaults] = {}` add `_PLACEMENT = ("pos", "align", "offset")`.
3. Insert before `def validate_widgets` (keep `resolve_panel` and `panels_for`; `MonitorShell` uses them until Task 5):

```python
def request_for(cfg: PanelConfig) -> PanelRequest:
    """The widget's defaults overlaid with one config entry. Placement is taken as a whole: if
    the entry sets any of pos / align / offset, the widget's default placement is dropped and
    the keys it leaves out are align = "center", offset = 0 (`pos = "center"` is align =
    "center"). Without any of them the widget's default placement applies."""
    d = _DEFAULTS.get(cfg.widget)
    if d is None:
        known = ", ".join(widget_names()) or "none"
        raise ConfigError(f"unknown widget {cfg.widget!r} (known: {known})")
    if any(getattr(cfg, key) is not None for key in _PLACEMENT):
        pos = None if cfg.pos in (None, "center") else cfg.pos
        align, offset = cfg.align or "center", cfg.offset or 0
    else:
        pos, align, offset = d.pos, d.align, d.offset
    return PanelRequest(
        widget=cfg.widget,
        edge=cfg.edge or d.edge,
        align=align,
        offset=offset,
        pos=pos,
        order=cfg.order or 0,
        length=d.length if cfg.length is None else cfg.length,
        min_length=cfg.min_length,
        max_length=cfg.max_length,
        depth=cfg.depth or d.depth,
        state=cfg.state or d.state,
        label=d.label,
        fallback_length=d.length,
    )


def requests_for(config: Config, monitor: str) -> list[PanelRequest]:
    return [request_for(p) for p in config.monitor(monitor).panels]


def deprecated_pos_paths(config: Config) -> list[str]:
    """Key paths of the panel entries that still use the deprecated `pos` (decision 2:
    EdgeShellApp logs them once per config load; never notified)."""
    return [
        f"monitors.{name}.panels.{i}.pos"
        for name, mon in config.monitors.items()
        for i, panel in enumerate(mon.panels)
        if panel.pos is not None
    ]


```

- [ ] **Step 4: Diff on requests in `shell/config/diff.py`**

1. `from shell.registry import panels_for` -> `from shell.registry import requests_for`.
2. Replace the `Kind` definition with:

```python
Kind = Literal[
    "restyle",
    "relayout",
    "rebuild-monitor",
    "panel-add",
    "panel-remove",
    "panel-rebuild",
    "panel-state",
]
```

3. Replace the last line inside the monitor loop of `diff_configs` (`changes.extend(_diff_panels(name, panels_for(old, name), panels_for(new, name)))`) by:

```python
        if old.layout_for(name) != new.layout_for(name):
            changes.append(Change("relayout", name))
        changes.extend(_diff_panels(name, requests_for(old, name), requests_for(new, name)))
```

(`_diff_panels` is unchanged: `replace(old[i], state=new[i].state) == new[i]` works on `PanelRequest` too. `EdgeShellApp._reload` already groups every change kind per monitor and calls `MonitorShell.apply`, which re-runs the layout; nothing else handles `relayout`.)

- [ ] **Step 5: Log the `pos` deprecation in `shell/app.py`**

1. After `from shell.monitors import MonitorShell, monitors_by_name` add `from shell.registry import deprecated_pos_paths`.
2. At the end of `EdgeShellApp.__init__` (after `self._layout_reported = {}`) add `self._log_deprecated(store.config)`.
3. In `_reload`, right after `old, new = result` add `self._log_deprecated(new)`.
4. Before `def _report_layout` add:

```python
    def _log_deprecated(self, config) -> None:
        """One INFO line per config load listing the entries that still use `pos` (decision 2:
        a notification would repeat on every start)."""
        paths = deprecated_pos_paths(config)
        if paths:
            log.info(
                'deprecated key pos (use align = "start" and offset = pos - 38 at the default '
                "theme): %s",
                ", ".join(paths),
            )

```

- [ ] **Step 6: Run the tests**

Run: `scripts/py -m pytest -q tests/test_registry.py tests/test_config_diff.py tests/test_app_sync.py`
Expected: all pass.

- [ ] **Step 7: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell/panel_spec.py shell/registry.py shell/config/diff.py shell/app.py tests/test_registry.py tests/test_config_diff.py tests/test_app_sync.py
git commit -m "feat(layout): panel requests from config; diff on requests with a relayout kind" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Resolver core: free span, slots, order, gap, offset, pos, overlap

**Files:**
- Modify: `shell/panel_layout.py` (whole file; the interim `resolve_layout` stays at the bottom, unchanged, until Task 5)
- Create: `tests/test_layout_resolver.py`

**Interfaces:**
- Consumes: `PanelRequest` (Task 2), `geometry.join_radius`, `geometry.is_horizontal`.
- Produces (used by Tasks 4, 5, 9):
  - `MIN_LENGTH = 60`, `EDGES: tuple[Edge, ...] = ("top", "right", "bottom", "left")`, `Note = tuple[int, str]`
  - `Layout(panels: list[PanelGeometry | None], warnings: list[str])` (unchanged)
  - `free_span(extent: int, thickness: int, radius: int, depth: int) -> tuple[int, int]`
  - `layout_edge(entries: Sequence[tuple[int, PanelRequest]], extent: int, thickness: int, radius: int, gap: int, natural: Mapping[int, int] | None = None, where: str = "monitor") -> tuple[dict[int, tuple[int, int] | None], list[Note]]`
  - `layout_monitor(requests: Sequence[PanelRequest], width: int, height: int, thickness: int, radius: int, gap: int, natural: Mapping[int, int] | None = None, where: str = "monitor") -> Layout` (warnings sorted by config index, stable)
  - Warning texts (exact): `"{where}.panels.{i} ({widget}): pos {p} would run into a screen corner; moved to {q}"`, `"…: offset {o} would run into a screen corner; moved to {q}"` (start/end), `"…: offset {o} would run into a screen corner or a neighbour; moved to {q}"` (center), `"…: length {n} px does not fit the {edge} edge; shrunk to {span}"`, `"…: the {edge} edge ({extent} px) has no room for it; not shown"`, `"…: overlaps {where}.panels.{j} ({widget}) or leaves less than the minimum gap between their joins; not shown"`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_layout_resolver.py`:

```python
"""The layout resolver (spec 16-17): slots, order, gap, offsets, pos, clamping, overlap."""

import pytest

from shell.panel_layout import free_span, layout_edge, layout_monitor
from shell.panel_spec import PanelRequest

W, H, T, R, GAP = 1920, 1080, 10, 14, 8


def req(
    widget="dock",
    edge="bottom",
    align="center",
    offset=0,
    pos=None,
    order=0,
    length=560,
    depth=64,
    min_length=None,
    max_length=None,
    fallback=200,
):
    return PanelRequest(
        widget, edge, align, offset, pos, order, length, min_length, max_length, depth,
        "extended", widget, length if isinstance(length, int) else fallback,
    )  # fmt: skip


def placed(*requests, width=W, height=H, gap=GAP, natural=None):
    layout = layout_monitor(list(requests), width, height, T, R, gap, natural, "monitors.X")
    return [None if p is None else (p.pos, p.length) for p in layout.panels], layout.warnings


# ---- free span ----------------------------------------------------------------------


def test_free_span_is_the_corner_clearance_at_full_depth():
    assert free_span(1920, T, R, 64) == (38, 1882)  # r = 14
    assert free_span(1080, T, R, 16) == (32, 1048)  # r = 8
    assert free_span(1920, T, R, 27) == (38, 1882)  # r = 13.5: rounded inward


def test_layout_edge_returns_positions_by_config_index():
    got, notes = layout_edge([(3, req(align="start")), (7, req(align="end"))], W, T, R, GAP)
    assert got == {3: (38, 560), 7: (1322, 560)} and notes == []


# ---- slots ----------------------------------------------------------------------------


def test_centred_panel_keeps_the_old_centring():
    assert placed(req())[0] == [(680, 560)]
    assert placed(req("clock", "top", length=168, depth=46))[0] == [(876, 168)]


def test_start_and_end_sit_at_the_corner_clearance():
    assert placed(req(align="start"), req("clock", align="end", length=168, depth=46)) == (
        [(38, 560), (1882 - 168, 168)],
        [],
    )


def test_offset_is_measured_from_the_aligned_end():
    assert placed(req(align="start", offset=100))[0] == [(138, 560)]
    assert placed(req(align="end", offset=20))[0] == [(1882 - 20 - 560, 560)]


def test_the_system_bar_default_keeps_its_place():
    # widgets/system_bar.py: align = "end", offset = 142 -> y = 600 on a 1080 px edge
    assert placed(req("bar", "right", "end", offset=142, length=300, depth=56))[0] == [(600, 300)]


def test_two_centred_panels_are_packed_side_by_side_r1_plus_r2_plus_gap_apart():
    got, warnings = placed(req(), req("clock", length=168, depth=46))
    total = 560 + (14 + 14 + GAP) + 168
    first = (W - total) // 2
    assert got == [(first, 560), (first + 560 + 36, 168)] and warnings == []


def test_order_sorts_within_a_slot_and_ties_keep_config_order():
    a = req("a", "top", "start", order=1, length=168, depth=46)
    b = req("b", "top", "start", order=0, length=168, depth=46)
    c = req("c", "top", "start", order=1, length=100, depth=46)
    assert placed(a, b, c)[0] == [(38 + 168 + 36, 168), (38, 168), (38 + 2 * (168 + 36), 100)]


def test_the_first_end_panel_is_nearest_the_end():
    a = req("a", "top", "end", length=168, depth=46)
    b = req("b", "top", "end", length=168, depth=46)
    assert placed(a, b)[0] == [(1714, 168), (1714 - 36 - 168, 168)]


@pytest.mark.parametrize(("gap", "second"), [(0, 38 + 168 + 28), (8, 38 + 168 + 36), (50, 284)])
def test_gap_is_added_to_the_joins(gap, second):
    a = req("a", "top", "start", length=168, depth=46)
    b = req("b", "top", "start", length=168, depth=46)
    assert placed(a, b, gap=gap)[0][1] == (second, 168)


def test_a_later_panels_offset_is_extra_space_before_it():
    a = req("a", "top", "start", length=168, depth=46)
    b = req("b", "top", "start", offset=10, length=168, depth=46)
    assert placed(a, b)[0][1] == (38 + 168 + 36 + 10, 168)


@pytest.mark.parametrize(("offset", "pos"), [(100, 780), (-100, 580)])
def test_center_offset_shifts_the_group(offset, pos):
    assert placed(req(offset=offset)) == ([(pos, 560)], [])


def test_center_offset_past_the_corner_is_clamped_with_a_warning():
    assert placed(req(offset=1000)) == (
        [(1322, 560)],
        [
            "monitors.X.panels.0 (dock): offset 1000 would run into a screen corner or a "
            "neighbour; moved to 1322"
        ],
    )


def test_start_offset_past_the_corner_is_clamped_with_a_warning():
    assert placed(req(align="start", offset=5000)) == (
        [(1322, 560)],
        ["monitors.X.panels.0 (dock): offset 5000 would run into a screen corner; moved to 1322"],
    )


def test_the_center_group_is_pushed_clear_of_the_start_group():
    got, warnings = placed(req(align="start", length=1000), req("clock", length=168, depth=46))
    assert got == [(38, 1000), (38 + 1000 + 36, 168)] and warnings == []


def test_a_centre_offset_counts_from_where_the_neighbours_pushed_the_group():
    got, warnings = placed(
        req(align="start", length=1000), req("clock", offset=50, length=168, depth=46)
    )
    assert got == [(38, 1000), (38 + 1000 + 36 + 50, 168)] and warnings == []


def test_a_negative_offset_on_a_later_centre_panel_counts_as_zero():
    a = req("a", "top", length=168, depth=46)
    b = req("b", "top", offset=-50, length=168, depth=46)
    assert placed(a, b) == ([(774, 168), (978, 168)], [])  # as without the offset


# ---- pos (deprecated alias) -------------------------------------------------------------


@pytest.mark.parametrize(
    ("pos", "expected"), [(0, 38), (37, 38), (38, 38), (5000, 1920 - 38 - 560)]
)
def test_pos_is_clamped_to_the_corner_clearance(pos, expected):
    got, warnings = placed(req(pos=pos))
    assert got == [(expected, 560)]
    if pos == expected:
        assert warnings == []
    else:
        assert warnings == [
            f"monitors.X.panels.0 (dock): pos {pos} would run into a screen corner; "
            f"moved to {expected}"
        ]


def test_clearance_uses_the_join_radius_of_a_shallow_panel():
    assert placed(req(pos=0, depth=16))[0] == [(32, 560)]
    assert placed(req(pos=0, depth=27))[0] == [(38, 560)]


def test_pos_panel_stays_out_of_the_slots():
    got, _ = placed(req("bar", "right", pos=600, length=300, depth=56), req("x", "right"))
    assert got == [(600, 300), None]  # the centred one would sit on it: the later one goes


# ---- shrink, no room, overlap ------------------------------------------------------------


def test_too_long_is_shrunk_to_the_free_span():
    got, warnings = placed(req("bar", "right", pos=100, length=1500, depth=56))
    assert got == [(38, 1004)]
    assert "shrunk to 1004" in warnings[0]


def test_no_room_at_all_hides_the_panel():
    got, warnings = placed(req("bar", "right", pos=0, length=300, depth=56), height=130)
    assert got == [None]
    assert "has no room for it; not shown" in warnings[0]


def test_pos_neighbours_need_a_gap_of_r1_plus_r2():
    a = req(pos=400, length=300)  # ends at 700, r = 14
    ok = req("clock", pos=700 + 14 + 8, length=100, depth=16)  # r = 8: gap exactly 22
    tight = req("clock", pos=700 + 14 + 7, length=100, depth=16)
    assert placed(a, ok)[1] == []
    got, warnings = placed(a, tight)
    assert got[1] is None and got[0] is not None
    assert warnings[0].startswith("monitors.X.panels.1 (clock): overlaps monitors.X.panels.0")


def test_deep_panels_on_neighbouring_edges_must_not_cross():
    top = req("a", "top", pos=40, length=300, depth=400)
    left = req("b", "left", pos=40, length=300, depth=400)
    assert placed(top, left)[0][1] is None
    far = req("b", "left", pos=600, length=300, depth=400)
    assert placed(top, far)[1] == []


def test_corner_neighbours_on_adjacent_edges_collide():
    clock = req("clock", "bottom", "end", length=168, depth=46)

    def bar(offset):
        return req("bar", "right", "end", offset=offset, length=300, depth=56)

    got, warnings = placed(clock, bar(0))
    assert got[1] is None and warnings == [
        "monitors.X.panels.1 (bar): overlaps monitors.X.panels.0 (clock) or leaves less than "
        "the minimum gap between their joins; not shown"
    ]
    assert placed(clock, bar(45))[0][1] is None
    assert placed(clock, bar(46))[1] == []  # offset >= the clock's depth + r - R (= 46)
    top = req("a", "top", "start", length=168, depth=46)
    left = req("b", "left", "start", length=168, depth=46)
    assert placed(top, left)[0][1] is None
    assert placed(top, req("b", "left", "start", offset=46, length=168, depth=46))[1] == []


def test_warnings_come_in_config_order_whatever_the_edge():
    _, warnings = placed(req(pos=0), req("clock", "top", pos=0, length=168, depth=46))
    assert [w.split(" ")[0] for w in warnings] == ["monitors.X.panels.0", "monitors.X.panels.1"]
```

Run: `scripts/py -m pytest -q tests/test_layout_resolver.py`
Expected: FAIL (`ImportError: cannot import name 'free_span'`).

- [ ] **Step 2: Replace `shell/panel_layout.py`**

```python
"""Panel layout (spec 16-17): every panel of one monitor resolved to an exact body start and
length, from align / offset / order / gap, keeping the minimum geometry the single-outline
canvas needs. Pure: no GTK.

Per edge (`layout_edge`):

1. Free span. A body must stay `T + R + r` from each end of the edge (`r` = its join radius
   at full depth), so its fillet never reaches into a screen-corner arc. A free span shorter
   than MIN_LENGTH hides the panel.
2. Lengths. px as given (other length modes: the widget's default px for now). A length
   longer than the free span is shrunk to it (warning).
3. Slots. start / center / end, each sorted by (order, config index). Neighbours in the
   sequence start -> center -> end are `r1 + r2 + gap` apart. The start slot packs from the
   start of the free span, the end slot from its end (its first panel nearest the end); each
   panel's `offset` is extra space before it, counted from the end (first panel) or from its
   neighbour. The center slot is centred on the edge as one group and pushed clear of the
   start and end groups; its first panel's offset then shifts the group from there (a
   negative offset on a later center panel counts as 0).
4. `pos` (deprecated alias): the panel is placed alone at `pos` px from the start of the
   edge, clamped into its free span (warning); it takes no part in the slots.

Across the monitor (`layout_monitor`): panels are checked in config order; a panel whose body
box (full depth, from the screen edge, grown by its `r`) overlaps an earlier panel's is not
shown (warning). On one edge that is the minimum gap `r1 + r2`; it also catches deep panels on
neighbouring edges (two panels meeting at a shared screen corner at offset 0 always collide:
one needs an offset of at least the other's depth + r - R), and `pos` panels dropped onto
slotted ones. Touching is allowed. A hidden panel keeps the slot space it was given: its
neighbours do not close up.

Every warning names the key path (`where`.panels.N (widget)).

`resolve_layout` is the interim rule set (pos only) that MonitorShell still uses; it goes when
MonitorShell switches to `layout_monitor`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from itertools import pairwise

from shell import geometry
from shell.config.models import Edge
from shell.panel_spec import PanelGeometry, PanelRequest

MIN_LENGTH = 60  # same floor as the config model's px lengths
EDGES: tuple[Edge, ...] = ("top", "right", "bottom", "left")

Box = tuple[float, float, float, float]  # x0, y0, x1, y1
Note = tuple[int, str]  # (config index, warning)


@dataclass(frozen=True)
class Layout:
    panels: list[PanelGeometry | None]  # config order; None = not shown
    warnings: list[str]


def free_span(extent: int, thickness: int, radius: int, depth: int) -> tuple[int, int]:
    """(first, last) px along the edge a body of this depth may occupy (corner clearance)."""
    clearance = thickness + radius + geometry.join_radius(depth, radius)
    return math.ceil(clearance), math.floor(extent - clearance)


@dataclass
class _Item:
    index: int
    req: PanelRequest
    name: str
    lo: int
    hi: int
    r: float
    length: int = 0
    pos: int = 0


def _wanted(it: _Item, natural: Mapping[int, int]) -> int:
    spec = it.req.length
    return spec if isinstance(spec, int) else it.req.fallback_length


def _fit(it: _Item, length: int, notes: list[Note]) -> int:
    length = max(length, MIN_LENGTH)
    span = it.hi - it.lo
    if length > span:
        notes.append(
            (
                it.index,
                f"{it.name}: length {length} px does not fit the {it.req.edge} edge; "
                f"shrunk to {span}",
            )
        )
        length = span
    return length


def _clamp(it: _Item, wanted: int, what: str | None, notes: list[Note]) -> int:
    """Keep the body inside its free span; `what` names the user value for the warning."""
    pos = min(max(wanted, it.lo), it.hi - it.length)
    if what is not None and pos != wanted:
        notes.append(
            (it.index, f"{it.name}: {what} would run into a screen corner; moved to {pos}")
        )
    return pos


def layout_edge(
    entries: Sequence[tuple[int, PanelRequest]],
    extent: int,
    thickness: int,
    radius: int,
    gap: int,
    natural: Mapping[int, int] | None = None,
    where: str = "monitor",
) -> tuple[dict[int, tuple[int, int] | None], list[Note]]:
    """Resolve the panels of ONE edge. `entries` are (config index, request) pairs; returns
    {index: (pos, length) or None when the edge has no room} and (index, warning) notes."""
    natural = natural or {}
    out: dict[int, tuple[int, int] | None] = {}
    notes: list[Note] = []
    items: list[_Item] = []
    for index, req in entries:
        name = f"{where}.panels.{index} ({req.widget})"
        lo, hi = free_span(extent, thickness, radius, req.depth)
        if hi - lo < MIN_LENGTH:
            notes.append(
                (index, f"{name}: the {req.edge} edge ({extent} px) has no room for it; not shown")
            )
            out[index] = None
            continue
        items.append(_Item(index, req, name, lo, hi, geometry.join_radius(req.depth, radius)))

    def space(a: _Item, b: _Item) -> float:
        return a.r + b.r + gap

    def slot(align: str) -> list[_Item]:
        chosen = [it for it in items if it.req.pos is None and it.req.align == align]
        return sorted(chosen, key=lambda it: (it.req.order, it.index))

    start, center, end = slot("start"), slot("center"), slot("end")
    for it in items:
        if it.req.length != "fill":
            it.length = _fit(it, _wanted(it, natural), notes)

    cursor: float = start[0].lo if start else 0
    for k, it in enumerate(start):
        wanted = math.ceil(cursor + it.req.offset)
        it.pos = _clamp(it, wanted, f"offset {it.req.offset}" if it.req.offset else None, notes)
        if k + 1 < len(start):
            cursor = it.pos + it.length + space(it, start[k + 1])
    cursor = end[0].hi if end else 0
    for k, it in enumerate(end):
        wanted = math.floor(cursor - it.req.offset - it.length)
        it.pos = _clamp(it, wanted, f"offset {it.req.offset}" if it.req.offset else None, notes)
        if k + 1 < len(end):
            cursor = it.pos - space(it, end[k + 1])
    if center:
        head, shift = center[0], center[0].req.offset
        inner = sum(space(a, b) for a, b in pairwise(center))
        total = math.ceil(
            sum(it.length for it in center)
            + inner
            + sum(max(0, it.req.offset) for it in center[1:])
        )
        left = (
            math.ceil(start[-1].pos + start[-1].length + space(start[-1], head))
            if start
            else head.lo
        )
        right = math.floor(end[-1].pos - space(center[-1], end[-1])) if end else center[-1].hi
        base = max(left, min((extent - total) // 2, right - total))  # without the offset
        first = max(left, min(base + shift, right - total))
        if shift and first != base + shift:
            notes.append(
                (
                    head.index,
                    f"{head.name}: offset {shift} would run into a screen corner or a "
                    f"neighbour; moved to {first}",
                )
            )
        cursor = first
        for k, it in enumerate(center):
            if k:
                cursor = math.ceil(cursor + space(center[k - 1], it) + max(0, it.req.offset))
            it.pos = min(max(int(cursor), it.lo), it.hi - it.length)
            cursor = it.pos + it.length
    for it in items:
        if it.req.pos is not None:
            it.pos = _clamp(it, it.req.pos, f"pos {it.req.pos}", notes)
    for it in items:
        out[it.index] = (it.pos, it.length)
    return out, notes


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


def layout_monitor(
    requests: Sequence[PanelRequest],
    width: int,
    height: int,
    thickness: int,
    radius: int,
    gap: int,
    natural: Mapping[int, int] | None = None,
    where: str = "monitor",
) -> Layout:
    """Resolve every panel of one monitor. `natural` maps a config index to the measured
    length of a "content" panel; `where` prefixes warnings, e.g. "monitors.HDMI-A-1"."""
    resolved: dict[int, tuple[int, int] | None] = {}
    notes: list[Note] = []
    for edge in EDGES:
        entries = [(i, req) for i, req in enumerate(requests) if req.edge == edge]
        if entries:
            extent = width if geometry.is_horizontal(edge) else height
            got, edge_notes = layout_edge(entries, extent, thickness, radius, gap, natural, where)
            resolved.update(got)
            notes.extend(edge_notes)
    out: list[PanelGeometry | None] = []
    placed: list[tuple[int, PanelGeometry, Box]] = []
    for i, req in enumerate(requests):
        got = resolved[i]
        if got is None:
            out.append(None)
            continue
        geo = PanelGeometry(req.widget, req.edge, got[0], got[1], req.depth, req.state, req.label)
        box = _grown_body(geo, width, height, thickness, geometry.join_radius(req.depth, radius))
        clash = next(((j, other) for j, other, b in placed if _overlap(box, b)), None)
        if clash is not None:
            notes.append(
                (
                    i,
                    f"{where}.panels.{i} ({req.widget}): overlaps {where}.panels.{clash[0]} "
                    f"({clash[1].widget}) or leaves less than the minimum gap between their "
                    "joins; not shown",
                )
            )
            out.append(None)
            continue
        placed.append((i, geo, box))
        out.append(geo)
    notes.sort(key=lambda note: note[0])  # stable: per panel, in the order they arose
    return Layout(out, [message for _, message in notes])


def resolve_layout(
    geos: list[PanelGeometry],
    width: int,
    height: int,
    thickness: int,
    radius: int,
    where: str = "monitor",
) -> Layout:
    """Interim rules (pos only). `where` prefixes warnings, e.g. "monitors.HDMI-A-1"."""
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

(The interim `resolve_layout` body is byte-for-byte the old one, so `tests/test_panel_layout.py` and `MonitorShell` keep passing; only its docstring line changed.)

- [ ] **Step 3: Run the tests**

Run: `scripts/py -m pytest -q tests/test_layout_resolver.py tests/test_panel_layout.py`
Expected: all pass.

- [ ] **Step 4: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell/panel_layout.py tests/test_layout_resolver.py
git commit -m "feat(layout): resolver core with align slots, order, gap, offset and pos" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Length modes: percent, content, fill, min/max

**Files:**
- Modify: `shell/panel_layout.py` (docstring items 2 and 4, constants, `_wanted`, `_fit`, the fill block in `layout_edge`, the center-offset warning condition, the `pos` loop)
- Test: `tests/test_layout_resolver.py`

**Interfaces:**
- Consumes: Task 3.
- Produces: `CONTENT_PAD = 12`; `content_length(natural: int) -> int` (= `max(MIN_LENGTH, natural + 2 * CONTENT_PAD)`, used by `EdgePanel.natural_length` in Task 7); `layout_edge` / `layout_monitor` honour `"NN%"` (of the panel's own free span), `"content"` (`natural[index]`, else `fallback_length`), `"fill"` (decision 4; a fill that is the first center panel gives up `abs(offset)` px and moves that way, without a warning), `min_length` / `max_length` and the 60 px floor for every mode; a `pos` panel with `"fill"` runs to the end of its free span. Signatures unchanged.

- [ ] **Step 1: Write the failing tests**

In `tests/test_layout_resolver.py` replace the import line `from shell.panel_layout import free_span, layout_edge, layout_monitor` with:

```python
from shell.panel_layout import (
    CONTENT_PAD,
    MIN_LENGTH,
    content_length,
    free_span,
    layout_edge,
    layout_monitor,
)
```

and append:

```python
# ---- length modes ---------------------------------------------------------------------


def test_content_length_pads_the_natural_size_and_keeps_the_floor():
    assert content_length(200) == 200 + 2 * CONTENT_PAD
    assert content_length(5) == MIN_LENGTH


def test_percent_is_of_the_free_span():
    assert placed(req(length="50%"))[0] == [((W - 922) // 2, 922)]  # 50% of 1844


def test_percent_below_the_floor_gets_the_floor():
    assert placed(req(length="1%"))[0][0][1] == MIN_LENGTH


def test_min_and_max_clamp_every_mode():
    assert placed(req(length="50%", max_length=600))[0][0][1] == 600
    assert placed(req(length=300, min_length=400))[0][0][1] == 400
    assert placed(req(length="fill", max_length=500))[0] == [(710, 500)]


def test_min_length_beyond_the_free_span_is_shrunk_with_a_warning():
    got, warnings = placed(req("bar", "right", length=300, min_length=2000, depth=56))
    assert got == [(38, 1004)] and "length 2000 px does not fit" in warnings[0]


def test_content_uses_the_measured_length_or_the_fallback():
    assert placed(req(length="content", fallback=300))[0][0][1] == 300
    assert placed(req(length="content"), natural={0: 240})[0][0][1] == 240


def test_fill_alone_spans_the_free_span():
    assert placed(req(length="fill")) == ([(38, 1844)], [])


def test_fill_takes_what_the_neighbours_leave():
    a = req("a", "top", "start", length=168, depth=46)
    f = req("f", "top", length="fill", depth=46)
    c = req("c", "top", "end", length=168, depth=46)
    got, warnings = placed(a, f, c)
    assert got == [(38, 168), (242, 1436), (1714, 168)] and warnings == []
    assert 242 - (38 + 168) == 36 and 1714 - (242 + 1436) == 36  # joins + gap either side


def test_fills_share_equally_and_the_first_gets_the_odd_pixel():
    a = req("a", "top", length="fill", depth=46)
    b = req("b", "top", length="fill", depth=46)
    assert placed(a, b, gap=9)[0] == [(38, 904), (38 + 904 + 37, 903)]


def test_a_fill_without_room_gets_the_floor_and_the_later_neighbour_goes():
    a = req("a", "top", "start", length=1100, depth=46)
    fill = req("f", "top", length="fill", depth=46)
    c = req("c", "top", "end", length=700, depth=46)
    got, warnings = placed(a, fill, c)
    assert got == [(38, 1100), (38 + 1100 + 36, MIN_LENGTH), None]
    assert warnings == [
        "monitors.X.panels.2 (c): overlaps monitors.X.panels.1 (f) or leaves less than the "
        "minimum gap between their joins; not shown"
    ]


def test_fill_with_a_pos_runs_to_the_end_of_the_free_span():
    assert placed(req("bar", "right", pos=600, length="fill", depth=56))[0] == [(600, 442)]


@pytest.mark.parametrize(("offset", "expected"), [(100, (138, 1744)), (-100, (38, 1744))])
def test_a_centred_fill_gives_up_its_offset_and_moves_that_way(offset, expected):
    assert placed(req(length="fill", offset=offset)) == ([expected], [])


def test_a_centred_fill_between_neighbours_leaves_its_offset_free_before_it():
    a = req("a", "top", "start", length=168, depth=46)
    f = req("f", "top", offset=40, length="fill", depth=46)
    c = req("c", "top", "end", length=168, depth=46)
    assert placed(a, f, c) == ([(38, 168), (282, 1396), (1714, 168)], [])


def test_a_smaller_monitor_recentres_rescales_and_clamps():
    got, warnings = placed(
        req(),
        req("p", "top", length="50%", depth=46),
        req("bar", "right", pos=600, length=300, depth=56),
        width=1280,
        height=720,
    )
    assert got == [(360, 560), ((1280 - 602) // 2, 602), (382, 300)]
    assert warnings == [
        "monitors.X.panels.2 (bar): pos 600 would run into a screen corner; moved to 382"
    ]
```

Run: `scripts/py -m pytest -q tests/test_layout_resolver.py`
Expected: FAIL (`ImportError: cannot import name 'CONTENT_PAD'`).

- [ ] **Step 2: Implement in `shell/panel_layout.py`**

1. Docstring item 2: replace

```
2. Lengths. px as given (other length modes: the widget's default px for now). A length
   longer than the free span is shrunk to it (warning).
```

with

```
2. Lengths. px as given; "NN%" of the panel's own free span; "content" = the measured natural
   length (`natural[index]`, the widget's default px until measured); then min_length /
   max_length and the MIN_LENGTH floor. "fill" panels share what the slotted neighbours, the
   offsets and the spacing leave, equally (the first fill gets the odd pixels). A length
   longer than the free span is shrunk to it (warning).
```

2. Docstring item 4: replace `edge, clamped into its free span (warning); it takes no part in the slots.` with

```
   edge, clamped into its free span (warning); it takes no part in the slots or the fill
   (a `pos` panel with length "fill" runs to the end of its free span).
```

3. After `MIN_LENGTH = 60  # same floor as the config model's px lengths` add `CONTENT_PAD = 12  # body px on each side of a "content" panel's natural size`.
4. Before `def free_span(` add:

```python
def content_length(natural: int) -> int:
    """Body length for a widget whose content is `natural` px long along the edge."""
    return max(MIN_LENGTH, natural + 2 * CONTENT_PAD)


```

5. Replace `_wanted` and the first line of `_fit` (`length = max(length, MIN_LENGTH)`) so they read:

```python
def _wanted(it: _Item, natural: Mapping[int, int]) -> int:
    spec = it.req.length
    if spec == "content":
        return natural.get(it.index, it.req.fallback_length)
    if isinstance(spec, str):  # "NN%" (the model only lets through px, fill, content, NN%)
        return round((it.hi - it.lo) * float(spec[:-1]) / 100)
    return spec


def _fit(it: _Item, length: int, notes: list[Note]) -> int:
    length = max(length, MIN_LENGTH, it.req.min_length or 0)
    if it.req.max_length is not None:
        length = min(length, it.req.max_length)
```

(the rest of `_fit` is unchanged).

6. In `layout_edge` replace

```python
    start, center, end = slot("start"), slot("center"), slot("end")
    for it in items:
        if it.req.length != "fill":
            it.length = _fit(it, _wanted(it, natural), notes)
```

with

```python
    start, center, end = slot("start"), slot("center"), slot("end")
    seq = start + center + end[::-1]  # left to right (top to bottom)
    for it in items:
        if it.req.length != "fill":
            it.length = _fit(it, _wanted(it, natural), notes)
    fills = [it for it in seq if it.req.length == "fill"]
    if fills:
        fixed = sum(it.length for it in seq if it.req.length != "fill")
        gaps = sum(space(a, b) for a, b in pairwise(seq))
        offsets = sum(it.req.offset for it in start + end) + sum(
            max(0, it.req.offset) for it in center[1:]
        )
        if center and center[0].req.length == "fill":  # it gives up its offset (see below)
            offsets += abs(center[0].req.offset)
        room = math.floor(seq[-1].hi - seq[0].lo - fixed - gaps - offsets)
        share, extra = divmod(max(0, room), len(fills))
        for k, it in enumerate(fills):
            it.length = _fit(it, share + (extra if k == 0 else 0), notes)
```

(The center group's offset is not in the sum: it only shifts the group. A fill that is the first center panel is the exception: it leaves `abs(offset)` px free so the shift has room; decision 4.)

7. In the center block of `layout_edge` replace `        if shift and first != base + shift:` with

```python
        if shift and first != base + shift and head.req.length != "fill":
```

(a fill took its offset as room: the clamp only decides which side the free space is on, so it is no warning).

8. Replace the `pos` loop body

```python
        if it.req.pos is not None:
            it.pos = _clamp(it, it.req.pos, f"pos {it.req.pos}", notes)
```

with

```python
        if it.req.pos is not None:
            if it.req.length == "fill":
                it.length = _fit(it, it.hi - max(it.req.pos, it.lo), notes)
            it.pos = _clamp(it, it.req.pos, f"pos {it.req.pos}", notes)
```

- [ ] **Step 3: Run the tests**

Run: `scripts/py -m pytest -q tests/test_layout_resolver.py`
Expected: all pass.

- [ ] **Step 4: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell/panel_layout.py tests/test_layout_resolver.py
git commit -m "feat(layout): fill, content and percentage lengths with min/max" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: MonitorShell on the new resolver; the interim rules go

**Files:**
- Modify: `shell/monitors.py:24-26` (imports), `shell/monitors.py:143-152` (`_layout`)
- Modify: `shell/panel_layout.py` (drop `resolve_layout`, its docstring paragraph and the `replace` import)
- Modify: `shell/panel_spec.py` (`PanelGeometry`)
- Modify: `shell/registry.py` (drop `resolve_panel`, `panels_for`; import)
- Modify: `shell/geometry.py:80-85` (`anchor_and_margin`)
- Modify: `shell/edge_panel.py:45-46` (docstring)
- Modify: `widgets/system_bar.py:16-19` (default placement, decision 10)
- Test: `tests/test_panel_layout.py` (rewrite), `tests/test_monitor_shell.py`, `tests/test_registry.py`, `tests/test_geometry.py`, `tests/test_canvas_stats.py`

**Interfaces:**
- Consumes: `layout_monitor` (Tasks 3-4), `requests_for` and `Config.layout_for` (Tasks 1-2).
- Produces: `PanelGeometry.pos: int` (always resolved); `geometry.anchor_and_margin(edge: Edge, pos: int, along: int, radius: int, extent: int) -> tuple[str, str]` (no `None` branch: every panel is anchored at its edge's start with a margin); `MonitorShell._layout(config, theme) -> Layout` uses `requests_for`, `config.layout_for(self.name).gap`; `shell.registry` exports `register`, `widget_names`, `widget_class`, `request_for`, `requests_for`, `validate_widgets` only.

- [ ] **Step 1: Port the tests (they fail until Step 2)**

1. Replace `tests/test_panel_layout.py` with the pixel tests, now driven through `layout_monitor` (the rule tests moved to `tests/test_layout_resolver.py`):

```python
"""The layout's minimum geometry renders correctly (spec 17): pixel tests pin panels placed by
shell.panel_layout at the rule boundaries to the legacy per-window renderers. The rules
themselves are in tests/test_layout_resolver.py."""

import cairo
import pytest

from shell import geometry as g
from shell.canvas.outline import fill_mass
from shell.panel_layout import layout_monitor
from shell.panel_spec import PanelRequest
from tests.legacy_draw import draw_panel, draw_screen_corner

T, R = 10, 14
SW, SH = 400, 300
RGBA = (0.04, 0.05, 0.05, 1.0)
EDGES = ["top", "bottom", "left", "right"]


def req(edge, align="center", offset=0, pos=None, length=120, depth=50):
    return PanelRequest(
        "p", edge, align, offset, pos, 0, length, None, None, depth, "extended", "p", length
    )


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


def resolved(*requests, gap=8):
    layout = layout_monitor(list(requests), SW, SH, T, R, gap)
    assert None not in layout.panels and layout.warnings == []
    return layout.panels


def as_outline(panels, d_fraction=1.0):
    return [(p.edge, p.pos, p.length, p.depth, p.depth * d_fraction) for p in panels]


@pytest.mark.parametrize("edge", EDGES)
@pytest.mark.parametrize("fraction", [1.0, 0.5, 0.2])
def test_start_aligned_panel_at_the_corner_renders_like_legacy(edge, fraction):
    (p,) = resolved(req(edge, "start"))
    assert p.pos == T + R + 14
    panels = as_outline([p], fraction)
    assert bad_pixels(legacy(panels), outline(panels)) <= 2


@pytest.mark.parametrize("edge", EDGES)
@pytest.mark.parametrize("fraction", [1.0, 0.5, 0.2])
def test_end_aligned_panel_next_to_the_corner_renders_like_legacy(edge, fraction):
    (p,) = resolved(req(edge, "end"))
    extent = SW if g.is_horizontal(edge) else SH
    assert p.pos + p.length == extent - (T + R + 14)  # exactly at the clearance
    panels = as_outline([p], fraction)
    assert bad_pixels(legacy(panels), outline(panels)) <= 2


def test_pos_clamped_to_the_corner_renders_like_legacy():
    layout = layout_monitor([req("top", pos=0)], SW, SH, T, R, 8)
    assert layout.panels[0].pos == T + R + 14 and len(layout.warnings) == 1
    panels = as_outline(layout.panels)
    assert bad_pixels(legacy(panels), outline(panels)) <= 2


@pytest.mark.parametrize(
    "panels",
    [
        [("top", 20, 120, 50, 50.0)],  # start: pos - r = 6 < T + R, the fillet hits the arc
        [("top", SW - 20 - 120, 120, 50, 50.0)],  # end: the same at the other corner
    ],
)
def test_without_the_clearance_the_outline_breaks_inside_the_corner_arc(panels):
    assert bad_pixels(legacy(panels), outline(panels)) > 20


@pytest.mark.parametrize("fraction", [1.0, 0.6, 0.3])
def test_slot_neighbours_at_gap_zero_render_like_legacy(fraction):
    a = req("top", "start", offset=22, length=100)
    b = req("top", "start", length=80)
    pa, pb = resolved(a, b, gap=0)
    assert (pa.pos, pb.pos) == (60, 60 + 100 + 28)  # touching joins: r1 + r2 apart
    panels = as_outline([pa, pb], fraction)
    assert bad_pixels(legacy(panels), outline(panels)) <= 2
```

2. In `tests/test_monitor_shell.py` replace `test_panel_that_breaks_the_layout_rules_is_hidden_and_reported` (two centred docks are now packed side by side, so the overlap needs a `pos`) by:

```python
def test_two_centred_panels_on_one_edge_are_both_shown(build):
    shell, _, _ = build(edge({"widget": "dock"}, {"widget": "dock", "length": 300}))
    a, b = shell.panels
    assert a.args[0].pos + 560 + 14 + 14 + 8 == b.args[0].pos  # packed: joins + default gap
    assert shell.layout_warnings == [] and len(shell.canvas.shapes) == 2


def test_panel_that_breaks_the_layout_rules_is_hidden_and_reported(build):
    shell, _, _ = build(edge({"widget": "dock"}, {"widget": "dock", "pos": 700}))
    assert shell.panels[1] is None and len(shell.canvas.shapes) == 1
    assert "monitors.HDMI-A-1.panels.1 (dock): overlaps" in shell.layout_warnings[0]
```

and in `test_a_neighbour_change_rebuilds_the_panel_it_unhides` replace its first lines up to the `make_config(` argument so the test reads:

```python
def test_a_neighbour_change_rebuilds_the_panel_it_unhides(build, make_config):
    shell, _, _ = build(edge({"widget": "dock"}, {"widget": "dock", "pos": 700}))
    assert shell.panels[1] is None
    shell.apply(
        make_config(
            monitors=edge({"widget": "dock", "align": "end"}, {"widget": "dock", "pos": 700})
        ),
        [Change("panel-rebuild", "HDMI-A-1", 0)],
    )
    assert shell.panels[1] is not None and shell.layout_warnings == []
    assert len(shell.canvas.shapes) == 2
```

and append (gap through the monitor's layout table, and a `relayout` reload):

```python
def test_the_monitor_gap_spaces_slotted_panels(build):
    mons = edge({"widget": "clock", "align": "start"}, {"widget": "clock", "align": "start"})
    mons["HDMI-A-1"]["layout"] = {"gap": 30}
    shell, _, _ = build(mons)
    a, b = (p.args[0] for p in shell.panels)
    assert b.pos - (a.pos + a.length) == 14 + 14 + 30


def test_a_gap_change_moves_the_neighbours(build, make_config):
    two = edge({"widget": "clock", "align": "start"}, {"widget": "clock", "align": "start"})
    shell, _, _ = build(two)
    first, second = shell.panels
    wider = edge({"widget": "clock", "align": "start"}, {"widget": "clock", "align": "start"})
    wider["HDMI-A-1"]["layout"] = {"gap": 40}
    shell.apply(make_config(monitors=wider), [Change("relayout", "HDMI-A-1")])
    assert shell.panels[0] is first and not first.destroyed  # did not move: kept
    assert second.destroyed and shell.panels[1].args[0].pos == second.args[0].pos + 32
```

3. In `tests/test_registry.py`: change the import to `from shell.panel_spec import PanelDefaults, PanelRequest`; delete `test_resolve_uses_widget_defaults`, `test_overrides_win`, `test_pos_default_override_and_center`, `test_unknown_widget_lists_known` and `test_panels_for_keeps_order_and_duplicates` (Task 2's `request_for` tests cover them).
4. In `tests/test_geometry.py` delete `test_anchor_centered_has_single_edge_and_no_margin` (there is no centred anchoring any more).
5. In `tests/test_canvas_stats.py`, in `test_default_shapes_fit_the_simulated_surface`, replace the lines from `from shell.panel_layout import resolve_layout` to `layout = resolve_layout(geos, w, h, 10, 14)` with:

```python
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
```

Run: `scripts/py -m pytest -q tests/test_monitor_shell.py tests/test_panel_layout.py`
Expected: FAIL (the shell still uses the interim rules: two centred docks hide the second; `layout` table ignored).

- [ ] **Step 2: Switch the code**

1. `shell/monitors.py` imports: `from shell.panel_layout import Layout, layout_monitor` and `from shell.registry import requests_for, widget_class`; `_layout` becomes:

```python
    def _layout(self, config: Config, theme) -> Layout:
        g = self.monitor.get_geometry()
        return layout_monitor(
            requests_for(config, self.name),
            g.width,
            g.height,
            theme.thickness,
            theme.radius,
            config.layout_for(self.name).gap,
            where=f"monitors.{self.name}",
        )
```

(`_sync_panels`, `_new_panel` and `apply` are unchanged: they already rebuild every panel whose resolved `PanelGeometry` changed, which covers neighbours moved by a gap, order or fill change.)

2. `shell/panel_layout.py`: delete the `resolve_layout` function, delete the docstring paragraph that starts with `` `resolve_layout` is the interim rule set``, and change `from dataclasses import dataclass, replace` to `from dataclasses import dataclass`.
3. `shell/panel_spec.py`, class `PanelGeometry`: docstring `"""A panel resolved by shell.panel_layout: exact body start and length in px."""` and `pos: int`.
4. `shell/registry.py`: delete `resolve_panel` and `panels_for`; import line `from shell.panel_spec import PanelDefaults, PanelRequest`.
5. `shell/geometry.py`: replace the head of `anchor_and_margin` (signature, docstring and the `if pos is None` branch) so it reads:

```python
def anchor_and_margin(
    edge: Edge, pos: int, along: int, radius: int, extent: int
) -> tuple[str, str]:
    """Layer-shell anchor string and margin string for a panel surface whose body starts at the
    resolved `pos` (shell.panel_layout), measured from the start of the edge."""
    offset = max(0, pos - radius)  # the body starts `radius` into the surface
```

(the remaining three lines are unchanged).
6. `shell/edge_panel.py`, `__init__` docstring:

```python
        """`spec` is resolved by shell.panel_layout (exact pos and length in px); `on_depth(d)`
        is called on every animation frame with the current depth (MonitorShell forwards it to
        the canvas)."""
```

7. `widgets/system_bar.py`: the `@register(...)` call becomes

```python
@register(
    "system_bar",
    # y = 600 on a 1080 px tall monitor (free span ends at 1042: 1042 - 142 - 300 = 600)
    PanelDefaults(edge="right", length=300, depth=56, label="system bar", align="end", offset=142),
)
```

- [ ] **Step 3: Run the tests**

Run: `scripts/py -m pytest -q tests/test_monitor_shell.py tests/test_panel_layout.py tests/test_layout_resolver.py tests/test_registry.py tests/test_geometry.py tests/test_canvas_stats.py tests/test_canvas_outline.py`
Expected: all pass. Then `grep -rn -e resolve_layout -e panels_for -e resolve_panel shell widgets tests main.py` prints nothing.

- [ ] **Step 4: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell/monitors.py shell/panel_layout.py shell/panel_spec.py shell/registry.py shell/geometry.py shell/edge_panel.py widgets/system_bar.py tests/test_panel_layout.py tests/test_monitor_shell.py tests/test_registry.py tests/test_geometry.py tests/test_canvas_stats.py
git commit -m "feat(layout): MonitorShell resolves panels with layout_monitor; interim rules removed" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: GATE A (Phil, HDMI-A-1): slots, end anchoring, order, gap, reload, old configs

**Files:**
- Create: `examples/layout-test.toml`

**Interfaces:**
- Consumes: Tasks 1-5; no code changes.

- [ ] **Step 1: Create the example config**

```toml
# Gate A (layout plan): several panels per edge, on HDMI-A-1 only (DP-1 is left alone).
#   cp examples/layout-test.toml /tmp/edge-layout.toml
#   scripts/py main.py --config /tmp/edge-layout.toml -v      (edit the copy while it runs)
[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]    # 0: centre of the bottom edge (the dock's default)
widget = "dock"

[[monitors.HDMI-A-1.panels]]    # 1: bottom-left, next to the corner
widget = "clock"
edge = "bottom"
align = "start"

[[monitors.HDMI-A-1.panels]]    # 2: bottom-right, next to the corner
widget = "clock"
edge = "bottom"
align = "end"

[[monitors.HDMI-A-1.panels]]    # 3: top centre slot, second (order 1)
widget = "clock"
order = 1

[[monitors.HDMI-A-1.panels]]    # 4: top centre slot, first (order 0), shorter
widget = "clock"
length = 120

[[monitors.HDMI-A-1.panels]]    # 5: right edge, 60 px up from the bottom end
widget = "system_bar"
align = "end"
offset = 60
```

Check it loads and resolves without warnings (expected positions in the comment of each gate item below):

`scripts/py -c "import widgets; from pathlib import Path; from shell.config.loader import load_config; from shell.registry import requests_for; from shell.panel_layout import layout_monitor; c = load_config(Path('examples/layout-test.toml'), required=True); L = layout_monitor(requests_for(c, 'HDMI-A-1'), 1920, 1080, 10, 14, c.layout_for('HDMI-A-1').gap); print([(p.edge, p.pos, p.length) for p in L.panels], L.warnings)"`

Expected: `[('bottom', 680, 560), ('bottom', 38, 168), ('bottom', 1714, 168), ('top', 954, 168), ('top', 798, 120), ('right', 682, 300)] []`

- [ ] **Step 2: Commit**

```bash
git add examples/layout-test.toml
git commit -m "docs(examples): layout gate config with slots and end anchoring" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 3: GATE A (Phil)**

```bash
cp examples/layout-test.toml /tmp/edge-layout.toml
scripts/py main.py --config /tmp/edge-layout.toml -v
```
Edit `/tmp/edge-layout.toml` while it runs; each save applies within about a second.

1. **Bottom edge, three panels:** the dock is centred (x 680..1240); a clock sits at each bottom corner (x 38..206 and 1714..1882). At both corners the screen-corner arc flows straight into the clock's join: no notch, no bump, no stray fill.
2. **Top centre slot:** two clocks side by side as one centred group, the 120 px one on the left (order 0), the 168 px one on the right; between them exactly an 8 px straight piece of frame between the two curved joins.
3. **Right edge:** the system bar ends 60 px above the end of the free span (y 682..982), its lower join clear of the bottom-right clock's join.
   - **Shared screen corner (decision 3):** set panel 5's `offset = 0` and save: the bar disappears and a "Panels adjusted" notification says `monitors.HDMI-A-1.panels.5 (system_bar): overlaps monitors.HDMI-A-1.panels.2 (clock) or leaves less than the minimum gap between their joins; not shown`; nothing is drawn crossed in the bottom-right corner. Set `offset = 46` (the clock's depth) and save: the bar is back at y 696..996, its lower join just clear of the clock's. Set `offset = 60` again.
4. **Behaviour unchanged:** click, hover peek and drag still work on a top clock, a bottom clock and the system bar; collapsed handles are visible.
5. **Gap reload:** add `[monitors.HDMI-A-1.layout]` with `gap = 40` right after `shell = "edge"` and save: only the two top clocks move apart (32 px more); the bottom panels and the system bar do not flicker or rebuild. Remove it and save: back. Note whether the moving clocks' rebuild flicker is acceptable (decision 7).
6. **Order:** change panel 3's `order = 1` to `order = 0` and save: equal order keeps config order, so the 168 px clock moves to the left of the 120 px one. Undo.
7. **`pos` alias and its conflict:** in panel 1 replace `align = "start"` by `pos = 300` and save: the left clock moves to x = 300 (old `pos` semantics). Now add `align = "start"` back while `pos = 300` is still there and save: a "Config not applied" notification names `monitors.HDMI-A-1.panels.1` and says `pos cannot be combined with align or offset`; the previous look stays. Remove `pos = 300` and save: back at the corner.
8. **Overlap:** append a seventh panel (`[[monitors.HDMI-A-1.panels]]`, `widget = "dock"`, `pos = 700`) and save: a "Panels adjusted" notification says `monitors.HDMI-A-1.panels.6 (dock): overlaps monitors.HDMI-A-1.panels.0 (dock) …; not shown`; nothing else changes. Remove it and save: no new notification.
9. **Old configs look identical:** quit (Ctrl+C) and run `scripts/py main.py --config examples/panels-test.toml -v`: dock centred (x 680..1240), clock centred on the top edge (x 876..1044), system bar on the right at y 600..900, exactly as before this plan. Quit.
10. The `-v` logs have no errors (the warnings of items 7-8 are expected).

**On failure:** a wrong position -> compare with the expected list in Step 1 and the matching test in `tests/test_layout_resolver.py`; add a failing test reproducing the config before fixing. A broken corner or join -> screenshot plus config; reproduce with `tests/test_panel_layout.py`'s `legacy`/`outline` helpers first. A reload that rebuilds panels that did not move -> check `_sync_panels` and `diff_configs` (Task 2 tests). Item 9 differs -> stop: the backwards-compatibility rule (decision 2) is broken; compare `test_centred_panel_keeps_the_old_centring` and `test_the_system_bar_default_keeps_its_place`.

---

### Task 7: "content" lengths measured after build; content clipped in short bodies

**Files:**
- Modify: `shell/edge_panel.py:25` (import), after `HANDLE_LENGTH` (line 28) (`_centre_view`, `clip_container`), `shell/edge_panel.py:84-89` (content container), before `raise_to_top` (`natural_length`)
- Modify: `shell/monitors.py` (`__init__`, `_layout`, end of `_sync_panels`, `_new_panel`, new measurement methods, `apply`, `close`, module function `_measure_key`)
- Modify: `shell/app.py` (`__init__`, `sync_monitors`, `_reload`, new `_relayout_failed`)
- Test: `tests/test_monitor_shell.py`, `tests/test_edge_panel_drag.py`, `tests/test_app_sync.py`

**Interfaces:**
- Consumes: `content_length` (Task 4), `layout_monitor(..., natural=...)`.
- Produces:
  - `shell.edge_panel.clip_container(child: Gtk.Widget) -> Gtk.ScrolledWindow` (name `panel-clip`, both policies `EXTERNAL`, hexpand/vexpand, both adjustments' `changed` connected to `_centre_view`, `scroll-event` swallowed); `shell.edge_panel._centre_view(adjustment) -> None` (sets the value to `(lower + upper - page_size) / 2`)
  - `EdgePanel.natural_length() -> int` (content natural size along the edge + 2 x `CONTENT_PAD`, floor 60); attribute `EdgePanel._inner` (the widget from `build_content()`)
  - `MonitorShell(name, monitor, config, register_window, unregister_window=None, on_layout=None, on_error=None)`; `on_layout(shell)` is called after a re-layout the shell starts itself; `on_error(shell)` after such a re-layout raised (the exception is logged with its traceback and never reaches the main loop; decision 11)
  - `MonitorShell` attributes `_config`, `_theme`, `_requests: list[PanelRequest]`, `_natural: dict[int, tuple[tuple[str, bool], int]]`, `_remeasure: set[int]` (indices built since the last measurement, or all after a restyle), `_measure_id: int`; methods `_measured() -> dict[int, int]`, `_to_measure() -> list[int]`, `_schedule_measure()`, `_measure() -> bool`; module function `_measure_key(req: PanelRequest) -> tuple[str, bool]`
  - `EdgeShellApp.sync_monitors` passes `on_layout=lambda shell, n=name: self._report_layout(n, shell)` and `on_error=lambda shell, n=name: self._relayout_failed(n, shell)`; `EdgeShellApp._relayout_failed(name: str, shell) -> None`; `EdgeShellApp._relayout_rebuilt: set[str]` (monitors rebuilt after a failed re-layout since the last successful reload)

- [ ] **Step 1: Write the failing tests**

1. `tests/test_monitor_shell.py`:
   - In `FakeWindow.__init__` add `self.natural = 200` and `self.measured = 0` after `self.states = []`, and add the method:

     ```python
         def natural_length(self):
             self.measured += 1
             return self.natural
     ```

   - In `bare_shell` add `shell._measure_id = 0` before `return shell`.
   - Replace the timer part of the `build` fixture (from `timers = []` to the end of `_build`) with:

     ```python
         timers, idles, removed = [], [], []
         monkeypatch.setattr(
             mon_mod.GLib, "timeout_add", lambda ms, fn, *a: timers.append((ms, fn, a)) or len(timers)
         )
         monkeypatch.setattr(mon_mod.GLib, "idle_add", lambda fn: idles.append(fn) or 100 + len(idles))
         monkeypatch.setattr(mon_mod.GLib, "source_remove", removed.append)

         def _build(monitors, theme=None, on_layout=None, on_error=None):
             tracked = []
             cfg = make_config(monitors=monitors, theme=theme)
             shell = mon_mod.MonitorShell(
                 "HDMI-A-1", MONITOR, cfg, tracked.append, on_layout=on_layout, on_error=on_error
             )
             shell.test_idles, shell.test_removed = idles, removed
             return shell, tracked, timers
     ```

     (keep `return _build` after it).
   - In `test_failed_construction_closes_everything_already_built` add `monkeypatch.setattr(mon_mod.GLib, "idle_add", lambda *a: 1)` after the `timeout_add` patch.
   - Append:

     ```python
     # ---- "content" measurement ----------------------------------------------------------


     def test_content_panels_are_measured_when_idle_then_laid_out_again(build):
         reports = []
         shell, _, _ = build(edge({"widget": "dock", "length": "content"}), on_layout=reports.append)
         first = shell.panels[0]
         assert first.args[0].length == 560  # the widget's default until measured
         assert len(shell.test_idles) == 1 and reports == []
         first.natural = 300
         assert shell.test_idles[0]() is False  # one-shot
         rebuilt = shell.panels[0]
         assert first.destroyed and rebuilt.args[0].length == 300
         assert reports == [shell]
         rebuilt.natural = 300
         assert len(shell.test_idles) == 2  # the rebuilt panel is measured again
         assert shell.test_idles[1]() is False
         assert shell.panels[0] is rebuilt and reports == [shell]  # same size: nothing changes


     def test_no_measurement_without_content_panels(build):
         shell, _, _ = build(edge({"widget": "dock"}, {"widget": "clock", "length": "fill"}))
         assert shell.test_idles == []


     def test_a_measurement_belongs_to_its_widget(build, make_config):
         shell, _, _ = build(edge({"widget": "dock", "length": "content"}))
         shell.panels[0].natural = 300
         shell.test_idles[0]()
         shell.apply(make_config(monitors=edge({"widget": "clock", "length": "content"})), [])
         assert shell.panels[0].args[0].length == 168  # the clock's default, not the dock's 300


     def test_measuring_after_close_does_nothing(build):
         shell, _, _ = build(edge({"widget": "dock", "length": "content"}))
         pending = shell.test_idles[0]
         shell.close()
         assert 101 in shell.test_removed  # the pending idle was cancelled
         assert pending() is False


     def test_only_panels_built_since_the_last_measurement_are_measured(build, make_config):
         dock = {"widget": "dock", "length": "content"}
         clock = {"widget": "clock", "length": "content"}
         shell, _, _ = build(edge(dock, clock))
         shell.test_idles[0]()  # both measured at 200 px: both rebuilt
         shell.test_idles[1]()  # the rebuilt pair is measured once: nothing changes
         kept = shell.panels[0]
         seen = kept.measured
         shell.apply(
             make_config(monitors=edge(dock, {**clock, "min_length": 250})),
             [Change("panel-rebuild", "HDMI-A-1", 1)],
         )
         assert shell.panels[0] is kept and len(shell.test_idles) == 3
         assert shell.test_idles[2]() is False
         assert kept.measured == seen  # not rebuilt: not measured again
         assert shell.panels[1].measured == 1 and shell.panels[1].args[0].length == 250


     def test_a_restyle_measures_every_content_panel_again(build, make_config):
         panels = ({"widget": "dock", "length": "content"}, {"widget": "clock"})
         shell, _, _ = build(edge(*panels))
         shell.test_idles[0]()  # measured: rebuilt at 200 px
         shell.test_idles[1]()  # settled
         kept = shell.panels[0]
         kept.natural = 260  # the new theme's font is larger
         shell.apply(
             make_config(theme={"accent": "#112233"}, monitors=edge(*panels)),
             [Change("restyle", "HDMI-A-1")],
         )
         assert shell.panels[0] is kept and len(shell.test_idles) == 3
         shell.test_idles[2]()
         assert kept.destroyed and shell.panels[0].args[0].length == 260


     def test_a_failing_measurement_is_logged_and_reported(build, monkeypatch, caplog):
         errors, reports = [], []
         shell, _, _ = build(
             edge({"widget": "dock", "length": "content"}),
             on_layout=reports.append,
             on_error=errors.append,
         )
         shell.panels[0].natural = 300

         def explode(*a, **k):
             raise RuntimeError("widget broke")

         monkeypatch.setattr(mon_mod, "widget_class", lambda _w: explode)  # the rebuild raises
         assert shell.test_idles[0]() is False  # never raises into the main loop
         assert errors == [shell] and reports == []
         assert "widget broke" in caplog.text
     ```

2. `tests/test_edge_panel_drag.py`, append:

   ```python
   @pytest.mark.parametrize(("edge", "expected"), [("bottom", 200 + 24), ("right", 90 + 24)])
   def test_natural_length_measures_along_the_edge(edge, expected):
       s = SimpleNamespace(
           spec=SimpleNamespace(edge=edge),
           _inner=SimpleNamespace(
               get_preferred_width=lambda: (50, 200), get_preferred_height=lambda: (40, 90)
           ),
       )
       assert ep.EdgePanel.natural_length(s) == expected


   def test_clip_container_never_asks_for_the_content_size():
       from gi.repository import Gtk

       if not Gtk.init_check()[0]:
           pytest.skip("no display")
       content = Gtk.Box()
       content.set_size_request(800, 40)  # wider than any body it could be shrunk into
       clip = ep.clip_container(content)
       clip.show_all()  # visibility only; no window is created
       assert content.get_preferred_width() == (800, 800)
       assert tuple(clip.get_preferred_width()) == (0, 0)
       assert tuple(clip.get_preferred_height()) == (0, 0)
       assert clip.get_policy() == (Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.EXTERNAL)
       assert clip.get_child().get_child() is content  # inside the auto-added viewport
       h = clip.get_hadjustment()
       h.configure(0, 0, 800, 1, 10, 300)  # what the viewport sets for a 300 px long body
       assert h.get_value() == 250  # centred: 250 px cut off at each end
       h.set_page_size(500)  # the body got longer
       assert h.get_value() == 150


   def test_clipped_content_is_centred_in_the_body():
       values = []
       adjustment = SimpleNamespace(
           get_lower=lambda: 0.0,
           get_upper=lambda: 800.0,
           get_page_size=lambda: 300.0,
           set_value=values.append,
       )
       ep._centre_view(adjustment)
       assert values == [250.0]
   ```

3. `tests/test_app_sync.py`: `FakeShell.__init__` becomes

   ```python
       def __init__(
           self, name, monitor, config, register, unregister=None, on_layout=None, on_error=None
       ):
           self.name = name
           self.monitor = monitor
           self.on_layout = on_layout
           self.on_error = on_error
           FakeShell.opened.append(name)
   ```

   and in `test_shell_receives_unregister_callback` the inner `Capturing.__init__` signature becomes `def __init__(self, name, monitor, config, register, unregister=None, **callbacks):`. Append:

   ```python
   def test_a_relayout_started_by_the_shell_reports_through_the_app(env, monkeypatch):
       app, mapping = env
       notes = []
       monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, title, msg: notes.append(msg))
       mapping["HDMI-A-1"] = object()
       app.sync_monitors()
       shell = app.shells["HDMI-A-1"]
       shell.layout_warnings = ["monitors.HDMI-A-1.panels.0 (dock): shrunk"]
       shell.on_layout(shell)  # what MonitorShell calls after measuring or a geometry change
       assert notes == ["monitors.HDMI-A-1.panels.0 (dock): shrunk"]


   def test_a_failed_relayout_rebuilds_the_shell_once(env, monkeypatch):
       app, mapping = env
       notes = []
       monkeypatch.setattr(app_mod.EdgeShellApp, "_notify", lambda self, title, msg: notes.append(title))
       mapping["HDMI-A-1"] = object()
       app.sync_monitors()
       shell = app.shells["HDMI-A-1"]
       shell.on_error(shell)  # what MonitorShell calls when _measure or _relayout raised
       rebuilt = app.shells["HDMI-A-1"]
       assert rebuilt is not shell and notes == ["Panels rebuilt"]
       assert FakeShell.closed == ["HDMI-A-1"] and FakeShell.opened == ["HDMI-A-1", "HDMI-A-1"]
       rebuilt.on_error(rebuilt)  # fails again before the next reload: logged, shell kept
       shell.on_error(shell)  # a late call from the closed shell: ignored
       assert app.shells["HDMI-A-1"] is rebuilt and FakeShell.closed == ["HDMI-A-1"]
   ```

Run: `scripts/py -m pytest -q tests/test_monitor_shell.py tests/test_edge_panel_drag.py tests/test_app_sync.py`
Expected: FAIL (`MonitorShell` has no `on_layout` / `on_error`; `EdgePanel` has no `natural_length`; no `clip_container` / `_centre_view`; `EdgeShellApp` has no `_relayout_failed`).

- [ ] **Step 2: `shell/edge_panel.py`**

1. After `from shell.gdk_util import monitor_index` add `from shell.panel_layout import content_length`.
2. After `HANDLE_LENGTH = 44  # handle size along the edge` add:

```python


def _centre_view(adjustment) -> None:
    """Keep clipped content centred: equal parts cut off at both ends of the body."""
    adjustment.set_value(
        (adjustment.get_lower() + adjustment.get_upper() - adjustment.get_page_size()) / 2
    )


def clip_container(child: Gtk.Widget) -> Gtk.ScrolledWindow:
    """Show `child` at its natural size, centred, and clip it at the body edge. The layer
    surface cannot grow either way (Gtk.Overlay never measures its overlay children); without
    this, content longer than a shrunk body (spec 17: shrink to fit, max_length, a small
    percentage) would draw over the joins and the frame. No scrollbars, and wheel events never
    scroll the clipped content."""
    clip = Gtk.ScrolledWindow(
        name="panel-clip",
        hscrollbar_policy=Gtk.PolicyType.EXTERNAL,
        vscrollbar_policy=Gtk.PolicyType.EXTERNAL,
    )
    clip.set_hexpand(True)
    clip.set_vexpand(True)
    clip.add(child)
    for adjustment in (clip.get_hadjustment(), clip.get_vadjustment()):
        adjustment.connect("changed", _centre_view)  # the viewport re-configures on allocate
    clip.connect("scroll-event", lambda *_args: True)  # stop before the class handler scrolls
    return clip
```

3. Replace `self._content = Box(name="panel-content", children=[inner])` with

```python
        self._inner = inner
        self._content = Box(name="panel-content", children=[clip_container(inner)])
```

(The scoped CSS `{scope} * { all: unset; }` in `shell/theme.py` already makes the scrolled window and its viewport transparent.)

4. Before `def raise_to_top` add:

```python
    def natural_length(self) -> int:
        """The body length the content needs along the edge (natural size plus padding): the
        measured input of a `length = "content"` panel (MonitorShell._measure)."""
        if geometry.is_horizontal(self.spec.edge):
            _minimum, natural = self._inner.get_preferred_width()
        else:
            _minimum, natural = self._inner.get_preferred_height()
        return content_length(natural)

```

- [ ] **Step 3: `shell/monitors.py`**

1. Imports: add `from shell import geometry` as the first `shell` import (before `from shell.canvas.canvas import ShapeCanvas`), and replace the existing `from shell.panel_spec import PanelGeometry` with `from shell.panel_spec import PanelGeometry, PanelRequest`.
2. `__init__`: add the parameters `on_layout=None, on_error=None` after `unregister_window=None`, the docstring and the callbacks, and the new state after `self._keys = …`:

```python
        register_window,
        unregister_window=None,
        on_layout=None,
        on_error=None,
    ):
        """`on_layout(shell)` is called after a re-layout this shell starts by itself (content
        measured, monitor geometry changed), so the app can report new layout warnings;
        `on_error(shell)` when such a re-layout raised (logged here; the app rebuilds us)."""
        self.name = name
        self.monitor = monitor
        self._register = register_window
        self._unregister = unregister_window or (lambda _window: None)
        self._on_layout = on_layout or (lambda _shell: None)
        self._on_error = on_error or (lambda _shell: None)
```

```python
        self._keys = itertools.count()  # scene keys for the canvas
        self._config = config
        self._theme = config.theme_for(name)
        self._requests: list[PanelRequest] = []  # of the last layout, config order
        # Measured "content" lengths: index -> ((widget, horizontal), px). Kept across
        # re-layouts; an entry only counts while the same widget sits at that index.
        self._natural: dict[int, tuple[tuple[str, bool], int]] = {}
        self._remeasure: set[int] = set()  # built since the last measurement (or restyled)
        self._measure_id = 0  # pending idle measurement
```

3. `_layout` becomes (plus `_measured`):

```python
    def _layout(self, config: Config, theme) -> Layout:
        g = self.monitor.get_geometry()
        self._requests = requests_for(config, self.name)
        return layout_monitor(
            self._requests,
            g.width,
            g.height,
            theme.thickness,
            theme.radius,
            config.layout_for(self.name).gap,
            self._measured(),
            where=f"monitors.{self.name}",
        )

    def _measured(self) -> dict[int, int]:
        """Measured natural lengths that still belong to the widget at each index."""
        out = {}
        for i, req in enumerate(self._requests):
            got = self._natural.get(i)
            if got is not None and got[0] == _measure_key(req):
                out[i] = got[1]
        return out
```

4. At the end of `_sync_panels` (after the loop, same indentation as `layout = …`) add `self._schedule_measure()`, and after `_sync_panels` add:

```python
    # ---- "content" lengths ----------------------------------------------------------------
    def _to_measure(self) -> list[int]:
        """Live "content" panels built since the last measurement (or restyled), or without a
        measurement for the widget now at their index."""
        known = self._measured()
        return [
            i
            for i, (panel, req) in enumerate(zip(self.panels, self._requests, strict=True))
            if panel is not None
            and req.length == "content"
            and (i in self._remeasure or i not in known)
        ]

    def _schedule_measure(self) -> None:
        """Measure "content" panels when the main loop is next idle: by then the app's
        stylesheet is applied (EdgeShellApp.run sets it after building the shells), so fonts
        have their real size. Only new, restyled or unmeasured panels are measured; an
        unchanged size changes nothing."""
        if self._measure_id or self._closed:
            return
        if self._to_measure():
            self._measure_id = GLib.idle_add(self._measure)

    def _measure(self) -> bool:
        self._measure_id = 0
        if self._closed:
            return False
        try:
            todo = self._to_measure()
            self._remeasure.clear()
            changed = False
            for i in todo:
                entry = (_measure_key(self._requests[i]), self.panels[i].natural_length())
                if self._natural.get(i) != entry:
                    self._natural[i] = entry
                    changed = True
            if changed:
                self._sync_panels(self._config, self._theme, startup=False)
                self._on_layout(self)
        except Exception:  # a GLib callback: never raise into the main loop (decision 11)
            log.exception("measuring the content panels of %s failed", self.name)
            self._on_error(self)
        return False
```

5. `_new_panel`: as its first line (before `key = next(self._keys)`) add `self._remeasure.add(index)  # measured when idle if it is a "content" panel`.
6. `apply`: right after `theme = config.theme_for(self.name)` add `self._config, self._theme = config, theme`, and inside the `if any(change.kind == "restyle" …)` block, after the `for panel in self.live_panels(): panel.apply_theme(theme)` loop, add `self._remeasure.update(range(len(self.panels)))  # fonts may have changed`.
7. `close`: after `self._closed = True` add

```python
        if self._measure_id:
            GLib.source_remove(self._measure_id)
            self._measure_id = 0
```

8. At the end of the module add:

```python


def _measure_key(req: PanelRequest) -> tuple[str, bool]:
    """A measurement belongs to a widget at an orientation (along a horizontal edge or not)."""
    return req.widget, geometry.is_horizontal(req.edge)
```

- [ ] **Step 4: `shell/app.py`**

1. In `sync_monitors` the shell is created as

```python
            self.shells[name] = MonitorShell(
                name,
                desired[name],
                self.config,
                self.register_window,
                self.unregister_window,
                on_layout=lambda shell, n=name: self._report_layout(n, shell),
                on_error=lambda shell, n=name: self._relayout_failed(n, shell),
            )
```

2. In `__init__`, after `self._layout_reported: dict[str, list[str]] = {}  # …`, add `self._relayout_rebuilt: set[str] = set()  # rebuilt after a failed re-layout, until a reload`.
3. In `_reload`, right after `old, new = result` (and the Task 2 `self._log_deprecated(new)`), add `self._relayout_rebuilt.clear()  # a new config may fix the failing widget`.
4. Before `def _report_layout` add:

```python
    def _relayout_failed(self, name: str, shell) -> None:
        """A re-layout the shell started by itself raised (MonitorShell._measure / _relayout
        logged it): close that shell and rebuild it from the current config, as a failed
        reload does. Only once per monitor until the next reload, so a widget that always
        fails cannot rebuild forever; a stale call from a closed shell is ignored."""
        if self.shells.get(name) is not shell:
            return
        if name in self._relayout_rebuilt:
            log.error("re-layout of %s failed again; keeping its panels as they are", name)
            return
        self._relayout_rebuilt.add(name)
        log.error("re-layout of %s failed; rebuilding its panels", name)
        self._notify("Panels rebuilt", f"{name}: laying out the panels failed; rebuilt them")
        self.shells.pop(name)
        try:
            shell.close()
        except Exception:
            log.exception("closing the failed shell on %s failed", name)
        self.sync_monitors()  # reopens it from self.config (and refreshes the CSS)

```

(`_relayout_failed` runs inside the shell's own GLib callback, after that callback caught the exception; the shell does nothing after `on_error` returns, so closing it there is safe.)

- [ ] **Step 5: Run the tests**

Run: `scripts/py -m pytest -q tests/test_monitor_shell.py tests/test_edge_panel_drag.py tests/test_app_sync.py`
Expected: all pass (`test_clip_container_never_asks_for_the_content_size` skips without a display, as in CI).

- [ ] **Step 6: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell/edge_panel.py shell/monitors.py shell/app.py tests/test_monitor_shell.py tests/test_edge_panel_drag.py tests/test_app_sync.py
git commit -m "feat(layout): measure content lengths after build; clip and centre content in short bodies" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Re-layout when the monitor's geometry changes

**Files:**
- Modify: `shell/monitors.py` (constant, `__init__` state, end of `_build`, new `_on_geometry` / `_relayout`, `close`)
- Modify: `shell/canvas/canvas.py` (new `set_monitor_size`, before `add_panel`)
- Test: `tests/test_monitor_shell.py`, `tests/test_canvas_window.py`

**Interfaces:**
- Consumes: Task 7 (`_config`, `_theme`, `_on_layout`, `_on_error`).
- Produces: `shell.monitors.RELAYOUT_DELAY_MS = 250`; `MonitorShell._relayout_id: int`, `MonitorShell._monitor_handlers: list[int]`; `MonitorShell._on_geometry(*args) -> None` (debounced) and `MonitorShell._relayout() -> bool` (re-layout from the monitor's current geometry, `canvas.set_monitor_size`, `_on_layout(self)`; a zero or negative width or height is ignored; any exception is logged and passed to `_on_error(self)`, decision 11); `ShapeCanvas.set_monitor_size(width: int, height: int) -> None`.

- [ ] **Step 1: Write the failing tests**

1. `tests/test_monitor_shell.py`:
   - Replace `MONITOR = SimpleNamespace(...)` with:

     ```python
     class FakeMonitor:
         """A Gdk.Monitor stand-in: geometry, plus the notify::geometry connection."""

         def __init__(self, width=1920, height=1080):
             self.width, self.height = width, height
             self.handlers = {}

         def get_geometry(self):
             return SimpleNamespace(x=0, y=0, width=self.width, height=self.height)

         def connect(self, signal, fn):
             self.handlers[len(self.handlers) + 1] = (signal, fn)
             return len(self.handlers)

         def disconnect(self, handler):
             del self.handlers[handler]


     MONITOR = FakeMonitor()
     ```

   - In `FakeCanvas.__init__` add `self.monitor_sizes = []` and the method:

     ```python
         def set_monitor_size(self, width, height):
             self.monitor_sizes.append((width, height))
     ```

   - In `bare_shell` replace `shell._measure_id = 0` with

     ```python
         shell.monitor = FakeMonitor()
         shell._monitor_handlers = []
         shell._measure_id = shell._relayout_id = 0
     ```

   - In the `build` fixture, `_build` gets a `monitor` parameter:

     ```python
         def _build(monitors, theme=None, monitor=None, on_layout=None, on_error=None):
             tracked = []
             cfg = make_config(monitors=monitors, theme=theme)
             shell = mon_mod.MonitorShell(
                 "HDMI-A-1",
                 monitor or FakeMonitor(),
                 cfg,
                 tracked.append,
                 on_layout=on_layout,
                 on_error=on_error,
             )
             shell.test_idles, shell.test_removed = idles, removed
             return shell, tracked, timers
     ```

   - Append:

     ```python
     # ---- monitor geometry ---------------------------------------------------------------


     def test_a_resolution_change_relayouts_once_it_settles(build):
         reports = []
         monitor = FakeMonitor()
         shell, _, timers = build(edge({"widget": "dock"}), monitor=monitor, on_layout=reports.append)
         dock = shell.panels[0]
         assert dock.args[0].pos == 680
         ((signal, handler),) = monitor.handlers.values()
         assert signal == "notify::geometry"
         monitor.width, monitor.height = 1280, 720
         handler(monitor, None)
         handler(monitor, None)  # a burst: the first timer is replaced
         relayouts = [t for t in timers if t[0] == mon_mod.RELAYOUT_DELAY_MS]
         assert len(relayouts) == 2 and len(shell.test_removed) == 1
         assert relayouts[-1][1]() is False
         assert dock.destroyed and shell.panels[0].args[0].pos == (1280 - 560) // 2  # re-centred
         assert shell.canvas.monitor_sizes == [(1280, 720)] and reports == [shell]


     def test_close_disconnects_from_the_monitor(build):
         monitor = FakeMonitor()
         shell, _, _ = build(edge({"widget": "dock"}), monitor=monitor)
         shell.close()
         assert monitor.handlers == {}


     def test_a_zero_geometry_is_ignored(build):
         reports = []
         monitor = FakeMonitor()
         shell, _, timers = build(edge({"widget": "dock"}), monitor=monitor, on_layout=reports.append)
         dock = shell.panels[0]
         ((_, handler),) = monitor.handlers.values()
         monitor.width = monitor.height = 0  # what an unplugged monitor reports
         handler(monitor, None)
         assert timers[-1][0] == mon_mod.RELAYOUT_DELAY_MS and timers[-1][1]() is False
         assert shell.panels[0] is dock and not dock.destroyed  # no 0 px layout, no warnings
         assert shell.layout_warnings == [] and reports == [] and shell.canvas.monitor_sizes == []


     def test_a_failing_relayout_is_logged_and_reported(build, monkeypatch, caplog):
         errors, reports = [], []
         monitor = FakeMonitor()
         shell, _, timers = build(
             edge({"widget": "dock"}),
             monitor=monitor,
             on_layout=reports.append,
             on_error=errors.append,
         )
         ((_, handler),) = monitor.handlers.values()

         def explode(*a, **k):
             raise RuntimeError("widget broke")

         monkeypatch.setattr(mon_mod, "widget_class", lambda _w: explode)  # the rebuild raises
         monitor.width, monitor.height = 1280, 720
         handler(monitor, None)
         assert timers[-1][1]() is False  # never raises into the main loop
         assert errors == [shell] and reports == []
         assert "widget broke" in caplog.text
     ```

2. `tests/test_canvas_window.py`, append:

   ```python
   def test_a_new_monitor_size_is_expected_and_warned_about_again(make_config, caplog):
       s = stand_in(make_config, size=(1920, 1080))
       ShapeCanvas.set_monitor_size(s, 1280, 720)
       assert s._monitor_size == (1280, 720) and s._size_warned is False
       ShapeCanvas._check_size(s)  # the scene is still 1920x1080 until the allocation
       assert caplog.text.count("panels may be misaligned") == 1
   ```

Run: `scripts/py -m pytest -q tests/test_monitor_shell.py tests/test_canvas_window.py`
Expected: FAIL (no `notify::geometry` handler; no `RELAYOUT_DELAY_MS`; no `set_monitor_size`).

- [ ] **Step 2: Implement**

1. `shell/monitors.py`, after `RAISE_FALLBACK_MS = 2000`:

```python
# A resolution change arrives as several notify::geometry signals; re-layout once it settles.
RELAYOUT_DELAY_MS = 250
```

2. `__init__`, after `self._measure_id = 0  # pending idle measurement`:

```python
        self._relayout_id = 0  # pending geometry re-layout
        self._monitor_handlers: list[int] = []
```

3. End of `_build` (after the raise timers):

```python
        self._monitor_handlers.append(monitor.connect("notify::geometry", self._on_geometry))
```

4. After `_measure`:

```python
    # ---- monitor geometry -----------------------------------------------------------------
    def _on_geometry(self, *_args) -> None:
        """The monitor's resolution (or position) changed: re-layout once it settles."""
        if self._relayout_id:
            GLib.source_remove(self._relayout_id)
        self._relayout_id = GLib.timeout_add(RELAYOUT_DELAY_MS, self._relayout)

    def _relayout(self) -> bool:
        self._relayout_id = 0
        if self._closed:
            return False
        try:
            g = self.monitor.get_geometry()
            if g.width <= 0 or g.height <= 0:  # being unplugged: the hot-plug sync closes us
                return False
            self.canvas.set_monitor_size(g.width, g.height)
            self._sync_panels(self._config, self._theme, startup=False)
            self._on_layout(self)
        except Exception:  # a GLib callback: never raise into the main loop (decision 11)
            log.exception("re-laying out %s after a geometry change failed", self.name)
            self._on_error(self)
        return False
```

5. `close`: replace the Task 7 block (`if self._measure_id: …`) with

```python
        for source in (self._measure_id, self._relayout_id):
            if source:
                GLib.source_remove(source)
        self._measure_id = self._relayout_id = 0
        for handler in self._monitor_handlers:
            try:
                self.monitor.disconnect(handler)
            except Exception:  # the monitor may be gone already (unplugged)
                log.debug("could not disconnect from %s", self.name, exc_info=True)
        self._monitor_handlers.clear()
```

6. `shell/canvas/canvas.py`, before `def add_panel`:

```python
    def set_monitor_size(self, width: int, height: int) -> None:
        """The monitor's resolution changed (MonitorShell re-layout): the allocation that
        follows resizes the scene; only the size check needs to know."""
        self._monitor_size = (width, height)
        self._size_warned = False

```

(The canvas and strips are anchored to all/three edges, so the compositor resizes them; `ShapeCanvas._on_allocate` already resizes the scene and forces a full redraw.)

- [ ] **Step 3: Run the tests**

Run: `scripts/py -m pytest -q tests/test_monitor_shell.py tests/test_canvas_window.py`
Expected: all pass.

- [ ] **Step 4: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell/monitors.py shell/canvas/canvas.py tests/test_monitor_shell.py tests/test_canvas_window.py
git commit -m "feat(layout): re-layout panels when the monitor geometry changes" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Simulation of a real config; effects at the corners

**Files:**
- Modify: `shell/canvas/simulate.py:8-17` (imports), after `default_shapes` (new `config_shapes`), `main()` (`--config`, `--monitor`)
- Test: `tests/test_canvas_stats.py`, `tests/test_canvas_scene.py`

**Interfaces:**
- Consumes: `layout_monitor`, `requests_for`, `Config.layout_for`.
- Produces: `shell.canvas.simulate.config_shapes(config: Config, monitor: str, width: int, height: int) -> tuple[list[PanelShape], list[str]]` (shown panels only, plus warnings); CLI `python -m shell.canvas.simulate --config PATH [--monitor NAME]` lays out that monitor's panels with its theme (`--elevation` / `--border` still override), prints each layout warning as `layout: …`, exits 2 on a bad config or an unknown widget (`validate_widgets` runs inside the same `try` as `load_config`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_canvas_stats.py`:

```python
def test_config_shapes_lays_out_the_monitors_panels(fake_registry, make_config):
    from shell.canvas.simulate import config_shapes

    cfg = make_config(
        monitors={
            "HDMI-A-1": {
                "shell": "edge",
                "panels": [
                    {"widget": "dock", "align": "end"},
                    {"widget": "dock", "pos": 1300},  # dropped onto the first: not shown
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
        '[[monitors.HDMI-A-1.panels]]\nwidget = "dock"\nalign = "end"\n'
        '[[monitors.HDMI-A-1.panels]]\nwidget = "clock"\nlength = "fill"\n'
    )
    assert main(["--config", str(path), "--frames", "20", "--size", "1280x720"]) == 0
    out = capsys.readouterr().out
    assert "panel 1:" in out and "panel 2:" not in out  # exactly the two configured panels
    assert "simulated 20 frames at 1280x720" in out and "layout:" not in out


def test_cli_reports_a_bad_config(tmp_path):
    pytest.importorskip("gi")
    pytest.importorskip("fabric")
    path = tmp_path / "bad.toml"
    path.write_text('[[monitors.HDMI-A-1.panels]]\nwidget = "dock"\nlength = "half"\n')
    with pytest.raises(SystemExit) as exc:
        main(["--config", str(path), "--frames", "1"])
    assert exc.value.code == 2


def test_cli_reports_an_unknown_widget(tmp_path, capsys):
    pytest.importorskip("gi")
    pytest.importorskip("fabric")
    path = tmp_path / "unknown.toml"
    path.write_text(
        '[monitors.HDMI-A-1]\nshell = "edge"\n[[monitors.HDMI-A-1.panels]]\nwidget = "nope"\n'
    )
    with pytest.raises(SystemExit) as exc:  # a usage error, not a traceback
        main(["--config", str(path), "--frames", "1"])
    assert exc.value.code == 2
    assert "unknown widget 'nope'" in capsys.readouterr().err
```

Append to `tests/test_canvas_scene.py`:

```python
def test_corner_aligned_panels_redraw_cleanly_with_border_and_shadow(make_config):
    """End- and start-aligned panels resolved by the layout, one next to each screen corner,
    animating under the strongest effects: clipped redraws still equal a full redraw."""
    from shell.panel_layout import layout_monitor
    from shell.panel_spec import PanelRequest

    theme = make_config(theme=THEMES[-1]).theme
    requests = [
        PanelRequest(w, e, a, 0, None, 0, 160, None, None, d, "extended", w, 160)
        for w, e, a, d in [
            ("a", "bottom", "end", 64),
            ("b", "left", "end", 40),
            ("c", "top", "start", 46),
            ("d", "right", "start", 56),
        ]
    ]
    layout = layout_monitor(requests, 640, 400, theme.thickness, theme.radius, 8)
    assert None not in layout.panels and layout.warnings == []
    shapes = [PanelShape(p.edge, p.pos, p.length, p.depth) for p in layout.panels]
    res = simulate(theme, (640, 400), shapes, 80, check_every=7)
    assert res.checked == 12
    assert res.max_noisy <= 40 and res.max_diff <= 32, res
```

Run: `scripts/py -m pytest -q tests/test_canvas_stats.py tests/test_canvas_scene.py`
Expected: FAIL (`ImportError: cannot import name 'config_shapes'`; the CLI rejects `--config`). The corner test passes already (it pins Tasks 3-5 under effects); that is fine.

- [ ] **Step 2: Implement in `shell/canvas/simulate.py`**

1. Imports: add `from pathlib import Path` after `from dataclasses import dataclass, field`; replace `from shell.config.models import Theme` with

```python
from shell.config.models import Config, Theme
from shell.panel_layout import layout_monitor
from shell.registry import requests_for, validate_widgets
```

2. After `default_shapes` add:

```python
def config_shapes(
    config: Config, monitor: str, width: int, height: int
) -> tuple[list[PanelShape], list[str]]:
    """The shown panels of `monitor` in `config`, laid out by shell.panel_layout at width x
    height, plus the layout warnings. The widgets must be registered (import widgets)."""
    theme = config.theme_for(monitor)
    layout = layout_monitor(
        requests_for(config, monitor),
        width,
        height,
        theme.thickness,
        theme.radius,
        config.layout_for(monitor).gap,
        where=f"monitors.{monitor}",
    )
    shapes = [PanelShape(p.edge, p.pos, p.length, p.depth) for p in layout.panels if p]
    return shapes, layout.warnings
```

3. In `main()`: `from shell.config.models import deep_merge` -> `from shell.config.models import ConfigError, deep_merge`; after the `--border` argument add

```python
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="lay out this config's panels and use its theme (needs Fabric for the widgets)",
    )
    p.add_argument("--monitor", default="HDMI-A-1", help="monitor of --config (default HDMI-A-1)")
```

replace `theme = load_config(None).theme` with

```python
    shapes = default_shapes(width, height)
    if args.config is None:
        theme = load_config(None).theme
    else:
        import widgets  # noqa: F401  (registers the built-in panels: their default geometry)

        try:
            config = load_config(args.config, required=True)
            validate_widgets(config)  # an unknown widget is a usage error (exit 2), as in main.py
        except ConfigError as exc:
            p.error(str(exc))
        theme = config.theme_for(args.monitor)
        shapes, warnings = config_shapes(config, args.monitor, width, height)
        for warning in warnings:
            print(f"layout: {warning}")
```

and in the `simulate(...)` call replace the argument `default_shapes(width, height),` with `shapes,`.

- [ ] **Step 3: Run the tests and the CLI**

Run: `scripts/py -m pytest -q tests/test_canvas_stats.py tests/test_canvas_scene.py`
Expected: all pass.
Run: `scripts/py -m shell.canvas.simulate --config examples/layout-test.toml --frames 120`
Expected: a stats report with `panel 0:` … `panel 5:`, no `layout:` line, last line `simulated 120 frames at 1920x1080: … draws, 1 full`.

- [ ] **Step 4: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell/canvas/simulate.py tests/test_canvas_stats.py tests/test_canvas_scene.py
git commit -m "feat(canvas): simulate a config's resolved layout; effects test at the corners" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 10: GATE B (Phil, HDMI-A-1): fill, content, percent, clipping, re-layout, measurement

**Files:**
- Create: `examples/layout-sizes-test.toml`

**Interfaces:**
- Consumes: Tasks 1-9; no code changes.

- [ ] **Step 1: Create the example config**

```toml
# Gate B (layout plan): fill, content and percentage lengths, on HDMI-A-1 only.
#   cp examples/layout-sizes-test.toml /tmp/edge-sizes.toml
#   scripts/py main.py --config /tmp/edge-sizes.toml -v       (edit the copy while it runs)
[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]    # 0: bottom, fills the span between the two clocks
widget = "dock"
length = "fill"

[[monitors.HDMI-A-1.panels]]    # 1: bottom-left, as long as its content
widget = "clock"
edge = "bottom"
align = "start"
length = "content"

[[monitors.HDMI-A-1.panels]]    # 2: bottom-right, as long as its content
widget = "clock"
edge = "bottom"
align = "end"
length = "content"

[[monitors.HDMI-A-1.panels]]    # 3: top, half of the free span but at most 700 px
widget = "clock"
length = "50%"
max_length = 700

[[monitors.HDMI-A-1.panels]]    # 4: right, as long as its content, centred
widget = "system_bar"
align = "center"
length = "content"
```

Check it: `scripts/py -m shell.canvas.simulate --config examples/layout-sizes-test.toml --frames 60`
Expected: no `layout:` line (before measurement the clocks use 168 px and the system bar 300 px), last line `simulated 60 frames at 1920x1080: …`.

- [ ] **Step 2: Commit**

```bash
git add examples/layout-sizes-test.toml
git commit -m "docs(examples): layout gate config with fill, content and percent lengths" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 3: GATE B (Phil)**

```bash
cp examples/layout-sizes-test.toml /tmp/edge-sizes.toml
scripts/py main.py --config /tmp/edge-sizes.toml -v
```

1. **content:** the two bottom clocks hug their text (about 12 px of body either side of HH:MM) at the two bottom corners; the system bar on the right hugs its two labels vertically and is centred on the edge.
2. **Startup rebuild (decision 5, default pending Phil):** just after start the content panels may appear at their default length for a moment and then shrink once. Record whether that flash is visible. Only a visible flash plans the in-place resize (decision 5's cost: 1-2 tasks).
3. **fill:** the dock body spans everything between the two clocks with exactly 8 px of straight frame either side between the joins; the three dock buttons stay centred in the long body.
4. **percent + max:** the top clock body is 700 px (50 % = 922 px, capped by `max_length = 700`), centred (x 610..1310).
5. **Live reload:** set the top clock `length = "25%"` -> 461 px, centred; `length = "fill"` -> spans the whole top free span (x 38..1882); back to `"50%"`. Only the top clock rebuilds each time.
6. **Clipping (decision 8):** set the dock `length = 100` (replacing `"fill"`) -> the dock body is 100 px, centred between the clocks; its row of buttons is cut off equally at both body ends (the middle "Files" button stays whole in the centre), nothing is drawn over the joins or the frame, there is no scrollbar, and the mouse wheel over it does nothing. Keep `length = 100` for item 7.
7. **Interaction through the clip container:** on the clipped 100 px dock and on the unclipped bottom-left clock, exactly as Gate A item 4 checks them: click the dock's middle button -> Dolphin opens (close it); hover the dock's middle button -> its "Files" tooltip appears; collapse each panel and hover it -> the peek shows; drag each panel -> the body follows and settles; collapse and expand each panel -> the content fades out and back in, with no flicker of the clipped dock content. Then set the dock back to `"fill"`.
8. **min/max on fill:** add `max_length = 900` to the dock -> 900 px centred between the clocks. Remove it.
9. **Hot-plug** (terminal on DP-1; never touch DP-1 itself): `kscreen-doctor output.HDMI-A-1.disable`, then `kscreen-doctor output.HDMI-A-1.enable`: within about 3 s everything returns, the content panels measured again (same sizes as item 1); no "Panels adjusted" notification while HDMI-A-1 is off (decision 6).
10. **Resolution change (required; only HDMI-A-1, never touch DP-1's settings):** change HDMI-A-1's resolution through **System Settings > Display**: pick HDMI-A-1, choose a smaller mode (1280x720 if listed, otherwise the smallest), Apply. During the ~15 s Keep/Revert window watch the panels re-lay out within about a second: the top clock re-centres (at 1280x720: 602 px, 50 % of 1204), the dock fill shrinks, the system bar re-centres, nothing runs into a corner. Then press **Revert** (or let it time out): the original 1920x1080 layout returns. If `kscreen-doctor` is used instead, first save the current state with `kscreen-doctor -o > /tmp/kscreen-before.txt`, pick a mode string listed there for HDMI-A-1 (e.g. `kscreen-doctor output.HDMI-A-1.mode.1280x720@60`), and switch back with the original mode string from that file. In both cases record from the `-v` log which path ran: an `opening Edge Shell on HDMI-A-1` line = the hot-plug path (the shell was rebuilt); no reopen = the `notify::geometry` path (Task 8).
11. **Measurement:** quit, then `scripts/py main.py --config /tmp/edge-sizes.toml --stats 10`: `fps while animating` >= 55, `canvas damaged draws` p95 <= 8 ms (Plan 1 targets).
12. The `-v` logs have no errors.

**On failure:** item 1/2 wrong sizes -> log `natural_length()` values (add a temporary `log.debug` in `MonitorShell._measure`, not committed) and compare with the CSS font size; reproduce with a fake in `tests/test_monitor_shell.py` before fixing. Item 6: content drawn over the joins or not centred -> add a failing case to `test_clip_container_never_asks_for_the_content_size` (e.g. a `Gtk.Label`, or a page size the viewport really sets) before fixing. Item 7: clicks, hover, drags or tooltips no longer reach the content -> confirm the clip container is the cause with a local, uncommitted edit that builds the content without `clip_container`; then add a stand-in test for the event path (e.g. the swallowed `scroll-event` handler must not return True for button events) before fixing. Item 10: nothing happens and the log shows no reopen -> GDK did not emit `notify::geometry`; fallback: also call `MonitorShell._on_geometry` from `ShapeCanvas._on_allocate` when `painter.resize(...)` returns True (pass a callback from `MonitorShell` into `ShapeCanvas`), add a test on a stand-in, and repeat item 10. Item 11 misses targets -> record the report and compare with `examples/panels-test.toml` (fill bodies are longer, so damaged boxes are wider); discuss with Phil.

---

### Task 11: Docs: README and spec

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-10-11-edge-shell-design.md` (sections 6, 16, 17)

**Interfaces:**
- Consumes: Gate A and Gate B results (record any deviation they produced).

- [ ] **Step 1: README**

1. Under `- [Shape canvas plan](…)` add `- [Layout and anchoring plan](docs/superpowers/plans/2026-10-13-layout-anchoring.md)`.
2. In **Features**, after the `- Panels: …` line add:
   `- Several panels per edge: align slots (start, center, end) with order and offset, a configurable gap, lengths in px, "fill", "content" or a percentage with optional min/max. Panels keep clear of the rounded screen corners and re-lay out when the monitor's resolution changes.`
3. In **Run**, after the effects line add:

```bash
scripts/py main.py --config examples/layout-test.toml -v        # several panels per edge
scripts/py main.py --config examples/layout-sizes-test.toml -v  # fill, content, percent
```

and in **Develop** after the simulate line: `scripts/py -m shell.canvas.simulate --config examples/layout-test.toml   # a config's layout, headless`.
4. In **Configure**, replace the panel example's comment line `depth = 80                # edge, pos, length, depth, state override the widget's defaults` by `depth = 80                # edge, length, depth, state, align, offset, order override the defaults` and add after that code block:

````markdown
Panels are placed per edge in three slots and sized in one of four ways:

```toml
[[monitors.HDMI-A-1.panels]]
widget = "clock"
edge = "bottom"
align = "end"             # start | center (default) | end of the edge
offset = 0                # px from that end; for a later panel in the slot: extra space before it
order = 0                 # order within the slot; equal orders keep the config order
length = "content"        # px, "fill", "content" or a percentage such as "50%"
min_length = 100          # optional bounds, for every length mode
max_length = 600

[monitors.HDMI-A-1.layout]
gap = 8                   # straight frame between neighbouring panels, on top of their joins
```

Each edge's free span stops `thickness + radius + join radius` (38 px by default) short of
each screen corner. A panel that does not fit is shrunk (its content is clipped at the body
edge, centred), one that would overlap an earlier panel is hidden and keeps its place in the
slot (its neighbours do not close up); both send a "Panels adjusted" notification. A negative
`offset` only works on the first centred panel of an edge (it shifts the group towards the
start); on a later centred panel it counts as 0. Two panels that meet at a shared screen
corner (an `align = "end"` bottom panel and an `align = "end"` right panel, or `"start"` on
the top and the left edge) always collide at offset 0: give one of them an `offset` of at
least the other panel's depth (exactly `depth + r - radius`, which is the depth for any panel
at least 28 px deep). "content" panels are measured after they are built.

`pos` (pixels from the start of the edge) still works but is deprecated: it cannot be combined
with `align` or `offset`, and every start logs one line listing the entries that use it. A
lone `pos = N` equals `align = "start"`, `offset = N - 38` at the default theme (38 =
`thickness + radius + join radius`; 32-38 px depending on the panel's depth). The system
bar's own default moved from `pos = 600` to `align = "end"`, `offset = 142`: the same place on
a 1080 px tall monitor (y = 600), but 142 px from the end of the free span elsewhere (y = 960
at 1440 px, y = 240 at 720 px, where `pos = 600` gave 600 and, clamped, 382).
````

5. In **Known limitations / planned**, replace the bullet `- Several panels on one edge are not auto-arranged …` (both lines) with
   `- Moving a panel (a layout change on reload or a resolution change) rebuilds its window; there is no in-place move yet. "content" panels are built twice at startup (default length, then measured).`
   and replace the bullet `- Changing a connected monitor's resolution or scale does not reflow panels: …` (three lines) with
   `- One layout gap per monitor (no per-edge gap). Scale changes re-lay out panels, but HiDPI drawing is not supported yet (see below).`
   Update them if Gates A/B recorded a deviation.

- [ ] **Step 2: Spec**

1. Section 6, config example: after `length = 168` add the lines

```toml
align = "center"              # start | center | end; offset = px from that end
order = 0                     # within the slot (edge + align)
```

In the reload table, replace the row `| Panel \`edge\`, \`pos\`, \`length\` or \`depth\` | … |` by

`| Panel \`edge\`, \`pos\`, \`align\`, \`offset\`, \`order\`, \`length\`, \`min_length\`, \`max_length\` or \`depth\` | Rebuild that panel's window, and any panel whose resolved position or visibility changed with it (section 17 rules) |`

and add the row `| Layout \`gap\` (\`[layout]\`, \`[monitors.X.layout]\`) | Re-layout the monitor: rebuild only the panels that moved |`.

2. Section 16: after the **Today (core plan, as built)** paragraph add:

`**Implemented (2026-10-13, plan \`docs/superpowers/plans/2026-10-13-layout-anchoring.md\`):** \`shell/panel_layout.py\` (\`layout_edge\`, \`layout_monitor\`) resolves every panel per edge from slots (start, center, end), \`order\` within a slot (ties keep config order) and one \`gap\` per monitor (\`[layout]\`, \`[monitors.X.layout]\`, default 8 px) measured between neighbouring joins, on top of \`r1 + r2\`. \`pos\` keeps its old meaning (pixels from the start of the edge) as a deprecated alias placed outside the slots; combining it with \`align\`/\`offset\` is a validation error whose message gives the conversion (\`pos = N\` = \`align = "start"\`, \`offset = N - (T + R + r)\`), and each config load logs one INFO line listing the entries still using it. The system bar's default moved from \`pos = 600\` to \`align = "end"\`, \`offset = 142\` (identical on a 1080 px monitor only). Overlaps hide the later panel (config order) with a notification. No \`panel-move\` change kind: moved panels are rebuilt; a \`gap\` change is a \`relayout\`.`

3. Section 17: replace the bullet that starts with `**Interim implementation (2026-10-13):**` with:

`- **Implemented (2026-10-13, layout plan):** the free span is \`T + R + r\` from each end; \`length\` takes px, \`"fill"\` (equal shares of what the neighbours, offsets and spacing leave), \`"content"\` (the content's natural size plus 12 px each side, measured in an idle callback after each build, the widget's default until then) or a percentage of the free span, then \`min_length\`/\`max_length\` and a 60 px floor; too long is shrunk with a warning and the content is clipped at the body edge and kept centred (a scroll-less container), never drawn over the joins and frame. \`MonitorShell\` re-lays out on the monitor's \`notify::geometry\` (debounced 250 ms; a zero geometry while unplugging is ignored), so centred, percentage and fill panels follow resolution changes. Two panels meeting at a shared screen corner collide at offset 0 (one needs an offset of at least the other's depth + r - R); a panel hidden by an overlap keeps its slot space; a re-layout the shell starts itself that fails is logged and rebuilds that monitor once.`

and in **Design implications** replace `- \`anchor_and_margin\` moves behind this resolver; \`EdgePanel\` receives a resolved offset and length.` with `- Done: \`anchor_and_margin\` takes the resolved start; \`EdgePanel\` receives a resolved \`PanelGeometry\` (pos and length in px).`

- [ ] **Step 3: Commit**

```bash
git add README.md docs/superpowers/specs/2026-10-11-edge-shell-design.md
git commit -m "docs: layout and anchoring in README and spec" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage**

| Requirement (spec 16/17, Phil's brief) | Task |
| --- | --- |
| `align` start/center/end (default center), `offset` from that end | 1, 2, 3 |
| `order` within a slot; configurable `gap` respecting `r1 + r2` | 1, 3 (decisions 1, 3) |
| `length` px / `"fill"` / `"content"` / `"NN%"`, `min_length`/`max_length` | 1, 4 |
| `pos` deprecated alias; precedence decided and documented | 1, 2, 3, 11 (decision 2) |
| Pydantic validation with key paths | 1 |
| Pure resolver (`layout_edge`-style), no GTK, headless tests | 3, 4 |
| Free span `T + R + r`, 38 px default; shrink with warning; clamp offsets | 3, 4 |
| Overlap / too close: hide the later panel and notify, minimum gap `r1 + r2` | 3 (and the existing `_report_layout`) |
| Deterministic ordering (slots, ties, warnings by config index) | 3 |
| `content` measured once after build, re-measured on rebuild (only new, restyled or unmeasured panels) | 7 (decision 5) |
| Self-started re-layouts (measurement, geometry change) never crash the main loop | 7, 8 (decision 11) |
| Panels meeting at a shared screen corner; hidden panels keep their slot space | 3, 6, 11 (decision 3) |
| `EdgePanel` receives resolved pos/length; `anchor_and_margin` behind the resolver | 5 |
| Reload semantics (which changes rebuild which panels; `panel-move` considered) | 2, 5 (decision 7) |
| Re-layout on monitor geometry change (README limitation) | 8, 11 |
| Scene shapes follow the resolved layout | 5 (`_new_panel` builds `PanelShape` from the resolved geometry; tests check shapes) |
| Widgets: natural size, container behaviour for fill/percent | 7 (decision 8) |
| Render test: end-aligned panel next to the corner piece | 5 (`test_end_aligned_panel_next_to_the_corner_renders_like_legacy`), 9 (effects) |
| Simulation coverage | 9 |
| Example configs, README, spec | 6, 10, 11 |
| Human gates on HDMI-A-1 only, with commands and checklists | 6, 10 |

Not covered by design (out of scope): handle customization (15), settings window, corner-spanning panels, HiDPI, in-place move.

**2. Placeholder scan:** every code step carries the code; every test step carries the test; the gate checklists name exact values. The only conditional work is in the gates' "On failure" paths, each with a concrete first action.

**3. Type consistency:** `PanelRequest` field order (widget, edge, align, offset, pos, order, length, min_length, max_length, depth, state, label, fallback_length) is the same in Task 2's dataclass and every positional construction (Tasks 3, 5, 9 tests). `layout_monitor(requests, width, height, thickness, radius, gap, natural=None, where="monitor")` is called with that order in Tasks 5, 7, 9 and the gate checks. `MonitorShell(name, monitor, config, register_window, unregister_window=None, on_layout=None, on_error=None)` (Task 7) matches `FakeShell` and `Capturing` (`**callbacks`) in `tests/test_app_sync.py`, the `build` fixture of Tasks 7 and 8 (`on_layout=`, `on_error=` by keyword) and `EdgeShellApp.sync_monitors` (`on_layout=`, `on_error=` -> `_report_layout`, `_relayout_failed`). `content_length` (Task 4) is the one `EdgePanel.natural_length` (Task 7) uses. `_centre_view` / `clip_container` (Task 7) match their two tests. `RELAYOUT_DELAY_MS`, `set_monitor_size` (Task 8) match their tests; Task 8's `close` replaces Task 7's `_measure_id` block. `deprecated_pos_paths(config)` (Task 2, `shell/registry.py`) is called only by `EdgeShellApp._log_deprecated` (Task 2), never by `request_for`. `validate_widgets` (existing) is imported by `shell/canvas/simulate.py` in Task 9.

**4. Review Focus:** each of the six lines has its pinning test in the owning task (Tasks 1, 2, 3, 4, 5, 7, 8, 9) plus a gate item where a gate can see it.

**5. Test counts (expected, counted from the tests written here):** baseline 493 passed. After Task 1: 519 (+26). Task 2: 541 (+22). Task 3: 573 (+32, `tests/test_layout_resolver.py` has 32). Task 4: 588 (+15, the resolver file has 47). Task 5: 586 (`tests/test_panel_layout.py` 29 -> 30, `tests/test_monitor_shell.py` +3, `tests/test_registry.py` -5, `tests/test_geometry.py` -1). Task 7: 599 (+13). Task 8: 604 (+5). Task 9: 609 (+5). Without a display `test_clip_container_never_asks_for_the_content_size` is skipped (one fewer passed, one skipped). A different total is not a failure by itself, but check which test it is.

Verification while planning: Tasks 1-9 were first prototyped in a scratch copy of the worktree (not committed), and the interim state after Tasks 1-4 and the final state after Task 9 passed the full suite and ruff. After the review corrections, Tasks 2-4 were re-extracted from this file's text into a fresh scratch copy: `tests/test_layout_resolver.py` passes with the Task 3 code (32) and after the Task 4 edits (47), the full suite there passes (540 = 493 + 47; Tasks 1-2 tests not included) and ruff is clean. `clip_container`'s preferred size and the adjustment centring (`configure(0, 0, 800, 1, 10, 300)` -> value 250; page size 500 -> 150) were checked with a standalone GTK script (widgets only, no window). The other review changes in Tasks 2 and 5-11 (the deprecation log line, `on_error`, the measurement subset, the zero-geometry guard, the simulator's `validate_widgets`) were written against the current code but not run. The two example configs still resolve without warnings at 1920x1080 and 1280x720 (no center offsets, no corner neighbours at offset 0).

## Defaults pending Phil

Phil has not answered these yet; the plan is written for the default, and each changes little if he disagrees.

1. **Gap (decision 1): default pending Phil, 8 px kept.** Another value changes one default and the expected positions in the tests and gates.
2. **"content" startup rebuild (decision 5): default pending Phil, the one-off rebuild is accepted.** The in-place resize (1-2 tasks) is planned only if Gate B item 2 shows a visible flash.
3. **`pos` deprecation (decision 2): default pending Phil, no notification; one INFO log line per config load and reload** listing the key paths still using `pos` (`deprecated_pos_paths`, Task 2).
4. Resolution change at Gate B (former open question): now a required item done through System Settings > Display with Revert (or a saved `kscreen-doctor -o`), on HDMI-A-1 only; DP-1's settings are never touched.
