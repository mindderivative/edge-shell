# Edge Shell — Design

Date: 2026-10-11 · Owner: Phil Hodgins · Status: draft for review

## 1. Overview

Edge Shell is a Fabric (Python, GTK3, gtk-layer-shell) overlay that draws a thin frame around each monitor and grows panels out of that frame. It runs alongside KDE Plasma on KWin Wayland and adds to Plasma rather than replacing it. Everything about it is configurable: theme, which monitors run it, which panels exist, where they sit, and whether Plasma's own panel is shown.

**Goals**

- A continuous frame with rounded desktop corners on every enabled monitor.
- Panels that animate out of the frame and stay fused to it through curved joins.
- Every panel is a handle on the frame when collapsed: hover, click or drag opens it.
- Fully data-driven: theme, monitors, panels and widgets come from a config file.
- Safe to develop on one monitor while the other keeps Plasma's panel.
- A Python codebase that works as a sandbox for new widgets.

**Non-goals**

- Replacing KWin, Plasma window management, the lock screen or KRunner.
- X11 support. The shell depends on `wlr-layer-shell`, which KWin implements.
- Owning bus names Plasma already holds (notifications, status notifier watcher).

## 2. Environment (verified 2026-10-11)

- Plasma 6.7.5, KWin Wayland, `GDK_BACKEND=wayland`, Python 3.14.7.
- Venv: `/home/phil/Projects/pyDev/pyEnvs/global-base` — Fabric 0.0.2, PyGObject 3.50.0, pycairo 1.29.2, Pydantic 2.14.1, loguru.
- **PyGObject must stay below 3.52.** 3.52+ turns GI enums into Python enums, and Fabric 0.0.2's `@Property(GtkLayerShell.Layer)` raises `TypeError: Unsupported type`. Pin `PyGObject<3.52` wherever dependencies are recorded.
- Monitors (stacked vertically, 1920×1080, scale 1): `HDMI-A-1` at 0,0 (no Plasma panel; test monitor) and `DP-1` at 0,1080 (primary; holds the one Plasma panel, bottom edge).
- Missing typelibs: `Cvc-1.0` (Fabric audio) and `GnomeBluetooth-3.0` (Fabric Bluetooth). Volume and Bluetooth use `wpctl` and BlueZ D-Bus instead.
- Fonts: Hack Nerd Font Mono and JetBrains Mono are installed.

## 3. Visual spec

A frame of thickness `T` surrounds each enabled monitor. Desktop corners are rounded with radius `R`, and every panel meets the frame with curved joins of radius `R` on both sides.

| Token | Default | Notes |
| --- | --- | --- |
| `T` frame thickness | 10 px | Also the space reserved on each edge |
| `R` corner and join radius | 14 px | Joins shrink to half the panel's depth while it animates (so the convex corner and concave join stack into a smooth S-curve instead of overlapping) |
| Frame color | `#0b0c0d` | Panels use the same color so they read as part of the frame |
| Text / secondary | `#e6e8ea` / `#9ba0a6` | |
| Accent | `#8fd3b6` | Active workspace and focus rings only |
| Handle dots | `#7b7f84`, hover `#e6e8ea` | Three 3 px dots, 3 px gaps |
| Font | `["Hack Nerd Font Mono", "JetBrains Mono", "monospace"]` | Ordered fallback list |
| Icon buttons | 44×44 px, radius 10 px | 20 px glyphs |

Colours accept `#rrggbb` or `#rrggbbaa` (the alpha form matters for the border and shadow).

**Default surfaces** (one 1920×1080 monitor; depth measured past the frame)

| Widget | Edge | Position | Length | Extended depth | Default state |
| --- | --- | --- | --- | --- | --- |
| clock | top | centered | 168 | 46 | extended |
| dock | bottom | centered | 560 | 64 | extended |
| widget_panel | bottom-left corner | x = 0 | 300 (incl. left frame) | 380 | extended |
| system_bar | right | y = 600 | 300 | 56 | extended |
| workspaces | left | y = 150 | 220 | 52 | collapsed |

All values are defaults. Any of them can be overridden per monitor in the config.

**Curved joins.** Each join is an `R`×`R` square, frame-colored outside a quarter circle, so the desktop corner beside a panel is convex while the frame stays one continuous shape. A corner-anchored panel has one free-edge join; its other join sits on the frame beside it.

## 4. Interaction model

Three states per panel. Only **extended** shows content.

| State | Depth past frame | Content | Enters on | Leaves on |
| --- | --- | --- | --- | --- |
| Collapsed | 0 | Hidden | Start-up default, handle click while extended, drag released below 50% | Pointer enters the strip |
| Peek | 14 px | Hidden; handle dots brighten | Pointer enters the strip | Pointer leaves, or handle clicked |
| Extended | Full depth | Fades in | Handle click, or drag released at ≥50% | Handle click |

