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

Each enabled monitor gets: 4 `FrameEdge` strips, 4 `ScreenCorner`s, and one `EdgePanel` per configured panel.

| Window | Layer | Anchor | Exclusive zone | Input |
| --- | --- | --- | --- | --- |
| `FrameEdge` × 4 | top | 3 edges | `auto` = T px | Whole strip |
| `ScreenCorner` × 4 | top | 2 edges, margin T | −1 | None (`pass_through=True`) |
| `EdgePanel` × N | top | 1 edge (centered) or 2 (positioned) | −1 | Panel body only, updated each frame |

Two Fabric details that change the design:

1. `exclusivity="normal"` reserves 1 px, not the window's size. Use `"auto"` for the frame strips.
2. `exclusivity="none"` sets the zone to 0, which makes KWin move the surface clear of other surfaces' reserved space. Call `GtkLayerShell.set_exclusive_zone(self, -1)` right after `super().__init__()` for corners and panels.

**Surface sizing.** Each panel's surface is allocated once at its fully extended size `(length + 2R) × (T + depth)`. Animation redraws and moves the input region only; KWin never resizes a layer surface mid-animation.

**Fallback.** If KWin stacking or seams make this unworkable, the alternative is four invisible zone-reserving strips plus one click-through full-screen canvas per monitor that draws frame, corners and panels in one cairo path. `EdgePanel`'s drawing code carries over largely intact.

### 5.2 Drawing

Panels are drawn with cairo, not CSS boxes, so the body and both joins come from one path with one radius. Drawing happens in a canonical bottom-edge coordinate space; a cairo matrix rotates it onto the real edge, so the join maths exists once, in `shell/geometry.py`.

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

[monitors.HDMI-A-1]
shell = "edge"
theme.accent = "#d3a68f"      # optional per-monitor override

[[monitors.HDMI-A-1.panels]]
widget = "clock"
edge = "top"                  # omitted keys fall back to the widget's defaults
length = 168
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
  | Theme color | Regenerate CSS and cairo colors; redraw |
  | Panel `state` | Retarget the tween |
  | Panel `edge`, `pos`, `length` or `depth` | Rebuild that panel's window |
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
│   ├── frame.py              # FrameEdge, ScreenCorner
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
| `shell/geometry.py`, `shell/config/models.py` | Pure logic | Import GTK |
| `shell/anim.py` | Easing, frame-clock ticks | Know about panels |
| `shell/edge_panel.py` | Window setup, drawing, input region, states | Contain widget content |
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
