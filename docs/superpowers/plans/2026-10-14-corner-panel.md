# Corner Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new kind of panel, the corner panel: one rectangular window in a screen corner that is connected to the frame along two of its sides. It is declared in the same `[[monitors.X.panels]]` list as edge panels, animates like an edge panel (collapse, hover peek, click, drag), and is drawn by the shape canvas as part of the one outline, with border and shadow. The first corner widget is the spec's `widget_panel`: bottom-left, 300 x 390 px, showing the time, date, CPU and RAM.

**Architecture:** First the pure core, built and tested headlessly:
- the config keys (`corner`, `edge`, `width`, `height`) in `shell/config/models.py`;
- a corner request and geometry in `shell/panel_spec.py`, with the registry deciding the kind from the widget's defaults (`shell/registry.py`);
- corner geometry in the new `shell/corner.py`: surface, body, content, hit target, input rects and damage box, all rectangles;
- the outline: `shell/canvas/outline.py` gains a `corners` argument that changes only the two ends of each edge's walk. Edge-panel paths stay byte-identical;
- scene, painter and simulation in `shell/canvas/*`;
- the layout resolver (`shell/panel_layout.py`): corner panels are placed first, then edge panels keep clear of them;
- a PNG review sheet (`shell/canvas/corner_sheet.py`).

Then the GTK side. `CornerPanel(EdgePanel)` (`shell/corner_panel.py`) overrides only the geometry hooks: surface layout, input rects, content and handle placement. The handle, interactions, tween, fade and raise all stay `EdgePanel`'s. `MonitorShell` builds corner panels through the same `_sync_panels` path. The widget is `widgets/widget_panel.py`.

**Tech Stack:** Python 3.14 (>=3.12), Fabric 0.0.2, PyGObject 3.50.0 (`<3.52`), pycairo, GtkLayerShell, Pydantic 2, pytest, ruff 0.17.0.

**Spec:** `docs/superpowers/specs/2026-10-11-edge-shell-design.md`. The relevant sections:
- section 3: the `widget_panel` row of the default surfaces table, and "A corner-anchored panel has one free-edge join; its other join sits on the frame beside it";
- section 17: "Corner-spanning panels ... are a separate widget type with their own geometry (`corner`, width, height), built later; they are the only panels that meet two edges";
- section 12: milestone 8, corner widget panel;
- sections 4 (interaction), 5 (surfaces), 6 (config, reload table), 15 (handle rules), 16-17 (layout) and 18 (canvas, border outside the mass, damaged-region redraw).

Previous plans (style, gates, constraints): `docs/superpowers/plans/2026-10-13-shape-canvas-and-effects.md`, `docs/superpowers/plans/2026-10-13-layout-anchoring.md` and `docs/superpowers/plans/2026-10-13-handle-customization.md`. Findings: `docs/superpowers/findings/2026-10-12-shape-canvas-spike.md` (self-intersection rules, damage contract).