**Timing.** Depth animates over 280 ms with `cubic-bezier(.2, .8, .2, 1)`. Content fades in over 170 ms starting 110 ms into the reveal; on collapse it fades out immediately. Join radius, for both the body's convex corners and the concave joins, is `min(R, depth/2)` on every frame, so the convex corner and concave join stack into a smooth S-curve instead of overlapping.

**Drag.** Pressing the handle and moving along the panel's axis sets depth directly, clamped to `[0, full]`. On release the panel snaps at the 50% threshold. A press that moves less than 4 px is a click.

**Keyboard.** Each handle is a focusable button with an accessible name such as "Expand dock". Panels with text input use `keyboard_mode="on-demand"`; all others use `"none"`.

**Hover events.** `enter-notify-event` and `leave-notify-event` require `add_events(ENTER_NOTIFY_MASK | LEAVE_NOTIFY_MASK)` on the window. This must be set explicitly.

**Hover target.** The collapsed input region is grown to 16 px beyond the frame without drawing it, so the strip is easy to hit.

## 5. Architecture

### 5.1 Surfaces per monitor

Each enabled monitor gets: one `ShapeCanvas`, 4 invisible `FrameEdge` strips, and one `EdgePanel` per configured panel (see section 18).

| Window | Layer | Anchor | Exclusive zone | Input |
| --- | --- | --- | --- | --- |
| `ShapeCanvas` × 1 | top | 4 edges | −1 | None (`pass_through=True`) |
| `FrameEdge` × 4 | bottom (invisible) | 3 edges | `auto` = T px (T + border width when the border is enabled) | None (`pass_through=True`) |
| `EdgePanel` × N | top | 1 edge + margin (resolved `pos`) | −1 | Panel body (+ hover zone) only, updated each frame |

Two Fabric details that change the design:

1. `exclusivity="normal"` reserves 1 px, not the window's size. Use `"auto"` for the frame strips.
2. `exclusivity="none"` sets the zone to 0, which makes KWin move the surface clear of other surfaces' reserved space. Call `GtkLayerShell.set_exclusive_zone(self, -1)` right after `super().__init__()` for corners and panels.

**Surface sizing.** Each panel's surface is allocated once at its fully extended size `(length + 2R) × (T + depth)`. Animation redraws and moves the input region only; KWin never resizes a layer surface mid-animation.

**Implemented (2026-10-13):** the single-canvas design (section 18, option B) replaced per-window drawing. The strips only reserve space; panels are content, handle and input windows above the canvas. The startup re-raise of panels is still needed: with it off, the collapsed handle dots stayed hidden behind the canvas (Gate 1 item 7), so the delayed `raise_to_top` was kept (`EDGE_SHELL_RAISE_MS=0` is a debug switch).

### 5.2 Drawing

The canvas draws one union outline of frame, corners and panels (`shell/canvas/outline.py`) in a canonical per-edge space rotated onto each edge, then the border and shadow (`shell/canvas/effects.py`). `shell/geometry.py` keeps the per-panel maths (join radius, input rects, anchors).

### 5.3 Monitors

Monitors are keyed by **connector name** (`DP-1`, `HDMI-A-1`), never by index. Gdk monitors are mapped to connector names by geometry against `kscreen-doctor -j`. Each monitor has a mode:

| `shell` | Edge Shell windows | Plasma panel |
| --- | --- | --- |
| `edge` | built | untouched |
| `plasma` | none | untouched |
| `both` | built | untouched (the bottom edge must be free of Edge Shell panels) |
| `none` | none | untouched |

Frames are **independent per monitor**: each enabled monitor is a complete frame with its own corners and panels; the band between the stacked monitors is left as it is. Hot-plug (`monitor-added`, `monitor-removed`) builds or destroys that monitor's windows.

## 6. Configuration

User config: `~/.config/edge-shell/config.toml`. The repo ships `config.default.toml` defining every key; the user file is overlaid on it, so a missing key always has a default. The settings UI only ever writes the user file. It never touches live windows.

```toml
[theme]
frame = "#0b0c0d"
text = "#e6e8ea"
accent = "#8fd3b6"
thickness = 10
radius = 14
font = ["Hack Nerd Font Mono", "JetBrains Mono", "monospace"]

[theme.border]                # opt-in border along the outline, outside the mass
enabled = true
width = 2                     # px, on the desktop side
color = "#8fd3b6ff"           # #rrggbb or #rrggbbaa

[theme.shadow]                # opt-in uniform shadow onto the desktop
enabled = true
elevation = 50                # 0-100 %; 100 % reaches 48 px
color = "#00000080"           # the alpha is the strength

[monitors.HDMI-A-1]
shell = "edge"
theme.accent = "#d3a68f"      # optional per-monitor override
theme.shadow.elevation = 80   # nested tables merge key by key

[[monitors.HDMI-A-1.panels]]
widget = "clock"
edge = "top"                  # omitted keys fall back to the widget's defaults
length = 168
align = "center"              # start | center | end; offset = px from that end
order = 0                     # within the slot (edge + align)
depth = 46
state = "extended"            # collapsed | extended

[monitors.DP-1]
shell = "plasma"
```

- **Validation** uses Pydantic models. Unknown widget names, bad colors and out-of-range numbers produce an error naming the key path. Invalid config never replaces a working one; the shell keeps the last good config and reports the error.
- **Panels are an ordered list**, so one monitor may have the same widget twice, and each monitor may place widgets differently.
- **Widget registry.** A widget registers by name with default geometry and a `build_content()` method. The registry also feeds the settings UI's widget list. Adding a widget means adding a file under `widgets/`.

  ```python
  @register("clock")
  class ClockPanel(EdgePanel):
      defaults = PanelSpec(edge="top", length=168, depth=46, label="clock")
      def build_content(self): ...
  ```

- **Live reload.** `Gio.FileMonitor` on the config file, debounced ~200 ms. The new config is diffed against the old:

  | Change | Reaction |
  | --- | --- |
  | Theme colour, border or shadow | Regenerate CSS; redraw the canvas (no rebuild) |
  | Panel `state` | Retarget the tween |
  | Panel `edge`, `pos`, `align`, `offset`, `order`, `length`, `min_length`, `max_length` or `depth` | Rebuild that panel's window, and any panel whose resolved position or visibility changed with it (section 17 rules) |
  | Layout `gap` (`[layout]`, `[monitors.X.layout]`) | Re-layout the monitor: rebuild only the panels that moved |
  | Panel added or removed | Create or destroy that window |
  | Monitor `shell` mode | Create or destroy that monitor's windows |
  | Invalid config | Keep the old config; report the error |

## 7. Plasma integration

Principle: read Plasma's services; never own a bus name Plasma holds. All access goes through `services/plasma.py`, which exposes plain Python objects with Fabric signals. Every call is async. A missing service sets `available = False` and the widget hides itself.

| Need | Mechanism |
| --- | --- |
| Virtual desktops | `org.kde.KWin` `/VirtualDesktopManager`: `current`, `desktops`, `currentChanged` (verified present) |
| Hide/show a Plasma panel | `org.kde.PlasmaShell.evaluateScript(script)` (method verified present; behavior to be tested in spike 2) |
| Tray | Register as a host on `org.kde.StatusNotifierWatcher`; do not use `fabric.system_tray` |
| Notifications | Left to Plasma |
| Battery, network, media | UPower, NetworkManager, MPRIS via Gio proxies |
| Volume, Bluetooth | `wpctl`; BlueZ over D-Bus |

**Plasma panel toggle.** Before the first change, the original `hiding` and `location` of every affected panel are saved to `~/.local/state/edge-shell/plasma-restore.json`. "Show Plasma again" restores from that file. `edge-shell --restore-plasma` performs the restore from the command line even if the shell crashed.

**Monitor mapping.** Gdk monitor to Plasma screen id is matched by geometry (`screenGeometry` from the scripting API against `kscreen-doctor -j`); monitors do not overlap, so geometry is unambiguous.

## 8. Project layout

```
edge-shell/
├── pyproject.toml
├── config.default.toml
├── main.py                   # entry point + --restore-plasma
├── shell/
│   ├── app.py                # config -> monitors -> windows
│   ├── monitors.py           # connector names, hot-plug, MonitorShell per screen
│   ├── config/{models,loader,watcher}.py
│   ├── geometry.py           # PURE: matrices, join radius, input rects
│   ├── anim.py               # Tween
│   ├── theme.py              # theme -> CSS + cairo colors
│   ├── canvas/               # shape canvas: outline, effects, scene, painter, window
│   ├── panel_layout.py       # PURE: resolved positions, minimum geometry rules
│   ├── frame.py              # FrameEdge (invisible zone strips)
│   ├── edge_panel.py         # EdgePanel base
│   └── registry.py
├── widgets/                  # clock, dock, system_bar, workspaces, widget_panel
├── services/plasma.py
├── spikes/                   # throwaway probes
├── tests/
└── docs/superpowers/{specs,plans}/
```

| Module | Owns | Must not |
| --- | --- | --- |
| `shell/geometry.py`, `shell/config/models.py`, `shell/canvas/*` (except `canvas.py`), `shell/panel_layout.py` | Pure logic | Import GTK |
| `shell/anim.py` | Easing, frame-clock ticks | Know about panels |
| `shell/edge_panel.py` | Window setup, content placement, handle, input region, states; reports its depth to the canvas | Draw the panel body; contain widget content |
| `shell/canvas/*` (except `canvas.py`), `shell/panel_layout.py` | Pure logic: outline, border, shadow, scene, damage boxes, panel positions | Import GTK |
| `shell/canvas/canvas.py` | The `ShapeCanvas` window: draws frame, corners, panel bodies, border, shadow | Take input; know widget content |
| `widgets/*` | Defaults, `build_content()` | Call cairo or GtkLayerShell |
| `services/*` | D-Bus and Fabric signals | Build widgets |