**Why now:** Phil asked: "Did we plan for the corner panel? The one that connects to two edges of the frame?" It had only been noted and deferred (spec 17, Plan 2's out-of-scope list). He wants it planned and built before the settings window (Plan 4, drafted separately on `feat/settings-window`), because the settings window's panel list should include corner panels. Phil's clarification (verbatim): "the corner panel window should be a square that connects to two edges. I want to make sure that is clear, it is not an L shaped panel window".

**Scope (Plan 5).**
- In:
  - the config keys and their validation;
  - corner widgets in the registry;
  - pure geometry, outline, scene and damage, and layout for corner panels;
  - the review sheet;
  - `CornerPanel`, its `MonitorShell` integration and the `widget_panel` widget;
  - reload (the existing change kinds), an example config, two gates, README and spec.
- Out:
  - the settings window (its inputs are made ready: decision 6);
  - letting an edge widget (clock, dock) sit in a corner (decision 6, with the cost);
  - a "content" length for corner panels;
  - several corner panels in one corner;
  - per-panel border and shadow;
  - HiDPI.

**Date:** 2026-10-14 (the plan's execution date, as in the file name).

**Size:** 13 tasks.
- 10 carry code and tests: Tasks 1-7 and 9-11.
- 2 are human gates: Gate A (Task 8) is a PNG review that needs no running shell; Gate B (Task 12) is live on HDMI-A-1.
- Task 13 is docs.

The riskiest tasks:
- **Task 4:** the outline walk at the corners. One wrong arc direction makes a spike or a hole. 64 reference-union pixel tests check every corner, opening edge and depth, at R = 14 and at R = 40.
- **Task 6:** layout precedence and clearance. A missed rule gives a self-intersecting outline (spike finding: 20-30 wrong pixels).
- **Task 9:** the corner window's absolute placement inside a GTK Overlay. Only stand-ins test it; Gate B items 1-5 check it live.

## Decisions (each default pending Phil, with the cost if Phil disagrees)

The spec leaves these open. They are the planner's choices; nothing below is built yet.

1. **Geometry: a rectangle in the corner that opens from one edge.** *Default pending Phil.*
   - **The shape.** A corner panel is a plain rectangle (a square-ish block) in one screen corner. It is `width` x `height` px measured from the screen corner, with both frame bands included. It is NOT an L: **the corner panel window is a rectangle, not an L.**
   - **Its two sides on the screen edges.** They lie on the two screen edges of the corner, so the panel covers that corner's piece of both frame bands.
   - **Its two free sides.** Each meets one of the two frame bands with a concave fillet. This is what "connects to two edges" means.
     - The free side parallel to the opening edge (for the bottom-left `widget_panel`: its top side) meets the OTHER band (the left band). There the fillet is the screen corner's own arc, radius R, lifted along that band by the panel's current depth. At depth 0 it is exactly today's screen corner, so a collapsed corner panel draws the plain frame.
     - The free side perpendicular to the opening edge (its right side) meets the band of the opening edge (the bottom band) with an edge panel's join: a concave fillet plus a convex free corner, radius `min(R, d/2)`, the S-curve rule of spec 4.
   - **What animates.** Only one extent animates: the depth past the band of the edge it opens from (`edge`, default the corner's top or bottom edge, so the `widget_panel` rises out of the bottom edge as the spec's table implies). This works exactly like an edge panel: collapsed means depth 0, peek is `theme.peek`, the 50% drag snap applies, and the 280 ms tween is the same. The other extent stays constant.
   - **The widget_panel's numbers.** `along` = 300 px along the bottom edge from the corner (the spec's "300 incl. left frame"), depth = 380 px past the bottom band (the spec's "extended depth 380"). That is `width = 300`, `height = 390`.
   - **How the outline is traced.** Each edge's walk (`trace_edge`) gains a `head` and a `tail` (a corner panel on this edge in its start or end corner) and a `lead` and a `trail` (one in the neighbouring edge's corner that lifts this edge's start or end arc). With every depth 0 the path is operation-for-operation the plain frame (pinned by a test).
   - **Minimum geometry** (the spike's self-intersection rules, applied by the layout):
     - along >= max(T + 60, T + R + r): the 60 px body floor past the band, and the side from the lifted arc (`T + R`) to the free corner (`along - r`) never runs backwards. `T + 60` alone covers only `R + r <= 60`, but the theme allows R up to 64: with R = 40 and r = 40 the outline would fold (the reviewer's stress sheet). The layout floors `along` to this `need` and hides the panel when less remains;
     - depth >= 16 (`MIN_DEPTH`). The hover zone and the peek can be larger (both up to 64 px); they are clamped to the depth exactly as on edge panels (`input_rects` uses `min(hover_zone, depth)`, `panel_state.target_depth` uses `min(peek, depth)`), so a 16 px deep corner panel peeks 16 px. Pinned by `test_a_shallow_corner_panel_clamps_the_hover_zone_and_the_peek` (Task 3);
     - the lifted arc stays clear of the far corner of the other edge: `T + R + depth <= extent - (T + R)`, or minus that corner's occupant;
     - the free end stays clear of the far corner of its edge (plus `gap` when it faces another corner panel).
   - **Cost if Phil wants both extents to animate** (a diagonal grow out of the corner): at small sizes the panel lies inside the screen corner's rounding. Its lifted arc would need a radius that jumps from R to `min(R, a, b)`, or a traced union of the corner piece and the body. That is about one more task (union tracing plus its reference tests), a different handle (diagonal drag), and a new Gate A. A lifted arc that shrinks to `min(R, d/2)`, like a join: a discontinuity at d = 0, where the screen corner is R. Rejected.

2. **Canvas: one `corners` argument through the existing pipeline; edge panels unchanged.** *Default pending Phil.*
   - `outline_path`, `fill_mass`, `draw_border`, `draw_shadow_uniform`, `draw_shadow_reach` and `draw_scene` gain a keyword `corners` (default empty). Every existing call is unchanged, and so is the legacy renderer contract (`tests/legacy_draw.py`, `tests/test_canvas_outline.py`).
   - The new contract is a reference union of simple filled pieces: frame bands, screen-corner pieces, the body with its rounded free corner, the free-end fillet, and the lifted corner piece. It is checked in all 8 (corner, edge) cases at depths 0, 3, 14, 27.5, 60 and 100, with the same tolerance as the legacy test.
   - `Scene` keeps `CornerShape`s next to `PanelShape`s. The damage box (`shell.corner.corner_box`) covers the body, the free-end fillet and the lifted arc (`along + R` by `T + d + R`), grown by `pad`.
   - The damage contract (clipped redraws equal a full redraw) is pinned with border and shadow, as for edge panels.
   - Strips unchanged: corner panels float like edge panels; the strips reserve thickness + border width.
   - *Cost:* none structural. A separate corner renderer would break the one-path union (shadow double-darkening, seams).

3. **Layout: corner panels first, one per corner, shrink to fit; edge panels keep clear of them.** *Default pending Phil.*
   - **Order.** Corner panels are placed first, in config order.
   - **A taken corner.** A second corner panel in that corner is not shown: `... the bottom-left corner already holds monitors.X.panels.N (widget_panel); not shown`, with a "Panels adjusted" notification.
   - **Shrinking.** A corner panel is shrunk to fit beside the corner panels already placed (a warning names `width` or `height`), and not shown when `along` falls below `max(T + 60, T + R + r)` or less than 16 px of depth remains. A panel that ends up hidden gets only the "has no room for it; not shown" warning, never a "shrunk to" one before it. On its own edge it keeps `r1 + r2 + gap` from another corner panel's free end; against a lifted arc it keeps `r` (like a plain screen corner).
   - **Edge panels on the edge it opens from.** The free span starts `along + r_c + gap + r` from that corner, the same spacing as two neighbours.
   - **Edge panels on the other edge.** The free span starts `T + R + depth + r` from the corner: the lifted screen-corner arc, at full depth so animation never collides. No `gap` there (option A; whether to add one is open decision 10).
   - **The overlap check.** Corner panels are checked against each other inside `layout_corners`, before any is held: a corner panel that overlaps an earlier one is hidden with the usual "overlaps ... not shown" warning and takes no clearance, so it moves no edge panel (bottom-left 1200 x 700 plus top-right 1200 x 700: the top-right one is hidden, and a top `align = "end"` panel stays at the plain corner, pos 1582, not 384). Then edge panels are checked (config order) against the shown corner panels and each other, so a deep corner panel hides an edge panel on a far edge that it overlaps, whatever their config order.
   - **Resolution changes and hot-plug.** They reuse Plan 2's `notify::geometry` re-layout and the hot-plug sync unchanged: a smaller monitor shrinks a corner panel with a warning, never an error.
   - *Cost if Phil prefers one config order for both kinds:* a corner listed after an edge panel would lose to it. That is a small change (merge the two orders in `layout_monitor` and drop the corners from the edges' clearances when hidden), but then an edge panel can hide the corner panel it sits next to.

4. **Window: one rectangular layer-shell window per corner panel, a subclass of `EdgePanel`.** *Default pending Phil.* **The corner panel window is a rectangle, not an L.**
   - **Anchoring.** `CornerPanel(EdgePanel)` is anchored to the corner's two screen edges (`"bottom left"`) with zero margins. Its surface is exactly the extended body: `along` x `(T + depth)` (300 x 390 for the `widget_panel`), allocated once.
   - **Placement.** The content box sits past both bands (`along - T` x `depth`). The handle sits on the body's inner edge.
   - **Input.** The region is the body rectangle at depth d (plus the invisible hover zone while collapsed), or the body plus the handle's hit target when hover is off, or nothing when collapsed with every interaction off. Always plain rectangles; never an L-shaped region.
   - **Unchanged.** The frame band beside a collapsed corner panel stays click-through like any band. Exclusive zone -1 (`exclusivity="none"` then `set_exclusive_zone(-1)`, inherited). The delayed `raise_to_top` workaround (corner panels are live panels and are raised with the rest). Strips unchanged.
   - *Cost if Phil wants a stand-alone class:* about 300 duplicated lines of `EdgePanel` (handle, drag, hover, fade, input upkeep). The subclass needs two small, behaviour-preserving hooks in `EdgePanel` (`surface_layout`, `_input_rects`), pinned by the existing tests.

5. **Handle: on the free side parallel to the opening edge, with Plan 3's rules unchanged.** *Default pending Phil.*
   - **Position.** It is centred on the body past the adjacent band. For the `widget_panel`: x = 10 + 290 / 2 = 155 (hit target x 133-177, 14 px tall), riding the body's inner edge (the band while collapsed) at Plan 3's inset (`shape_offset`, `hit_inset`, `shape_room`, 14 px target).
   - **Unchanged rules.** `handle.offset` keeps its screen meaning (negative = left or up) in every corner. Shapes `auto | dots | bar | chevron | none` and the per-panel `handle` and `interaction` tables work as on edge panels. The chevron folds the same way (it points into the desktop while collapsed). The drag axis is the opening edge's axis (vertical for the `widget_panel`). The peek is `theme.peek`.
   - *Cost if Phil wants the handle at the free corner, dragged diagonally:* a new handle placement and a diagonal `drag_depth`, plus a new review sheet. About 1 task.

6. **Config: the same `[[monitors.X.panels]]` list; the kind comes from the widget.** *Default pending Phil.*
   - **Registration.** A widget registered with `CornerDefaults(corner, width, height, label, edge=None, state, handle, interaction)` is a corner widget. Its entries take `corner` (`top-left | top-right | bottom-left | bottom-right`), `edge` (one of the corner's two edges), `width` and `height` (60-4000 px), plus `state`, `handle` and `interaction`.
   - **Rejected keys.** An entry mixing corner keys with edge-only keys (`pos`, `align`, `offset`, `order`, `length`, `min_length`, `max_length`, `depth`) is rejected by the model with its key path. An edge key on a corner widget, a corner key on an edge widget, or an `edge` that is not an edge of the corner is rejected by `validate_widgets` at load, naming the key path (for example `monitors.HDMI-A-1.panels[0].align: widget_panel is a corner panel; it takes corner, edge, width and height, not align`). An invalid config never replaces the working one.
   - **Moving corners.** A moved `corner` without an `edge` keeps the widget's edge when it belongs to the new corner, else uses the corner's top or bottom edge.
   - **Reload.** It uses the existing change kinds: `state` is `panel-state`; `handle` and `interaction` are `panel-handle` (in place); `corner`, `edge`, `width` and `height` are `panel-rebuild`, plus a rebuild of any edge panel whose resolved place changed.
   - **Settings-window readiness: the contract the settings plan must use.** The models and the registry stay the single source; the settings window reads only these public names:
     - `registry.widget_kind(name)` (`"edge"` or `"corner"`) decides which keys a panel's section shows;
     - `shell.config.models.SHARED_KEYS = ("widget", "edge", "state", "handle", "interaction")` are shown for both kinds; `EDGE_ONLY_KEYS` only for edge widgets and `CORNER_ONLY_KEYS = ("corner", "width", "height")` only for corner widgets. The three partition `PanelConfig`'s fields (pinned by `test_the_key_sets_partition_the_panel_keys`, Task 1);
     - `registry.defaults(name)` gives a widget's `PanelDefaults` or `CornerDefaults` (placeholders, "reset to default"); the settings window never reads `registry._DEFAULTS` (Task 2);
     - "the corner's two edges" are `corner.split("-")` (for example `("bottom", "left")`), and the edge used when none is set is `panel_spec.default_edge(corner)`; `corner_has_edge(corner, edge)` checks a choice;
     - `Corner` / `CORNERS` for the corner choice, and the JSON schema (`corner`, `width` and `height` are pinned in `Config.model_json_schema()`, 60-4000 px).
   - **Only corner widgets go in corners.** An edge widget (clock, dock) cannot sit in a corner in this plan. *Cost if Phil wants any widget in a corner:* a corner subclass built per widget at registration (a dynamic `type()` per widget class, cached; PyGObject registers one GType each). About 1 task.
   - *Cost if Phil wants a separate `[[monitors.X.corners]]` table:* a second index space in `diff_configs`, `MonitorShell` and the layout, and two lists in the settings window. About 1 task, against Phil's wish of one panel list.

7. **Content: `widget_panel` v1 is one centred column: the time (32 px), the date, CPU % and RAM %.** *Default pending Phil.* It reuses `widgets.clock.format_time` and `services.sysinfo`, refreshes every second (stats every 2 s) and stops its timer on destroy. Defaults: `corner = "bottom-left"`, `edge = "bottom"` (implied), `width = 300`, `height = 390`, `state = "extended"`, label `"widget panel"`. *Cost:* a container API for other widgets later is a separate small plan; the column is built by one `build_content`.

8. **Sizes are measured from the screen corner, with both frame bands included.** *Default pending Phil.* `width` and `height` are the panel's outer size on screen, whatever edge it opens from, so "a 300 x 390 box in the bottom-left corner" means what it says. Depth past the band = the extent across the opening edge minus `T`. *Cost if Phil prefers "past the frame":* subtract `T` in `layout_corners` and update the defaults and tests (trivial).

9. **Gates.**
   - Gate A (Task 8): two PNG sheets, no shell. Every corner, both opening edges, six collapse fractions, edge panels placed by the resolver right beside it; plain and with border and shadow.
   - Gate B (Task 12): live, on HDMI-A-1 ONLY (never DP-1), with `examples/corner-test.toml`. Live probes at most 10 s.

10. **Open decision for Phil: a gap on the other edge too?** *Option A, default pending Phil (what this plan builds).*
    - **Option A (as planned).** An edge panel on the corner panel's other edge starts at `T + R + depth + r` from the corner: at full depth its fillet starts exactly where the lifted corner arc ends. There is no straight piece of frame between them: a stepped silhouette, but valid geometry (no overlap, no self-intersection; pinned by `test_corner_panels_next_to_edge_panels_cleared_by_the_layout`, Task 4). On the edge the corner panel opens from, the `gap` is kept as between two neighbours.
    - **Option B.** Keep the `gap` on the other edge as well: in `corner_clearance`, drop the `held.edge == edge` condition (`spare = gap if held is not None else 0`). It changes these expected numbers (checked in the scratch copy: 3 tests fail, the rest pass): `test_corner_clearance` (`24 + 380` -> `24 + 380 + 8`, `24 + 290` -> `24 + 290 + 8`), `test_an_edge_panel_on_the_other_edge_stays_below_the_lifted_corner_arc` (`("left", 362, 300)` -> `("left", 354, 300)`), `test_a_corner_panel_opening_from_the_side_edge_moves_the_other_edge` (`("bottom", 328, 560)` -> `("bottom", 336, 560)`), Task 11 Step 5's expected `('left', 362, 300)` -> `('left', 354, 300)`, and Gate B item 4 (the system bar at y 362-662 -> 354-654). A one-line code change plus those numbers, made before Task 6 runs; nothing else moves.

## Prerequisites

- Branch `feat/corner-panel` from `origin/main` at `ad58f61` (Plans 1-3 merged).
- Baseline before Task 1: `scripts/py -m pytest -q` prints `1192 passed` (2 GLib deprecation warnings are normal); `scripts/py -m ruff check .` prints `All checks passed!`.
- Always stage files by name, never `git add -A` or `git add .`.
- The pure parts of this plan (Tasks 1-7, 9-11) were prototyped in a scratch copy by the planner: every code block and test below passed as written, task by task (1424 passed at the end, ruff check and ruff format clean after every task). The review sheet was rendered and inspected. After the independent review's corrections the code and tests were re-extracted into a fresh copy and re-run the same way.
- **The settings plan must be updated before it executes.** Plan 4 (`feat/settings-window`, 14 tasks) was drafted before corner panels and does not know them. Before its Task 1 runs, update it to use decision 6's contract (`widget_kind`, `SHARED_KEYS` / `EDGE_ONLY_KEYS` / `CORNER_ONLY_KEYS`, `registry.defaults`, `corner.split("-")`, `default_edge`), with these 10 changes:
  1. two panel sections, edge and corner, built through `section_for` with skip sets (`CORNER_ONLY_KEYS` skipped for edge widgets, `EDGE_ONLY_KEYS` for corner widgets);
  2. a `corner` enum row (`CORNERS`) and `width` / `height` spinbuttons (60-4000) in the corner section;
  3. the `edge` row of a corner panel offers only the corner's two edges (`corner.split("-")`), unset meaning `default_edge(corner)`;
  4. a `CornerDefaults` branch in `settings/values.py` (placeholders from `registry.defaults(name)`, never `_DEFAULTS`);
  5. panel titles for `CornerRequest` in `settings/panels.py`: `{widget}: {corner}, from {edge}, {width}x{height}`;
  6. switching a panel's widget to the other kind unsets the other kind's keys in the same single edit (one save, one reload);
  7. changing `corner` unsets an `edge` that is no longer an edge of the new corner (same edit);
  8. the widget combo grouped by kind (edge widgets, then corner widgets);
  9. the layout-warning preview lists corner items too (the three new warning texts of Task 6);
  10. handle right-click (its Task 11) works on corner panels: `CornerPanel` inherits it from `EdgePanel`; add a corner case to its tests.
- **Expect merge conflicts with the settings plan.** Its Task 11 (right-click on a handle) and this plan's Tasks 9-10 both change `shell/edge_panel.py` and `shell/monitors.py`. Whichever plan runs second rebases onto the first and resolves them there (both sides keep their changes: the hooks `surface_layout` / `_input_rects` and corner building here, the right-click handler there).

## Global Constraints

- Python only through `scripts/py` (shared venv `/home/phil/Projects/pyDev/pyEnvs/global-base`). **PyGObject must stay `<3.52`** (Fabric 0.0.2 breaks on 3.52+).
- **Monitor is an INT.** Fabric 0.0.2's `WaylandWindow.monitor` is an int property; a `Gdk.Monitor` object is silently dropped. Always pass `monitor=monitor_index(monitor)` (`shell/gdk_util.py`). `CornerPanel` inherits `EdgePanel.__init__`, which already does.
- **Input shape after allocate.** Fabric's `Window.do_size_allocate` resets the input shape on every allocate. `EdgePanel.do_size_allocate` re-applies the panel's region. Never drop that override. `_update_input_region` (and so `_input_rects`, which `CornerPanel` overrides) must stay callable from it: everything it reads is set before `_d` in `__init__`.
- **Exclusive zones** unchanged: panels and the canvas use `exclusivity="none"` then `GtkLayerShell.set_exclusive_zone(self, -1)`.
- **Keep the delayed `raise_to_top` workaround** (`RAISE_DELAY_MS` / `RAISE_FALLBACK_MS` in `shell/monitors.py`, and the re-raise of rebuilt panels in `_new_panel`). The canvas covers panel windows until the re-raise (confirmed live at Plan 3 Gate B item 11). Corner panels are raised like edge panels. An in-place update must not schedule a re-raise.
- **The border is drawn OUTSIDE the mass.** The shadow is measured from its outer edge. The strips reserve thickness + border width. None of that changes.
- **Handle rules of Plan 3** stay as they are:
  - the shape's centre sits `T + d - min(T/2, 5)` px from the screen edge (`hd.shape_offset`);
  - the shape is at most `shape_room(T)` across;
  - the hit target is at least 44 x 14 px and rides the inner edge (`hd.hit_inset`);
  - `handle.offset` is clamped to the body.
- **The corner panel window is a rectangle, not an L.** Its surface, body, content box and input rects are rectangles (decision 4).
- **Pure modules import no GTK / `gi`:** `shell/corner.py`, `shell/panel_spec.py`, `shell/registry.py`, `shell/panel_layout.py`, `shell/geometry.py`, `shell/handle.py`, `shell/config/*`, and `shell/canvas/*` except `canvas.py`. pycairo is allowed (CI has it).
- **Colours** are `#rrggbb` or `#rrggbbaa` (`check_hex`, `hex_to_rgba`).
- **Tests.** CI has only pycairo, pydantic, pytest and ruff: any test importing `gi` or `fabric` starts with `pytest.importorskip("gi")` / `pytest.importorskip("fabric")`. Tests never create a window (that would draw on Phil's screen): GTK classes are tested by calling their methods on stand-ins (`SimpleNamespace`).
- **Lint.** `ruff` 0.17.0, line length 100, rules E, F, I, UP, B, excludes `docs/` and `*.md`.
- **VERIFY** (before every commit): `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`. The suite must be green at the end of EVERY task (0 failed).
- **Git.**
  - Plain separate git commands run from the worktree (no `cd … && git`, no command substitution around git).
  - Stage files by name.
  - **Never push.**
  - Every commit message ends with a second `-m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"`.
- **Live runs.**
  - Phil is the only visual tester, on `HDMI-A-1` only. **Never touch `DP-1`**: it holds the Plasma panel; never configure it as `edge`.
  - Subagents executing tasks never launch the shell or any GUI (`main.py` without `--list-outputs`). Headless commands are fine: `pytest`, `scripts/py -m shell.canvas.corner_sheet …`, `scripts/py -m shell.canvas.simulate …`, and the `scripts/py -c` checks, which import the widgets but create no window.
  - Live probes are capped at 10 s (`main.py --stats` refuses more) and are run by Phil at the gates.
  - If a live run is refused for a subagent, stop and report.

## Review Focus

The six input classes most likely to bite Phil that the spec implies but a happy-path test would not catch, each pinned by a test in the owning task:

1. **The corner panel window is a rectangle, not an L** (Phil's words: "it is not an L shaped panel window"). Expect:
   - the surface is anchored in the corner and sized to the extended body;
   - every input rect is a plain rectangle inside the surface, at every depth and interaction set;
   - the content box is a rectangle past both bands.

   Pinned by:
   - `test_every_input_rect_is_a_plain_rectangle_inside_the_surface` and `test_the_window_is_a_rectangle_in_the_corner` (Task 3);
   - `test_the_corner_window_is_a_rectangle_anchored_in_its_corner` and `test_the_content_sits_past_both_frame_bands` (Task 9);

   live by Gate B item 1.
2. **A collapsed or barely open corner panel** must draw exactly the plain frame at depth 0 and a smooth S-curve while shallow: no notch, spike or hole at the lifted corner arc or the free-end fillet, in every corner and from both opening edges.

   Pinned by:
   - `test_with_every_depth_zero_the_path_is_the_plain_frame` and `test_a_corner_panel_matches_the_reference_union` at depths 0, 3 and 14 (Task 4);
   - `test_a_collapsed_corner_panel_draws_the_plain_frame` (Task 7);

   live by Gate A items 1-3 and Gate B item 2.
3. **Edge panels near a corner panel, a large theme radius, and a smaller monitor.** An edge panel aligned towards the corner, a "fill" panel, a second corner panel on a shared edge, a corner panel hidden by the overlap check, a deep panel on a far edge, a theme radius up to 64, or a resolution change. Expect no overlap and no self-intersecting outline: clearances applied (and none taken by a hidden corner panel), `along` floored to `max(T + 60, T + R + r)`, things shrunk or hidden with one "Panels adjusted" warning per outcome naming the key, never a crash.

   Pinned by:
   - `test_an_edge_panel_starts_past_the_corner_panel_on_its_edge`, `test_an_edge_panel_on_the_other_edge_stays_below_the_lifted_corner_arc`, `test_a_fill_panel_fills_up_to_the_corner_panel`, `test_two_corner_panels_facing_on_one_edge_keep_their_joins_and_the_gap`, `test_a_lifted_corner_arc_limits_the_next_corner_across`, `test_corner_panels_win_over_earlier_edge_panels_they_overlap`, `test_a_hidden_corner_panel_takes_no_clearance`, `test_a_large_radius_raises_the_minimum_along`, `test_a_corner_squeezed_below_the_minimum_is_not_shown` (Task 6);
   - `test_corner_panels_next_to_edge_panels_cleared_by_the_layout` and the R = 40 rows of `test_a_corner_panel_matches_the_reference_union` (Task 4);
   - `test_a_smaller_monitor_shrinks_the_corner_panel` (Task 10);

   live by Gate B items 4 and 11.
4. **Keys of the wrong kind or bad corner values** must be rejected with the key path while the last good config stays: `align` on a corner widget, `width` on the dock, `edge = "top"` on a bottom-left panel, `corner = "middle"`, `width = 59`.

   Pinned by:
   - `test_bad_corner_values_name_the_key_path` (Task 1);
   - `test_keys_of_the_other_kind_are_rejected_with_the_key_path` and `test_bad_corner_defaults_fail_at_registration` (Task 2);

   live by Gate B item 9.
5. **Animating corner panels with the border and the shadow** must leave no stale pixels (trails) where the lifted arc moves along the other band.

   Pinned by:
   - `test_damaged_redraws_with_corner_panels_equal_a_full_redraw` (three themes), `test_random_corner_depth_jumps_never_leave_stale_pixels` and `test_set_depth_damages_old_and_new_corner_box` (Task 5);
   - `test_the_border_never_touches_the_corner_panels_mass` and `test_the_shadow_follows_the_corner_panel_and_stays_off_its_mass` (Task 4);

   live by Gate B item 7.
6. **A reload that changes only the handle, interactions or state of a corner panel** must update it in place: no rebuild, no re-raise. A size change rebuilds only the panels that moved.

   Pinned by:
   - `test_reload_kinds_for_corner_panels` (Task 2);
   - `test_a_corner_handle_change_is_applied_in_place`, `test_a_corner_state_change_retargets_in_place` and `test_a_corner_size_change_rebuilds_only_that_panel` (Task 10);

   live by Gate B item 8.

## File Structure

```
shell/config/models.py        # + Corner, CORNERS, SHARED_KEYS, EDGE_ONLY_KEYS, CORNER_ONLY_KEYS;
                              #   PanelConfig.corner / .width / .height + kind / edge checks
shell/panel_spec.py           # + default_edge, corner_has_edge, CornerDefaults, CornerRequest,
                              #   CornerGeometry
shell/registry.py             # register() takes CornerDefaults; widget_kind; defaults; corner requests;
                              #   validate_widgets checks keys against the widget's kind
shell/corner.py               # NEW, PURE: to_xy, pq_box, surface_size, anchor, corner_box,
                              #   body_rect, content_rect, hit_rect, input_rects
shell/canvas/outline.py       # + CornerSpan; trace_edge head / tail / lead / trail; corners arg
shell/canvas/effects.py       # corners arg through border, shadow, draw_scene
shell/canvas/scene.py         # + CornerShape, Shape, shape_for; Scene keeps corner shapes;
                              #   outline_corners; corner damage box
shell/canvas/painter.py       # draws corners; Shape type
shell/canvas/canvas.py        # Shape type only
shell/canvas/simulate.py      # Shape type; config_shapes via shape_for
shell/panel_layout.py         # + MIN_DEPTH, AXIS_START / AXIS_END, corner_clearance,
                              #   layout_corners; free_span / layout_edge take clearances;
                              #   layout_monitor places corners first
shell/canvas/corner_sheet.py  # NEW, PURE: Gate A review sheet (python -m shell.canvas.corner_sheet)
shell/edge_panel.py           # hooks: surface_layout (classmethod), _input_rects
shell/corner_panel.py         # NEW (GTK): CornerPanel(EdgePanel), place_at
shell/monitors.py             # corner shapes via shape_for; corner panels never measured
widgets/widget_panel.py       # NEW: the widget_panel corner widget
widgets/__init__.py           # registers widget_panel
shell/theme.py                # + #widget-panel-time CSS
examples/corner-test.toml     # Gate B
tests/conftest.py             # + corner_registry fixture
tests/test_config_corner.py, tests/test_corner_requests.py, tests/test_corner_geometry.py,
tests/test_canvas_corner_outline.py, tests/test_canvas_corner_scene.py,
tests/test_corner_layout.py, tests/test_corner_sheet.py, tests/test_corner_panel.py,
tests/test_widget_panel.py    # NEW
tests/test_edge_panel_handle.py  # the stand-in binds _input_rects (Task 9)
tests/test_monitor_shell.py   # 9 corner tests appended (Task 10)
README.md, docs/superpowers/specs/2026-10-11-edge-shell-design.md   # Task 13
```

| Task | Deliverable | Expected `pytest -q` | Keeps the suite green because |
| --- | --- | --- | --- |
| 1 | config keys and checks, the key sets | 1208 (+16) | new keys optional |
| 2 | corner requests, registry kind and defaults, key checks, diff | 1233 (+25) | edge widgets unchanged; new fixture only |
| 3 | pure corner geometry | 1270 (+37) | new module |
| 4 | outline and effects with corners | 1340 (+70) | `corners` defaults to empty; edge paths identical |
| 5 | scene, painter, simulate | 1350 (+10) | `Shape` includes `PanelShape` |
| 6 | layout resolver | 1378 (+28) | no corner requests = old layout |
| 7 | review sheet | 1396 (+18) | new module |
| 8 | Gate A (PNG sheets, Phil) | 1396 | no code |
| 9 | `EdgePanel` hooks, `CornerPanel` | 1410 (+14) | hooks are behaviour-preserving |
| 10 | `MonitorShell` builds corner panels | 1419 (+9) | edge path unchanged |
| 11 | `widget_panel` widget, CSS, example | 1424 (+5) | new widget |
| 12 | Gate B (live, Phil) | 1424 | no code |
| 13 | README, spec | 1424 | docs only |

Without `gi`/Fabric (CI) the GTK tests skip themselves: Task 9's 14, Task 10's 9 and Task 11's 5, as the existing GTK tests do.

---

### Task 1: Config keys for corner panels

**Files:**
- Modify: `shell/config/models.py`
- Test: `tests/test_config_corner.py` (new)

**Interfaces:**
- Consumes: `_Strict`, `Edge`, `PanelConfig` (existing).
- Produces:
  - `shell.config.models.Corner = Literal["top-left", "top-right", "bottom-left", "bottom-right"]`, `CORNERS: tuple[str, ...]` (same order);
  - `SHARED_KEYS = ("widget", "edge", "state", "handle", "interaction")` (the keys both kinds take), `EDGE_ONLY_KEYS = ("pos", "align", "offset", "order", "length", "min_length", "max_length", "depth")` and `CORNER_ONLY_KEYS = ("corner", "width", "height")`: public module constants that together partition `PanelConfig`'s fields (the settings window reads them; decision 6);
  - `PanelConfig.corner: Corner | None`, `.width: Length | None`, `.height: Length | None` (the existing 60-4000 px `Length`), all default None;
  - `PanelConfig._placement` rejects an entry mixing the two kinds' keys, and an `edge` that is not an edge of the entry's own `corner`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_corner.py`:

```python
"""Corner panel keys in the config models (spec 19): corner, edge, width, height."""

import pytest

from shell.config.loader import parse_config
from shell.config.models import (
    CORNER_ONLY_KEYS,
    CORNERS,
    EDGE_ONLY_KEYS,
    SHARED_KEYS,
    Config,
    ConfigError,
    PanelConfig,
)


def entry(**keys):
    return PanelConfig.model_validate({"widget": "widget_panel", **keys})


def load(make_config, **keys):
    return parse_config(
        {
            "theme": make_config().theme.model_dump(),
            "monitors": {"HDMI-A-1": {"shell": "edge", "panels": [{"widget": "w", **keys}]}},
        }
    )


def test_corner_keys_default_to_none():
    p = entry()
    assert (p.corner, p.width, p.height) == (None, None, None)


def test_corner_keys_are_read():
    p = entry(corner="bottom-left", edge="left", width=300, height=390)
    assert (p.corner, p.edge, p.width, p.height) == ("bottom-left", "left", 300, 390)


def test_the_four_corners_are_exported_in_order():
    assert CORNERS == ("top-left", "top-right", "bottom-left", "bottom-right")


def test_the_key_sets_partition_the_panel_keys():
    """The settings window shows SHARED_KEYS plus the keys of the widget's kind."""
    assert SHARED_KEYS == ("widget", "edge", "state", "handle", "interaction")
    assert CORNER_ONLY_KEYS == ("corner", "width", "height")
    keys = SHARED_KEYS + EDGE_ONLY_KEYS + CORNER_ONLY_KEYS
    assert len(set(keys)) == len(keys) and set(keys) == set(PanelConfig.model_fields)


@pytest.mark.parametrize(
    ("keys", "path", "words"),
    [
        ({"corner": "middle"}, "corner", "'top-left', 'top-right', 'bottom-left' or"),
        ({"width": 59}, "width", "greater than or equal to 60"),
        ({"height": 4001}, "height", "less than or equal to 4000"),
        ({"width": 300.5}, "width", "valid integer"),
        ({"corner": "bottom-left", "edge": "top"}, "", "not an edge of the bottom-left corner"),
        ({"corner": "top-right", "align": "end"}, "", "align cannot be combined with corner"),
        ({"width": 300, "depth": 80, "length": 200}, "", "length, depth cannot be combined"),
        ({"height": 300, "pos": 40}, "", "pos cannot be combined with height"),
    ],
)
def test_bad_corner_values_name_the_key_path(make_config, keys, path, words):
    with pytest.raises(ConfigError) as exc:
        load(make_config, **keys)
    where = "monitors.HDMI-A-1.panels.0" + (f".{path}" if path else "")
    assert where in str(exc.value) and words in str(exc.value), str(exc.value)


def test_the_edge_may_be_either_edge_of_the_corner():
    assert entry(corner="top-right", edge="right").edge == "right"
    assert entry(corner="top-right", edge="top").edge == "top"


def test_an_edge_without_a_corner_is_left_to_the_registry():
    # the widget's default corner is only known to the registry (validate_widgets)
    assert entry(edge="top", width=200).edge == "top"


def test_the_schema_offers_the_corner_keys():
    panel = Config.model_json_schema()["$defs"]["PanelConfig"]["properties"]
    assert {"corner", "width", "height"} <= set(panel)
    corner = panel["corner"]["anyOf"][0]
    assert corner["enum"] == list(CORNERS)
    width = panel["width"]["anyOf"][0]
    assert (width["minimum"], width["maximum"]) == (60, 4000)


def test_defaults_change_nothing(make_config):
    cfg = make_config(monitors={"HDMI-A-1": {"shell": "edge", "panels": [{"widget": "dock"}]}})
    p = cfg.monitor("HDMI-A-1").panels[0]
    assert (p.corner, p.width, p.height) == (None, None, None)
```

- [ ] **Step 2: Run them to see them fail**

Run: `scripts/py -m pytest -q tests/test_config_corner.py`
Expected: FAIL at import: `ImportError: cannot import name 'CORNER_ONLY_KEYS' from 'shell.config.models'`.

- [ ] **Step 3: Implement**

Apply this change to `shell/config/models.py` (a diff against `ad58f61`):

```diff
--- a/shell/config/models.py
+++ b/shell/config/models.py
@@ -20,6 +20,8 @@ Edge = Literal["top", "bottom", "left", "right"]
 PanelState = Literal["collapsed", "extended"]
 ShellMode = Literal["edge", "plasma", "both", "none"]
 Align = Literal["start", "center", "end"]
+Corner = Literal["top-left", "top-right", "bottom-left", "bottom-right"]
+CORNERS: tuple[str, ...] = get_args(Corner)  # the settings window's choices
 
 _HEX = re.compile(r"#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?")  # #rrggbb or #rrggbbaa
 _FONT_FORBIDDEN = re.compile(r'["\\{};]')  # font names go unescaped into generated CSS
@@ -219,7 +221,19 @@ class InteractionConfig(_Strict):
     drag: StrictBool | None = None
 
 
+# The panel keys by kind (spec 19; the settings window reads them): both kinds take
+# SHARED_KEYS; an entry mixing EDGE_ONLY_KEYS with CORNER_ONLY_KEYS is rejected.
+SHARED_KEYS = ("widget", "edge", "state", "handle", "interaction")
+EDGE_ONLY_KEYS = ("pos", "align", "offset", "order", "length", "min_length", "max_length", "depth")
+CORNER_ONLY_KEYS = ("corner", "width", "height")
+
+
 class PanelConfig(_Strict):
+    """One panel entry. Edge panels use edge / align / offset / order / length / depth; corner
+    panels (spec 19) use corner / edge (the edge they open from) / width / height. Which kind an
+    entry is comes from its widget (shell.registry.validate_widgets checks the keys against
+    it); an entry that mixes the two kinds' keys is rejected here already."""
+
     widget: str
     edge: Edge | None = None
     pos: Offset | Literal["center"] | None = None  # deprecated: align + offset
@@ -233,6 +247,9 @@ class PanelConfig(_Strict):
     state: PanelState | None = None
     handle: HandleConfig = Field(default_factory=HandleConfig)
     interaction: InteractionConfig = Field(default_factory=InteractionConfig)
+    corner: Corner | None = None
+    width: Length | None = None  # px from the screen corner, both frame bands included
+    height: Length | None = None
 
     @field_validator("length")
     @classmethod
@@ -241,6 +258,21 @@ class PanelConfig(_Strict):
 
     @model_validator(mode="after")
     def _placement(self) -> PanelConfig:
+        corner_keys = [k for k in CORNER_ONLY_KEYS if getattr(self, k) is not None]
+        edge_keys = [k for k in EDGE_ONLY_KEYS if getattr(self, k) is not None]
+        if corner_keys and edge_keys:
+            raise ValueError(
+                f"{', '.join(edge_keys)} cannot be combined with {', '.join(corner_keys)}: a "
+                "corner panel takes corner, edge, width and height; an edge panel takes edge, "
+                "align, offset, order, length, min_length, max_length and depth"
+            )
+        if self.corner is not None and self.edge is not None:
+            if self.edge not in self.corner.split("-"):
+                first, second = self.corner.split("-")
+                raise ValueError(
+                    f"edge {self.edge!r} is not an edge of the {self.corner} corner "
+                    f"(use {first} or {second})"
+                )
         if self.pos is not None and (self.align is not None or self.offset is not None):
             advice = (
                 "drop pos; center is the default align (use offset to shift it)"
```

- [ ] **Step 4: Run them to see them pass**

Run: `scripts/py -m pytest -q tests/test_config_corner.py`
Expected: `16 passed`.

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `1208 passed`.

```bash
git add shell/config/models.py tests/test_config_corner.py
git commit -m "feat(config): corner, width and height keys for corner panels" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Corner widgets in the registry; corner requests; key checks; reload kinds

**Files:**
- Modify: `shell/panel_spec.py`, `shell/registry.py`, `tests/conftest.py`
- Test: `tests/test_corner_requests.py` (new)

**Interfaces:**
- Consumes: Task 1 (`Corner`, `EDGE_ONLY_KEYS`, `CORNER_ONLY_KEYS`, `PanelConfig.corner/width/height`); `HandleSpec`, `Interaction`, `_handle`, `_interaction`, `diff_configs` (existing; `shell/config/diff.py` needs no change: `dataclasses.replace` and `==` work on `CornerRequest`).
- Produces (`shell/panel_spec.py`):
  - `default_edge(corner) -> Edge` (the corner's top or bottom edge) and `corner_has_edge(corner, edge) -> bool`;
  - `CornerDefaults(corner, width, height, label, edge=None, state="extended", handle=HandleSpec(), interaction=Interaction())`;
  - `CornerRequest(widget, corner, edge, width, height, state, label, handle=HandleSpec(), interaction=Interaction())`;
  - `CornerGeometry(widget, corner, edge, along, length, depth, state, label)`, where `along` = px along `edge` from the corner (band included), `length = along - T` (what the handle centres on; `EdgePanel._hit` reads it) and `depth` = px past the band.
- Produces (`shell/registry.py`):
  - `register(name, PanelDefaults | CornerDefaults)` (corner defaults are checked: an edge of the corner, 60-4000 px);
  - `widget_kind(name) -> "edge" | "corner"`;
  - `defaults(name) -> PanelDefaults | CornerDefaults` (public; KeyError for an unknown widget): the settings window shows a widget's defaults through it and never reads `_DEFAULTS`;
  - `request_for(cfg) -> PanelRequest | CornerRequest`, and `requests_for` returns both kinds in config order;
  - `validate_widgets` also rejects keys of the other kind and a wrong `edge`, with the key path `monitors.NAME.panels[i].KEY`.
- Produces (`tests/conftest.py`): fixture `corner_registry` = `fake_registry` plus the corner widget `"box"` (bottom-left, 300 x 390).

- [ ] **Step 1: Add the fixture**

Append to `tests/conftest.py`:

```diff
--- a/tests/conftest.py
+++ b/tests/conftest.py
@@ -48,3 +48,15 @@ def fake_registry(monkeypatch):
         PanelDefaults(edge="right", length=300, depth=56, pos=600, label="bar", state="collapsed"),
     )(type("Bar", (), {}))
     return registry
+
+
+@pytest.fixture
+def corner_registry(fake_registry):
+    """fake_registry plus a corner widget "box" (spec 19): bottom-left, 300 x 390, opening from
+    the bottom edge (its default), extended."""
+    from shell.panel_spec import CornerDefaults
+
+    fake_registry.register(
+        "box", CornerDefaults(corner="bottom-left", width=300, height=390, label="box")
+    )(type("Box", (), {}))
+    return fake_registry
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_corner_requests.py`:

```python
"""Corner widgets in the registry, their requests, key checks and reload diff (spec 19)."""

import pytest

from shell.config.diff import diff_configs
from shell.config.models import ConfigError
from shell.panel_spec import (
    CornerDefaults,
    CornerGeometry,
    CornerRequest,
    HandleSpec,
    Interaction,
    PanelRequest,
    corner_has_edge,
    default_edge,
)


def mon(*panels):
    return {"HDMI-A-1": {"shell": "edge", "panels": list(panels)}}


def requests(registry, make_config, *panels):
    return registry.requests_for(make_config(monitors=mon(*panels)), "HDMI-A-1")


def test_default_edge_is_the_top_or_bottom_edge_of_the_corner():
    assert [default_edge(c) for c in ("top-left", "top-right", "bottom-left", "bottom-right")] == [
        "top",
        "top",
        "bottom",
        "bottom",
    ]
    assert corner_has_edge("bottom-left", "left") and not corner_has_edge("bottom-left", "top")


def test_corner_geometry_carries_the_handle_length():
    geo = CornerGeometry("box", "bottom-left", "bottom", 300, 290, 380, "extended", "box")
    assert (geo.along, geo.length, geo.depth) == (300, 290, 380)


def test_a_corner_widget_gives_a_corner_request(corner_registry, make_config):
    (req,) = requests(corner_registry, make_config, {"widget": "box"})
    assert req == CornerRequest(
        "box", "bottom-left", "bottom", 300, 390, "extended", "box", HandleSpec(), Interaction()
    )
    assert corner_registry.widget_kind("box") == "corner"
    assert corner_registry.widget_kind("dock") == "edge"


def test_a_widgets_defaults_are_public(corner_registry):
    """The settings window reads defaults(name), never _DEFAULTS."""
    assert corner_registry.defaults("box") == CornerDefaults(
        corner="bottom-left", width=300, height=390, label="box"
    )
    assert corner_registry.defaults("dock").edge == "bottom"
    with pytest.raises(KeyError):
        corner_registry.defaults("nope")


def test_entry_keys_override_the_corner_defaults(corner_registry, make_config):
    (req,) = requests(
        corner_registry,
        make_config,
        {
            "widget": "box",
            "corner": "top-right",
            "edge": "right",
            "width": 200,
            "height": 150,
            "state": "collapsed",
            "handle": {"shape": "bar"},
            "interaction": {"hover": False},
        },
    )
    assert (req.corner, req.edge, req.width, req.height, req.state) == (
        "top-right",
        "right",
        200,
        150,
        "collapsed",
    )
    assert req.handle.shape == "bar" and req.interaction == Interaction(hover=False)


def test_a_new_corner_without_an_edge_opens_from_its_top_or_bottom(corner_registry, make_config):
    (req,) = requests(corner_registry, make_config, {"widget": "box", "corner": "top-right"})
    assert req.edge == "top"


def test_a_widget_edge_that_fits_the_new_corner_is_kept(corner_registry, make_config):
    corner_registry.register(
        "side", CornerDefaults(corner="bottom-left", width=200, height=300, label="s", edge="left")
    )(type("Side", (), {}))
    a, b = requests(
        corner_registry,
        make_config,
        {"widget": "side", "corner": "top-left"},
        {"widget": "side", "corner": "top-right"},
    )
    assert a.edge == "left" and b.edge == "top"


def test_edge_widgets_still_give_panel_requests(corner_registry, make_config):
    (req,) = requests(corner_registry, make_config, {"widget": "dock"})
    assert isinstance(req, PanelRequest) and req.edge == "bottom"


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        (
            {"widget": "box", "align": "end"},
            "monitors.HDMI-A-1.panels[0].align: box is a corner panel; it takes corner, edge, "
            "width and height, not align",
        ),
        (
            {"widget": "box", "edge": "top"},
            "monitors.HDMI-A-1.panels[0].edge: 'top' is not an edge of the bottom-left corner "
            "(use bottom or left)",
        ),
        (
            {"widget": "dock", "width": 300},
            "monitors.HDMI-A-1.panels[0].width: dock is an edge panel; corner, width and height "
            "only apply to corner panels",
        ),
        (
            {"widget": "clock", "corner": "top-left"},
            "monitors.HDMI-A-1.panels[0].corner: clock is an edge panel",
        ),
    ],
)
def test_keys_of_the_other_kind_are_rejected_with_the_key_path(
    corner_registry, make_config, entry, message
):
    with pytest.raises(ConfigError) as exc:
        corner_registry.validate_widgets(make_config(monitors=mon(entry)))
    assert message in str(exc.value)


def test_a_valid_corner_entry_passes(corner_registry, make_config):
    corner_registry.validate_widgets(
        make_config(monitors=mon({"widget": "box", "corner": "top-right", "edge": "right"}))
    )


@pytest.mark.parametrize(
    "defaults",
    [
        CornerDefaults(corner="bottom-left", width=300, height=390, label="x", edge="top"),
        CornerDefaults(corner="bottom-left", width=30, height=390, label="x"),
        CornerDefaults(
            corner="bottom-left", width=300, height=390, label="x", handle=HandleSpec(size=99)
        ),
    ],
)
def test_bad_corner_defaults_fail_at_registration(corner_registry, defaults):
    with pytest.raises(ValueError):
        corner_registry.register("bad", defaults)
    assert "bad" not in corner_registry.widget_names()


def test_all_off_corner_panels_are_listed(corner_registry, make_config):
    cfg = make_config(
        monitors=mon(
            {"widget": "box", "interaction": {"click": False, "hover": False, "drag": False}}
        )
    )
    assert corner_registry.all_off_paths(cfg) == ["monitors.HDMI-A-1.panels.0"]


def _diff(make_config, before, after):
    return [c.kind for c in diff_configs(make_config(monitors=before), make_config(monitors=after))]


@pytest.mark.parametrize(
    ("change", "kind"),
    [
        ({"state": "collapsed"}, "panel-state"),
        ({"handle": {"shape": "chevron"}}, "panel-handle"),
        ({"interaction": {"drag": False}}, "panel-handle"),
        ({"width": 320}, "panel-rebuild"),
        ({"height": 200}, "panel-rebuild"),
        ({"corner": "top-left"}, "panel-rebuild"),
        ({"edge": "left"}, "panel-rebuild"),
    ],
)
def test_reload_kinds_for_corner_panels(corner_registry, make_config, change, kind):
    assert _diff(make_config, mon({"widget": "box"}), mon({"widget": "box", **change})) == [kind]


def test_swapping_an_edge_widget_for_a_corner_widget_rebuilds(corner_registry, make_config):
    assert _diff(make_config, mon({"widget": "dock"}), mon({"widget": "box"})) == ["panel-rebuild"]
```

- [ ] **Step 3: Run them to see them fail**

Run: `scripts/py -m pytest -q tests/test_corner_requests.py`
Expected: FAIL at import: `ImportError: cannot import name 'CornerDefaults' from 'shell.panel_spec'`.

- [ ] **Step 4: Implement**

Apply to `shell/panel_spec.py`:

```diff
--- a/shell/panel_spec.py
+++ b/shell/panel_spec.py
@@ -4,7 +4,7 @@ from __future__ import annotations
 
 from dataclasses import dataclass
 
-from shell.config.models import Align, Edge, HandleShape, PanelState
+from shell.config.models import Align, Corner, Edge, HandleShape, PanelState
 
 LengthSpec = int | str  # px, "fill", "content" or "NN%" (validated by shell.config.models)
 
@@ -90,3 +90,62 @@ class PanelGeometry:
     depth: int
     state: PanelState
     label: str
+
+
+def default_edge(corner: Corner) -> Edge:
+    """The edge a corner panel opens from unless told otherwise: the corner's top or bottom
+    edge (the spec's widget_panel rises out of the bottom edge)."""
+    return corner.split("-")[0]  # type: ignore[return-value]
+
+
+def corner_has_edge(corner: Corner, edge: Edge) -> bool:
+    return edge in corner.split("-")
+
+
+@dataclass(frozen=True)
+class CornerDefaults:
+    """A corner widget's registered defaults (spec 19). `width` and `height` are px from the
+    screen corner, both frame bands included; `edge` is the edge it opens from (None: the
+    corner's top or bottom edge, `default_edge`)."""
+
+    corner: Corner
+    width: int
+    height: int
+    label: str
+    edge: Edge | None = None
+    state: PanelState = "extended"
+    handle: HandleSpec = HandleSpec()
+    interaction: Interaction = Interaction()
+
+
+@dataclass(frozen=True)
+class CornerRequest:
+    """What the config asks for a corner panel (widget defaults + config overrides), before
+    layout. `edge` is always one of the corner's two edges."""
+
+    widget: str
+    corner: Corner
+    edge: Edge
+    width: int
+    height: int
+    state: PanelState
+    label: str
+    handle: HandleSpec = HandleSpec()
+    interaction: Interaction = Interaction()
+
+
+@dataclass(frozen=True)
+class CornerGeometry:
+    """A corner panel resolved by shell.panel_layout. The body is the rectangle from the screen
+    corner `along` px along `edge` (the adjacent frame band included) and `thickness + depth`
+    px across it; `length` = `along` minus the adjacent band, the part of the body the handle
+    centres on (EdgePanel's hit target reads `length`)."""
+
+    widget: str
+    corner: Corner
+    edge: Edge
+    along: int
+    length: int
+    depth: int
+    state: PanelState
+    label: str
```

Apply to `shell/registry.py`:

```diff
--- a/shell/registry.py
+++ b/shell/registry.py
@@ -8,20 +8,33 @@ from dataclasses import asdict
 from pydantic import ValidationError
 
 from shell.config.models import (
+    CORNER_ONLY_KEYS,
+    EDGE_ONLY_KEYS,
     Config,
     ConfigError,
     HandleConfig,
     InteractionConfig,
     PanelConfig,
 )
-from shell.panel_spec import HandleSpec, Interaction, PanelDefaults, PanelRequest
+from shell.panel_spec import (
+    CornerDefaults,
+    CornerRequest,
+    HandleSpec,
+    Interaction,
+    PanelDefaults,
+    PanelRequest,
+    corner_has_edge,
+    default_edge,
+)
 
 _WIDGETS: dict[str, type] = {}
-_DEFAULTS: dict[str, PanelDefaults] = {}
+_DEFAULTS: dict[str, PanelDefaults | CornerDefaults] = {}
 _PLACEMENT = ("pos", "align", "offset")
 
 
-def register(name: str, defaults: PanelDefaults) -> Callable[[type], type]:
+def register(name: str, defaults: PanelDefaults | CornerDefaults) -> Callable[[type], type]:
+    """Register a widget class. PanelDefaults make it an edge panel, CornerDefaults a corner
+    panel (spec 19); the kind decides which config keys its entries take."""
     _check_defaults(name, defaults)  # a bad widget default fails at import, before any window
 
     def decorate(cls: type) -> type:
@@ -34,7 +47,7 @@ def register(name: str, defaults: PanelDefaults) -> Callable[[type], type]:
     return decorate
 
 
-def _check_defaults(name: str, defaults: PanelDefaults) -> None:
+def _check_defaults(name: str, defaults: PanelDefaults | CornerDefaults) -> None:
     """Widget defaults do not pass through the config models: check the handle and interaction
     ones with the same rules as a config entry (spec 15: shape, size 4-40, weight 1-8, offset,
     #rrggbb[aa] colours, strict booleans)."""
@@ -43,6 +56,13 @@ def _check_defaults(name: str, defaults: PanelDefaults) -> None:
         InteractionConfig.model_validate(asdict(defaults.interaction))
     except ValidationError as exc:
         raise ValueError(f"widget {name!r}: invalid handle or interaction default: {exc}") from exc
+    if isinstance(defaults, CornerDefaults):
+        if defaults.edge is not None and not corner_has_edge(defaults.corner, defaults.edge):
+            raise ValueError(
+                f"widget {name!r}: edge {defaults.edge!r} is not an edge of {defaults.corner}"
+            )
+        if not (60 <= defaults.width <= 4000 and 60 <= defaults.height <= 4000):
+            raise ValueError(f"widget {name!r}: width and height must be 60-4000 px")
 
 
 def widget_names() -> list[str]:
@@ -53,7 +73,18 @@ def widget_class(name: str) -> type:
     return _WIDGETS[name]
 
 
-def request_for(cfg: PanelConfig) -> PanelRequest:
+def widget_kind(name: str) -> str:
+    """The widget's kind, "edge" or "corner" (the settings window shows the matching keys)."""
+    return "corner" if isinstance(_DEFAULTS[name], CornerDefaults) else "edge"
+
+
+def defaults(name: str) -> PanelDefaults | CornerDefaults:
+    """The widget's registered defaults (the settings window shows them; it never reads
+    _DEFAULTS). KeyError for an unknown widget, like widget_class."""
+    return _DEFAULTS[name]
+
+
+def request_for(cfg: PanelConfig) -> PanelRequest | CornerRequest:
     """The widget's defaults overlaid with one config entry. Placement is taken as a whole: if
     the entry sets any of pos / align / offset, the widget's default placement is dropped and
     the keys it leaves out are align = "center", offset = 0 (`pos = "center"` is align =
@@ -62,6 +93,8 @@ def request_for(cfg: PanelConfig) -> PanelRequest:
     if d is None:
         known = ", ".join(widget_names()) or "none"
         raise ConfigError(f"unknown widget {cfg.widget!r} (known: {known})")
+    if isinstance(d, CornerDefaults):
+        return _corner_request(cfg, d)
     if any(getattr(cfg, key) is not None for key in _PLACEMENT):
         pos = None if cfg.pos in (None, "center") else cfg.pos
         align, offset = cfg.align or "center", cfg.offset or 0
@@ -86,6 +119,27 @@ def request_for(cfg: PanelConfig) -> PanelRequest:
     )
 
 
+def _corner_request(cfg: PanelConfig, d: CornerDefaults) -> CornerRequest:
+    """A corner widget's defaults overlaid with one entry. The edge it opens from: the entry's,
+    else the widget's when it is an edge of the corner, else the corner's top or bottom edge
+    (so moving a panel to another corner never leaves it with an impossible edge)."""
+    corner = cfg.corner or d.corner
+    edge = cfg.edge or d.edge
+    if edge is None or not corner_has_edge(corner, edge):
+        edge = default_edge(corner)
+    return CornerRequest(
+        widget=cfg.widget,
+        corner=corner,
+        edge=edge,
+        width=cfg.width or d.width,
+        height=cfg.height or d.height,
+        state=cfg.state or d.state,
+        label=d.label,
+        handle=_handle(cfg, d.handle),
+        interaction=_interaction(cfg, d.interaction),
+    )
+
+
 def _handle(cfg: PanelConfig, default: HandleSpec) -> HandleSpec:
     """Key by key: the entry's [handle] value, else the widget's default (None = the theme's)."""
     own = cfg.handle
@@ -107,7 +161,7 @@ def _interaction(cfg: PanelConfig, default: Interaction) -> Interaction:
     )
 
 
-def requests_for(config: Config, monitor: str) -> list[PanelRequest]:
+def requests_for(config: Config, monitor: str) -> list[PanelRequest | CornerRequest]:
     return [request_for(p) for p in config.monitor(monitor).panels]
 
 
@@ -153,13 +207,41 @@ def all_off_paths(config: Config) -> list[str]:
     ]
 
 
-def validate_widgets(config: Config) -> None:
-    problems = [
-        f"monitors.{name}.panels[{i}].widget: unknown widget {panel.widget!r}"
-        for name, mon in config.monitors.items()
-        for i, panel in enumerate(mon.panels)
-        if panel.widget not in _DEFAULTS
+def _kind_problems(where: str, panel: PanelConfig) -> list[str]:
+    """Keys an entry sets that its widget's kind does not take (spec 19)."""
+    d = _DEFAULTS[panel.widget]
+    if isinstance(d, CornerDefaults):
+        wrong = [k for k in EDGE_ONLY_KEYS if getattr(panel, k) is not None]
+        problems = [
+            f"{where}.{key}: {panel.widget} is a corner panel; it takes corner, edge, width "
+            f"and height, not {key}"
+            for key in wrong
+        ]
+        corner = panel.corner or d.corner
+        if panel.edge is not None and not corner_has_edge(corner, panel.edge):
+            first, second = corner.split("-")
+            problems.append(
+                f"{where}.edge: {panel.edge!r} is not an edge of the {corner} corner "
+                f"(use {first} or {second})"
+            )
+        return problems
+    return [
+        f"{where}.{key}: {panel.widget} is an edge panel; corner, width and height only "
+        "apply to corner panels"
+        for key in CORNER_ONLY_KEYS
+        if getattr(panel, key) is not None
     ]
+
+
+def validate_widgets(config: Config) -> None:
+    problems = []
+    for name, mon in config.monitors.items():
+        for i, panel in enumerate(mon.panels):
+            where = f"monitors.{name}.panels[{i}]"
+            if panel.widget not in _DEFAULTS:
+                problems.append(f"{where}.widget: unknown widget {panel.widget!r}")
+            else:
+                problems.extend(_kind_problems(where, panel))
     if problems:
         known = ", ".join(widget_names()) or "none"
         raise ConfigError("\n".join(problems) + f"\nknown widgets: {known}")
```

- [ ] **Step 5: Run them to see them pass**

Run: `scripts/py -m pytest -q tests/test_corner_requests.py`
Expected: `25 passed`.

- [ ] **Step 6: VERIFY and commit**

Run VERIFY. Expected: `1233 passed` (`tests/test_registry.py::test_widget_names_sorted` still sees `["bar", "clock", "dock"]`: the corner widget lives only in the new fixture).

```bash
git add shell/panel_spec.py shell/registry.py tests/conftest.py tests/test_corner_requests.py
git commit -m "feat(registry): corner widgets, corner requests and key checks by kind" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Pure corner geometry (`shell/corner.py`)

**Files:**
- Create: `shell/corner.py`
- Test: `tests/test_corner_geometry.py` (new)

**Interfaces:**
- Consumes: `shell.geometry.is_horizontal`; `shell.handle.clamp_offset`, `hit_inset`, `hit_size` (Plan 3); `Interaction` (Plan 3); `Corner`, `Edge` (Task 1).
- Produces (all pure; `p` runs along the opening edge from the corner, `q` away from that edge's screen edge):
  - `to_xy(corner, edge, p, q, width, height) -> (x, y)` maps onto a `width` x `height` box anchored in that corner (the screen, or the panel's own surface);
  - `pq_box(corner, edge, p0, p1, q0, q1, width, height) -> (x0, y0, x1, y1)`, sorted floats;
  - `surface_size(edge, along, depth, thickness) -> (w, h)`: `along` x `(T + depth)`, swapped for left and right;
  - `anchor(corner) -> str`, for example `"bottom left"`;
  - `corner_box(corner, edge, along, d, width, height, thickness, radius, pad=0) -> Box`: ints, clamped to the screen;
  - `body_rect(corner, edge, along, depth, d, thickness) -> Rect`, `content_rect(corner, edge, along, depth, thickness) -> Rect`, and `hit_rect(corner, edge, along, depth, d, thickness, hit, offset) -> Rect`, all `(x, y, w, h)` in surface px;
  - `input_rects(corner, edge, along, depth, d, thickness, hover_zone, interaction, hit, offset) -> list[Rect]`, with the same rules as `shell.handle.input_rects`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_corner_geometry.py`:

```python
"""Corner panel geometry (spec 19): surface, body, content, hit target, input, damage box."""

import pytest

from shell import corner as cn
from shell import handle as hd
from shell.panel_spec import Interaction

T, R = 10, 14
HIT = hd.hit_size(T, 15, 290)  # (44, 14) for the default 300 px panel
ALL, NONE = Interaction(), Interaction(False, False, False)


@pytest.mark.parametrize(
    ("corner", "edge", "expected"),
    [
        ("bottom-left", "bottom", (5, 1075)),
        ("bottom-right", "bottom", (1915, 1075)),
        ("top-left", "top", (5, 5)),
        ("top-right", "top", (1915, 5)),
        ("bottom-left", "left", (5, 1075)),
        ("top-right", "right", (1915, 5)),
    ],
)
def test_to_xy_maps_from_the_corner(corner, edge, expected):
    assert cn.to_xy(corner, edge, 5, 5, 1920, 1080) == expected


def test_p_runs_along_the_opening_edge_and_q_across_it():
    assert cn.to_xy("bottom-left", "bottom", 300, 10, 1920, 1080) == (300, 1070)
    assert cn.to_xy("bottom-left", "left", 300, 10, 1920, 1080) == (10, 780)


def test_the_window_is_a_rectangle_in_the_corner():
    assert cn.anchor("bottom-left") == "bottom left"
    assert cn.anchor("top-right") == "top right"
    assert cn.surface_size("bottom", 300, 380, T) == (300, 390)
    assert cn.surface_size("left", 300, 380, T) == (390, 300)


@pytest.mark.parametrize(
    ("corner", "edge", "d", "expected"),
    [
        ("bottom-left", "bottom", 0, (0, 380, 300, 10)),
        ("bottom-left", "bottom", 380, (0, 0, 300, 390)),
        ("bottom-left", "bottom", 14.5, (0, 365, 300, 25)),
        ("top-right", "top", 0, (0, 0, 300, 10)),
        ("bottom-left", "left", 0, (0, 0, 10, 300)),
        ("top-right", "right", 100, (280, 0, 110, 300)),
    ],
)
def test_body_rect(corner, edge, d, expected):
    assert cn.body_rect(corner, edge, 300, 380, d, T) == expected


@pytest.mark.parametrize(
    ("corner", "edge", "expected"),
    [
        ("bottom-left", "bottom", (10, 0, 290, 380)),
        ("bottom-right", "bottom", (0, 0, 290, 380)),
        ("top-left", "top", (10, 10, 290, 380)),
        ("top-right", "right", (0, 10, 380, 290)),
    ],
)
def test_the_content_sits_past_both_frame_bands(corner, edge, expected):
    assert cn.content_rect(corner, edge, 300, 380, T) == expected


@pytest.mark.parametrize(
    ("corner", "edge", "d", "offset", "expected"),
    [
        ("bottom-left", "bottom", 0, 0, (133, 376, 44, 14)),
        ("bottom-left", "bottom", 380, 0, (133, 0, 44, 14)),
        ("bottom-right", "bottom", 0, 0, (123, 376, 44, 14)),
        ("bottom-right", "bottom", 0, 30, (153, 376, 44, 14)),  # + = right, as on edges
        ("bottom-left", "bottom", 0, 30, (163, 376, 44, 14)),
        ("bottom-left", "bottom", 0, 9999, (256, 376, 44, 14)),  # clamped to the body
        ("top-left", "left", 0, -20, (0, 113, 14, 44)),  # - = up, as on edges
        ("bottom-left", "left", 0, -20, (0, 103, 14, 44)),
    ],
)
def test_hit_rect_centres_on_the_body_past_the_band(corner, edge, d, offset, expected):
    assert cn.hit_rect(corner, edge, 300, 380, d, T, HIT, offset) == expected


def test_the_hit_target_stays_inside_the_body_past_the_band():
    for offset in (-9999, 9999):
        x, _y, w, _h = cn.hit_rect("bottom-left", "bottom", 300, 380, 0, T, HIT, offset)
        assert T <= x and x + w <= 300


def test_input_with_hover_is_the_body_plus_the_hover_zone():
    assert cn.input_rects("bottom-left", "bottom", 300, 380, 0, T, 16, ALL, HIT, 0) == [
        (0, 364, 300, 26)
    ]
    assert cn.input_rects("bottom-left", "bottom", 300, 380, 200, T, 16, ALL, HIT, 0) == [
        (0, 180, 300, 210)
    ]


def test_input_without_hover_is_the_body_and_the_hit_target():
    click = Interaction(hover=False)
    assert cn.input_rects("bottom-left", "bottom", 300, 380, 0, T, 16, click, HIT, 0) == [
        (133, 376, 44, 14)
    ]
    assert cn.input_rects("bottom-left", "bottom", 300, 380, 50, T, 16, click, HIT, 0) == [
        (0, 330, 300, 60),
        (133, 330, 44, 14),
    ]


def test_a_shallow_corner_panel_clamps_the_hover_zone_and_the_peek():
    """MIN_DEPTH (16) is below the largest hover zone and peek (64): both stop at the depth,
    the clamps edge panels already use (input_rects, panel_state.target_depth)."""
    from shell.panel_state import target_depth

    assert cn.input_rects("bottom-left", "bottom", 300, 16, 0, T, 64, ALL, HIT, 0) == [
        (0, 0, 300, 26)
    ]
    assert target_depth(False, True, 16, 64) == 16.0


def test_with_every_interaction_off_a_collapsed_corner_panel_is_click_through():
    assert cn.input_rects("bottom-left", "bottom", 300, 380, 0, T, 16, NONE, HIT, 0) == []


def test_every_input_rect_is_a_plain_rectangle_inside_the_surface():
    """The window is a rectangle, not an L: every region is one or two plain rectangles."""
    for corner in ("top-left", "top-right", "bottom-left", "bottom-right"):
        for edge in corner.split("-"):
            w, h = cn.surface_size(edge, 300, 380, T)
            for d in (0, 7.5, 190, 380):
                for inter in (ALL, Interaction(hover=False), NONE):
                    rects = cn.input_rects(corner, edge, 300, 380, d, T, 16, inter, HIT, 0)
                    for x, y, rw, rh in rects:
                        assert 0 <= x and 0 <= y and x + rw <= w and y + rh <= h


@pytest.mark.parametrize(
    ("corner", "edge", "expected"),
    [
        ("bottom-left", "bottom", (0, 676, 314, 1080)),
        ("bottom-right", "bottom", (1606, 676, 1920, 1080)),
        ("top-left", "left", (0, 0, 404, 314)),
        ("top-right", "right", (1516, 0, 1920, 314)),
    ],
)
def test_corner_box_covers_body_fillet_and_lifted_arc(corner, edge, expected):
    assert cn.corner_box(corner, edge, 300, 380, 1920, 1080, T, R) == expected


def test_corner_box_grows_by_pad_and_rounds_depth_up():
    assert cn.corner_box("bottom-left", "bottom", 300, 20.2, 1920, 1080, T, R, pad=26) == (
        0,
        1009,
        340,
        1080,
    )
```

- [ ] **Step 2: Run them to see them fail**

Run: `scripts/py -m pytest -q tests/test_corner_geometry.py`
Expected: FAIL at import: `ImportError: cannot import name 'corner' from 'shell'`.

- [ ] **Step 3: Implement**

Create `shell/corner.py`:

```python
"""Corner panel geometry (spec 19). Pure: no GTK.

A corner panel is a RECTANGLE in a screen corner (never an L): `along` px along the edge it
opens from (`edge`), the adjacent frame band included, and `thickness + depth` px across that
edge. Two of its sides lie on the screen edges; its two free sides meet the two frame bands.
Only its depth animates (0 = collapsed into the band of `edge`), exactly like an edge panel.

Coordinates: `p` runs along `edge` away from the corner, `q` away from `edge`'s screen edge
(towards the desktop), both from the screen corner. `to_xy` maps (p, q) onto a `width` x
`height` box anchored in that corner: the screen (canvas, layout) or the panel's own surface.
"""

from __future__ import annotations

import math

from shell import geometry
from shell import handle as hd
from shell.config.models import Corner, Edge
from shell.panel_spec import Interaction

Rect = tuple[int, int, int, int]  # x, y, width, height
Box = tuple[int, int, int, int]  # x0, y0, x1, y1 (x1 / y1 exclusive)


def to_xy(
    corner: Corner, edge: Edge, p: float, q: float, width: float, height: float
) -> tuple[float, float]:
    """(p, q) from the corner -> (x, y) in a `width` x `height` box anchored in that corner."""
    dx, dy = (p, q) if geometry.is_horizontal(edge) else (q, p)
    x = dx if corner.endswith("left") else width - dx
    y = dy if corner.startswith("top") else height - dy
    return x, y


def pq_box(
    corner: Corner,
    edge: Edge,
    p0: float,
    p1: float,
    q0: float,
    q1: float,
    width: float,
    height: float,
) -> tuple[float, float, float, float]:
    """The (p0..p1) x (q0..q1) rectangle as (x0, y0, x1, y1) in the box, sorted."""
    xa, ya = to_xy(corner, edge, p0, q0, width, height)
    xb, yb = to_xy(corner, edge, p1, q1, width, height)
    return min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb)


def _rect(box: tuple[float, float, float, float]) -> Rect:
    x, y = math.floor(box[0]), math.floor(box[1])
    return x, y, math.ceil(box[2]) - x, math.ceil(box[3]) - y


def surface_size(edge: Edge, along: int, depth: int, thickness: int) -> tuple[int, int]:
    """The panel window: exactly the extended body, `along` x (thickness + depth)."""
    across = thickness + depth
    return (along, across) if geometry.is_horizontal(edge) else (across, along)


def anchor(corner: Corner) -> str:
    """Layer-shell anchor: the two screen edges of the corner (margins stay 0)."""
    return " ".join(corner.split("-"))


def corner_box(
    corner: Corner,
    edge: Edge,
    along: int,
    d: float,
    width: int,
    height: int,
    thickness: int,
    radius: int,
    pad: int = 0,
) -> Box:
    """Every canvas pixel the panel can change at depth `d`: the body, its free-end fillet
    (radius <= R) along `edge`, and the screen-corner arc it lifts `d` px up the other edge
    (radius R), grown by `pad` (border + shadow), clamped to the screen."""
    x0, y0, x1, y1 = pq_box(
        corner,
        edge,
        0,
        along + radius + pad,
        0,
        thickness + math.ceil(max(0.0, d)) + radius + pad,
        width,
        height,
    )
    return max(0, int(x0)), max(0, int(y0)), min(width, int(x1)), min(height, int(y1))


def body_rect(corner: Corner, edge: Edge, along: int, depth: int, d: float, thickness: int) -> Rect:
    """The body at depth `d` in surface px: the whole `along`, from the screen edge to the
    body's inner edge (the frame band under it included, like an edge panel's body)."""
    w, h = surface_size(edge, along, depth, thickness)
    return _rect(pq_box(corner, edge, 0, along, 0, thickness + max(0.0, d), w, h))


def content_rect(corner: Corner, edge: Edge, along: int, depth: int, thickness: int) -> Rect:
    """Where the content box sits in the surface: past both frame bands, `along - thickness`
    by `depth` px."""
    w, h = surface_size(edge, along, depth, thickness)
    return _rect(pq_box(corner, edge, thickness, along, thickness, thickness + depth, w, h))


def _along_sign(corner: Corner, edge: Edge) -> int:
    """+1 when p grows towards the end of the screen axis (right, down): handle.offset keeps
    its edge-panel meaning (negative = towards the left or the top) in every corner."""
    if geometry.is_horizontal(edge):
        return 1 if corner.endswith("left") else -1
    return 1 if corner.startswith("top") else -1


def hit_rect(
    corner: Corner,
    edge: Edge,
    along: int,
    depth: int,
    d: float,
    thickness: int,
    hit: tuple[int, int],
    offset: int,
) -> Rect:
    """The handle's hit target in surface px: centred on the body past the adjacent band
    (`along - thickness` px), moved by `offset` (clamped to that body), riding the body's inner
    edge across (shell.handle.hit_inset) exactly as on an edge panel. Whole pixels."""
    length = along - thickness
    hit_along, hit_across = hit
    shift = _along_sign(corner, edge) * hd.clamp_offset(offset, length, hit_along)
    p0 = thickness + (length - hit_along) // 2 + shift
    q0 = hd.hit_inset(thickness, d, hit_across)
    w, h = surface_size(edge, along, depth, thickness)
    return _rect(pq_box(corner, edge, p0, p0 + hit_along, q0, q0 + hit_across, w, h))


def input_rects(
    corner: Corner,
    edge: Edge,
    along: int,
    depth: int,
    d: float,
    thickness: int,
    hover_zone: int,
    interaction: Interaction,
    hit: tuple[int, int],
    offset: int,
) -> list[Rect]:
    """Where the panel takes input at depth `d` (shell.handle.input_rects' rules): with hover
    on, the body plus the invisible hover zone while collapsed; with hover off, the body while
    it is out plus the hit target when click or drag is on; nothing at all while collapsed
    with every interaction off. Every rect is a plain rectangle."""
    if interaction.hover:
        effective = max(d, min(hover_zone, depth))
        return [body_rect(corner, edge, along, depth, effective, thickness)]
    rects = []
    if d > 0:
        rects.append(body_rect(corner, edge, along, depth, d, thickness))
    if interaction.click or interaction.drag:
        rects.append(hit_rect(corner, edge, along, depth, d, thickness, hit, offset))
    return rects
```

- [ ] **Step 4: Run them to see them pass**

Run: `scripts/py -m pytest -q tests/test_corner_geometry.py`
Expected: `37 passed`. The numbers to check by hand, for the default 300 x 390 bottom-left panel:
- the hit target is `hd.hit_size(10, 15, 290) = (44, 14)`, starting `10 + (290 - 44) // 2 = 133` px from the corner;
- collapsed it sits on the bottom 14 px of the 390 px surface (y 376), extended on the top 14 (y 0);
- with `d = 50`, `hit_inset = 10 + 50 - 14 = 46`, so `q` is 46-60 and y = 390 - 60 = 330.

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `1270 passed`.

```bash
git add shell/corner.py tests/test_corner_geometry.py
git commit -m "feat(corner): pure geometry of a corner panel: surface, body, handle, input, damage" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Corner panels in the one outline, the border and the shadow

**Files:**
- Modify: `shell/canvas/outline.py`, `shell/canvas/effects.py`
- Test: `tests/test_canvas_corner_outline.py` (new)

**Interfaces:**
- Consumes: `shell.geometry.join_radius`; `tests/legacy_draw.py` (`draw_panel`, `draw_screen_corner`); `tests/test_canvas_outline.py` (`alpha_bytes`, `surface_origin`, for the reference only).
- Produces:
  - `shell.canvas.outline.CornerSpan = tuple[str, str, int, int, float]`, i.e. `(corner, opening edge, along, depth_full, d_now)`;
  - `trace_edge(cr, length, thickness, radius, spans, first, head=None, tail=None, lead=0.0, trail=0.0)`;
  - `outline_path(cr, w, h, T, R, panels, corners=())` and `fill_mass(cr, w, h, T, R, panels, rgba, corners=())`;
  - in `shell/canvas/effects.py`, `draw_border(..., corners=())`, `draw_shadow_uniform(..., offset=0, corners=())`, `draw_shadow_reach(..., offset=0, corners=())` and `draw_scene(..., clip=None, corners=())`. Every new parameter is last, with an empty default, so every existing call is unchanged.

**How the walk changes.** Each edge's walk runs clockwise from the end of the previous corner arc (see `_START` and `_END` in the code). For a corner panel `(corner, opens, along, depth, d)` at depth `d > 0`:
- On its own edge, in that edge's start corner, it is a `head`. The walk starts on the body's inner edge `(T + R, T + d)` and leaves it through a convex corner and a concave fillet of radius `r = min(R, d/2)` at `u = along`.
- In the end corner it is a `tail`: a fillet and a convex corner at `u0 = length - along`, and the screen-corner arc moved `d` across.
- On the neighbouring edge it lifts that edge's arc. As `lead` (it sits in that edge's start corner), that edge's walk starts `d` later. As `trail` (it sits in that edge's end corner), the end arc moves `d` back along.

The screen-corner arc keeps radius R throughout: at `d = 0` it is today's corner.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_canvas_corner_outline.py`:

```python
"""Corner panels in the one union outline (spec 19), against an independent reference: the
mass drawn as a union of simple filled pieces (frame bands, screen-corner pieces, the corner
panel's body, its free-end fillet and its lifted screen-corner piece, legacy edge panels)."""

import math

import cairo
import pytest

from shell import geometry as g
from shell.canvas.effects import draw_border, draw_shadow_reach
from shell.canvas.outline import fill_mass, outline_path
from tests.legacy_draw import draw_panel, draw_screen_corner
from tests.test_canvas_outline import alpha_bytes, surface_origin

W, H, T, R = 400, 300, 10, 14
RGBA = (0.04, 0.05, 0.05, 1.0)
ALONG, DEPTH = 120, 100
CORNER_EDGES = [
    (corner, edge)
    for corner in ("top-left", "top-right", "bottom-left", "bottom-right")
    for edge in corner.split("-")
]


def _offsets(radius):
    return {
        "top-left": (T, T),
        "top-right": (W - T - radius, T),
        "bottom-left": (T, H - T - radius),
        "bottom-right": (W - T - radius, H - T - radius),
    }


def pq_matrix(corner, edge):
    """(p, q) from the corner (p along `edge`, q away from its screen edge) -> screen."""
    sx = 1 if corner.endswith("left") else -1
    sy = 1 if corner.startswith("top") else -1
    x0 = 0 if sx == 1 else W
    y0 = 0 if sy == 1 else H
    if g.is_horizontal(edge):
        return cairo.Matrix(sx, 0, 0, sy, x0, y0)
    return cairo.Matrix(0, sy, sx, 0, x0, y0)


def draw_corner_reference(cr, corner, edge, along, d, radius=R):
    """The corner panel's pieces in (p, q), each filled on its own."""
    cr.save()
    cr.transform(pq_matrix(corner, edge))
    cr.set_source_rgba(*RGBA)
    # the screen-corner piece, lifted d px along the other edge
    cr.move_to(T, T + d)
    cr.line_to(T + radius, T + d)
    cr.arc_negative(T + radius, T + d + radius, radius, -0.5 * math.pi, -math.pi)
    cr.close_path()
    cr.fill()
    if d > 0:
        r = g.join_radius(d, radius)
        # the body: from the screen corner, its free corner rounded by r
        cr.move_to(0, 0)
        cr.line_to(along, 0)
        cr.line_to(along, T + d - r)
        cr.arc(along - r, T + d - r, r, 0, 0.5 * math.pi)
        cr.line_to(0, T + d)
        cr.close_path()
        cr.fill()
        # the concave fillet where its free side meets the band of `edge`
        cr.move_to(along, T)
        cr.line_to(along + r, T)
        cr.arc_negative(along + r, T + r, r, -0.5 * math.pi, -math.pi)
        cr.close_path()
        cr.fill()
    cr.restore()


def render_reference(corners, panels=(), radius=R):
    """corners: [(corner, edge, along, d)], panels: [(edge, pos, length, depth, d)]."""
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(s)
    cr.set_source_rgba(*RGBA)
    for rect in [(0, 0, W, T), (0, H - T, W, T), (0, 0, T, H), (W - T, 0, T, H)]:
        cr.rectangle(*rect)
    cr.fill()
    taken = {c for c, _e, _a, _d in corners}
    for name, (ox, oy) in _offsets(radius).items():
        if name not in taken:
            cr.save()
            cr.translate(ox, oy)
            draw_screen_corner(cr, name, radius, RGBA)
            cr.restore()
    for corner, edge, along, d in corners:
        draw_corner_reference(cr, corner, edge, along, d, radius)
    for edge, pos, length, depth, d in panels:
        ox, oy = surface_origin(edge, pos, length, depth)
        cr.save()
        cr.translate(ox, oy)
        draw_panel(cr, edge, length, depth, d, T, radius, RGBA)
        cr.restore()
    return alpha_bytes(s)


def render_canvas(corners, panels=(), radius=R):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    spans = [(c, e, a, DEPTH, d) for c, e, a, d in corners]
    fill_mass(cairo.Context(s), W, H, T, radius, list(panels), RGBA, spans)
    return alpha_bytes(s)


def bad_pixels(a, b):
    return [
        (x, y, a[y][x], b[y][x])
        for y in range(H)
        for x in range(W)
        if abs(a[y][x] - b[y][x]) > 24  # antialiasing tolerance on edge pixels only
    ]


@pytest.mark.parametrize(("corner", "edge"), CORNER_EDGES)
@pytest.mark.parametrize(
    ("d", "radius", "along"),
    [
        (0, R, ALONG),
        (3, R, ALONG),
        (14, R, ALONG),
        (27.5, R, ALONG),
        (60, R, ALONG),
        (100, R, ALONG),
        # a large theme radius at the layout's minimum along, T + R + r (Task 6): 80 and 90
        (60, 40, 80),
        (100, 40, 90),
    ],
)
def test_a_corner_panel_matches_the_reference_union(corner, edge, d, radius, along):
    bad = bad_pixels(
        render_reference([(corner, edge, along, d)], radius=radius),
        render_canvas([(corner, edge, along, d)], radius=radius),
    )
    assert len(bad) < 40, bad[:10]


def test_four_corner_panels_at_once():
    corners = [
        ("bottom-left", "bottom", ALONG, 60),
        ("bottom-right", "right", ALONG, 40),
        ("top-right", "top", ALONG, 100),
        ("top-left", "left", ALONG, 7),
    ]
    bad = bad_pixels(render_reference(corners), render_canvas(corners))
    assert len(bad) < 60, bad[:10]


def test_corner_panels_next_to_edge_panels_cleared_by_the_layout():
    # bottom: the edge panel starts at along + r_c + r_p = 120 + 14 + 14 = 148 (gap 12 more);
    # left: the bottom-left panel lifts the corner arc to T + R + depth = 124 px from the bottom
    # (y 176), and the left panel's fillet ends at 40 + 80 + 14 = 134
    corners = [("bottom-left", "bottom", ALONG, DEPTH)]
    panels = [("bottom", 160, 100, 40, 40), ("left", 40, 80, 30, 30)]
    bad = bad_pixels(render_reference(corners, panels), render_canvas(corners, panels))
    assert len(bad) < 60, bad[:10]


def test_with_every_depth_zero_the_path_is_the_plain_frame():
    def ops(corners):
        cr = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H))
        outline_path(cr, W, H, T, R, [("top", 120, 140, 50, 28)], corners)
        return list(cr.copy_path_flat())

    collapsed = [(c, e, ALONG, DEPTH, 0.0) for c, e in CORNER_EDGES[::2]]
    assert ops(collapsed) == ops([])


def test_the_outline_stays_one_closed_path_with_corner_panels():
    cr = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H))
    corners = [("bottom-left", "bottom", ALONG, DEPTH, 50), ("top-right", "right", ALONG, DEPTH, 9)]
    outline_path(cr, W, H, T, R, [], corners)
    kinds = [kind for kind, _ in cr.copy_path()]
    assert kinds.count(cairo.PATH_CLOSE_PATH) == 1 and kinds.count(cairo.PATH_MOVE_TO) == 2


def test_the_border_never_touches_the_corner_panels_mass():
    corners = [("bottom-left", "bottom", ALONG, DEPTH, 60)]
    mass = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    fill_mass(cairo.Context(mass), W, H, T, R, [], RGBA, corners)
    border = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    draw_border(cairo.Context(border), W, H, T, R, [], 3, (1, 1, 1, 1), corners)
    m, b = alpha_bytes(mass), alpha_bytes(border)
    assert not [(x, y) for y in range(H) for x in range(W) if m[y][x] == 255 and b[y][x]]
    # and it follows the lifted outline: the pixel just above the body's inner edge is border
    assert b[H - T - 60 - 2][60] == 255


def test_the_shadow_follows_the_corner_panel_and_stays_off_its_mass():
    corners = [("bottom-left", "bottom", ALONG, DEPTH, 60)]
    shadow = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    draw_shadow_reach(cairo.Context(shadow), W, H, T, R, [], 12, (0, 0, 0, 0.5), 0, corners)
    s = alpha_bytes(shadow)
    assert s[H - T - 60 - 1][60] > 0  # just outside the body's inner edge
    assert s[H - T - 30][60] == 0  # inside the body: never under the mass
```

- [ ] **Step 2: Run them to see them fail**

Run: `scripts/py -m pytest -q tests/test_canvas_corner_outline.py`
Expected: FAIL: `TypeError: fill_mass() takes 7 positional arguments but 8 were given` (and the same for `outline_path`, `draw_border`, `draw_shadow_reach`).

- [ ] **Step 3: Implement**

Apply to `shell/canvas/outline.py`:

```diff
--- a/shell/canvas/outline.py
+++ b/shell/canvas/outline.py
@@ -7,12 +7,16 @@ Pure cairo. Migrated from the shape-canvas spike (spikes/canvas/outline.py at 87
 from __future__ import annotations
 
 import math
+from collections.abc import Sequence
 
 import cairo
 
 from shell import geometry
 
 Panel = tuple[str, int, int, int, float]  # (edge, pos, length, depth_full, d_now)
+# A corner panel (spec 19): (corner, edge it opens from, along, depth_full, d_now); `along` is px
+# from the screen corner along that edge, the adjacent frame band included.
+CornerSpan = tuple[str, str, int, int, float]
 
 # Canonical frame -> device matrices. Canonical: u along the edge (clockwise), v from the
 # screen edge towards the desktop. Pure rotations, so arc angles are unchanged.
@@ -23,6 +27,9 @@ _MATRICES = {
     "left": lambda w, h: cairo.Matrix(0, -1, 1, 0, 0, h),
 }
 _ORDER = ("top", "right", "bottom", "left")
+# The screen corner each edge's clockwise walk starts and ends in.
+_START = {"top": "top-left", "right": "top-right", "bottom": "bottom-right", "left": "bottom-left"}
+_END = {"top": "top-right", "right": "bottom-right", "bottom": "bottom-left", "left": "top-left"}
 
 
 def trace_edge(
@@ -32,18 +39,40 @@ def trace_edge(
     radius: float,
     spans: list[tuple[float, float, float]],
     first: bool,
+    head: tuple[float, float] | None = None,
+    tail: tuple[float, float] | None = None,
+    lead: float = 0.0,
+    trail: float = 0.0,
 ) -> None:
     """Trace one edge in the canonical frame (edge at v=0, desktop towards +v).
 
     Runs from the end of the previous corner arc, along the frame's inner line, over each
     panel bump `(u0, u1, d)` (sorted by u0), and through the following corner arc.
+
+    Corner panels (spec 19) change only the two ends. `head = (u1, d)`: a corner panel on this
+    edge in its start corner, body from the corner to `u1` at depth `d`; the walk starts on
+    its body's inner edge and leaves it through a convex corner and a concave fillet (radius
+    min(R, d/2)), like a bump's far side. `tail = (u0, d)`: the same in the end corner. The
+    screen-corner arc keeps radius R and rides with the body: `tail` moves the end arc `d`
+    across, `trail` (a corner panel in the end corner that opens from the NEXT edge) moves it
+    back along by that panel's depth, and `lead` (one in the start corner that opens from the
+    PREVIOUS edge) moves the start by its depth. With every depth 0 the walk is exactly the
+    one without corner panels.
     """
     t, big_r = thickness, radius
-    start = (t + big_r, t)
+    hd = max(0.0, head[1]) if head is not None else 0.0
+    td = max(0.0, tail[1]) if tail is not None else 0.0
+    start = (t + big_r + lead, t + hd)
     if first:
         cr.move_to(*start)
     else:
         cr.line_to(*start)
+    if head is not None and hd > 0:
+        u1, r = head[0], geometry.join_radius(hd, int(big_r))
+        cr.line_to(u1 - r, t + hd)
+        cr.arc_negative(u1 - r, t + hd - r, r, 0.5 * math.pi, 0)  # convex corner
+        cr.line_to(u1, t + r)
+        cr.arc(u1 + r, t + r, r, math.pi, 1.5 * math.pi)  # concave fillet
     for u0, u1, d in spans:
         if d <= 0:
             continue
@@ -56,12 +85,29 @@ def trace_edge(
         cr.arc_negative(u1 - r, t + d - r, r, 0.5 * math.pi, 0)
         cr.line_to(u1, t + r)
         cr.arc(u1 + r, t + r, r, math.pi, 1.5 * math.pi)  # concave fillet
-    cr.line_to(length - t - big_r, t)
-    cr.arc(length - t - big_r, t + big_r, big_r, -0.5 * math.pi, 0)  # inner screen corner
+    if tail is not None and td > 0:
+        u0, r = tail[0], geometry.join_radius(td, int(big_r))
+        cr.line_to(u0 - r, t)
+        cr.arc(u0 - r, t + r, r, -0.5 * math.pi, 0)  # concave fillet
+        cr.line_to(u0, t + td - r)
+        cr.arc_negative(u0 + r, t + td - r, r, math.pi, 0.5 * math.pi)  # convex corner
+    cr.line_to(length - t - big_r - trail, t + td)
+    cr.arc(length - t - big_r - trail, t + big_r + td, big_r, -0.5 * math.pi, 0)  # screen corner
+
 
+def outline_path(
+    cr: cairo.Context,
+    w: int,
+    h: int,
+    T: int,
+    R: int,
+    panels: list[Panel],
+    corners: Sequence[CornerSpan] = (),
+) -> None:
+    """Append the inner desktop boundary as ONE closed clockwise path (from the top-left).
 
-def outline_path(cr: cairo.Context, w: int, h: int, T: int, R: int, panels: list[Panel]) -> None:
-    """Append the inner desktop boundary as ONE closed clockwise path (from the top-left)."""
+    `corners` are corner panels (spec 19), at most one per screen corner; shell.panel_layout
+    guarantees that and the minimum geometry that keeps the path simple."""
     first = True
     for edge in _ORDER:
         length = w if geometry.is_horizontal(edge) else h  # type: ignore[arg-type]
@@ -74,9 +120,22 @@ def outline_path(cr: cairo.Context, w: int, h: int, T: int, R: int, panels: list
             else:
                 spans.append((pos, pos + plen, d))
         spans.sort()
+        head = tail = None
+        lead = trail = 0.0
+        for corner, opens, along, _depth, d in corners:
+            if corner == _START[edge]:
+                if opens == edge:
+                    head = (along, d)
+                else:
+                    lead = max(0.0, d)
+            elif corner == _END[edge]:
+                if opens == edge:
+                    tail = (length - along, d)
+                else:
+                    trail = max(0.0, d)
         cr.save()
         cr.transform(_MATRICES[edge](w, h))
-        trace_edge(cr, length, T, R, spans, first)
+        trace_edge(cr, length, T, R, spans, first, head, tail, lead, trail)
         cr.restore()
         first = False
     cr.close_path()
@@ -90,12 +149,13 @@ def fill_mass(
     R: int,
     panels: list[Panel],
     rgba: tuple[float, float, float, float],
+    corners: Sequence[CornerSpan] = (),
 ) -> None:
     """Fill the dark mass: the whole screen minus the inner desktop region."""
     cr.save()
     cr.new_path()
     cr.rectangle(0, 0, w, h)
-    outline_path(cr, w, h, T, R, panels)
+    outline_path(cr, w, h, T, R, panels, corners)
     cr.set_source_rgba(*rgba)
     cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
     cr.fill()
```

Apply to `shell/canvas/effects.py`:

```diff
--- a/shell/canvas/effects.py
+++ b/shell/canvas/effects.py
@@ -10,10 +10,11 @@ from __future__ import annotations
 
 import functools
 import math
+from collections.abc import Sequence
 
 import cairo
 
-from shell.canvas.outline import Panel, fill_mass, outline_path
+from shell.canvas.outline import CornerSpan, Panel, fill_mass, outline_path
 
 RGBA = tuple[float, float, float, float]
 
@@ -73,6 +74,7 @@ def draw_border(
     panels: list[Panel],
     width: float,
     rgba: RGBA,
+    corners: Sequence[CornerSpan] = (),
 ) -> None:
     """RGBA border `width` px thick on the desktop side of the outline; nothing over the mass.
 
@@ -83,10 +85,10 @@ def draw_border(
     """
     cr.save()
     cr.new_path()
-    outline_path(cr, w, h, T, R, panels)
+    outline_path(cr, w, h, T, R, panels, corners)
     cr.clip()
     cr.new_path()
-    outline_path(cr, w, h, T, R, panels)
+    outline_path(cr, w, h, T, R, panels, corners)
     cr.set_line_width(2 * width)
     cr.set_line_join(cairo.LINE_JOIN_ROUND)
     cr.set_source_rgba(*rgba)
@@ -104,9 +106,10 @@ def draw_shadow_uniform(
     elevation_pct: float,
     rgba: RGBA,
     offset: float = 0,
+    corners: Sequence[CornerSpan] = (),
 ) -> None:
     """Uniform shadow of the mass (+ border via `offset`): reach = reach_px(elevation_pct)."""
-    draw_shadow_reach(cr, w, h, T, R, panels, reach_px(elevation_pct), rgba, offset)
+    draw_shadow_reach(cr, w, h, T, R, panels, reach_px(elevation_pct), rgba, offset, corners)
 
 
 def draw_shadow_reach(
@@ -119,6 +122,7 @@ def draw_shadow_reach(
     reach: int,
     rgba: RGBA,
     offset: float = 0,
+    corners: Sequence[CornerSpan] = (),
 ) -> None:
     """Uniform shadow with an absolute `reach` in px (the primitive under draw_shadow_uniform).
 
@@ -136,13 +140,13 @@ def draw_shadow_reach(
     levels = shadow_levels(reach, a)
     cr.save()
     cr.new_path()
-    outline_path(cr, w, h, T, R, panels)
+    outline_path(cr, w, h, T, R, panels, corners)
     cr.clip()
     cr.set_line_join(cairo.LINE_JOIN_ROUND)
     cr.set_line_cap(cairo.LINE_CAP_ROUND)
     for i in range(reach, 0, -1):
         cr.new_path()
-        outline_path(cr, w, h, T, R, panels)
+        outline_path(cr, w, h, T, R, panels, corners)
         cr.set_line_width(2 * (i + offset))
         cr.set_source_rgba(r, g, b, levels[i - 1])
         cr.stroke()
@@ -160,6 +164,7 @@ def draw_scene(
     border: tuple[float, RGBA] | None = None,
     shadow: tuple[float, RGBA] | None = None,
     clip: tuple[int, int, int, int] | None = None,
+    corners: Sequence[CornerSpan] = (),
 ) -> None:
     """Clear, then draw shadow (under), mass, border (over, on the desktop side of the outline).
 
@@ -175,11 +180,11 @@ def draw_scene(
     cr.push_group()
     if shadow is not None:
         draw_shadow_uniform(
-            cr, w, h, T, R, panels, shadow[0], shadow[1], border[0] if border else 0
+            cr, w, h, T, R, panels, shadow[0], shadow[1], border[0] if border else 0, corners
         )
-    fill_mass(cr, w, h, T, R, panels, mass_rgba)
+    fill_mass(cr, w, h, T, R, panels, mass_rgba, corners)
     if border is not None:
-        draw_border(cr, w, h, T, R, panels, border[0], border[1])
+        draw_border(cr, w, h, T, R, panels, border[0], border[1], corners)
     cr.pop_group_to_source()
     cr.set_operator(cairo.OPERATOR_SOURCE)
     cr.paint()
```

- [ ] **Step 4: Run them to see them pass**

Run: `scripts/py -m pytest -q tests/test_canvas_corner_outline.py tests/test_canvas_outline.py tests/test_canvas_effects.py`
Expected: all pass. `test_canvas_corner_outline.py` has 70 tests. The legacy contract in `test_canvas_outline.py` must pass untouched: edge panels without corners walk exactly the old path.

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `1340 passed`.

```bash
git add shell/canvas/outline.py shell/canvas/effects.py tests/test_canvas_corner_outline.py
git commit -m "feat(canvas): corner panels in the one outline, border and shadow" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Corner shapes in the scene, painter and simulation

**Files:**
- Modify: `shell/canvas/scene.py`, `shell/canvas/painter.py`, `shell/canvas/canvas.py`, `shell/canvas/simulate.py`
- Test: `tests/test_canvas_corner_scene.py` (new)

**Interfaces:**
- Consumes: Task 3 (`corner_box`); Task 4 (`CornerSpan`, `draw_scene(..., corners=)`); Task 2 (`CornerGeometry`).
- Produces (`shell/canvas/scene.py`):
  - `CornerShape(corner, edge, along, depth)` (frozen dataclass) and `Shape = PanelShape | CornerShape`;
  - `shape_for(geo: PanelGeometry | CornerGeometry) -> Shape`;
  - `Scene.add_panel(key, shape: Shape, depth=0.0)` takes either kind;
  - `Scene.outline_panels()` (edge panels only) and `Scene.outline_corners() -> list[CornerSpan]`;
  - the damage of a corner shape is `corner_box(..., pad)`.
- Produces elsewhere:
  - `CanvasPainter.draw` passes `corners=scene.outline_corners()`, and `CanvasPainter.add_panel` / `ShapeCanvas.add_panel` take a `Shape`;
  - `simulate(..., shapes: list[Shape], ...)`, and `config_shapes` returns corner shapes too (tested in Task 6, which provides the layout).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_canvas_corner_scene.py`:

```python
"""Corner panels in the scene, the painter's damage and the headless simulation (spec 19)."""

import random

import cairo
import pytest

from shell.canvas.painter import CanvasPainter
from shell.canvas.scene import CornerShape, PanelShape, Scene, box_to_rect, shape_for, union_boxes
from shell.canvas.simulate import compare, simulate
from shell.canvas.style import style_for
from shell.panel_spec import CornerGeometry, PanelGeometry

W, H, T, R = 1920, 1080, 10, 14
BOX = CornerShape("bottom-left", "bottom", 300, 380)

# One scene with a corner panel in three corners (both opening edges used) and edge panels
# next to them, cleared as shell.panel_layout would (640 x 400, T 10, R 14).
MIXED = [
    CornerShape("bottom-left", "bottom", 140, 90),
    CornerShape("top-right", "right", 120, 80),
    CornerShape("top-left", "left", 100, 60),
    PanelShape("bottom", 300, 150, 64),
    PanelShape("right", 180, 100, 40),
]
THEMES = [
    {},
    {"shadow": {"enabled": True, "elevation": 50}},
    {
        "shadow": {"enabled": True, "elevation": 60, "color": "#000000a0"},
        "border": {"enabled": True, "width": 6, "color": "#ffffffa0"},
    },
]


def test_adding_a_corner_panel_damages_its_box():
    scene = Scene(W, H, T, R)
    assert scene.add_panel("c", BOX) == (0, 1080 - 24, 314, 1080)  # collapsed: band + R


def test_set_depth_damages_old_and_new_corner_box():
    scene = Scene(W, H, T, R, pad=5)
    scene.add_panel("c", BOX)
    assert scene.set_depth("c", 100) == (0, 1080 - 129, 319, 1080)
    assert scene.set_depth("c", 40) == (0, 1080 - 129, 319, 1080)  # the old, deeper footprint
    assert scene.set_depth("c", 40) is None


def test_outline_lists_keep_edge_and_corner_panels_apart():
    scene = Scene(W, H, T, R)
    scene.add_panel(1, PanelShape("bottom", 680, 560, 64), 10)
    scene.add_panel(2, BOX, 20)
    assert scene.outline_panels() == [("bottom", 680, 560, 64, 10.0)]
    assert scene.outline_corners() == [("bottom-left", "bottom", 300, 380, 20.0)]


def test_shape_for_maps_both_kinds_of_geometry():
    assert shape_for(PanelGeometry("dock", "bottom", 680, 560, 64, "extended", "dock")) == (
        PanelShape("bottom", 680, 560, 64)
    )
    assert shape_for(
        CornerGeometry("box", "top-right", "right", 200, 190, 150, "extended", "box")
    ) == CornerShape("top-right", "right", 200, 150)


def test_the_painter_draws_the_corner_panels(make_config):
    theme = make_config().theme
    scene = Scene(640, 400, T, R)
    scene.add_panel("c", CornerShape("bottom-left", "bottom", 140, 90), 90)
    with_corner = cairo.ImageSurface(cairo.FORMAT_ARGB32, 640, 400)
    CanvasPainter(scene, style_for(theme), lambda _b: None).draw(cairo.Context(with_corner), None)
    with_corner.flush()
    data = with_corner.get_data()
    stride = with_corner.get_stride()
    assert data[(400 - 50) * stride + 60 * 4 + 3] == 255  # inside the body: mass
    assert data[(400 - 150) * stride + 60 * 4 + 3] == 0  # above it: desktop


@pytest.mark.parametrize("theme", THEMES)
def test_damaged_redraws_with_corner_panels_equal_a_full_redraw(make_config, theme):
    res = simulate(make_config(theme=theme).theme, (640, 400), MIXED, 80, check_every=7)
    assert res.checked == 12
    assert res.max_noisy <= 40 and res.max_diff <= 32, res
    assert res.full_draws == 1


def test_random_corner_depth_jumps_never_leave_stale_pixels(make_config):
    theme = make_config(theme=THEMES[-1]).theme
    w, h = 640, 400
    pending = []
    scene = Scene(w, h, theme.thickness, theme.radius)
    painter = CanvasPainter(scene, style_for(theme), pending.append)
    for key, shape in enumerate(MIXED):
        painter.add_panel(key, shape)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    painter.draw(cairo.Context(surface), None)
    pending.clear()
    rng = random.Random(11)
    for _ in range(40):
        for key in rng.sample(range(len(MIXED)), 2):
            painter.set_depth(key, rng.uniform(0, MIXED[key].depth))
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


def test_a_corner_panel_at_1080p_keeps_damage_small(make_config):
    theme = make_config(theme={"shadow": {"enabled": True}}).theme
    res = simulate(theme, (W, H), [BOX], 40)
    assert res.full_draws == 1
    assert max(res.damage_px[1:]) < 0.1 * W * H  # never a full-surface redraw while animating
```

- [ ] **Step 2: Run them to see them fail**

Run: `scripts/py -m pytest -q tests/test_canvas_corner_scene.py`
Expected: FAIL at import: `ImportError: cannot import name 'CornerShape' from 'shell.canvas.scene'`.

- [ ] **Step 3: Implement**

Apply to `shell/canvas/scene.py`:

```diff
--- a/shell/canvas/scene.py
+++ b/shell/canvas/scene.py
@@ -7,8 +7,10 @@ import math
 from collections.abc import Hashable
 from dataclasses import dataclass
 
-from shell.canvas.outline import Panel
-from shell.config.models import Edge
+from shell.canvas.outline import CornerSpan, Panel
+from shell.config.models import Corner, Edge
+from shell.corner import corner_box
+from shell.panel_spec import CornerGeometry, PanelGeometry
 
 Box = tuple[int, int, int, int]  # (x0, y0, x1, y1) in surface px; x1 / y1 exclusive
 
@@ -24,6 +26,29 @@ class PanelShape:
     depth: int  # full depth past the frame
 
 
+@dataclass(frozen=True)
+class CornerShape:
+    """A corner panel as the canvas draws it (spec 19): a rectangle in `corner`, `along` px
+    along `edge` (the edge it opens from) from the screen corner, the adjacent frame band
+    included, `depth` px past the band of `edge` when extended."""
+
+    corner: Corner
+    edge: Edge
+    along: int
+    depth: int
+
+
+Shape = PanelShape | CornerShape
+
+
+def shape_for(geo: PanelGeometry | CornerGeometry) -> Shape:
+    """The canvas shape of a panel resolved by shell.panel_layout (PanelGeometry or
+    CornerGeometry)."""
+    if isinstance(geo, CornerGeometry):
+        return CornerShape(geo.corner, geo.edge, geo.along, geo.depth)
+    return PanelShape(geo.edge, geo.pos, geo.length, geo.depth)
+
+
 def union_boxes(a: Box | None, b: Box | None) -> Box | None:
     """Bounding union; None means 'no box' and is neutral."""
     if a is None:
@@ -67,7 +92,7 @@ class Scene:
         self.width, self.height = width, height
         self.thickness, self.radius = thickness, radius
         self.pad = pad
-        self._shapes: dict[Hashable, PanelShape] = {}
+        self._shapes: dict[Hashable, Shape] = {}
         self._depths: dict[Hashable, float] = {}
 
     # ---- whole-surface changes (callers redraw everything) ----------------------------
@@ -81,8 +106,8 @@ class Scene:
         return 0, 0, self.width, self.height
 
     # ---- panels -------------------------------------------------------------------------
-    def add_panel(self, key: Hashable, shape: PanelShape, depth: float = 0.0) -> Box:
-        """Add (or replace) a panel; returns the box to redraw."""
+    def add_panel(self, key: Hashable, shape: Shape, depth: float = 0.0) -> Box:
+        """Add (or replace) an edge or corner panel; returns the box to redraw."""
         old = self._box(key)
         self._shapes[key] = shape
         self._depths[key] = float(depth)
@@ -117,15 +142,37 @@ class Scene:
         return list(self._shapes)
 
     def outline_panels(self) -> list[Panel]:
-        """Panels in the form shell.canvas.outline expects: (edge, pos, length, depth, d)."""
+        """Edge panels in the form shell.canvas.outline expects: (edge, pos, length, depth, d)."""
+        return [
+            (s.edge, s.pos, s.length, s.depth, self._depths[k])
+            for k, s in self._shapes.items()
+            if isinstance(s, PanelShape)
+        ]
+
+    def outline_corners(self) -> list[CornerSpan]:
+        """Corner panels as shell.canvas.outline expects: (corner, edge, along, depth, d)."""
         return [
-            (s.edge, s.pos, s.length, s.depth, self._depths[k]) for k, s in self._shapes.items()
+            (s.corner, s.edge, s.along, s.depth, self._depths[k])
+            for k, s in self._shapes.items()
+            if isinstance(s, CornerShape)
         ]
 
     def _box(self, key: Hashable) -> Box | None:
         shape = self._shapes.get(key)
         if shape is None:
             return None
+        if isinstance(shape, CornerShape):
+            return corner_box(
+                shape.corner,
+                shape.edge,
+                shape.along,
+                self._depths[key],
+                self.width,
+                self.height,
+                self.thickness,
+                self.radius,
+                self.pad,
+            )
         return panel_box(
             shape,
             self._depths[key],
```

Apply to `shell/canvas/painter.py`:

```diff
--- a/shell/canvas/painter.py
+++ b/shell/canvas/painter.py
@@ -11,7 +11,7 @@ from typing import Protocol
 import cairo
 
 from shell.canvas.effects import draw_scene
-from shell.canvas.scene import Box, PanelShape, Scene
+from shell.canvas.scene import Box, Scene, Shape
 from shell.canvas.style import CanvasStyle
 
 Rect = tuple[int, int, int, int]  # (x, y, width, height)
@@ -55,7 +55,7 @@ class CanvasPainter:
         self._full()
         return True
 
-    def add_panel(self, key: Hashable, shape: PanelShape) -> None:
+    def add_panel(self, key: Hashable, shape: Shape) -> None:
         self._damage(self.scene.add_panel(key, shape))
 
     def remove_panel(self, key: Hashable) -> None:
@@ -87,6 +87,7 @@ class CanvasPainter:
             border=st.border,
             shadow=st.shadow,
             clip=None if full else clip,
+            corners=s.outline_corners(),
         )
         if self.recorder is not None:
             self.recorder.on_draw((time.perf_counter() - start) * 1000, full)
```

Apply to `shell/canvas/canvas.py`:

```diff
--- a/shell/canvas/canvas.py
+++ b/shell/canvas/canvas.py
@@ -16,7 +16,7 @@ from fabric.widgets.wayland import WaylandWindow
 from gi.repository import Gdk, Gtk, GtkLayerShell
 
 from shell.canvas.painter import CanvasPainter
-from shell.canvas.scene import Box, PanelShape, Scene, box_to_rect
+from shell.canvas.scene import Box, Scene, Shape, box_to_rect
 from shell.canvas.style import style_for
 from shell.config.models import Theme
 from shell.gdk_util import monitor_index
@@ -68,7 +68,7 @@ class ShapeCanvas(WaylandWindow):
         """Colour / border / shadow change (a restyle): full redraw, no rebuild."""
         self.painter.set_style(style_for(theme))
 
-    def add_panel(self, key: Hashable, shape: PanelShape) -> None:
+    def add_panel(self, key: Hashable, shape: Shape) -> None:
         self.painter.add_panel(key, shape)
 
     def remove_panel(self, key: Hashable) -> None:
```

Apply to `shell/canvas/simulate.py`:

```diff
--- a/shell/canvas/simulate.py
+++ b/shell/canvas/simulate.py
@@ -13,7 +13,15 @@ import cairo
 
 from shell.anim import Tween
 from shell.canvas.painter import CanvasPainter
-from shell.canvas.scene import Box, PanelShape, Scene, box_to_rect, union_boxes
+from shell.canvas.scene import (
+    Box,
+    PanelShape,
+    Scene,
+    Shape,
+    box_to_rect,
+    shape_for,
+    union_boxes,
+)
 from shell.canvas.style import style_for
 from shell.config.models import Config, Theme
 from shell.panel_layout import layout_monitor
@@ -80,7 +88,7 @@ def compare(a: bytes, b: bytes) -> tuple[int, int]:
 def simulate(
     theme: Theme,
     size: tuple[int, int],
-    shapes: list[PanelShape],
+    shapes: list[Shape],
     frames: int,
     toggle_every: int = 18,
     check_every: int = 0,
@@ -99,7 +107,7 @@ def simulate(
     painter = CanvasPainter(scene, style_for(theme), pending.append)
     painter.recorder = recorder
     ticker = FakeTicker()
-    tweens: list[tuple[Tween, PanelShape]] = []
+    tweens: list[tuple[Tween, Shape]] = []
     for key, shape in enumerate(shapes):
         painter.add_panel(key, shape)
         tween = Tween(ticker, lambda d, k=key: painter.set_depth(k, d), theme.duration_ms)
@@ -174,9 +182,10 @@ def default_shapes(width: int, height: int) -> list[PanelShape]:
 
 def config_shapes(
     config: Config, monitor: str, width: int, height: int
-) -> tuple[list[PanelShape], list[str]]:
-    """The shown panels of `monitor` in `config`, laid out by shell.panel_layout at width x
-    height, plus the layout warnings. The widgets must be registered (import widgets)."""
+) -> tuple[list[Shape], list[str]]:
+    """The shown panels of `monitor` in `config` (edge and corner panels), laid out by
+    shell.panel_layout at width x height, plus the layout warnings. The widgets must be
+    registered (import widgets)."""
     theme = config.theme_for(monitor)
     layout = layout_monitor(
         requests_for(config, monitor),
@@ -187,7 +196,7 @@ def config_shapes(
         config.layout_for(monitor).gap,
         where=f"monitors.{monitor}",
     )
-    shapes = [PanelShape(p.edge, p.pos, p.length, p.depth) for p in layout.panels if p]
+    shapes = [shape_for(p) for p in layout.panels if p]
     return shapes, layout.warnings
 
 
```

- [ ] **Step 4: Run them to see them pass**

Run: `scripts/py -m pytest -q tests/test_canvas_corner_scene.py tests/test_canvas_scene.py tests/test_canvas_window.py`
Expected: all pass (`test_canvas_corner_scene.py`: 10).

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `1350 passed`.

```bash
git add shell/canvas/scene.py shell/canvas/painter.py shell/canvas/canvas.py shell/canvas/simulate.py tests/test_canvas_corner_scene.py
git commit -m "feat(canvas): corner shapes in the scene, damage boxes and the simulation" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Corner panels in the layout resolver

**Files:**
- Modify: `shell/panel_layout.py`
- Test: `tests/test_corner_layout.py` (new)

**Interfaces:**
- Consumes: Task 2 (`CornerRequest`, `CornerGeometry`, `default_edge`); Task 3 (`pq_box`); Task 5 (`shape_for`, `config_shapes`); the existing `layout_edge`, `_grown_body`, `_overlap`.
- Produces:
  - `MIN_DEPTH = 16`, plus `AXIS_START` and `AXIS_END` (`{edge: corner}`: the corner at the left or top end, and at the right or bottom end, of each edge);
  - `free_span(extent, thickness, radius, depth, start=None, end=None)`: `start` and `end` are the px each corner takes (None = `T + R`, the old behaviour);
  - `corner_clearance(edge, held: CornerGeometry | None, thickness, radius, gap) -> float`;
  - `layout_corners(entries, width, height, thickness, radius, gap, where) -> ({index: CornerGeometry | None}, notes)`: floors `along` to `need = max(T + MIN_LENGTH, T + R + ceil(r))`; a corner panel is None (hidden) when its corner is taken, when `along < need` or `depth < MIN_DEPTH` after shrinking, or when it overlaps a corner panel shown before it (`_corner_grown` against the boxes already held). Only shown corner panels are held, so a hidden one takes no clearance in `layout_monitor`; a hidden one gets only its "not shown" note;
  - `layout_edge(..., clear=(None, None))`;
  - `layout_monitor(requests: Sequence[PanelRequest | CornerRequest], ...)` returns `Layout.panels: list[PanelGeometry | CornerGeometry | None]`.
- Warning texts (key paths as in Plan 2):
  - `{where}.panels.{i} ({widget}): the {corner} corner already holds {where}.panels.{j} ({widget}); not shown`
  - `{where}.panels.{i} ({widget}): width|height {n} px does not fit the {edge} edge; shrunk to {m}`
  - `{where}.panels.{i} ({widget}): the {corner} corner has no room for it; not shown`

  The overlap message is unchanged (`layout_corners` uses the same text for a corner panel that overlaps an earlier corner panel).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_corner_layout.py`:

```python
"""Corner panels in the layout resolver (spec 19): one per corner, shrink to fit, the free
spans of their two edges, and the overlap check."""

import pytest

from shell.panel_layout import (
    corner_clearance,
    free_span,
    layout_corners,
    layout_monitor,
)
from shell.panel_spec import CornerGeometry, CornerRequest, PanelRequest, default_edge

W, H, T, R, GAP = 1920, 1080, 10, 14, 8


def box(corner="bottom-left", edge=None, width=300, height=390, widget="box"):
    edge = edge or default_edge(corner)
    return CornerRequest(widget, corner, edge, width, height, "extended", widget)


def panel(edge="bottom", align="center", length=560, depth=64, widget="dock"):
    return PanelRequest(
        widget, edge, align, 0, None, 0, length, None, None, depth, "extended", widget, length
    )


def lay(*requests, width=W, height=H, thickness=T):
    return layout_monitor(list(requests), width, height, thickness, R, GAP, None, "monitors.X")


def where(geo):
    if geo is None:
        return None
    if isinstance(geo, CornerGeometry):
        return (geo.corner, geo.edge, geo.along, geo.depth)
    return (geo.edge, geo.pos, geo.length)


def placed(*requests, **kw):
    layout = lay(*requests, **kw)
    return [where(p) for p in layout.panels], layout.warnings


# ---- one corner panel -------------------------------------------------------------------


def test_the_default_box_is_placed_as_asked():
    layout = lay(box())
    assert layout.panels == [
        CornerGeometry("box", "bottom-left", "bottom", 300, 290, 380, "extended", "box")
    ]
    assert layout.warnings == []


@pytest.mark.parametrize(
    ("corner", "edge", "expected"),
    [
        ("bottom-left", "bottom", ("bottom-left", "bottom", 300, 380)),
        ("bottom-left", "left", ("bottom-left", "left", 390, 290)),
        ("top-right", "top", ("top-right", "top", 300, 380)),
        ("top-right", "right", ("top-right", "right", 390, 290)),
    ],
)
def test_along_and_depth_follow_the_opening_edge(corner, edge, expected):
    assert placed(box(corner, edge)) == ([expected], [])


def test_a_corner_panel_wider_than_the_edge_is_shrunk():
    assert placed(box(width=2000)) == (
        [("bottom-left", "bottom", 1882, 380)],
        ["monitors.X.panels.0 (box): width 2000 px does not fit the bottom edge; shrunk to 1882"],
    )


def test_a_corner_panel_taller_than_the_other_edge_is_shrunk():
    assert placed(box(height=1200)) == (
        [("bottom-left", "bottom", 300, 1032)],
        ["monitors.X.panels.0 (box): height 1200 px does not fit the left edge; shrunk to 1042"],
    )


def test_a_corner_panel_with_too_little_depth_is_not_shown():
    assert placed(box(height=70), thickness=64) == (
        [None],
        ["monitors.X.panels.0 (box): the bottom-left corner has no room for it; not shown"],
    )


def test_a_narrow_body_is_floored_to_the_minimum_length():
    assert placed(box(width=60)) == ([("bottom-left", "bottom", 70, 380)], [])


def test_a_large_radius_raises_the_minimum_along():
    # R = 40 (the theme allows up to 64): T + R + r = 10 + 40 + 40 = 90 > T + 60, so the side
    # from the lifted arc to the free corner never runs backwards (no folded outline)
    layout = layout_monitor([box(width=60)], W, H, T, 40, GAP, None, "monitors.X")
    assert [where(p) for p in layout.panels] == [("bottom-left", "bottom", 90, 380)]
    assert layout.warnings == []


# ---- several corner panels -----------------------------------------------------------------


def test_a_second_panel_in_the_same_corner_is_not_shown():
    assert placed(box(), box(edge="left", widget="other")) == (
        [("bottom-left", "bottom", 300, 380), None],
        [
            "monitors.X.panels.1 (other): the bottom-left corner already holds "
            "monitors.X.panels.0 (box); not shown"
        ],
    )


def test_two_corner_panels_facing_on_one_edge_keep_their_joins_and_the_gap():
    assert placed(box(), box("bottom-right", width=1700)) == (
        [("bottom-left", "bottom", 300, 380), ("bottom-right", "bottom", 1584, 380)],
        ["monitors.X.panels.1 (box): width 1700 px does not fit the bottom edge; shrunk to 1584"],
    )


def test_a_lifted_corner_arc_limits_the_next_corner_across():
    assert placed(box(), box("top-left", height=800)) == (
        [("bottom-left", "bottom", 300, 380), ("top-left", "top", 300, 652)],
        ["monitors.X.panels.1 (box): height 800 px does not fit the left edge; shrunk to 662"],
    )


def test_two_corner_panels_opening_from_the_same_side_edge():
    assert placed(box(edge="left"), box("top-left", "left", height=700)) == (
        [("bottom-left", "left", 390, 290), ("top-left", "left", 654, 290)],
        ["monitors.X.panels.1 (box): height 700 px does not fit the left edge; shrunk to 654"],
    )


def test_a_corner_squeezed_below_the_minimum_is_not_shown():
    got, warnings = placed(box(width=1840), box("bottom-right"))
    assert got == [("bottom-left", "bottom", 1840, 380), None]
    assert warnings == [  # only the outcome: no "shrunk to 44" for a panel that is not shown
        "monitors.X.panels.1 (box): the bottom-right corner has no room for it; not shown",
    ]


def test_opposite_corner_panels_that_overlap_hide_the_later_one():
    got, warnings = placed(box(width=1200, height=700), box("top-right", width=1200, height=700))
    assert got == [("bottom-left", "bottom", 1200, 690), None]
    assert "monitors.X.panels.1 (box): overlaps monitors.X.panels.0 (box)" in warnings[0]


def test_a_hidden_corner_panel_takes_no_clearance():
    # the top-right panel overlaps the bottom-left one and is hidden: the top edge's end is a
    # plain screen corner again, so the bar sits at 1920 - 24 - 14 - 300 = 1582 (not 384)
    got, warnings = placed(
        box(width=1200, height=700),
        box("top-right", width=1200, height=700),
        panel("top", "end", 300, 56, "bar"),
    )
    assert got == [("bottom-left", "bottom", 1200, 690), None, ("top", 1582, 300)]
    assert len(warnings) == 1 and "panels.1 (box): overlaps monitors.X.panels.0" in warnings[0]


# ---- edge panels beside corner panels ----------------------------------------------------


def test_free_span_takes_the_corner_clearances():
    assert free_span(W, T, R, 64) == (38, 1882)  # unchanged without corner panels
    assert free_span(W, T, R, 64, start=322) == (336, 1882)
    assert free_span(H, T, R, 56, None, 404) == (38, 662)


def test_corner_clearance():
    same = CornerGeometry("box", "bottom-left", "bottom", 300, 290, 380, "extended", "box")
    other = CornerGeometry("box", "bottom-left", "left", 390, 380, 290, "extended", "box")
    assert corner_clearance("bottom", None, T, R, GAP) == 24
    assert corner_clearance("bottom", same, T, R, GAP) == 300 + 14 + 8
    assert corner_clearance("left", same, T, R, GAP) == 24 + 380
    assert corner_clearance("bottom", other, T, R, GAP) == 24 + 290


def test_an_edge_panel_starts_past_the_corner_panel_on_its_edge():
    got, warnings = placed(box(), panel(align="start"))
    assert got[1] == ("bottom", 336, 560) and warnings == []  # 300 + 14 + 8 + 14


def test_an_edge_panel_on_the_other_edge_stays_below_the_lifted_corner_arc():
    got, warnings = placed(box(), panel("left", "end", 300, 56, "bar"))
    assert got[1] == ("left", 362, 300) and warnings == []  # 1080 - (24 + 380) - 14 - 300
    assert placed(panel("left", "end", 300, 56, "bar"))[0] == [("left", 742, 300)]


def test_a_corner_panel_opening_from_the_side_edge_moves_the_other_edge():
    got, _ = placed(box(edge="left"), panel(align="start"), panel("left", "end", 200, 56, "bar"))
    assert got[1] == ("bottom", 328, 560)  # T + R + 290 + 14
    assert got[2] == ("left", 454, 200)  # 1080 - (390 + 14 + 8) - 14 - 200


def test_a_centred_edge_panel_does_not_move_for_a_corner_panel():
    assert placed(box(), panel())[0][1] == ("bottom", 680, 560)


def test_a_fill_panel_fills_up_to_the_corner_panel():
    req = panel(length="fill")
    got, _ = placed(box(), req)
    assert got[1] == ("bottom", 336, 1882 - 336)


def test_corner_panels_win_over_earlier_edge_panels_they_overlap():
    got, warnings = placed(panel("top", "start", 560, 700), box())
    assert got == [None, ("bottom-left", "bottom", 300, 380)]
    assert warnings == [
        "monitors.X.panels.0 (dock): overlaps monitors.X.panels.1 (box) or leaves less than "
        "the minimum gap between their joins; not shown"
    ]


def test_layout_corners_reports_by_config_index():
    got, notes = layout_corners([(4, box()), (9, box())], W, H, T, R, GAP, "monitors.X")
    assert got[4] is not None and got[9] is None and [i for i, _ in notes] == [9]


def test_the_state_is_kept():
    req = CornerRequest("box", "top-left", "top", 300, 390, "collapsed", "box")
    assert lay(req).panels[0].state == "collapsed"


def test_simulate_lays_out_corner_panels_from_a_config(corner_registry, make_config):
    from shell.canvas.scene import CornerShape, PanelShape
    from shell.canvas.simulate import config_shapes

    cfg = make_config(
        monitors={
            "HDMI-A-1": {
                "shell": "edge",
                "panels": [{"widget": "box"}, {"widget": "dock", "align": "start"}],
            }
        }
    )
    shapes, warnings = config_shapes(cfg, "HDMI-A-1", W, H)
    assert shapes == [
        CornerShape("bottom-left", "bottom", 300, 380),
        PanelShape("bottom", 336, 560, 64),
    ]
    assert warnings == []
```

- [ ] **Step 2: Run them to see them fail**

Run: `scripts/py -m pytest -q tests/test_corner_layout.py`
Expected: FAIL at import: `ImportError: cannot import name 'corner_clearance' from 'shell.panel_layout'`.

- [ ] **Step 3: Implement**

Apply to `shell/panel_layout.py`:

```diff
--- a/shell/panel_layout.py
+++ b/shell/panel_layout.py
@@ -36,6 +36,19 @@ between different groups (start / center / end) only the minimum `r1 + r2` is gu
 not `r1 + r2 + gap` (the center group is pushed clear of the start and end groups by the
 minimum, and a fill sizes against the full spacing). Raised for a decision.
 
+Corner panels (spec 19, `layout_corners`) are placed first, in config order: at most one per
+screen corner (a later one in a taken corner is not shown); each is shrunk to fit beside the
+corner panels already placed (along its edge: their free ends plus `r1 + r2 + gap`, or their
+lifted screen-corner arc; across: the far corner's occupant), and not shown when `along` falls
+below max(T + MIN_LENGTH, T + R + r) (so the outline never folds, whatever the theme radius)
+or less than MIN_DEPTH px of depth remains; a hidden panel gets only its "not shown" warning.
+A corner panel that overlaps one placed before it is hidden there too, so only the corner
+panels that are shown are held. They then move the free span of their two edges: on the edge
+a corner panel opens from, the span starts `along + r_c + gap` from that corner (plus the
+panel's own `r`, as between neighbours); on the other edge the screen-corner arc rides up by
+its depth, so the span starts `T + R + depth` from the corner (plus `r`). The overlap check
+then runs over the shown corner panels first, then the edge panels.
+
 Every warning names the key path (`where`.panels.N (widget)).
 """
 
@@ -47,10 +60,12 @@ from dataclasses import dataclass
 from itertools import pairwise
 
 from shell import geometry
-from shell.config.models import Edge
-from shell.panel_spec import PanelGeometry, PanelRequest
+from shell.config.models import Corner, Edge
+from shell.corner import pq_box
+from shell.panel_spec import CornerGeometry, CornerRequest, PanelGeometry, PanelRequest
 
 MIN_LENGTH = 60  # same floor as the config model's px lengths
+MIN_DEPTH = 16  # a corner panel's smallest depth past the band (the model's Depth minimum)
 CONTENT_PAD = 12  # body px on each side of a "content" panel's natural size
 EDGES: tuple[Edge, ...] = ("top", "right", "bottom", "left")
 
@@ -58,9 +73,25 @@ Box = tuple[float, float, float, float]  # x0, y0, x1, y1
 Note = tuple[int, str]  # (config index, warning)
 
 
+# The screen corner at the start (left / top) and at the end (right / bottom) of each edge, in
+# the layout's screen-axis terms (`pos` grows left to right, top to bottom).
+AXIS_START: dict[str, Corner] = {
+    "top": "top-left",
+    "bottom": "bottom-left",
+    "left": "top-left",
+    "right": "top-right",
+}
+AXIS_END: dict[str, Corner] = {
+    "top": "top-right",
+    "bottom": "bottom-right",
+    "left": "bottom-left",
+    "right": "bottom-right",
+}
+
+
 @dataclass(frozen=True)
 class Layout:
-    panels: list[PanelGeometry | None]  # config order; None = not shown
+    panels: list[PanelGeometry | CornerGeometry | None]  # config order; None = not shown
     warnings: list[str]
 
 
@@ -69,10 +100,46 @@ def content_length(natural: int) -> int:
     return max(MIN_LENGTH, natural + 2 * CONTENT_PAD)
 
 
-def free_span(extent: int, thickness: int, radius: int, depth: int) -> tuple[int, int]:
-    """(first, last) px along the edge a body of this depth may occupy (corner clearance)."""
-    clearance = thickness + radius + geometry.join_radius(depth, radius)
-    return math.ceil(clearance), math.floor(extent - clearance)
+def free_span(
+    extent: int,
+    thickness: int,
+    radius: int,
+    depth: int,
+    start: float | None = None,
+    end: float | None = None,
+) -> tuple[int, int]:
+    """(first, last) px along the edge a body of this depth may occupy: `start` / `end` px of
+    each corner are taken (`T + R` without a corner panel, `corner_clearance`), plus the
+    body's own join radius."""
+    r = geometry.join_radius(depth, radius)
+    lo = (thickness + radius if start is None else start) + r
+    hi = extent - (thickness + radius if end is None else end) - r
+    return math.ceil(lo), math.floor(hi)
+
+
+def corner_clearance(
+    edge: Edge,
+    held: CornerGeometry | None,
+    thickness: int,
+    radius: int,
+    gap: int,
+) -> float:
+    """Px of `edge` taken from the corner that holds `held` (None: a plain screen corner,
+    T + R). A corner panel opening from `edge` takes its body, its free-end join and the gap
+    (edge panels keep `r1 + r2 + gap` from it, as from a neighbour); one opening from the
+    other edge lifts the screen-corner arc by its depth (no gap, as at a plain corner)."""
+    spare = gap if held is not None and held.edge == edge else 0
+    return _reach(edge, held, thickness, radius) + spare
+
+
+def _reach(edge: Edge, held: CornerGeometry | None, thickness: int, radius: int) -> float:
+    """Px of `edge` a corner's occupant reaches from its corner: its free end (body plus join)
+    when it opens from `edge`, else the screen-corner arc it lifts (T + R + depth)."""
+    if held is None:
+        return thickness + radius
+    if held.edge == edge:
+        return held.along + geometry.join_radius(held.depth, radius)
+    return thickness + radius + held.depth
 
 
 @dataclass
@@ -131,16 +198,19 @@ def layout_edge(
     gap: int,
     natural: Mapping[int, int] | None = None,
     where: str = "monitor",
+    clear: tuple[float | None, float | None] = (None, None),
 ) -> tuple[dict[int, tuple[int, int] | None], list[Note]]:
-    """Resolve the panels of ONE edge. `entries` are (config index, request) pairs; returns
-    {index: (pos, length) or None when the edge has no room} and (index, warning) notes."""
+    """Resolve the panels of ONE edge. `entries` are (config index, request) pairs; `clear`
+    is what corner panels take at the start and the end of the edge (corner_clearance; None:
+    a plain corner). Returns {index: (pos, length) or None when the edge has no room} and
+    (index, warning) notes."""
     natural = natural or {}
     out: dict[int, tuple[int, int] | None] = {}
     notes: list[Note] = []
     items: list[_Item] = []
     for index, req in entries:
         name = f"{where}.panels.{index} ({req.widget})"
-        lo, hi = free_span(extent, thickness, radius, req.depth)
+        lo, hi = free_span(extent, thickness, radius, req.depth, *clear)
         if hi - lo < MIN_LENGTH:
             notes.append(
                 (index, f"{name}: the {req.edge} edge ({extent} px) has no room for it; not shown")
@@ -271,12 +341,136 @@ def _grown_body(geo: PanelGeometry, width: int, height: int, thickness: int, r:
     return (width - across, a0, width + r, a1)
 
 
+def _corner_grown(geo: CornerGeometry, width: int, height: int, thickness: int, radius: int) -> Box:
+    """The corner panel's box for the overlap check: its body, its free-end join along its
+    edge and the lifted screen-corner arc (radius R) across, from beyond the screen corner."""
+    r = geometry.join_radius(geo.depth, radius)
+    return pq_box(
+        geo.corner,
+        geo.edge,
+        -radius,
+        geo.along + r,
+        -radius,
+        thickness + geo.depth + radius,
+        width,
+        height,
+    )
+
+
+def _other(corner: Corner, edge: Edge) -> Edge:
+    first, second = corner.split("-")
+    return second if edge == first else first  # type: ignore[return-value]
+
+
+def _far(corner: Corner, edge: Edge) -> Corner:
+    """The other screen corner on `edge`."""
+    return AXIS_END[edge] if AXIS_START[edge] == corner else AXIS_START[edge]
+
+
+def layout_corners(
+    entries: Sequence[tuple[int, CornerRequest]],
+    width: int,
+    height: int,
+    thickness: int,
+    radius: int,
+    gap: int,
+    where: str = "monitor",
+) -> tuple[dict[int, CornerGeometry | None], list[Note]]:
+    """Resolve the corner panels (spec 19), in config order (see the module docstring). Only
+    corner panels that are shown are held: a hidden one takes no clearance from anything."""
+    out: dict[int, CornerGeometry | None] = {}
+    notes: list[Note] = []
+    held: dict[Corner, tuple[int, CornerGeometry]] = {}
+    boxes: list[tuple[int, CornerGeometry, Box]] = []
+    for index, req in entries:
+        name = f"{where}.panels.{index} ({req.widget})"
+        if req.corner in held:
+            j, other = held[req.corner]
+            notes.append(
+                (
+                    index,
+                    f"{name}: the {req.corner} corner already holds {where}.panels.{j} "
+                    f"({other.widget}); not shown",
+                )
+            )
+            out[index] = None
+            continue
+        edge, side = req.edge, _other(req.corner, req.edge)
+        horizontal = geometry.is_horizontal(edge)
+        along_key, across_key = ("width", "height") if horizontal else ("height", "width")
+        extent_e, extent_f = (width, height) if horizontal else (height, width)
+        depth = getattr(req, across_key) - thickness
+        shrunk: list[Note] = []  # reported only when the panel is shown
+        # across: the screen-corner arc it lifts must stay clear of the far corner of `side`
+        far_f = held.get(_far(req.corner, side), (None, None))[1]
+        room = extent_f - thickness - radius - math.ceil(_reach(side, far_f, thickness, radius))
+        if depth > room:
+            shrunk.append(
+                (
+                    index,
+                    f"{name}: {across_key} {depth + thickness} px does not fit the {side} edge; "
+                    f"shrunk to {room + thickness}",
+                )
+            )
+            depth = room
+        r = geometry.join_radius(depth, radius)
+        # the side from the lifted arc (T + R) to the free corner (along - r) never runs
+        # backwards, and the body keeps MIN_LENGTH px past the band, whatever the theme radius
+        need = max(thickness + MIN_LENGTH, thickness + radius + math.ceil(r))
+        along = max(getattr(req, along_key), need)
+        # along: its free end must stay clear of the far corner of `edge`
+        far_e = held.get(_far(req.corner, edge), (None, None))[1]
+        room = math.floor(extent_e - corner_clearance(edge, far_e, thickness, radius, gap) - r)
+        if along > room:
+            shrunk.append(
+                (
+                    index,
+                    f"{name}: {along_key} {along} px does not fit the {edge} edge; "
+                    f"shrunk to {room}",
+                )
+            )
+            along = room
+        if depth < MIN_DEPTH or along < need:
+            notes.append((index, f"{name}: the {req.corner} corner has no room for it; not shown"))
+            out[index] = None
+            continue
+        geo = CornerGeometry(
+            req.widget,
+            req.corner,
+            edge,
+            along,
+            along - thickness,
+            depth,
+            req.state,
+            req.label,
+        )
+        # a corner panel across the screen may still overlap one placed before it: hidden,
+        # and never held, so it takes no clearance from any edge panel
+        box = _corner_grown(geo, width, height, thickness, radius)
+        clash = next(((j, other) for j, other, b in boxes if _overlap(box, b)), None)
+        if clash is not None:
+            notes.append(
+                (
+                    index,
+                    f"{name}: overlaps {where}.panels.{clash[0]} ({clash[1].widget}) or leaves "
+                    "less than the minimum gap between their joins; not shown",
+                )
+            )
+            out[index] = None
+            continue
+        notes.extend(shrunk)
+        held[req.corner] = (index, geo)
+        boxes.append((index, geo, box))
+        out[index] = geo
+    return out, notes
+
+
 def _overlap(a: Box, b: Box) -> bool:
     return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
 
 
 def layout_monitor(
-    requests: Sequence[PanelRequest],
+    requests: Sequence[PanelRequest | CornerRequest],
     width: int,
     height: int,
     thickness: int,
@@ -285,39 +479,62 @@ def layout_monitor(
     natural: Mapping[int, int] | None = None,
     where: str = "monitor",
 ) -> Layout:
-    """Resolve every panel of one monitor. `natural` maps a config index to the measured
-    length of a "content" panel; `where` prefixes warnings, e.g. "monitors.HDMI-A-1"."""
+    """Resolve every panel of one monitor, edge (PanelRequest) and corner (CornerRequest).
+    `natural` maps a config index to the measured length of a "content" panel; `where`
+    prefixes warnings, e.g. "monitors.HDMI-A-1"."""
+    corner_entries = [(i, r) for i, r in enumerate(requests) if isinstance(r, CornerRequest)]
+    corners, notes = layout_corners(corner_entries, width, height, thickness, radius, gap, where)
+    held = {geo.corner: geo for geo in corners.values() if geo is not None}
     resolved: dict[int, tuple[int, int] | None] = {}
-    notes: list[Note] = []
     for edge in EDGES:
-        entries = [(i, req) for i, req in enumerate(requests) if req.edge == edge]
+        entries = [
+            (i, req)
+            for i, req in enumerate(requests)
+            if isinstance(req, PanelRequest) and req.edge == edge
+        ]
         if entries:
             extent = width if geometry.is_horizontal(edge) else height
-            got, edge_notes = layout_edge(entries, extent, thickness, radius, gap, natural, where)
+            clear = (
+                corner_clearance(edge, held.get(AXIS_START[edge]), thickness, radius, gap),
+                corner_clearance(edge, held.get(AXIS_END[edge]), thickness, radius, gap),
+            )
+            got, edge_notes = layout_edge(
+                entries, extent, thickness, radius, gap, natural, where, clear
+            )
             resolved.update(got)
             notes.extend(edge_notes)
-    out: list[PanelGeometry | None] = []
-    placed: list[tuple[int, PanelGeometry, Box]] = []
-    for i, req in enumerate(requests):
-        got = resolved[i]
+    geos: dict[int, PanelGeometry | CornerGeometry | None] = dict(corners)
+    for i, got in resolved.items():
+        req = requests[i]
         if got is None:
-            out.append(None)
+            geos[i] = None
+            continue
+        pos, length = got
+        geos[i] = PanelGeometry(req.widget, req.edge, pos, length, req.depth, req.state, req.label)
+    out: list[PanelGeometry | CornerGeometry | None] = [geos[i] for i in range(len(requests))]
+    placed: list[tuple[int, PanelGeometry | CornerGeometry, Box]] = []
+    order = [i for i, _ in corner_entries] + [i for i in range(len(requests)) if i in resolved]
+    for i in order:
+        geo = out[i]
+        if geo is None:
             continue
-        geo = PanelGeometry(req.widget, req.edge, got[0], got[1], req.depth, req.state, req.label)
-        box = _grown_body(geo, width, height, thickness, geometry.join_radius(req.depth, radius))
+        if isinstance(geo, CornerGeometry):
+            box = _corner_grown(geo, width, height, thickness, radius)
+        else:
+            r = geometry.join_radius(geo.depth, radius)
+            box = _grown_body(geo, width, height, thickness, r)
         clash = next(((j, other) for j, other, b in placed if _overlap(box, b)), None)
         if clash is not None:
             notes.append(
                 (
                     i,
-                    f"{where}.panels.{i} ({req.widget}): overlaps {where}.panels.{clash[0]} "
+                    f"{where}.panels.{i} ({geo.widget}): overlaps {where}.panels.{clash[0]} "
                     f"({clash[1].widget}) or leaves less than the minimum gap between their "
                     "joins; not shown",
                 )
             )
-            out.append(None)
+            out[i] = None
             continue
         placed.append((i, geo, box))
-        out.append(geo)
     notes.sort(key=lambda note: note[0])  # stable: per panel, in the order they arose
     return Layout(out, [message for _, message in notes])
```

- [ ] **Step 4: Run them to see them pass**

Run: `scripts/py -m pytest -q tests/test_corner_layout.py tests/test_layout_resolver.py tests/test_panel_layout.py`
Expected: all pass (`test_corner_layout.py`: 28). The Plan 2 resolver tests must pass unchanged: without corner requests every clearance is `T + R` and the overlap order is config order.

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `1378 passed`.

```bash
git add shell/panel_layout.py tests/test_corner_layout.py
git commit -m "feat(layout): corner panels first, one per corner, and edge panels clear of them" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: The corner review sheet

**Files:**
- Create: `shell/canvas/corner_sheet.py`
- Test: `tests/test_corner_sheet.py` (new)

**Interfaces:**
- Consumes: Task 4 (`draw_scene(..., corners=)`); Task 5 (`CornerShape`, `PanelShape`, `shape_for`); Task 6 (`AXIS_START`, `Layout`, `layout_monitor`); `CornerRequest`, `PanelRequest`.
- Produces:
  - `ROWS` (8 rows of `(corner, opening edge)`), `FRACTIONS = (0.0, 0.05, 0.15, 0.3, 0.6, 1.0)`, `CELL = (360, 300)`, `ZOOM = 2`;
  - `cell_layout(corner, edge) -> Layout`, `render_cell(corner, edge, fraction, effects) -> cairo.ImageSurface`, `render_sheet(path, effects=False) -> (w, h)`;
  - `main(argv) -> int` (`python -m shell.canvas.corner_sheet --out FILE [--effects]`; 2 on a write error).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_corner_sheet.py`:

```python
"""The corner panel review sheet (spec 19, Gate A): headless, written to a PNG."""

import cairo
import pytest

from shell.canvas import corner_sheet as cs
from shell.canvas.scene import PanelShape, shape_for


def _bytes(surface):
    surface.flush()
    return bytes(surface.get_data())


@pytest.mark.parametrize(("corner", "edge"), cs.ROWS)
def test_every_cell_is_laid_out_without_warnings(corner, edge):
    layout = cs.cell_layout(corner, edge)
    assert layout.warnings == [] and None not in layout.panels
    assert (layout.panels[0].corner, layout.panels[0].edge) == (corner, edge)


@pytest.mark.parametrize(("corner", "edge"), cs.ROWS)
def test_a_collapsed_corner_panel_draws_the_plain_frame(corner, edge):
    shapes = [shape_for(p) for p in cs.cell_layout(corner, edge).panels]
    panels = [(s.edge, s.pos, s.length, s.depth, s.depth) for s in shapes[1:]]
    assert all(isinstance(s, PanelShape) for s in shapes[1:])
    w, h = cs.CELL
    plain = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(plain)
    cr.set_source_rgb(0.55, 0.6, 0.65)
    cr.paint()
    scene = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cs.draw_scene(cairo.Context(scene), w, h, cs.THICKNESS, cs.RADIUS, panels, cs.MASS)
    cr.set_source_surface(scene, 0, 0)
    cr.paint()
    assert _bytes(cs.render_cell(corner, edge, 0.0, False)) == _bytes(plain)
    assert _bytes(cs.render_cell(corner, edge, 1.0, False)) != _bytes(plain)


def test_main_writes_the_sheet(tmp_path, capsys):
    out = tmp_path / "corners.png"
    assert cs.main(["--out", str(out), "--effects"]) == 0
    w, h = cs.CELL
    expected = (
        (w + 2 * cs.PAD) * len(cs.FRACTIONS) * cs.ZOOM,
        (h + 2 * cs.PAD) * len(cs.ROWS) * cs.ZOOM,
    )
    png = cairo.ImageSurface.create_from_png(str(out))
    assert (png.get_width(), png.get_height()) == expected == (4464, 4992)
    assert capsys.readouterr().out == f"wrote {out} (4464x4992)\n"


def test_main_reports_an_unwritable_path(tmp_path, capsys):
    assert cs.main(["--out", str(tmp_path / "missing" / "x.png")]) == 2
    assert "corner_sheet: cannot write" in capsys.readouterr().err
```

- [ ] **Step 2: Run them to see them fail**

Run: `scripts/py -m pytest -q tests/test_corner_sheet.py`
Expected: FAIL at import: `ImportError: cannot import name 'corner_sheet' from 'shell.canvas'`.

- [ ] **Step 3: Implement**

Create `shell/canvas/corner_sheet.py`:

```python
"""Review sheet for corner panels (spec 19): the one union outline with a corner panel in each
corner, opening from each of the corner's two edges, at several collapse fractions, next to
edge panels placed by the layout resolver right beside it. Pure cairo; no shell, no GTK.

`python -m shell.canvas.corner_sheet --out FILE.png [--effects]` writes the sheet: one row per
(corner, opening edge) in the order of ROWS, one column per fraction in FRACTIONS (the corner
panel's depth / full depth; the edge panels stay extended), each cell a CELL-sized monitor
drawn by the real draw_scene on a grey desktop, enlarged ZOOM times without smoothing.
"""

from __future__ import annotations

import sys

import cairo

from shell.canvas.effects import draw_scene
from shell.canvas.scene import CornerShape, PanelShape, shape_for
from shell.panel_layout import AXIS_START, Layout, layout_monitor
from shell.panel_spec import CornerRequest, PanelRequest

ROWS = [
    (corner, edge)
    for corner in ("top-left", "top-right", "bottom-left", "bottom-right")
    for edge in corner.split("-")
]
FRACTIONS = (0.0, 0.05, 0.15, 0.3, 0.6, 1.0)
CELL = (360, 300)
THICKNESS, RADIUS, GAP = 10, 14, 8
ALONG, DEPTH = 120, 80  # the corner panel: px along its edge from the corner, px past the band
PAD, ZOOM = 6, 2
MASS = (0x0B / 255, 0x0C / 255, 0x0D / 255, 1.0)  # the default frame colour
BORDER = (2.0, (0x8F / 255, 0xD3 / 255, 0xB6 / 255, 1.0))  # the defaults once enabled
SHADOW = (50.0, (0.0, 0.0, 0.0, 0.5))


def _toward(corner: str, edge: str) -> str:
    """The align slot of `edge` nearest `corner`."""
    return "start" if AXIS_START[edge] == corner else "end"  # type: ignore[index]


def cell_layout(corner: str, edge: str) -> Layout:
    """The cell's corner panel plus one edge panel on each of its two edges, aligned towards
    it so they sit as close as the resolver allows."""
    side = next(e for e in corner.split("-") if e != edge)
    across = THICKNESS + DEPTH
    width, height = (ALONG, across) if edge in ("top", "bottom") else (across, ALONG)
    requests = [
        CornerRequest("corner", corner, edge, width, height, "extended", "corner"),
        _beside("next", edge, _toward(corner, edge), 80, 40),
        _beside("side", side, _toward(corner, side), 60, 30),
    ]
    return layout_monitor(requests, *CELL, THICKNESS, RADIUS, GAP, where=f"{corner}/{edge}")


def _beside(name: str, edge: str, align: str, length: int, depth: int) -> PanelRequest:
    return PanelRequest(
        widget=name,
        edge=edge,
        align=align,
        offset=0,
        pos=None,
        order=0,
        length=length,
        min_length=None,
        max_length=None,
        depth=depth,
        state="extended",
        label=name,
        fallback_length=length,
    )


def render_cell(corner: str, edge: str, fraction: float, effects: bool) -> cairo.ImageSurface:
    """One cell: the desktop grey, then the scene drawn by draw_scene."""
    w, h = CELL
    shapes = [shape_for(p) for p in cell_layout(corner, edge).panels if p is not None]
    panels = [
        (s.edge, s.pos, s.length, s.depth, s.depth) for s in shapes if isinstance(s, PanelShape)
    ]
    corners = [
        (s.corner, s.edge, s.along, s.depth, fraction * s.depth)
        for s in shapes
        if isinstance(s, CornerShape)
    ]
    scene = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    draw_scene(
        cairo.Context(scene),
        w,
        h,
        THICKNESS,
        RADIUS,
        panels,
        MASS,
        border=BORDER if effects else None,
        shadow=SHADOW if effects else None,
        corners=corners,
    )
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(out)
    cr.set_source_rgb(0.55, 0.6, 0.65)  # a mid-grey desktop
    cr.paint()
    cr.set_source_surface(scene, 0, 0)
    cr.paint()
    return out


def render_sheet(path: str, effects: bool = False) -> tuple[int, int]:
    w, h = CELL
    step_x, step_y = w + 2 * PAD, h + 2 * PAD
    small = cairo.ImageSurface(cairo.FORMAT_ARGB32, step_x * len(FRACTIONS), step_y * len(ROWS))
    cr = cairo.Context(small)
    cr.set_source_rgb(1, 1, 1)
    cr.paint()
    for row, (corner, edge) in enumerate(ROWS):
        for col, fraction in enumerate(FRACTIONS):
            cr.set_source_surface(
                render_cell(corner, edge, fraction, effects),
                col * step_x + PAD,
                row * step_y + PAD,
            )
            cr.paint()
    big = cairo.ImageSurface(
        cairo.FORMAT_ARGB32, small.get_width() * ZOOM, small.get_height() * ZOOM
    )
    out = cairo.Context(big)
    out.scale(ZOOM, ZOOM)
    out.set_source_surface(small, 0, 0)
    out.get_source().set_filter(cairo.FILTER_NEAREST)
    out.paint()
    big.write_to_png(path)
    return big.get_width(), big.get_height()


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        prog="python -m shell.canvas.corner_sheet",
        description="Render corner panels in every corner at several collapse fractions.",
    )
    p.add_argument("--out", required=True, help="output PNG path")
    p.add_argument("--effects", action="store_true", help="with the border and the shadow on")
    args = p.parse_args(argv)
    try:
        w, h = render_sheet(args.out, args.effects)
    except (OSError, cairo.Error) as exc:  # cairo raises its own error types
        print(f"corner_sheet: cannot write {args.out}: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {args.out} ({w}x{h})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run them to see them pass**

Run: `scripts/py -m pytest -q tests/test_corner_sheet.py`
Expected: `18 passed`.

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `1396 passed`.

```bash
git add shell/canvas/corner_sheet.py tests/test_corner_sheet.py
git commit -m "feat(canvas): corner panel review sheet for Gate A" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: GATE A (Phil): the outline in every corner, on review sheets (no shell)

**Files:** none (the sheets are written to `/tmp`, never committed).

**Interfaces:**
- Consumes: `shell.canvas.corner_sheet.main` (Task 7). No code changes.

This gate needs no running shell and no monitor choice: it is two PNG files. The implementer (a subagent may) runs Step 1; Phil looks at the pictures.

- [ ] **Step 1: Render the sheets**

```bash
scripts/py -m shell.canvas.corner_sheet --out /tmp/edge-corners.png
scripts/py -m shell.canvas.corner_sheet --out /tmp/edge-corners-fx.png --effects
```
Expected: `wrote /tmp/edge-corners.png (4464x4992)` and `wrote /tmp/edge-corners-fx.png (4464x4992)`.

- [ ] **Step 2: GATE A (Phil)**

Open `/tmp/edge-corners.png` (for example `gwenview /tmp/edge-corners.png`). It is enlarged 2x without smoothing. Each cell is a 360 x 300 px "monitor" with the default 10 px frame and 14 px corners:
- the dark mass is the frame plus panels; the grey is the desktop;
- each cell has a corner panel 120 px along its edge and 80 px deep at full extension, plus two small edge panels the layout placed as close to it as the rules allow: one on the edge the corner panel opens from, one on the other edge.

Rows, top to bottom:
1. top-left, opening from the top edge
2. top-left, opening from the left edge
3. top-right, opening from the top edge
4. top-right, opening from the right edge
5. bottom-left, opening from the bottom edge
6. bottom-left, opening from the left edge
7. bottom-right, opening from the bottom edge
8. bottom-right, opening from the right edge

Columns, left to right: the corner panel at 0, 5, 15, 30, 60 and 100 % of its depth (the edge panels stay fully extended).

1. **Collapsed (column 1)** looks exactly like a plain frame corner with today's rounded corner. No dent, bump or line where the panel will come out.
2. **Opening (columns 2-4):**
   - the corner panel rises out of its edge's band as a flat block;
   - its free corner is rounded and meets its band with a small concave fillet, the S-curve at shallow depth like an edge panel's;
   - the screen corner's rounding slides along the other band with the block's inner edge, keeping its size;
   - no spike, notch, hole or doubled line anywhere.
3. **Extended (columns 5-6):** the block is a rectangle in the corner, fused to both bands. Its two free sides meet the two bands with concave curves: on one side the screen-corner-sized curve, on the other the join-sized fillet. It is not an L.
4. **Neighbours:**
   - the edge panel on the corner panel's own edge sits beside it with a straight piece of frame between their fillets (the 8 px gap);
   - the edge panel on the other edge sits past the lifted corner curve at full depth, so the two never overlap at any column. At full depth (column 6) its fillet starts exactly where the lifted corner curve ends: there is no straight piece of frame between them, a stepped silhouette. That is valid geometry and what this plan builds (decision 10, option A). If Phil wants a straight piece there too, that is option B (the `gap` on the other edge as well): note it; option B's one-line change and its expected numbers (decision 10) then go into Task 6's code and tests, and Task 11's and Gate B's numbers, before Task 9.
5. **Mirroring:** rows 1, 3, 5 and 7 mirror each other, as do rows 2, 4, 6 and 8.
6. **Effects:** open `/tmp/edge-corners-fx.png`. The mint 2 px border runs as one unbroken line around every corner panel, its fillets and the lifted corner curve, and never over the dark mass. The soft shadow follows the same outline, including in columns 2-4.

**On failure:**
- A spike, notch or hole in one row and column: note the row, column and edge. Add that case to `test_a_corner_panel_matches_the_reference_union` (a `(fraction x 80, R, ALONG)` row; the parametrized corner and edge cover the cell) first. It must fail. Then fix the matching branch of `trace_edge` (head, tail, lead or trail) and re-run Task 4's VERIFY, then re-render.
- A neighbour too close or overlapping: add the cell's three requests to `tests/test_corner_layout.py` as a failing case, then fix `corner_clearance` or `layout_corners`.
- A border gap or a shadow seam: compare with `test_the_border_never_touches_the_corner_panels_mass`. A border over the mass is a canvas regression: stop and report.
- Phil prefers another geometry (decision 1's alternatives): stop here. The geometry decision changes Tasks 3-7.

Record Phil's answers for Task 13.

---

### Task 9: `EdgePanel` geometry hooks and the `CornerPanel` window

**Files:**
- Modify: `shell/edge_panel.py`, `tests/test_edge_panel_handle.py` (the stand-in binds the new hook)
- Create: `shell/corner_panel.py`
- Test: `tests/test_corner_panel.py` (new)

**Interfaces:**
- Consumes: Task 3 (`shell.corner`: `anchor`, `surface_size`, `content_rect`, `hit_rect`, `input_rects`); Task 2 (`CornerGeometry`); `EdgePanel` internals (`_hit`, `_look`, `_theme`, `_interaction`, `_content`, `_handle`, `_handle_area`).
- Produces (`shell/edge_panel.py`, behaviour-preserving):
  - `EdgePanel.surface_layout(spec, theme, monitor) -> (anchor, margin, (w, h))`, a classmethod called in `__init__` before the GObject exists;
  - `EdgePanel._input_rects(d) -> list[Rect]`, called by `_update_input_region`.
- Produces (`shell/corner_panel.py`):
  - `place_at(widget, x, y)`;
  - `CornerPanel(EdgePanel)`, which overrides `surface_layout`, `natural_length`, `_input_rects`, `_place_content` and `_place_handle`. Corner widgets subclass it and are registered with `CornerDefaults`.

**Why the overlay placement is absolute.** `EdgePanel` centres the content and the handle in its surface, because the body is centred there (`R` px of surface on each side). A corner panel's body runs from the screen corner, so `CornerPanel` places both at exact surface coordinates from `shell.corner`: start-aligned, offset by the start and top margins.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_corner_panel.py`:

```python
"""CornerPanel (spec 19) and EdgePanel's geometry hooks, called on stand-ins (no window)."""

from types import SimpleNamespace

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import shell.corner_panel as cp  # noqa: E402
import shell.edge_panel as ep  # noqa: E402
from shell import handle as hd  # noqa: E402
from shell.panel_spec import CornerGeometry, HandleSpec, Interaction, PanelGeometry  # noqa: E402
from tests.test_edge_panel_handle import FakeHandleWidget, rects_of  # noqa: E402

MONITOR = SimpleNamespace(get_geometry=lambda: SimpleNamespace(width=1920, height=1080))
BOX = CornerGeometry("box", "bottom-left", "bottom", 300, 290, 380, "extended", "box")


def stub(make_config, spec=BOX, interaction=None, handle=None, d=0.0):
    theme = make_config().theme
    interaction = interaction or Interaction()
    handle = handle or HandleSpec()
    s = SimpleNamespace(
        spec=spec,
        _theme=theme,
        _interaction=interaction,
        _look=hd.resolve_handle(handle, interaction, theme),
        _d=d,
        _last_rect=None,
        _handle=FakeHandleWidget(),
        _handle_area=SimpleNamespace(draws=0),
        _content=FakeHandleWidget(),
        regions=[],
    )
    s._handle_area.queue_draw = lambda: setattr(s._handle_area, "draws", s._handle_area.draws + 1)
    s.input_shape_combine_region = s.regions.append
    s._hit = lambda: ep.EdgePanel._hit(s)
    s._input_rects = lambda dd: cp.CornerPanel._input_rects(s, dd)
    return s


def test_a_corner_panel_is_an_edge_panel():
    assert issubclass(cp.CornerPanel, ep.EdgePanel)


def test_the_edge_panel_surface_is_unchanged(make_config):
    dock = PanelGeometry("dock", "bottom", 680, 560, 64, "extended", "dock")
    assert ep.EdgePanel.surface_layout(dock, make_config().theme, MONITOR) == (
        "bottom left",
        "0px 0px 0px 666px",
        (588, 74),
    )


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (BOX, ("bottom left", "0px 0px 0px 0px", (300, 390))),
        (
            CornerGeometry("w", "top-right", "right", 200, 190, 150, "collapsed", "w"),
            ("top right", "0px 0px 0px 0px", (160, 200)),
        ),
    ],
)
def test_the_corner_window_is_a_rectangle_anchored_in_its_corner(make_config, spec, expected):
    assert cp.CornerPanel.surface_layout(spec, make_config().theme, MONITOR) == expected


def test_the_input_region_is_the_body_plus_the_hover_zone(make_config):
    s = stub(make_config)
    ep.EdgePanel._update_input_region(s, 0.0)
    assert rects_of(s.regions[-1]) == [(0, 364, 300, 26)]
    ep.EdgePanel._update_input_region(s, 380.0)
    assert rects_of(s.regions[-1]) == [(0, 0, 300, 390)]


def test_without_hover_a_collapsed_corner_panel_takes_only_the_hit_target(make_config):
    s = stub(make_config, interaction=Interaction(hover=False))
    ep.EdgePanel._update_input_region(s, 0.0)
    assert rects_of(s.regions[-1]) == [(133, 376, 44, 14)]


def test_with_every_interaction_off_it_is_click_through(make_config):
    s = stub(make_config, interaction=Interaction(False, False, False))
    ep.EdgePanel._update_input_region(s, 0.0)
    assert rects_of(s.regions[-1]) == []


def test_the_content_sits_past_both_frame_bands(make_config):
    s = stub(make_config)
    cp.CornerPanel._place_content(s)
    assert s._content.set == {
        "size_request": (290, 380),
        "halign": (cp.Gtk.Align.START,),
        "valign": (cp.Gtk.Align.START,),
        "margin_start": (10,),
        "margin_top": (0,),
        "margin_end": (0,),
        "margin_bottom": (0,),
    }


@pytest.mark.parametrize(
    ("d", "offset", "x", "y"),
    [(0.0, 0, 133, 376), (380.0, 0, 133, 0), (100.0, 30, 163, 280), (0.0, 9999, 256, 376)],
)
def test_the_handle_rides_the_body_edge_centred_past_the_band(make_config, d, offset, x, y):
    s = stub(make_config, handle=HandleSpec(offset=offset))
    cp.CornerPanel._place_handle(s, d)
    assert (s._handle.set["margin_start"], s._handle.set["margin_top"]) == ((x,), (y,))
    assert s._handle.set["halign"] == (cp.Gtk.Align.START,)
    assert s._handle_area.draws == 1


def test_the_handle_size_follows_the_opening_edge(make_config):
    s = stub(make_config)
    ep.EdgePanel._size_handle(s)
    assert s._handle.set["size_request"] == (44, 14)
    side = CornerGeometry("w", "top-right", "right", 200, 190, 150, "extended", "w")
    s = stub(make_config, spec=side)
    ep.EdgePanel._size_handle(s)
    assert s._handle.set["size_request"] == (14, 44)


def test_corner_panels_report_no_content_length(make_config):
    assert cp.CornerPanel.natural_length(stub(make_config)) == 290
```

- [ ] **Step 2: Run them to see them fail**

Run: `scripts/py -m pytest -q tests/test_corner_panel.py`
Expected: FAIL at import: `ModuleNotFoundError: No module named 'shell.corner_panel'` (it skips only where `gi` or Fabric is missing).

- [ ] **Step 3: Add the hooks to `EdgePanel`**

Apply to `shell/edge_panel.py`:

```diff
--- a/shell/edge_panel.py
+++ b/shell/edge_panel.py
@@ -92,12 +92,8 @@ class EdgePanel(WaylandWindow):
         change later in place (set_handle)."""
         # resolved before the window exists: a bad look fails without leaving a half-built window
         look = hd.resolve_handle(handle, interaction, theme)
-        t, r = theme.thickness, theme.radius
-        mon = monitor.get_geometry()
-        extent = mon.width if geometry.is_horizontal(spec.edge) else mon.height
-        anchor, margin = geometry.anchor_and_margin(
-            spec.edge, spec.pos, spec.length + 2 * r, r, extent
-        )
+        # a classmethod: the GObject is not initialised yet (CornerPanel overrides it)
+        anchor, margin, size = type(self).surface_layout(spec, theme, monitor)
         super().__init__(
             layer="top",
             anchor=anchor,
@@ -146,8 +142,7 @@ class EdgePanel(WaylandWindow):
         self.add(Overlay(child=Box(name="panel-base"), overlays=[self._content, self._handle]))
 
         # Allocated once at full size; animation never resizes the layer surface.
-        w, h = geometry.surface_size(spec.edge, spec.length, spec.depth, t, r)
-        self.set_size_request(w, h)
+        self.set_size_request(*size)
         self._place_content()
 
         self.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
@@ -165,6 +160,21 @@ class EdgePanel(WaylandWindow):
     def build_content(self) -> Gtk.Widget:
         return Box()
 
+    @classmethod
+    def surface_layout(
+        cls, spec: PanelGeometry, theme: Theme, monitor
+    ) -> tuple[str, str, tuple[int, int]]:
+        """Layer-shell anchor, margin and the surface size (allocated once, fully extended).
+        An edge panel: anchored to its edge, `(length + 2R) x (T + depth)`, moved along the
+        edge by the margin (geometry.anchor_and_margin)."""
+        t, r = theme.thickness, theme.radius
+        mon = monitor.get_geometry()
+        extent = mon.width if geometry.is_horizontal(spec.edge) else mon.height
+        anchor, margin = geometry.anchor_and_margin(
+            spec.edge, spec.pos, spec.length + 2 * r, r, extent
+        )
+        return anchor, margin, geometry.surface_size(spec.edge, spec.length, spec.depth, t, r)
+
     # ---- public ----------------------------------------------------------------
     def toggle(self, *_) -> None:
         self._extended = not self._extended
@@ -292,26 +302,28 @@ class EdgePanel(WaylandWindow):
     def _update_input_region(self, d: float) -> None:
         # The body (plus an invisible hover zone while collapsed, or only the handle's hit
         # target when hover is off) takes input: shell.handle.input_rects.
-        t, s = self._theme, self.spec
-        rects = tuple(
-            hd.input_rects(
-                s.edge,
-                s.length,
-                s.depth,
-                d,
-                t.thickness,
-                t.radius,
-                t.hover_zone,
-                self._interaction,
-                self._hit(),
-                self._look.offset,
-            )
-        )
+        rects = tuple(self._input_rects(d))
         if rects == self._last_rect:
             return
         self._last_rect = rects
         self.input_shape_combine_region(cairo.Region([cairo.RectangleInt(*r) for r in rects]))
 
+    def _input_rects(self, d: float) -> list[tuple[int, int, int, int]]:
+        """The input region at depth `d` in surface px (CornerPanel overrides it)."""
+        t, s = self._theme, self.spec
+        return hd.input_rects(
+            s.edge,
+            s.length,
+            s.depth,
+            d,
+            t.thickness,
+            t.radius,
+            t.hover_zone,
+            self._interaction,
+            self._hit(),
+            self._look.offset,
+        )
+
     # ---- handle ----------------------------------------------------------------
     def _build_handle(self) -> Button:
         """The hit target: a Button (click, keyboard, accessible name) whose child draws the
```

Bind the hook in the existing stand-in (`tests/test_edge_panel_handle.py`, function `stub`), right after the `_hit` line:

```diff
--- a/tests/test_edge_panel_handle.py
+++ b/tests/test_edge_panel_handle.py
@@ -64,6 +64,7 @@ def stub(make_config, edge="bottom", interaction=ALL, handle=None, **extra):
     s._handle_area.queue_draw = lambda: setattr(s._handle_area, "draws", s._handle_area.draws + 1)
     s.input_shape_combine_region = s.regions.append
     s._hit = lambda: ep.EdgePanel._hit(s)
+    s._input_rects = lambda d: ep.EdgePanel._input_rects(s, d)
     for key, value in extra.items():
         setattr(s, key, value)
     return s
```

- [ ] **Step 4: Create `CornerPanel`**

Create `shell/corner_panel.py`:

```python
"""CornerPanel: the content, handle and input window of one corner panel (spec 19).

The window is a plain RECTANGLE anchored in a screen corner (two layer-shell anchors, zero
margins), exactly the extended body: `along` x (T + depth) px. It is not an L: its surface,
body, content box and input region are rectangles; only the shape canvas's outline curves
where the body's free sides meet the two frame bands. Everything else (handle look,
interactions, hover peek, click, drag, fade, input-region upkeep, the delayed re-raise) is
EdgePanel's, running on the edge the panel opens from (`spec.edge`). The geometry comes from
the pure shell.corner."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from shell import corner as cn
from shell.config.models import Theme
from shell.edge_panel import EdgePanel
from shell.panel_spec import CornerGeometry


def place_at(widget: Gtk.Widget, x: int, y: int) -> None:
    """Put an overlay child at (x, y) of the surface: start-aligned, offset by its margins."""
    widget.set_halign(Gtk.Align.START)
    widget.set_valign(Gtk.Align.START)
    widget.set_margin_start(x)
    widget.set_margin_top(y)
    widget.set_margin_end(0)
    widget.set_margin_bottom(0)


class CornerPanel(EdgePanel):
    """Base class for corner widgets: register them with CornerDefaults (shell.registry)."""

    spec: CornerGeometry

    @classmethod
    def surface_layout(
        cls, spec: CornerGeometry, theme: Theme, monitor
    ) -> tuple[str, str, tuple[int, int]]:
        """Anchored to the corner's two screen edges, no margins, the extended body's size."""
        size = cn.surface_size(spec.edge, spec.along, spec.depth, theme.thickness)
        return cn.anchor(spec.corner), "0px 0px 0px 0px", size

    def natural_length(self) -> int:
        """Corner panels have no "content" length; MonitorShell never measures them."""
        return self.spec.length

    def _input_rects(self, d: float) -> list[tuple[int, int, int, int]]:
        t, s = self._theme, self.spec
        return cn.input_rects(
            s.corner,
            s.edge,
            s.along,
            s.depth,
            d,
            t.thickness,
            t.hover_zone,
            self._interaction,
            self._hit(),
            self._look.offset,
        )

    def _place_content(self) -> None:
        s = self.spec
        x, y, w, h = cn.content_rect(s.corner, s.edge, s.along, s.depth, self._theme.thickness)
        self._content.set_size_request(w, h)
        place_at(self._content, x, y)

    def _place_handle(self, d: float) -> None:
        s = self.spec
        x, y, _w, _h = cn.hit_rect(
            s.corner,
            s.edge,
            s.along,
            s.depth,
            d,
            self._theme.thickness,
            self._hit(),
            self._look.offset,
        )
        place_at(self._handle, x, y)
        self._handle_area.queue_draw()  # the shape moves with the body's inner edge
```

- [ ] **Step 5: Run the tests**

Run: `scripts/py -m pytest -q tests/test_corner_panel.py tests/test_edge_panel_handle.py tests/test_edge_panel_drag.py`
Expected: all pass (`test_corner_panel.py`: 14). The Plan 3 handle tests pass unchanged apart from the one stand-in line.

- [ ] **Step 6: VERIFY and commit**

Run VERIFY. Expected: `1410 passed`.

```bash
git add shell/edge_panel.py shell/corner_panel.py tests/test_edge_panel_handle.py tests/test_corner_panel.py
git commit -m "feat(panel): CornerPanel, a rectangular window anchored in a screen corner" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 10: `MonitorShell` builds corner panels

**Files:**
- Modify: `shell/monitors.py`
- Test: `tests/test_monitor_shell.py` (9 tests appended)

**Interfaces:**
- Consumes: Task 5 (`shape_for`); Task 6 (`layout_monitor` with corner requests); Task 2 (`CornerGeometry`, `CornerRequest`); the existing `build` fixture and `FakeWindow`, `FakeCanvas` and `FakeMonitor` in `tests/test_monitor_shell.py`; `corner_registry` (Task 2).
- Produces:
  - `MonitorShell._new_panel(index, geo: PanelGeometry | CornerGeometry, theme, raise_later)` adds `shape_for(geo)` to the canvas;
  - `_to_measure` skips corner requests (no "content" length).

  Everything else (rebuild on a geometry change, in-place `set_handle` / `set_state`, raise, close) already works on both kinds, because `CornerGeometry` and `CornerRequest` are frozen dataclasses with `state`, `handle` and `interaction`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_monitor_shell.py`:

```diff
--- a/tests/test_monitor_shell.py
+++ b/tests/test_monitor_shell.py
@@ -843,3 +843,98 @@ def test_only_building_a_panel_logs_building_panel(build, make_config, caplog):
         [Change("panel-rebuild", "HDMI-A-1", 0)],
     )
     assert "building panel 0 (dock) on HDMI-A-1" in caplog.text
+
+
+# ---- corner panels (spec 19) ------------------------------------------------------------
+
+
+def test_a_corner_panel_gets_its_geometry_a_corner_shape_and_a_depth_callback(
+    build, corner_registry
+):
+    from shell.canvas.scene import CornerShape
+    from shell.panel_spec import CornerGeometry
+
+    shell, _, _ = build(edge({"widget": "box"}))
+    (box,) = shell.panels
+    assert box.args[0] == CornerGeometry(
+        "box", "bottom-left", "bottom", 300, 290, 380, "extended", "box"
+    )
+    assert list(shell.canvas.shapes.values()) == [CornerShape("bottom-left", "bottom", 300, 380)]
+    box.kwargs["on_depth"](40.0)
+    assert shell.canvas.depths == [(box.scene_key, 40.0)]
+
+
+def test_edge_panels_keep_clear_of_a_corner_panel(build, corner_registry):
+    shell, _, _ = build(edge({"widget": "box"}, {"widget": "dock", "align": "start"}))
+    assert shell.panels[1].args[0].pos == 336  # 300 + 14 + 8 + 14
+    assert shell.layout_warnings == []
+
+
+def test_a_second_corner_panel_in_one_corner_is_hidden_and_reported(build, corner_registry):
+    shell, _, _ = build(edge({"widget": "box"}, {"widget": "box", "edge": "left"}))
+    assert shell.panels[1] is None and len(shell.canvas.shapes) == 1
+    assert "the bottom-left corner already holds" in shell.layout_warnings[0]
+
+
+def test_corner_panels_are_raised_like_edge_panels(build, corner_registry):
+    shell, _, timers = build(edge({"widget": "box"}))
+    for _, fn, a in timers:
+        fn(*a)
+    assert shell.panels[0].raised == 2
+
+
+def test_corner_panels_are_never_measured(build, corner_registry):
+    shell, _, _ = build(edge({"widget": "box"}, {"widget": "dock", "length": "content"}))
+    box, dock = shell.panels
+    shell.test_idles[-1]()  # the idle measurement
+    assert dock.measured == 1 and box.measured == 0
+    assert shell.panels[0] is box  # a "content" neighbour's measurement never rebuilds it
+
+
+def test_a_corner_size_change_rebuilds_only_that_panel(build, corner_registry, make_config):
+    shell, _, _ = build(edge({"widget": "box"}, {"widget": "clock"}))
+    box, clock = shell.panels
+    shell.apply(
+        make_config(monitors=edge({"widget": "box", "width": 320}, {"widget": "clock"})),
+        [Change("panel-rebuild", "HDMI-A-1", 0)],
+    )
+    assert box.destroyed and shell.panels[0].args[0].along == 320
+    assert shell.panels[1] is clock and not clock.destroyed
+
+
+def test_a_corner_handle_change_is_applied_in_place(build, corner_registry, make_config):
+    from shell.panel_spec import HandleSpec, Interaction
+
+    shell, _, timers = build(edge({"widget": "box"}))
+    (box,) = shell.panels
+    before = len(timers)
+    shell.apply(
+        make_config(monitors=edge({"widget": "box", "handle": {"shape": "bar"}})),
+        [Change("panel-handle", "HDMI-A-1", 0)],
+    )
+    assert shell.panels == [box] and not box.destroyed
+    assert box.handles == [(HandleSpec(shape="bar"), Interaction())]
+    assert len(timers) == before
+
+
+def test_a_corner_state_change_retargets_in_place(build, corner_registry, make_config):
+    shell, _, _ = build(edge({"widget": "box"}))
+    (box,) = shell.panels
+    shell.apply(
+        make_config(monitors=edge({"widget": "box", "state": "collapsed"})),
+        [Change("panel-state", "HDMI-A-1", 0)],
+    )
+    assert shell.panels == [box] and box.states == ["collapsed"]
+
+
+def test_a_smaller_monitor_shrinks_the_corner_panel(build, corner_registry):
+    monitor = FakeMonitor()
+    shell, _, timers = build(edge({"widget": "box"}), monitor=monitor)
+    (box,) = shell.panels
+    monitor.width, monitor.height = 320, 720
+    ((_signal, handler),) = monitor.handlers.values()
+    handler(monitor, None)
+    relayout = [t for t in timers if t[0] == mon_mod.RELAYOUT_DELAY_MS][-1]
+    assert relayout[1]() is False
+    assert box.destroyed and shell.panels[0].args[0].along == 282  # 320 - (10 + 14) - 14
+    assert "width 300 px does not fit the bottom edge; shrunk to 282" in shell.layout_warnings[0]
```

- [ ] **Step 2: Run them to see them fail**

Run: `scripts/py -m pytest -q tests/test_monitor_shell.py -k corner`
Expected: FAIL. `_new_panel` builds a `PanelShape` from a `CornerGeometry`: `AttributeError: 'CornerGeometry' object has no attribute 'pos'`.

- [ ] **Step 3: Implement**

Apply to `shell/monitors.py`:

```diff
--- a/shell/monitors.py
+++ b/shell/monitors.py
@@ -16,14 +16,21 @@ from gi.repository import Gdk, GLib, GtkLayerShell
 
 from shell import geometry
 from shell.canvas.canvas import ShapeCanvas
-from shell.canvas.scene import PanelShape
+from shell.canvas.scene import shape_for
 from shell.config.diff import Change
 from shell.config.models import Config
 from shell.edge_panel import EdgePanel
 from shell.frame import EDGES, FrameEdge
 from shell.outputs import match_geometries, parse_kscreen, read_kscreen_json
 from shell.panel_layout import Layout, layout_monitor
-from shell.panel_spec import HandleSpec, Interaction, PanelGeometry, PanelRequest
+from shell.panel_spec import (
+    CornerGeometry,
+    CornerRequest,
+    HandleSpec,
+    Interaction,
+    PanelGeometry,
+    PanelRequest,
+)
 from shell.registry import requests_for, widget_class
 from shell.theme import scope_class
 
@@ -123,14 +130,15 @@ class MonitorShell:
         self.strips: list = []  # the 4 zone strips (also in `windows`)
         # Config order; None = not shown (rejected by shell.panel_layout, see layout_warnings).
         self.panels: list[EdgePanel | None] = []
-        self._resolved: list[PanelGeometry | None] = []
+        self._resolved: list[PanelGeometry | CornerGeometry | None] = []
         # Each index's (handle, interaction) as last given to its panel (changed in place).
         self._handles: list[tuple[HandleSpec, Interaction] | None] = []
         self.layout_warnings: list[str] = []
         self._keys = itertools.count()  # scene keys for the canvas
         self._config = config
         self._theme = config.theme_for(name)
-        self._requests: list[PanelRequest] = []  # of the last layout, config order
+        # Of the last layout, config order; corner panels (spec 19) are CornerRequests.
+        self._requests: list[PanelRequest | CornerRequest] = []
         # Measured "content" lengths: index -> ((widget, horizontal), px). Kept across
         # re-layouts; an entry only counts while the same widget sits at that index.
         self._natural: dict[int, tuple[tuple[str, bool], int]] = {}
@@ -240,6 +248,7 @@ class MonitorShell:
             i
             for i, (panel, req) in enumerate(zip(self.panels, self._requests, strict=True))
             if panel is not None
+            and isinstance(req, PanelRequest)  # corner panels have no "content" length
             and req.length == "content"
             and (i in self._remeasure or i not in known)
         ]
@@ -322,10 +331,14 @@ class MonitorShell:
         on_layout will fire after it."""
         return bool(self._measure_id)
 
-    def _new_panel(self, index: int, geo: PanelGeometry, theme, raise_later: bool) -> EdgePanel:
+    def _new_panel(
+        self, index: int, geo: PanelGeometry | CornerGeometry, theme, raise_later: bool
+    ) -> EdgePanel:
+        """Build one panel window (edge or corner: a CornerPanel is an EdgePanel) and its
+        canvas shape."""
         self._remeasure.add(index)  # measured when idle if it is a "content" panel
         key = next(self._keys)
-        self.canvas.add_panel(key, PanelShape(geo.edge, geo.pos, geo.length, geo.depth))
+        self.canvas.add_panel(key, shape_for(geo))
         req = self._requests[index]
         log.debug("building panel %d (%s) on %s", index, geo.widget, self.name)
         try:
```

- [ ] **Step 4: Run them to see them pass**

Run: `scripts/py -m pytest -q tests/test_monitor_shell.py`
Expected: `66 passed`.

- [ ] **Step 5: VERIFY and commit**

Run VERIFY. Expected: `1419 passed`.

```bash
git add shell/monitors.py tests/test_monitor_shell.py
git commit -m "feat(monitors): build corner panels with their canvas shape; never measure them" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 11: The `widget_panel` widget, its CSS and the example config

**Files:**
- Create: `widgets/widget_panel.py`, `examples/corner-test.toml`
- Modify: `widgets/__init__.py`, `shell/theme.py`
- Test: `tests/test_widget_panel.py` (new)

**Interfaces:**
- Consumes: Task 9 (`CornerPanel`); Task 2 (`CornerDefaults`, `register`, `widget_kind`); `widgets.clock.format_time`; `services.sysinfo` (`cpu_percent`, `read_cpu_times`, `read_meminfo_percent`).
- Produces:
  - `widgets.widget_panel`: `WidgetPanel` registered as `"widget_panel"` with `CornerDefaults(corner="bottom-left", width=300, height=390, label="widget panel")`;
  - `format_date(now) -> "Wed 14 Oct"`, `stats_lines(cpu, ram) -> ("CPU 12%", "RAM 57%")`, `REFRESH_MS = 1000`, `STATS_EVERY = 2`;
  - the CSS rule `#widget-panel-time { font-size: 32px; font-weight: 500; }`;
  - `examples/corner-test.toml` for Gate B.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_widget_panel.py`:

```python
"""The widget_panel corner widget (spec 19): registration, text and refresh (no window)."""

from datetime import datetime
from types import SimpleNamespace

import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")

import widgets.widget_panel as wp  # noqa: E402
from shell import registry  # noqa: E402
from shell.corner_panel import CornerPanel  # noqa: E402
from shell.panel_spec import CornerDefaults  # noqa: E402


class FakeLabel:
    def __init__(self, text=""):
        self.text, self.sets = text, 0

    def get_label(self):
        return self.text

    def set_label(self, text):
        self.text, self.sets = text, self.sets + 1


def test_it_is_registered_as_the_spec_corner_panel():
    assert registry.widget_class("widget_panel") is wp.WidgetPanel
    assert issubclass(wp.WidgetPanel, CornerPanel)
    assert registry.widget_kind("widget_panel") == "corner"
    assert registry.defaults("widget_panel") == CornerDefaults(
        corner="bottom-left", width=300, height=390, label="widget panel"
    )


def test_date_and_stats_text():
    assert wp.format_date(datetime(2026, 10, 14, 9, 5)) == "Wed 14 Oct"
    assert wp.stats_lines(12.4, 56.6) == ("CPU 12%", "RAM 57%")


def test_refresh_updates_the_time_every_tick_and_the_stats_every_second(monkeypatch):
    monkeypatch.setattr(wp, "datetime", SimpleNamespace(now=lambda: datetime(2026, 10, 14, 9, 5)))
    monkeypatch.setattr(wp, "read_cpu_times", lambda: (100, 50))  # (total, idle) jiffies
    monkeypatch.setattr(wp, "read_meminfo_percent", lambda: 40.0)
    s = SimpleNamespace(
        _destroyed=False,
        _ticks=0,
        _prev=(0, 0),
        _time=FakeLabel(),
        _date=FakeLabel(),
        _cpu=FakeLabel("CPU --%"),
        _mem=FakeLabel("RAM --%"),
    )
    assert wp.WidgetPanel._refresh(s) is True
    assert s._time.sets == 1 and s._cpu.text == "CPU --%"  # stats wait for the second tick
    assert wp.WidgetPanel._refresh(s) is True
    assert s._time.sets == 1  # the same minute: no relayout
    assert (s._cpu.text, s._mem.text) == ("CPU 50%", "RAM 40%")  # (100 - 50) / 100 busy


def test_a_destroyed_panel_stops_refreshing():
    assert wp.WidgetPanel._refresh(SimpleNamespace(_destroyed=True)) is False


def test_destroy_stops_the_timer(monkeypatch):
    removed = []
    monkeypatch.setattr(wp.GLib, "source_remove", removed.append)
    s = SimpleNamespace(_destroyed=False, _repeater_id=7)
    wp.WidgetPanel._on_destroy(s)
    assert s._destroyed and removed == [7] and s._repeater_id == 0
```

- [ ] **Step 2: Run them to see them fail**

Run: `scripts/py -m pytest -q tests/test_widget_panel.py`
Expected: FAIL at import: `ModuleNotFoundError: No module named 'widgets.widget_panel'`.

- [ ] **Step 3: Implement**

Create `widgets/widget_panel.py`:

```python
"""Widget panel: the spec's corner panel (spec 3 and 19) in the bottom-left corner, rising out of
the bottom edge, 300 x 390 px from the corner (both frame bands included): the time, the date,
CPU and RAM in one column. A first corner widget; later widgets can join its column."""

from __future__ import annotations

from datetime import datetime

from fabric.utils import invoke_repeater
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from gi.repository import GLib

from services.sysinfo import cpu_percent, read_cpu_times, read_meminfo_percent
from shell.corner_panel import CornerPanel
from shell.panel_spec import CornerDefaults
from shell.registry import register
from widgets.clock import format_time

REFRESH_MS = 1000  # the minute rolls over within a second of the real change
STATS_EVERY = 2  # CPU and RAM every second tick (the system bar's 2 s)


def format_date(now: datetime) -> str:
    return now.strftime("%a %d %b")


def stats_lines(cpu: float, ram: float) -> tuple[str, str]:
    return f"CPU {cpu:.0f}%", f"RAM {ram:.0f}%"


def _set(label, text: str) -> None:
    if label.get_label() != text:  # avoid a relayout every tick
        label.set_label(text)


@register(
    "widget_panel",
    CornerDefaults(corner="bottom-left", width=300, height=390, label="widget panel"),
)
class WidgetPanel(CornerPanel):
    def build_content(self):
        self._destroyed = False
        self._ticks = 0
        self._prev = read_cpu_times()
        now = datetime.now()
        self._time = Label(name="widget-panel-time", label=format_time(now))
        self._date = Label(style_classes="secondary", label=format_date(now))
        self._cpu = Label(style_classes="secondary", label="CPU --%")
        self._mem = Label(style_classes="secondary", label="RAM --%")
        self._repeater_id = invoke_repeater(REFRESH_MS, self._refresh)
        self.connect("destroy", self._on_destroy)
        return Box(
            name="widget-panel",
            orientation="v",
            spacing=8,
            h_align="center",
            v_align="center",
            children=[self._time, self._date, self._cpu, self._mem],
        )

    def _on_destroy(self, *_args) -> None:
        # Panels are rebuilt on config reload and hot-plug: stop the timer with them.
        self._destroyed = True
        if self._repeater_id:
            GLib.source_remove(self._repeater_id)
            self._repeater_id = 0

    def _refresh(self) -> bool:
        if self._destroyed:
            return False
        now = datetime.now()
        _set(self._time, format_time(now))
        _set(self._date, format_date(now))
        self._ticks += 1
        if self._ticks % STATS_EVERY == 0:
            cur = read_cpu_times()
            cpu, ram = stats_lines(cpu_percent(self._prev, cur), read_meminfo_percent())
            self._prev = cur
            _set(self._cpu, cpu)
            _set(self._mem, ram)
        return True
```

Register it and add its CSS:

```diff
--- a/widgets/__init__.py
+++ b/widgets/__init__.py
@@ -1,3 +1,3 @@
 """Built-in panel widgets. Importing this package registers them."""
 
-from widgets import clock, dock, system_bar  # noqa: F401
+from widgets import clock, dock, system_bar, widget_panel  # noqa: F401
```

```diff
--- a/shell/theme.py
+++ b/shell/theme.py
@@ -51,4 +51,5 @@ window{s} {{ background-color: transparent; }}
 {s} .secondary {{ color: {c["text_secondary"]}; }}
 {s} .active {{ color: {c["accent"]}; }}
 {s} #clock-time {{ font-size: 20px; font-weight: 500; }}
+{s} #widget-panel-time {{ font-size: 32px; font-weight: 500; }}
 """  # noqa: E501
```

`format_date` uses `%a` and `%b`. Python formats them in the C locale unless something calls `locale.setlocale`, which the shell never does, so the test's `"Wed 14 Oct"` holds.

- [ ] **Step 4: Run them to see them pass**

Run: `scripts/py -m pytest -q tests/test_widget_panel.py tests/test_theme.py`
Expected: all pass (`test_widget_panel.py`: 5).

- [ ] **Step 5: Create the example config and check it headless**

Create `examples/corner-test.toml`:

```toml
# Gate B (corner panel plan): corner panels next to edge panels, on HDMI-A-1 only (DP-1 is
# left alone).
#   cp examples/corner-test.toml /tmp/edge-corner.toml
#   scripts/py main.py --config /tmp/edge-corner.toml -v      (edit the copy while it runs)
[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]    # 0: the widget panel: bottom-left, rising out of the bottom edge
widget = "widget_panel"         #    (its defaults: 300 x 390 px from the corner, extended)

[[monitors.HDMI-A-1.panels]]    # 1: dock, bottom centre
widget = "dock"

[[monitors.HDMI-A-1.panels]]    # 2: clock at the start of the bottom edge: right of the widget panel
widget = "clock"
edge = "bottom"
align = "start"

[[monitors.HDMI-A-1.panels]]    # 3: system bar on the left edge, at its end: above the lifted corner
widget = "system_bar"
edge = "left"
align = "end"

[[monitors.HDMI-A-1.panels]]    # 4: a second widget panel, top-right, opening from the right
widget = "widget_panel"         #    edge, collapsed, click only (auto shape: a chevron)
corner = "top-right"
edge = "right"
width = 260
height = 240
state = "collapsed"
interaction.hover = false
interaction.drag = false
```

Check it loads, validates, lays out without warnings and resolves the expected handles. This is headless: it imports the widgets but creates no window.

`scripts/py -c "import widgets; from pathlib import Path; from shell.config.loader import load_config; from shell.registry import requests_for, validate_widgets; from shell.panel_layout import layout_monitor; from shell.handle import resolve_handle; c = load_config(Path('examples/corner-test.toml'), required=True); validate_widgets(c); t = c.theme_for('HDMI-A-1'); R = requests_for(c, 'HDMI-A-1'); L = layout_monitor(R, 1920, 1080, 10, 14, c.layout_for('HDMI-A-1').gap); print([(p.corner, p.edge, p.along, p.depth) if hasattr(p, 'corner') else (p.edge, p.pos, p.length) for p in L.panels], L.warnings); print([resolve_handle(r.handle, r.interaction, t).shape for r in R])"`

Expected:
```
[('bottom-left', 'bottom', 300, 380), ('bottom', 680, 560), ('bottom', 336, 168), ('left', 362, 300), ('top-right', 'right', 240, 250)] []
['dots', 'dots', 'dots', 'dots', 'chevron']
```

The headless canvas run (`scripts/py -m shell.canvas.simulate --config examples/corner-test.toml --frames 120 --elevation 50 --border 2`) ends with `simulated 120 frames at 1920x1080: 114 draws, 1 full`.

- [ ] **Step 6: VERIFY and commit**

Run VERIFY. Expected: `1424 passed`.

```bash
git add widgets/widget_panel.py widgets/__init__.py shell/theme.py examples/corner-test.toml tests/test_widget_panel.py
git commit -m "feat(widgets): widget_panel, the bottom-left corner panel with time, date, CPU and RAM" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 12: GATE B (Phil, HDMI-A-1 only): corner panels live

**Files:** none (the example is from Task 11).

**Interfaces:**
- Consumes: Tasks 1-11; no code changes.

Only Phil runs this gate. The shell is started on HDMI-A-1 only: the example configures `HDMI-A-1` and nothing else, so DP-1 keeps its Plasma panel and is never touched.

- [ ] **Step 1: GATE B (Phil)**

```bash
cp examples/corner-test.toml /tmp/edge-corner.toml
scripts/py main.py --config /tmp/edge-corner.toml -v
```
Edit `/tmp/edge-corner.toml` while it runs; each save applies within about a second. Ctrl+C quits.

1. **Start (decision 1, 4: a rectangle, not an L):**
   - the widget panel fills the bottom-left corner: 300 px wide (left frame band included), its top edge at y = 690 (390 px from the bottom);
   - it is one dark block fused with the left and the bottom frame bands, with no seam;
   - its top-left meets the left band with the screen corner's rounding (moved up to y = 690), and its right side meets the bottom band with a small concave fillet;
   - its content is a centred column: the time (large), the date, `CPU nn%` and `RAM nn%` (the stats appear after 2 s).
2. **Collapse:** click the handle (three dots on the panel's top edge, centred at x ≈ 155).
   - The block sinks into the bottom band in 280 ms and the content fades out at once.
   - The rounded corner slides down the left band to the screen corner.
   - Collapsed, the bottom-left looks like a plain frame corner, with the dots in the bottom band at x ≈ 155.
   - Click again: it rises back and the content fades in.
3. **Hover and drag:**
   - pointer on the bottom band near x 0-300: it peeks 14 px and the dots light up;
   - press the dots and drag up: the block follows the pointer; release above half way and it opens, below and it closes.
4. **Neighbours (decision 3):**
   - the bottom-start clock sits right of the widget panel, starting at x = 336 (two fillets and an 8 px straight piece of frame between them);
   - the system bar on the left edge ends 404 + 14 px above the bottom (y 362-662), clear of the rounded corner even when the widget panel is fully up;
   - the dock is centred as before;
   - nothing moves while the widget panel animates.
5. **Top-right panel (opening from the right, click only):**
   - collapsed at start, a chevron in the right band at y ≈ 125;
   - hovering the band does nothing (hover off); dragging does nothing (drag off);
   - click: it opens leftwards to x = 1660 (260 px from the right edge, band included), 240 px tall from the top, and the top-right corner's rounding slides left along the top band with the panel's left side;
   - click again: it closes.
6. **Click-through:**
   - with the widget panel collapsed, click the desktop just above the bottom band at x ≈ 600 (outside the dock): the desktop gets it;
   - with it extended, clicks just right of x = 300 or just above y = 690 reach the desktop: the window is only the 300 x 390 rectangle.
7. **Effects:** add at the top of the file `[theme.border]` / `enabled = true` and `[theme.shadow]` / `enabled = true`, and save (`restyle`, no `building panel`).
   - The border runs unbroken around both corner panels, the lifted corner rounding and the fillets.
   - The shadow follows them.
   - Toggle the widget panel 5 times and drag it: no trails or stale pixels along the left band or the bottom band.
   - Remove both and save.
8. **Reload in place (decision 6):**
   - set panel 0's `handle.shape = "bar"` and save: the log shows `config reloaded: 1 change(s): panel-handle` and NO `building panel` line after it;
   - set `state = "collapsed"` and save: `panel-state`, it sinks;
   - set `width = 360` and save: `panel-rebuild`, with `building panel 0 (widget_panel)` and `building panel 2 (clock)` (the clock moves to x = 396), and no `building panel 1`;
   - undo all three.
9. **Invalid keys:**
   - add `align = "end"` to panel 0 and save: a "Config not applied" notification names `monitors.HDMI-A-1.panels[0].align: widget_panel is a corner panel ...`, and the previous layout stays; undo;
   - add `edge = "top"` to panel 0: the notification says `'top' is not an edge of the bottom-left corner`; undo;
   - add `width = 300` to panel 1 (the dock): `dock is an edge panel; corner, width and height only apply to corner panels`; undo.
10. **Same corner:** append a sixth entry `widget = "widget_panel"` / `edge = "left"` and save. A "Panels adjusted" notification says `monitors.HDMI-A-1.panels.5 (widget_panel): the bottom-left corner already holds monitors.HDMI-A-1.panels.0 (widget_panel); not shown`. Remove it.
11. **Resolution change (optional, as at Plan 2 Gate B):** switch HDMI-A-1 to 1280x720 in System Settings.
    - The log shows `re-laying out HDMI-A-1 for 1280x720`.
    - The widget panel keeps its 300 x 390 size (it fits), and the top-right panel too.
    - The system bar no longer fits beside the lifted corner (the left edge is 720 px; 720 - 404 - 14 - 24 - 14 = 264 px remain): a "Panels adjusted" notification says `monitors.HDMI-A-1.panels.3 (system_bar): length 300 px does not fit the left edge; shrunk to 264`, and the bar sits at the top of the left edge, pos 38 (y 38-302).
    - Switch back to 1920x1080: the bar is 300 px again at y 362-662, with no warning.
12. **Stacking:** quit, start again, wait 10 s. Both corner panels' handles and the widget panel's content are visible (the delayed re-raise covers corner panels too).
13. **Measurement:** `scripts/py main.py --config /tmp/edge-corner.toml --stats 10` (10 s, every panel toggling): fps while animating >= 55 and canvas damaged-draw p95 <= 8 ms (Plan 1-3 targets). Copy the printed report.
14. The `-v` logs have no errors (the warnings of items 9, 10 and 11 are expected: item 11's is the system bar's `shrunk to 264` at 1280x720).

**On failure:**
- **Items 1-2 the content or the handle in the wrong place.** Compare the live position with `cn.content_rect` / `cn.hit_rect` (Task 3) and `test_the_handle_rides_the_body_edge_centred_past_the_band` (Task 9). The margins must be set with start alignment.
- **The Overlay ignores the start/top margins of an overlay child.** Fall back to a `Gtk.Fixed` base in `CornerPanel` (put content and handle with `fixed.put(widget, x, y)`, `fixed.move` in `_place_handle`). Add a stand-in test for the `move` calls first.
- **Item 1 the outline wrong but Gate A was right.** Print `shell.canvas.scene.outline_corners()` (add a temporary `log.debug` in `ShapeCanvas.add_panel`) and compare with `cell_layout`. Stop and report if the scene holds the right shape.
- **Item 3 a drag in the wrong direction.** `panel_state.drag_depth` uses the opening edge (`spec.edge`): check `CornerGeometry.edge` with the Task 11 Step 5 check.
- **Item 4 or 10 wrong positions or warnings.** Reproduce headless with the Task 11 Step 5 check on `/tmp/edge-corner.toml`, then add a failing case to `tests/test_corner_layout.py` before fixing.
- **Item 6 clicks blocked outside the rectangle.** Print the region (temporary `log.debug` of `rects` in `_update_input_region`) and compare with `test_the_input_region_is_the_body_plus_the_hover_zone`.
- **Item 7 trails.** Add the failing depths to `test_random_corner_depth_jumps_never_leave_stale_pixels` first (`corner_box` too small).
- **Item 8 a `building panel` line after a handle-only change.** Check `test_reload_kinds_for_corner_panels` and `test_a_corner_handle_change_is_applied_in_place`.
- **Item 12 corner panels hidden with the raise on.** Stop and report (a stacking regression, not corner code).
- **Item 13 below target.** Run `--stats 10` on `examples/panels-test.toml` for comparison; if only the corner example is slower, profile `corner_box` damage sizes with `scripts/py -m shell.canvas.simulate --config examples/corner-test.toml --elevation 50`.

Write down each item's result; Task 13 records them.

---

### Task 13: Docs: README and spec

**Files:**
- Modify: `README.md`, `docs/superpowers/specs/2026-10-11-edge-shell-design.md`

**Interfaces:**
- Consumes: the decisions above and the Gate A and Gate B results (Tasks 8 and 12). No code.

- [ ] **Step 1: README**

In `README.md`:
- **Plan links.** Under the plan links, add `- [Corner panel plan](docs/superpowers/plans/2026-10-14-corner-panel.md)`. The handle plan link is missing as well: add `- [Handle customization plan](docs/superpowers/plans/2026-10-13-handle-customization.md)` before it.
- **Features.** Add after the `Panels:` bullet: `- Corner panels: a rectangular panel in a screen corner, joined to both frame bands (`widget_panel`: time, date, CPU and RAM in the bottom-left corner).`
- **Run.** Add `scripts/py main.py --config examples/corner-test.toml -v      # corner panels next to edge panels`.
- **Configure.** Add this section after the paragraph on the system bar's old `pos` default:

````markdown
### Corner panels

A corner panel is a rectangle in a screen corner, joined to the frame along both of its
corner's edges. It opens and closes like an edge panel, out of one of those edges:

```toml
[[monitors.HDMI-A-1.panels]]
widget = "widget_panel"      # a corner widget (registered with CornerDefaults)
corner = "bottom-left"       # top-left | top-right | bottom-left | bottom-right
edge = "bottom"              # the edge it opens from: one of the corner's two edges
width = 300                  # px from the corner, the frame bands included
height = 390                 # 390 = 380 px past the 10 px bottom band
state = "extended"
handle.shape = "bar"         # handle and interaction work as on edge panels
```

Corner panels are laid out first: one per corner (a second one in the same corner is hidden
with a "Panels adjusted" notification), shrunk to fit beside the other corner panels. Edge
panels on the edge a corner panel opens from keep its join, the gap and their own join from
it; on the other edge they start past the rounded corner, which rides up with the panel.
`align`, `offset`, `order`, `length` and `depth` do not apply to corner panels, and `corner`,
`width` and `height` do not apply to edge panels: both are rejected with the key path.
````

- **Develop.** Add `scripts/py -m shell.canvas.corner_sheet --out /tmp/corners.png       # corner panels in every corner, enlarged`.
- **Known limitations.** Add: `- Corner panels: one per corner; only corner widgets (widget_panel) can sit in a corner; no "content" length; a corner panel's sizes are fixed px (no percentages).`

- [ ] **Step 2: Spec**

In `docs/superpowers/specs/2026-10-11-edge-shell-design.md`:
- **Section 3.** After the "Curved joins" paragraph, add: `**Corner panels (section 19, implemented).** The widget_panel is a rectangle in the bottom-left corner: width 300 and height 390 px from the corner (the 10 px bands included, so 380 px past the bottom band), opening from the bottom edge.`
- **Section 5.1.** Add a row to the surfaces table: `| `CornerPanel` × N | top | 2 edges (its corner), margins 0 | −1 | Body rectangle (+ hover zone) only, updated each frame |`.
- **Section 8.** Add `corner.py` (`# PURE: corner panel geometry`) and `corner_panel.py` (`# CornerPanel(EdgePanel)`) under `shell/`, and `widget_panel` already listed under `widgets/` stays.
- **Section 12.** In milestone 8, append `(corner panels done: section 19)`.
- **Section 17.** Replace the last bullet's "built later" with "implemented, section 19".
- **New section 19.** Add at the end, filling the result fields from Tasks 8 and 12:

```markdown
## 19. Implemented: corner panels

Asked by Phil before the settings window ("Did we plan for the corner panel? The one that
connects to two edges of the frame?"; "the corner panel window should be a square that
connects to two edges ... it is not an L shaped panel window"). Plan:
`docs/superpowers/plans/2026-10-14-corner-panel.md`.

- **Shape.** A rectangle in one screen corner, `width` x `height` px from the corner (both
  frame bands included). Two sides lie on the screen edges; the two free sides meet the two
  bands with concave fillets: the side parallel to the opening edge meets the other band with
  the screen corner's own arc (radius R, lifted by the current depth, so depth 0 is the plain
  corner); the other free side meets the opening edge's band with an edge panel's join
  (min(R, d/2), convex free corner). The window, surface, body, content box and input region
  are rectangles; only the canvas outline curves.
- **Animation.** One depth, past the band of `edge` (the edge it opens from, default the
  corner's top or bottom edge), exactly like an edge panel: peek, click, drag (50 % snap),
  280 ms tween, fade.
- **Handle.** On the free side parallel to the opening edge, centred on the body past the
  adjacent band; section 15's rules unchanged.
- **Layout.** Corner panels first, one per corner, shrunk to fit beside each other (`along` at
  least max(T + 60, T + R + r); a corner panel hidden by an overlap takes no clearance); edge panels
  keep `along + r_c + gap + r` from a corner panel on their edge and `T + R + depth + r` from
  one on the neighbouring edge; the overlap check runs corners first.
- **Config.** In `[[monitors.X.panels]]`; the kind comes from the widget (CornerDefaults);
  keys `corner`, `edge`, `width`, `height`; mixing kinds is rejected with the key path. Reload:
  `panel-state`, `panel-handle` in place; size or corner changes rebuild.
- **Content.** `widget_panel`: time, date, CPU, RAM.

**Results.** Gate A (Phil, review sheets): RESULT_A. Gate B (Phil, HDMI-A-1): RESULT_B;
`--stats 10` on `examples/corner-test.toml`: STATS_B.
```

Replace `RESULT_A`, `RESULT_B` and `STATS_B` with the recorded gate results: pass or fail per item, Phil's words where he gave any, and the printed `--stats` numbers (fps, damaged-draw median, p95 and max, CPU). Record any decision Phil changed at the gates in the bullets above.

- [ ] **Step 3: Check and commit**

Run: `scripts/py -m ruff check .` (docs are excluded; expect `All checks passed!`) and `scripts/py -m pytest -q` (expect `1424 passed`).

```bash
git add README.md docs/superpowers/specs/2026-10-11-edge-shell-design.md
git commit -m "docs: corner panels in README and spec" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-review (planner)

- **Spec coverage:**
  - section 3's `widget_panel` row: Task 11, defaults 300 / 390 = 380 past the band;
  - "one free-edge join plus one join on the adjacent frame": decision 1, Task 4;
  - section 17's `corner`, width, height: Tasks 1-2;
  - minimum geometry (spike: corner clearance, `r1 + r2` gap): Task 6, and Task 4's reference tests;
  - section 18's border outside and damaged-region redraw: Tasks 4-5;
  - section 15's handle rules and toggles: Tasks 3 and 9;
  - section 6's validation with key paths and live reload kinds: Tasks 1, 2 and 10;
  - section 5's surfaces, exclusive zone, raise and input region: Task 9;
  - section 9's human gates on HDMI-A-1: Tasks 8 and 12;
  - settings-window readiness (Plan 4): decision 6's contract, all public and tested: `registry.widget_kind(name)` and `registry.defaults(name)` (Task 2, `test_a_corner_widget_gives_a_corner_request`, `test_a_widgets_defaults_are_public`); `SHARED_KEYS`, `EDGE_ONLY_KEYS`, `CORNER_ONLY_KEYS` exported from `shell.config.models` and partitioning `PanelConfig` (Task 1, `test_the_key_sets_partition_the_panel_keys`); the corner's two edges as `corner.split("-")` with `default_edge(corner)` (Task 2); the schema (Task 1). The settings plan itself must be updated before it runs (Prerequisites: its 10 changes, and the merge conflicts with its Task 11).
- **Review corrections applied** (independent review of the first draft): `along` floored to `max(T + 60, T + R + r)` (large theme radii folded the outline); corner-vs-corner overlap moved into `layout_corners`, so a hidden corner panel takes no clearance; one warning per hidden corner panel; `Extent` dropped for the existing `Length`; hover zone and peek clamped to the depth (as on edge panels, now tested); `registry.defaults` and `SHARED_KEYS` added; Gate B item 11 expects the system bar shrunk at 1280x720; Gate A item 4 describes the zero-length straight piece honestly, with option B left to Phil (decision 10).
- **Placeholders:** none in code steps. Task 13's `RESULT_A`, `RESULT_B` and `STATS_B` are gate outputs that do not exist before the gates; Step 2 says exactly what goes there.
- **Type consistency:** `CornerGeometry(widget, corner, edge, along, length, depth, state, label)` is used the same way in Tasks 2, 5, 6, 9 and 10. `CornerShape(corner, edge, along, depth)` and `CornerSpan = (corner, edge, along, depth, d)` match in Tasks 4, 5 and 7. `shell.corner` signatures match in Tasks 3, 5, 6 and 9. `corner_clearance(edge, held, thickness, radius, gap)` matches in Task 6. The window stays one rectangle: **the corner panel window is a rectangle, not an L** (decisions 1 and 4, Global Constraints, Review Focus 1).
- **Review Focus:** each of the six lines names its tests, all in this plan.

## Open questions for Phil

1. **Opening edge** (decision 1): should corner panels open out of the top or bottom edge by default (the `widget_panel` rises from the bottom band), or out of the side edge?
2. **Lifted corner rounding** (decision 1): the screen corner's full rounding (R = 14) rides with the panel's inner edge on the other band. Is that the look you want, or a smaller join-sized curve there?
3. **Precedence** (decision 3): corner panels win over edge panels (edge panels move, shrink or hide around them), whatever the config order. Agreed?
4. **Sizes** (decision 8): `width` and `height` measured from the screen corner with the frame bands included (the spec's 380 deep becomes `height = 390`). Agreed?
5. **Content** (decision 7): the `widget_panel` v1 column (time, date, CPU, RAM). Enough for now, or should it host other widgets first?
6. **Which widgets in corners** (decision 6): only corner widgets for now. Do you want a clock or dock in a corner panel later (about 1 task)?
7. **Gap on the other edge** (decision 10): at full depth an edge panel on the corner panel's other edge starts right where the lifted corner curve ends, with no straight piece of frame between them (option A, planned). Or keep the 8 px gap there too (option B, a one-line change)?