## 9. Testing

1. **Pure logic (pytest, no display; runs in CI).** Config parsing and validation including bad input; config diffing; `geometry.py` for all four edges against hand-computed values; `Tween` with a fake clock; theme to CSS.
2. **Render tests (headless).** `EdgePanel`'s draw routine runs against a cairo `ImageSurface` and is compared with stored PNGs for each edge at depths 0, shallow and full. This locks in "joins never stick out" and catches seams.
3. **Compositor checks — human-in-the-loop.** Phil is the visual tester for everything that renders to screen. Each milestone that draws to screen ends with a short checklist (what to launch, what to look for: seams, join shape, hover feel, animation smoothness, whether maximized windows stop at the frame). Claude launches the shell on `HDMI-A-1`; Phil reports what is on screen, and screenshots (`spectacle`) are used where they help. Automating this with a virtual KWin session is a stretch goal, not part of the plan.
4. **Plasma integration.** The restore logic is tested against a fake script runner (record original state, apply, restore exactly). The real `evaluateScript` call is only tested manually, on `HDMI-A-1` first.

Conventions: `ruff` for lint and format, `pytest`, TDD for layers 1 and 2. GitHub Actions runs layers 1 and 2 only.

## 10. Risks

| Risk | Effect | Mitigation |
| --- | --- | --- |
| Exclusive-zone semantics differ across KWin versions | Panels sit inside the frame instead of fusing | Spike 3 and milestone 2 check `set_exclusive_zone(-1)` on KWin 6.7 first |
| Seams where a panel overlaps the frame | Hairline gaps | Panels repaint the frame strip beneath them; render tests; fall back to the single-canvas approach (5.1). Scale is 1 today; re-test if scaling changes |
| Per-frame `input_shape_combine_region` cost | Animation stutter | Update the region only when its integer rectangle changes |
| Hard-coded positions | Misplaced panels on other resolutions | Positions are edge offsets in config; windows are built per monitor |
| Fabric incompatible with newer PyGObject | Shell will not import | Pin `PyGObject<3.52` |
| Plasma panel toggle leaves Plasma in a bad state | Lost panel | Saved restore file plus `--restore-plasma`; test on `HDMI-A-1` first |
| Gdk monitor to connector name mapping unavailable | Config keyed by connector cannot resolve | Spike 1; fall back to geometry matching |

## 11. Spikes (before the plan is final)

Each is a throwaway script in `spikes/` that answers one question.

1. **Resolved:** `Gdk.Monitor.get_model()` returns the panel model, not the connector (both monitors report `G24M2020G`). Gdk monitors are mapped to connector names by geometry against `kscreen-doctor -j`. See `docs/superpowers/findings/2026-10-11-monitor-names.md`.
2. Does `evaluateScript` hide and restore a Plasma panel cleanly with no flicker or layout side effects? Only a temporary test panel on `HDMI-A-1` is touched first; Phil confirms before the live panel on DP-1 is touched.
3. **Folded into the build:** frame strips, corners and the dock are built for real in milestones 2-3; Phil's visual gates A and B answer this. If either gate fails, stop and choose the single-canvas fallback in 5.1.

## 12. Build order

| # | Milestone | Done when |
| --- | --- | --- |
| 0 | Spikes 1–3 | Findings note in `docs/` |
| 1 | Config layer | Defaults and user overlay load, validate and report bad keys; no GTK |
| 2 | Frame on HDMI-A-1 | Strips and corners; maximized windows stop at the frame; monitor manager honors `shell = "edge"` |
| 3 | `EdgePanel` with dock | Fused with the frame, no seam, driven by `PanelSpec` |
| 4 | Animation and states | Click toggles, hover peeks, input region follows the body |
| 5 | Remaining edge panels | Clock (top) and system bar (right) prove the other matrices; drag-to-open |
| 6 | Live reload and hot-plug | Editing the TOML updates the shell; unplugging a monitor does not crash it |
| 7 | Plasma integration | Workspaces panel, tray host, Plasma panel toggle with restore |
| 8 | Corner widget panel, then the settings window | Last, once the schema is stable |

## 13. Later: settings window

A normal window (opened from a key binding, tray icon or frame handle) for editing colors, monitor modes, panel positions and the widget list, and for hiding or showing the Plasma shell. It writes the user config file only. Its form fields can be generated from the Pydantic JSON schema and the widget registry. Designed once the schema has settled, after milestone 7.

## 14. Open questions

- Should a pinned panel reserve space (push windows) or float over them? This spec assumes **float**.
- Should the settings window also expose a drag-and-drop layout editor, or only form fields? Deferred to its own design.

## 15. Planned: handle customization and per-interaction toggles

Requested by Phil at Gate D of the core plan. It is not part of the core plan, but the core must not paint this into a corner.

**Requirements**

- The handle (today: three 3 px dots) is customizable per panel: shape, color (rest and hover), size, and position along the edge.
- Handle shapes include at least: dots, a thin bar, and a chevron/arrow. A chevron can **morph with the panel's depth**: pointing one way when collapsed, rotating to point the other way when expanded.
- The three interactions are individually opt-in/opt-out per panel: **click to toggle**, **hover to peek**, **drag to open**. Defaults stay all-on, so existing configs behave as today.
- A handle style may depend on which interactions are enabled (e.g. a thin bar when only drag is on, an arrow when only click is on).

**Design implications (for the future plan; nothing here changes the current core)**

- Config: a per-panel `[handle]` table (`shape`, `size`, `offset`, `color`, `hover_color`) and an `[interaction]` table (`click`, `hover`, `drag`, all default true) in the Pydantic models; the registry can supply per-widget defaults. Unknown shapes fail validation with the key path as elsewhere.
- Rendering: the handle moves from CSS-styled widgets to cairo drawing inside the panel canvas (or a dedicated drawing area), driven by a pure `draw_handle(cr, shape, ...)` plus a morph parameter derived from `d / depth`. That makes the arrow morph free and keeps shapes testable with the same headless pixel tests as the panels.
- Hit area vs visual: the clickable/hover/drag area stays a separate, larger target than the drawn shape.
- Behavior: `panel_state` and `EdgePanel` consult the interaction flags (no hover peek when hover is off; ignore press-drag when drag is off; the handle is not a button when click is off). Keyboard activation still follows the click flag.
- Diffing: handle and interaction changes are cheap in-place updates (restyle or flag change), not window rebuilds.
- Today's code touch points: `EdgePanel._build_handle`, `_place_handle`, the pointer handlers, the `.handle-dot` CSS in `shell/theme.py`, and the `handle`/`handle_hover` theme tokens.
- The settings window (section 13) exposes these controls.

## 16. Planned: several panels on one edge (layout and separation)

Raised by Phil at Gate E of the core plan.

**Today (core plan, as built).** Each panel positions itself independently: `edge` plus `pos`, the distance in pixels along the edge where the panel body starts; no `pos` means centred. Nothing arranges panels relative to each other and nothing detects overlap: two centred panels on one edge sit on top of each other, and side-by-side placement means hand-computing `pos` values. The default layout avoids this by using a different edge per panel.

**Implemented (2026-10-13, plan `docs/superpowers/plans/2026-10-13-layout-anchoring.md`):** `shell/panel_layout.py` (`layout_edge`, `layout_monitor`) resolves every panel per edge from slots (start, center, end), `order` within a slot (ties keep config order) and one `gap` per monitor (`[layout]`, `[monitors.X.layout]`, default 8 px) measured between neighbouring joins, on top of `r1 + r2`. `pos` keeps its old meaning (pixels from the start of the edge) as a deprecated alias placed outside the slots; combining it with `align`/`offset` is a validation error whose message gives the conversion (`pos = N` = `align = "start"`, `offset = N - (T + R + r)`), and each config load logs one INFO line listing the entries still using it. The system bar's default moved from `pos = 600` to `align = "end"`, `offset = 142` (identical on a 1080 px monitor only). Overlaps hide the later panel (config order) with a notification. No `panel-move` change kind: moved panels are rebuilt; a `gap` change is a `relayout`.

Resolver details settled in review: spacing is rounded up per neighbour pair; a `MIN_LENGTH` floor (60 px) applies after the `max_length` clamp; extra warnings `{name}: no room after its neighbours in the {align} slot; moved to {q}` and `{name}: no room to fill; shown at 60 px`. Inside a slot the gap is always honoured; between different slot groups (start, centre, end) that run out of room only `r1 + r2` (not the gap) is guaranteed. Two panels meeting at a shared screen corner collide at offset 0; the minimum offset is the other panel's depth + r - R (its depth for panels at least 28 px deep). Verified live on HDMI-A-1 (Gates A and B, both passed): layout, offsets, the corner rule (offset 0 hides the later panel with a "Panels adjusted" notification, offset 46 shows it), fill/content/percent lengths, and the resolution-change re-layout. Gate B `--stats 10` on `examples/layout-sizes-test.toml`: 56.8 fps while animating, damaged canvas draws median 0.30 / p95 0.58 / max 1.00 ms, one full draw 1.60 ms, CPU 0.21 of a core. Known limits: HiDPI is unsupported (one warning); a "content" panel hidden at its default length is never measured and stays hidden.

**Requirements**

- Several panels can share an edge and be separated predictably, without hand-computed pixel offsets.
- Each panel can be placed by **alignment slot** (`start`, `center`, `end` of the edge), with an **order** within a slot and a configurable **gap** between neighbours. Explicit `pos` stays available as an override.
- Overlap is detected and reported (log plus notification, like config errors) instead of silently stacking; the shell still runs.
- Panels keep their own length and depth; the layout only decides the position along the edge.
- Corner interaction: the length available to an edge is the monitor extent minus the corner radius on each end, so slotted panels never run into the screen corners.

**Design implications (for the future plan)**

- Config: panel entries gain `align` (default `center`) and optionally `order`; a per-edge/per-monitor `gap` setting; `pos` remains and wins when present.
- Layout: a pure function `layout_edge(panels, extent, gap, radius) -> {panel: pos}` (no GTK) computes positions per edge, so it is unit-testable like the geometry; `EdgePanel` keeps taking a resolved `pos`.
- Reload: reordering or changing `align`/`gap` moves panels, which today means rebuilding the affected panels' windows (their surface margin changes); the diff gains a `panel-move` change kind if rebuild flicker proves annoying.
- Handle placement (section 15) should be relative to the panel body, independent of the slot.
- The settings window (section 13) exposes slot, order and gap, and shows the overlap warning.

## 17. Planned: panel anchoring, sizing and corner behaviour

Raised by Phil after Gate G of the core plan; the three choices below were decided with Phil. This extends section 16 and, with it, replaces today's `pos`-only placement.

**Behaviour of the core plan as built (for reference)**

- A panel attaches to one edge and is placed by `pos`: pixels from the **start** of the edge (left for top/bottom, top for left/right). There is no end-anchoring.
- `length` is a fixed pixel count. Depth grows only perpendicular to the edge, away from it.
- If `pos + length` runs past the end of the edge, the surface is shifted inward to stay on screen. If the panel is longer than the edge, it overhangs the far end and the screen clips it (untested). The only length bound is absolute (4000 px), unrelated to the monitor.
- Content is centred at its natural size; there is no fill, content-fit, percentage, or min/max.
- Panels have no corner awareness: the frame's rounded corner pieces are separate R x R windows, and a panel placed within about R + T of a screen corner overlaps them. Corner-spanning (L-shaped) panels are not built.

**Decisions**

1. **Anchoring: `align` + `offset`.** `align = start | center | end` and `offset` is the distance in pixels from **that** end (default 0). A bottom-right bar is `edge = "bottom"`, `align = "end"`, `offset = 0`. This subsumes `pos` (start-aligned offset) and composes with the slot/order/gap layout of section 16.
2. **Sizing: `length` accepts a pixel number, `"fill"`, `"content"`, or a percentage** (e.g. `"50%"`), with optional `min_length` / `max_length`. `"fill"` spans the available span between the corner zones (minus gaps and neighbours); `"content"` wraps the widget's natural size; percentages are of the available span. Depth stays in pixels. Growth along the edge is from the anchored end toward the free side (an end-aligned panel grows toward the start).
3. **Overflow and corners: clamp to the free span.**
   - The **free span** of an edge is the monitor extent minus a corner clearance at each end (`T + R`, so panels never run into the rounded corner pieces).
   - A requested length larger than the free span is **shrunk to fit**, with a log warning (and a notification on config reload); content that no longer fits is clipped. It is never a load-time error, so smaller or hot-plugged monitors keep working.
   - Offsets that would push a panel past the free span are clamped inward.
   - **Minimum geometry rules (found by the shape-canvas spike):** the single-outline renderer self-intersects (fills overlap, about 20-30 wrong pixels) when two curves collide. Two cases: (a) a panel whose concave fillet lands inside a screen-corner arc, so the **corner clearance is `pos - r >= T + R`** where `r = min(R, depth/2)` is the current join radius; (b) neighbouring panels on one edge whose fillets overlap, so the **minimum gap between adjacent panels is `r1 + r2`** (up to `2R` = 28 px at full depth). The layout resolver enforces both (clamping, with a warning); a panel exactly at the clearance renders correctly.
   - **Implemented (2026-10-13, layout plan):** the free span is `T + R + r` from each end; `length` takes px, `"fill"` (equal shares of what the neighbours, offsets and spacing leave), `"content"` (the content's natural size plus 12 px each side, measured once after build in an idle callback, the widget's default until then; a one-off startup rebuild of content panels, an in-place resize is planned only if a flash is observed) or a percentage of the free span, then `min_length`/`max_length` and a 60 px floor; too long is shrunk with a warning and the content is clipped (not scrolled) at the body edge and kept centred, never drawn over the joins and frame. `MonitorShell` re-lays out on the monitor's `notify::geometry` (debounced 250 ms; a zero geometry while unplugging is ignored), so centred, percentage and fill panels follow resolution changes. Two panels meeting at a shared screen corner collide at offset 0 (one needs an offset of at least the other's depth + r - R); a panel hidden by an overlap keeps its slot space; a re-layout the shell starts itself that fails is logged and rebuilds that monitor once, with a "Panels rebuilt" notification.
   - **Corner-spanning panels** (the original `widget_panel`: one free-edge join plus one join on the adjacent frame) are a separate widget type with their own geometry (`corner`, width, height), built later; they are the only panels that meet two edges.

**Design implications (for the future plan)**

- Pure layout module (`layout_edge(panels, extent, gap, radius, thickness) -> {panel: (offset, length)}`) resolving align/offset/length/fill/content/percent/min/max and the free span for each edge; no GTK, headless tests. `"content"` needs the widget's natural size, which comes from GTK, so the layout takes it as an input (measured once after build, re-measured on rebuild) and the pure function stays testable with fake sizes.
- Done: `anchor_and_margin` takes the resolved start; `EdgePanel` receives a resolved `PanelGeometry` (pos and length in px).
- Models: `PanelConfig` gains `align`, `offset`, `length: int | "fill" | "content" | str-percent`, `min_length`, `max_length`; `pos` is kept as a deprecated alias for start-aligned offset until removed.
- The free span depends on the monitor extent, so geometry/scale changes (see README limitation) must trigger a re-layout; the same hook should handle that known gap.
- Tests: headless unit tests for the layout function (align/offset/fill/content/percent/min/max/clamping/corner clearance) plus a render test for a panel at the end of an edge next to the corner piece.

## 18. Planned: frame/panel border and shadow (drawing architecture)

Raised by Phil after the core PR; requirements are Phil's, the architecture options are the controller's analysis and need a spike before a decision.

**Requirements**

- **Border:** a stroke drawn *outside* the mass, on the desktop side of the frame's inner edge (changed after Gate 4: it adds its width to the 10 px frame band instead of eating into it; the shadow is measured from its outer edge and the invisible zone strips reserve thickness + border width), that flows seamlessly around the rounded screen corners, down into each panel's joins, along the panel body, and back out, as one continuous line. Configurable `width` (px, user-specified) and `color` as **RGBA** (`#rrggbbaa`, so the border can be translucent).
- **Shadow:** a soft, **uniform** shadow cast by the frame and by the panels onto the desktop on every side (no offset, no top/bottom bias), as one smooth shape that flows into the panels' joins so the frame and widgets look like they float above the desktop. Only two controls: `elevation` and `color` as RGBA (its alpha is the shadow's strength). `elevation` is a **percentage from 0% to 100%** (0% = no shadow, 100% = the maximum reach), so users adjust it to taste without thinking in pixels. It must **move with the animation**: as a panel's depth changes, its border and shadow follow it every frame.
- **Opt-in/opt-out:** border and shadow are independent toggles (`enabled`), off by default so today's look is unchanged; overridable per monitor via the theme, and per panel later.

**Why this is an architecture decision.** Today the outline is drawn by separate windows (CSS frame strips, cairo screen corners, one cairo window per panel). A border only reads as one line if every piece hands off exactly where the next begins, and a shadow of a *union* of shapes is not the sum of per-window shadows: overlapping per-window shadows darken twice at joins and show seams, and every window would also have to grow by the shadow extent and animate it.

**Options**

- **A. Keep per-window drawing** and add border/shadow per piece: strips, corners and panels each draw their part, with matching end caps. Smallest change, but seam-prone (the same class of problem as the spec's seam risk), double-darkened shadows at overlaps, and every window must grow by the shadow extent.
- **B. One click-through shape canvas per monitor (recommended):** a single monitor-sized, input-transparent layer surface draws the frame, corners and all panel shapes as one outline, plus the border stroke and the shadow, in one cairo pass. Panels stop drawing their own bodies and become content/handle/input windows stacked above the canvas, reading their current depth from a shared per-panel value. This is the single-canvas approach already named as the fallback in 5.1. Seams are impossible by construction (one fill, one stroke), the shadow is of the union, border and shadow animate for free with depth, and the panel-over-strip stacking workaround (`raise_to_top`) disappears because the canvas is a single surface under all content windows. Costs: a larger refactor (`EdgePanel` loses its draw routine; depth is shared with the canvas; stacking and input regions change) and per-frame redraw cost of a large surface.

**Shadow rendering (decided with Phil): stacked grown copies of the one outline.** Cairo has no blur, and none is needed. The shadow is the single outline path (frame, corners and every panel at its current depth) stroked **under** the shapes with **round joins** at increasing widths (about 1 px steps up to the elevation), each at a lower alpha, so the shape is "copied, layered under, and grown uniformly toward the screen centre" with a soft falloff. Cairo's stroker computes the grown shape, so there is no offset-curve maths.
- Convex corners round off naturally (the radial-gradient look); concave joins and screen-corner fillets shrink as the stroke grows and fill in to a sharp inside corner once the stroke is wider than their radius, as a real shadow does.
- One path means the shadow is of the **union**: no double-darkening at joins, and it follows each panel's depth every frame.
- **Profile (revised after the first renders looked embossed):** the cumulative alpha at distance k px outside the shape is `C(k) = a * 0.5 * erfc(k / (sigma * sqrt(2)))` with `a` the colour's alpha, `reach = round(48 * elevation / 100)` logical px (48 px at 100%, multiplied by the display scale factor on scaled monitors), `sigma = reach / 2.5`, cut to 0 at `reach`. So it starts at about half of `a` at the edge (as a real blurred drop shadow does, the other half is hidden under the shape) and fades smoothly. The first prototype started at full strength at the edge with a short reach, which reads as a bevelled glow, not a floating shadow. Per-layer alphas are chosen so the cumulative 1 minus the product of (1 minus a_i) matches `C(k)` under 8-bit rounding (naive float alphas lose up to 15/255 over 32-48 layers). The number of 1 px layers equals `reach`; `elevation = 0` draws no shadow at all. Values outside 0-100 are clamped (config validation rejects them with the key path).
- **Uniform only (decided with Phil):** no offset or directional light, no second contact layer; the only parameters are `elevation` and the RGBA `color`. A user wanting a stronger or weaker shadow changes the colour's alpha; on dark themes they raise the alpha or lighten nothing, since a shadow cannot darken a dark background.
- Optional radial/linear gradients can smooth any visible banding but are not expected to be needed.
- Cost: wide strokes over a long path are not free. Redraw is limited to the damaged region (the animating panel's bounding box plus the shadow extent). **Spike result:** a cached shadow mask was tried and rejected: the union shadow behaves like a per-pixel max of its parts while cairo composites with OVER, so combining a cached part with a freshly stroked part over-darkens the two concave fillets by up to 63/255 for only about 0.15 ms saved. The design redraws the damaged region every frame with no shadow cache (about 2 ms live at 50% elevation, about 4 ms at 100%; see `docs/superpowers/findings/2026-10-12-shape-canvas-spike.md`).

**Status (2026-10-13):** spike done (`docs/superpowers/findings/2026-10-12-shape-canvas-spike.md`); option B implemented by `docs/superpowers/plans/2026-10-13-shape-canvas-and-effects.md`. The frame band is click-through now (the old strips took input). The panel `raise_to_top` workaround was not removed after all: the delayed re-raise is still needed for the collapsed handle dots (section 5.1).

**Spike required before choosing B (throwaway scripts, then a report):**
1. Can one monitor-sized transparent layer surface redraw a panel's bounding box plus shadow at 60 fps on this machine (damage regions, cairo software rendering)?
2. Does the union shadow from stacked grown strokes look right at joins and corners, without banding at typical elevations (render tests plus a visual check by Phil), and what do N strokes cost per frame versus a cached mask?
3. Stacking: does a click-through canvas under per-panel content windows stay below them and above the desktop on KWin, without needing the raise workaround?

**Design implications**

- Config: `[theme.border]` (`enabled`, `width`, `color`) and `[theme.shadow]` (`enabled`, `elevation` as a percentage 0-100, `color`), all optional, defaults off; per-monitor overrides through the existing theme-override mechanism. Theme colours accept `#rrggbb` or `#rrggbbaa` (the model validator and `hex_to_rgba` gain the alpha form; `border.color` and `shadow.color` are the first colours where alpha matters).
- **Calibrated values (decided with Phil from the calibration sheets):** "reasonable" shadow reach ends at **32 px**; `MAX_REACH_PX = 48`, so elevation 100% = 48 px (slightly above reasonable) and 67% = 32 px. Defaults when the effects are enabled: shadow colour black at alpha **0.5** (`#00000080`), elevation **50%** (24 px, inside the reasonable range; confirmed by Phil), border **2 px** in the theme accent colour (`#8fd3b6ff`). The effects themselves remain opt-in (`enabled = false` unless set). Cost at the maximum is small: damaged-region redraw of the animating panel measured about 2 ms at 48 px (spike, 1080p), versus the 8 ms target.
- Pure drawing layer: `draw_outline(cr, shapes, border, shadow)` taking resolved geometry for the frame and each panel at their current depth; headless pixel tests like `draw.py`'s today.
- Interplay: panel anchoring/sizing (section 17) produces the resolved panel rectangles the canvas draws; handle customization (section 15) stays on the content windows; layout (section 16) feeds the same resolved rectangles.
- Reload: border/shadow changes are colour/parameter updates (a canvas redraw), not window rebuilds.
