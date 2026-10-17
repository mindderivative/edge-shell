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
| Handle | `#7b7f84`, hover `#e6e8ea` (theme `handle` / `handle_hover`) | Default: three 3 px dots, 3 px gaps; shape, size, weight, position and colours customizable per panel (section 15) |
| Font | `["Hack Nerd Font Mono", "JetBrains Mono", "monospace"]` | Ordered fallback list |
| Icon buttons | 44×44 px, radius 10 px | 20 px glyphs |

Colours accept `#rrggbb` or `#rrggbbaa` (the alpha form matters for the border and shadow).

**Default surfaces** (one 1920×1080 monitor; depth measured past the frame)

| Widget | Edge | Position | Length | Extended depth | Default state |
| --- | --- | --- | --- | --- | --- |
| clock | top | centered | 168 | 46 | extended |
| dock | bottom | centered | 560 | 64 | extended |
| summary (was widget_panel) | bottom-left corner | x = 0 | 300 (incl. left frame) | 380 | extended |
| system_bar | right | y = 600 | 300 | 56 | extended |
| workspaces | left | y = 150 | 220 | 52 | collapsed |

All values are defaults. Any of them can be overridden per monitor in the config.

**Curved joins.** Each join is an `R`×`R` square, frame-colored outside a quarter circle, so the desktop corner beside a panel is convex while the frame stays one continuous shape. A corner-anchored panel has one free-edge join; its other join sits on the frame beside it.

**Corner panels (section 19, implemented).** The summary block (the `summary` widget, was `widget_panel`; section 20) is a rectangle in the bottom-left corner: width 300 and height 390 px from the corner (the 10 px bands included, so 380 px past the bottom band), opening from the bottom edge.

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

**Per-panel toggles (section 15, implemented).** Each of click, hover and drag can be turned off per panel (`interaction` table). Hover off: no peek; drag off: a press never drags; click off: the handle ignores clicks and takes no keyboard focus (built-in panels use `keyboard_mode="none"`, so their handles never take keyboard focus anyway). With hover off the collapsed input region is only the handle's hit target; with all three off a collapsed panel takes no input and each config load logs one INFO line naming it.

## 5. Architecture

### 5.1 Surfaces per monitor

Each enabled monitor gets: one `ShapeCanvas`, 4 invisible `FrameEdge` strips, and one `EdgePanel` per configured panel (see section 18).

| Window | Layer | Anchor | Exclusive zone | Input |
| --- | --- | --- | --- | --- |
| `ShapeCanvas` × 1 | top | 4 edges | −1 | None (`pass_through=True`) |
| `FrameEdge` × 4 | bottom (invisible) | 3 edges | `auto` = T px (T + border width when the border is enabled) | None (`pass_through=True`) |
| `EdgePanel` × N | top | 1 edge + margin (resolved `pos`) | −1 | Panel body (+ hover zone) only, updated each frame |
| `CornerPanel` × N | top | 2 edges (its corner), margins 0 | −1 | Body rectangle (+ hover zone) only, updated each frame |

Two Fabric details that change the design:

1. `exclusivity="normal"` reserves 1 px, not the window's size. Use `"auto"` for the frame strips.
2. `exclusivity="none"` sets the zone to 0, which makes KWin move the surface clear of other surfaces' reserved space. Call `GtkLayerShell.set_exclusive_zone(self, -1)` right after `super().__init__()` for corners and panels.

**Surface sizing.** Each panel's surface is allocated once at its fully extended size `(length + 2R) × (T + depth)`. Animation redraws and moves the input region only; KWin never resizes a layer surface mid-animation.

**Implemented (2026-10-13):** the single-canvas design (section 18, option B) replaced per-window drawing. The strips only reserve space; panels are content, handle and input windows above the canvas. The startup re-raise of panels is still needed: with it off, the collapsed handle dots stayed hidden behind the canvas (Gate 1 item 7), so the delayed `raise_to_top` was kept (`EDGE_SHELL_RAISE_MS=0` is a debug switch). Re-checked by the handle plan's Gate B (item 11, Phil): with the raise off, the collapsed handles and the extended content (dock icons, clock text, system bar labels) were both hidden, so the canvas covers the panel windows until the delayed re-raise; drawing only the handle on the canvas could not remove the workaround, and the raise stays.

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

A configured monitor name that is not connected gets a warning in the log and one "Monitor not connected" notification naming the connected monitors to use (`shell/monitor_check.py`); a name counts as unknown only when it is not connected now and was never seen connected during this shell session (so unplugging and replugging a correctly named monitor says nothing; at startup a typo and an absent monitor look the same and are both reported); it is repeated only when the set of unknown names changes, and nothing is compared when `kscreen-doctor` reports no monitor.

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
panel = "edge"                # edge | corner | float (float: reserved, rejected)
name = "Clock"                # required, unique per monitor
widget = "clock"
format = "HH:mm"              # a widget property (section 20)
edge = "top"                  # omitted keys fall back to the widget's defaults
length = 168
align = "center"              # start | center | end; offset = px from that end
order = 0                     # within the slot (edge + align)
depth = 46
state = "extended"            # collapsed | extended
handle.shape = "auto"         # auto | dots | bar | chevron | none (section 15)
interaction.hover = true      # click / hover / drag, each optional

[monitors.DP-1]
shell = "plasma"
```

- **Validation** uses Pydantic models. Unknown widget names, bad colors and out-of-range numbers produce an error naming the key path. Invalid config never replaces a working one; the shell keeps the last good config and reports the error.
- **Panels are an ordered list**, so one monitor may have the same widget twice, and each monitor may place widgets differently.
- **Widget registry.** A widget is a `Widget` class (`build(props)`, `destroy()`) registered with a display title, a property model and default geometry per panel kind; the panel classes (`EdgePanel`, `CornerPanel`) are never subclassed by widgets. The registry also feeds the settings UI's widget list and Widget rows. Adding a widget means adding a file under `widgets/` (section 20).

  ```python
  @register_widget("clock", title="Clock", props=ClockProps,
                   edge=PanelDefaults(edge="top", length=168, depth=46, label="clock"))
  class ClockWidget(Widget):
      def build(self, props: ClockProps): ...
      def destroy(self): ...
  ```

- **Live reload.** `Gio.FileMonitor` on the config file, debounced ~200 ms. The new config is diffed against the old:

  | Change | Reaction |
  | --- | --- |
  | Theme colour, border, shadow or handle style | Regenerate CSS; redraw the canvas (no rebuild) |
  | Panel `state` | Retarget the tween |
  | Panel `handle` or `interaction` | Update the live panel in place (no rebuild) |
  | Panel `edge`, `pos`, `align`, `offset`, `order`, `length`, `min_length`, `max_length` or `depth` | Rebuild that panel's window, and any panel whose resolved position or visibility changed with it (section 17 rules) |
  | Panel `corner`, `edge`, `width` or `height` (corner panels) | Rebuild that panel, and any edge panel whose place changed (section 19) |
  | Panel `panel`, `widget`, `name` or a widget property | Rebuild that panel (section 20) |
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
│   ├── corner.py             # PURE: corner panel geometry
│   ├── corner_panel.py       # CornerPanel(EdgePanel)
│   └── registry.py
├── widgets/                  # clock, dock, system_bar, summary (workspaces later)
├── settings/                 # the settings window (own process): form, document, session, GTK view
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
| `widgets/*` | Defaults, `Widget.build()` | Call cairo or GtkLayerShell |
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
| 8 | Corner widget panel, then the settings window (corner panels done: section 19) | Last, once the schema is stable |

## 13. Later: settings window

A normal window (opened from a key binding, tray icon or frame handle) for editing colors, monitor modes, panel positions and the widget list, and for hiding or showing the Plasma shell. It writes the user config file only. Its form fields can be generated from the Pydantic JSON schema and the widget registry. Designed once the schema has settled, after milestone 7.

**Implemented (2026-10-14, plan `docs/superpowers/plans/2026-10-14-settings-window.md`):** a separate process (`main.py --settings`, a `Gtk.Application` `org.edgeshell.Settings.c<hash of the config path>`: one instance per config file), opened from the CLI, a right-click on any panel handle, edge or corner (on the shell's config file), or a KDE custom shortcut; the config file is its only link to the shell. Corner panels (section 19) share the panel list, with rows by the panel's kind (`panel`; before section 20 `registry.widget_kind`, the models' `EDGE_ONLY_KEYS` / `CORNER_ONLY_KEYS`). The form is generated from `Config.model_json_schema()` and the widget registry (`settings/form.py`; per-monitor overrides use the base models' bounds, which `ThemeOverride`/`LayoutOverride` lose). Edits are made in place with tomlkit (comments kept; a comment run directly above a table header is that table's label and stays attached to it; an edit that would lose such a comment is refused), verified by re-parsing, checked by the shell's own loader and `validate_widgets`, and written atomically (symlinks kept; the shell's `ConfigWatcher` also watches a symlinked config's target); never an invalid file. Live apply (spin buttons debounced 400 ms; the mouse wheel never edits), Undo/Ctrl+Z, Revert all, per-field reset; `config.toml.bak` per session and `main.py --restore-config`; hand edits while the window is open are re-read, never overwritten, and a valid one becomes Revert all's starting point (Revert all returns to the state at the start of the session or after the last valid hand edit; an invalid hand edit it replaces is first saved as `config.toml.before-revert`, numbered like `.before-restore`); an invalid file opens read-only; file-system errors are shown, not raised. The shell's Fabric D-Bus client (`Execute`/`Evaluate`) is switched off. Known limits: unsetting a whole table leaves its label behind (not reachable from the window); CRLF files get LF on written lines; comments inside a multi-line array go when it is set; `kscreen-doctor` may delay the window start by up to 5 s; `--config=~/x` is not expanded; the first instance imports the widgets (Fabric typelibs load, no layer surface); a close after a failed write keeps the window open once. Deferred: hiding or showing Plasma's panel (needs section 7 and spike 2), tray icon, drag-and-drop layout, HiDPI. Results (Phil, live on HDMI-A-1, 2026-10-14). Gate A (14 items: window, wheel guard, colours and sources, border and thickness reloads, dock and handle edits, add/move/remove, lengths, layout and corner warnings, shell mode, refused min/max length, reset, corner panel rows, Revert all, backup) passed. It found three things, all fixed: a refused edit left its row showing the refused value and another row's reset cleared the error (now the row snaps back and keeps its error); the shell loaded an empty stylesheet when the last Edge Shell monitor left (a Gtk-CRITICAL, older than this branch); and the settings process printed `G_IS_OBJECT` warnings (a rebuild destroyed pages from inside a widget's own signal; now destroyed when the loop is idle). Known cosmetic limit: an unset `max_length` shows the spin's lowest value (60) with the source label "not set". The accent colour is stored but not yet used by anything. Gate B (11 items: hand edit while open, edit on top of it, invalid hand edit, `--restore-config`, one window per file, right-click on edge and corner handles, window without the shell, a panel over the window with Ctrl+Z, symlinked config) passed, except the optional KDE shortcut (item 8): the README command pointed at a checkout path without `scripts/py`; the README now uses a `/path/to/edge-shell` placeholder.

**Menus and file operations (2026-10-15, plan `docs/superpowers/plans/2026-10-15-settings-menus.md`; design in `2026-10-14-panel-widget-model-design.md` section 6):** a menu bar (File: New, Open, Save, Save As, Close, Exit; Edit: Undo, Redo, Cut, Copy, Paste, Revert all; Help: About) with Ctrl+N/O/S/Shift+S/W/Q/Z/Shift+Z/Y (Ctrl+X/C/V stay the text field's own). Live apply stays; **Save** sets the saved point and refreshes `config.toml.bak` (so `--restore-config` puts back the last Save, or the file before the window's first change); leaving with unsaved changes (Close, Exit, New, Open, the close button) asks Save / Discard / Cancel, and Discard returns the file to the saved point (an invalid hand edit made while the window was open, if Discard replaces it, is first kept as `.before-revert`; the text the file had when the window opened is not copied); a hand edit counts as saved. New never replaces a file and adds `.toml`; Open, New and Save As show their file in its own window (one window per file); Save As writes a copy first and then puts the original back to its saved point; Close leaves an empty window with New and Open. A config that is not the shell's own (`~/.config/edge-shell/config.toml` or its `--config` file) says so once. File dialogs come through the desktop portal (`GTK_USE_PORTAL=1` unless set). The project is MIT licensed; Help > About shows the licence. Results (Phil, live on HDMI-A-1, 2026-10-15): all 15 gate items passed. Item 1 passed but the once-only "not the default config" note was not blue and its text was orange in a focused window and white in an unfocused one (GTK's theme infobar colours); fixed with a theme-independent style class (blue background, white text, with a `:backdrop` rule) installed once at USER priority. Item 15 (`GTK_USE_PORTAL=0` against the default): with `GTK_USE_PORTAL=0` the window looks very different (GTK's own dialogs and look); Phil prefers the default, so portal stays on and `os.environ.setdefault("GTK_USE_PORTAL", "1")` stays (`GTK_USE_PORTAL=0` still overrides it). Known limits: KDE's portal dialog may ask "overwrite?" for New on an existing name, after which the window refuses it (New never replaces a file); the Panel type row and the other panel-model items are unaffected.

**Toolbar, tree and tabbed pages (2026-10-15, plan `docs/superpowers/plans/2026-10-15-settings-tree.md`; design in `2026-10-14-panel-widget-model-design.md` section 7):** the window is a per-screen toolbar (the screen's name, Enable and the desktop's checkbox writing the monitor's `shell`, the panel type list with Add, Move up/down and Remove), a tree (Theme; each monitor, "(not connected)" when only in the config, with its panels by name; Detect monitors) and the selected page. Theme and monitor pages have the tabs General, Borders, Shadows, Handle and Layout (a monitor page under an always-shown override banner); each panel has its own page with the tabs Panel, Position, Handle, Interaction and Widget, and is renamed through the Name row. Every edit goes through one ordered queue (`settings/queue.py`): spin buttons share one 0.4 s timer, the last edit of a setting wins, structural edits, Undo, Save, leaving the config and Detect monitors apply the queue first, and a hand edit drops what is queued and the banner names it. Undo and Revert all are in the Edit menu only. The shell compares the config's monitor names with the connected ones (`shell/monitor_check.py`) and warns once per change of unknown names (a monitor seen connected in this session is never unknown); the window shows the same text, and a Detect monitors that returns no monitor keeps the list and says so. Known limits: no tree search or context menu; a right-click on a handle does not yet open that panel's page. Results (Phil, live on HDMI-A-1, 2026-10-16): all 15 gate items of the tree plan passed with no finding that needed a change.

**Input styles (2026-10-16, plan `docs/superpowers/plans/2026-10-16-input-styles.md`; design in `2026-10-14-panel-widget-model-design.md` section 8):** dropdowns open below their row at the size of their entries (`wrap_width` 1; the old placement laid the active entry over the combo and KWin shrank the menu), toggles are thin `Gtk.Switch`es with a round knob (one scoped stylesheet), whole numbers with a range of at most 500 are a slider plus a spin button (the wider ranges keep the spin button; the wheel never edits either), and fonts are a searchable popover picker over the installed families (the desktop's font first, then `monospace`, `sans-serif`, `serif`, then the families; a font that is not installed is kept; the theme's font list is one picker per family with Move up, Move down, Remove and Add font; a widget's font starts with "Theme font"). The theme's default font list is unchanged: the shell does not follow the KDE font by itself. Known limits: the font list is read once per window process; a dropdown's list may be a little narrower than its box; the popover list is the fallback if a dropdown still opens short. Results (Phil, live on HDMI-A-1, 2026-10-16): all 13 gate items passed. Findings and what was done: slider updates now happen on mouse-button release, not while the pointer pauses (a slow mouse wrote too often; the number beside the slider still follows the drag, a keyboard change or a trough click keeps the pause, and Undo, Save or a structural edit during a drag apply the current value); Page Up and Page Down were inverted (GTK's binding for a horizontal slider) and now raise and lower the value; the tree's row buttons read Up, Down, Remove from left to right (Remove was first) and are 27 px instead of 30; item 12 (narrow window) is accepted as expected: at the narrowest width a horizontal scrollbar appears and the Reset buttons are reached by scrolling, at the default 860 px nothing scrolls sideways; the dropdown fix (`wrap_width` 1) is confirmed working live (item 1 passed).

## 14. Open questions

- Should a pinned panel reserve space (push windows) or float over them? This spec assumes **float**.
- Should the settings window also expose a drag-and-drop layout editor, or only form fields? **v1 is forms only** (settings window plan, decision 1); drag-and-drop is revisited after Phil has used v1.

## 15. Implemented: handle customization and per-interaction toggles

Requested by Phil at Gate D of the core plan. It is not part of the core plan, but the core must not paint this into a corner.

**Requirements**

- The handle (today: three 3 px dots) is customizable per panel: shape, color (rest and hover), size, and position along the edge.
- Handle shapes include at least: dots, a thin bar, and a chevron/arrow. A chevron can **morph with the panel's depth**: pointing one way when collapsed, rotating to point the other way when expanded. **Implemented as a fold, not a rotation:** the chevron folds through a flat bar (a rotation would point along the edge half-way, which reads as "slide sideways"); handle plan decision 4, judged at its Gate A.
- The three interactions are individually opt-in/opt-out per panel: **click to toggle**, **hover to peek**, **drag to open**. Defaults stay all-on, so existing configs behave as today.
- A handle style may depend on which interactions are enabled (e.g. a thin bar when only drag is on, an arrow when only click is on).

**Design implications (for the future plan; nothing here changes the current core)**

- Config: a per-panel `[handle]` table (`shape`, `size`, `offset`, `color`, `hover_color`) and an `[interaction]` table (`click`, `hover`, `drag`, all default true) in the Pydantic models; the registry can supply per-widget defaults. Unknown shapes fail validation with the key path as elsewhere. **Added:** a `weight` key (dot diameter, bar and chevron thickness, needed for "thin bar") and a theme-wide `[theme.handle_style]` (a `[theme.handle]` table would clash with the existing `handle` colour key); widget defaults are validated at registration.
- Rendering: the handle moves from CSS-styled widgets to cairo drawing inside the panel canvas (or a dedicated drawing area), driven by a pure `draw_handle(cr, shape, ...)` plus a morph parameter derived from `d / depth`. That makes the arrow morph free and keeps shapes testable with the same headless pixel tests as the panels.
- Hit area vs visual: the clickable/hover/drag area stays a separate, larger target than the drawn shape.
- Behavior: `panel_state` and `EdgePanel` consult the interaction flags (no hover peek when hover is off; ignore press-drag when drag is off; the handle is not a button when click is off). Keyboard activation still follows the click flag. **Deviation:** with click off the handle stays a Gtk.Button that ignores clicks and cannot take focus; it is still the drag and hover target and carries the accessible name ("Drag to expand clock", or "clock handle" with drag off too).
- Diffing: handle and interaction changes are cheap in-place updates (restyle or flag change), not window rebuilds.
- Today's code touch points: `EdgePanel._build_handle`, `_place_handle`, the pointer handlers, the `.handle-dot` CSS in `shell/theme.py`, and the `handle`/`handle_hover` theme tokens.
- The settings window (section 13) exposes these controls.

**Implemented (2026-10-13, plan `docs/superpowers/plans/2026-10-13-handle-customization.md`):** the handle stays in the panel's own window: its Button is the hit target (click, keyboard, accessible name) and a `Gtk.DrawingArea` child draws it with the pure `draw_handle` (`shell/handle_draw.py`); the shape canvas is unchanged and the delayed re-raise stays (without it both the collapsed handles and the extended content are hidden, Gate B item 11, Phil, so drawing only the handle on the canvas could not retire it; `EDGE_SHELL_RAISE_MS=0` remains a debugging switch). Config: per panel `handle` (`shape` auto/dots/bar/chevron/none, `size` 4-40, `weight` 1-8, `offset`, `color`, `hover_color`) and `interaction` (`click`, `hover`, `drag`); theme-wide `[theme.handle_style]` (`shape`, `size`, `weight`, per monitor through the theme override; colours from `handle` / `handle_hover`); widget defaults through `PanelDefaults.handle` / `.interaction`, validated at registration. `auto` follows the interactions (dots; bar for drag only; chevron for click only; none when all are off); a panel with all three off never draws the theme's shape (only its own entry's or widget's) and each config load logs one INFO line naming it. The chevron folds through a flat bar as `d / depth` goes from 0 to 1. Placement: the shape's centre sits `T + d - min(T / 2, 5)` px from the screen edge, i.e. 5 px inside the body's leading edge (the band's inner edge while collapsed) from the default `T = 10` up, and in the middle of a thinner band; the shape is at most `shape_room(T) = band_room(min(T, 10))` px across (6 px from `T = 10` up, so 2 px of the band stay empty on both sides at `T = 10`; 4 / 5 / 4 / 2 / 0 at `T = 8 / 7 / 6 / 4 / 2`); a larger size or weight is clamped across; snapped to the pixel grid as a distance from the screen edge (the same rounding on every edge, so the four edges mirror each other). The hit target is at least 44 x 14 px (14 across on any frame) and rides the inner edge. Phil's Gate B finding at `thickness = 64` (the handle sat mid-body when extended, mid-band when collapsed, and the chevron grew with the frame) decided that handles hug the frame's inner edge and keep one small size at every thickness; the earlier "centred in the last `T` px, room `T - 2` or `band_room(T)`" rule, and decision 12's "thickness = 12 gives room 8", are superseded. Consequences: with `hover` off on a thick frame only the 14 px target toggles (the outer band is click-through, like the rest of the band); frames of 11-14 px move the handle 0.5-2 px toward the body edge; `T <= 10` renders byte-identically to before the change. Hover-only and all-off panels keep an invisible inert button over the inner 14 px of the extended body. Reload: a `panel-handle` change kind, applied in place (`EdgePanel.set_handle`); theme handle changes are a restyle; `-v` shows `building panel ...` for every panel built and the change kinds of every reload.

**Results.** Gate A (Phil, the PNG sheets): passed; defaults accepted (size 15, weight 3; at `T = 10` the chevron rises 3 px and is 6 px across); the chevron folds through a flat bar and reads fine at this height. Phil's answers to the open questions: 1, 2, 4, 5 and 6 as recommended (handle in the panel window; `auto` default; canonical snap; the handle lights up while peeking and all-off is allowed with one INFO line; a theme-level shape never draws on an all-off panel); 3: the fold kept, with the handle away from the band edges (2 px clear at the default theme), default thickness unchanged. Gate B (Phil, live on HDMI-A-1): passed. `--stats 10` on `examples/handles-test.toml`: 56.7 fps while animating; canvas damaged draws median 0.26 ms, p95 0.48 ms, max 0.56 ms; one full draw 1.55 ms; CPU 0.23 of a core; ticks between canvas draws: every panel 550-551 in step, 1-2 idle redraws, none skipped. The startup log showed the all-off INFO line and the `building panel` debug lines. The all-off panel (all three interactions false) drew nothing and was click-through. In-place edits, theme-level changes, invalid-shape rejection, the border and the thin frame items (including `thickness = 6`): no problems reported. At `thickness = 64` the handle was mid-body, mid-band and oversized (fixed, see above; the 64 px sheet looked good). Raise-off record run (`EDGE_SHELL_RAISE_MS=0`, item 11, observed after about 10 s): Phil answered "All hidden, content and handles", i.e. the collapsed handles and the extended content (dock icons, clock text, bar labels) were both hidden, so the canvas covers the panel windows until the delayed re-raise; the re-raise stays (decision 1).

## 16. Implemented: several panels on one edge (layout and separation)

Raised by Phil at Gate E of the core plan.

**Today (core plan, as built).** Each panel positions itself independently: `edge` plus `pos`, the distance in pixels along the edge where the panel body starts; no `pos` means centred. Nothing arranges panels relative to each other and nothing detects overlap: two centred panels on one edge sit on top of each other, and side-by-side placement means hand-computing `pos` values. The default layout avoids this by using a different edge per panel.

**Implemented (2026-10-13, plan `docs/superpowers/plans/2026-10-13-layout-anchoring.md`):** `shell/panel_layout.py` (`layout_edge`, `layout_monitor`) resolves every panel per edge from slots (start, center, end), `order` within a slot (ties keep config order) and one `gap` per monitor (`[layout]`, `[monitors.X.layout]`, default 8 px) measured between neighbouring joins, on top of `r1 + r2`. `pos` keeps its old meaning (pixels from the start of the edge) as a deprecated alias placed outside the slots; combining it with `align`/`offset` is a validation error whose message gives the conversion (`pos = N` = `align = "start"`, `offset = N - (T + R + r)`), and each config load logs one INFO line listing the entries still using it. The system bar's default moved from `pos = 600` to `align = "end"`, `offset = 142` (the same place as `pos = 600` only on a 1080 px tall monitor with edge right or left, length 300, depth >= 28 and the default thickness and radius; an entry overriding edge, length or depth without `pos`/`align`/`offset` moves, and each config load logs one INFO line listing such entries, with `pos = 600` as the way to keep the old place at 1080p). Gate B (live, 2026-10-13): no startup flash was visible with content panels, so the in-place resize stays unplanned; a resolution change (System Settings, HDMI-A-1 to 1280x720 and back) took the `notify::geometry` path (`re-laying out HDMI-A-1 for 1280x720`, then `for 1920x1080`, no shell reopen) and the collapsed handle dots survived it; a scale change is not verified. Overlaps hide the later panel (config order) with a notification. No `panel-move` change kind: moved panels are rebuilt; a `gap` change is a `relayout`.

Resolver details settled in review: spacing is rounded up per neighbour pair; a `MIN_LENGTH` floor (60 px) applies after the `max_length` clamp; extra warnings `{name}: no room after its neighbours in the {align} slot; moved to {q}` and `{name}: no room to fill; shown at 60 px`. Inside a slot the gap is always honoured; between different slot groups (start, centre, end) that run out of room only `r1 + r2` (not the gap) is guaranteed. Two panels meeting at a shared screen corner collide at offset 0; the minimum offset is the other panel's depth + r - R (its depth for panels at least 28 px deep). Verified live on HDMI-A-1 (Gates A and B, both passed): layout, offsets, the corner rule (offset 0 hides the later panel with a "Panels adjusted" notification, offset 46 shows it), fill/content/percent lengths, and the resolution-change re-layout. Gate B `--stats 10` on `examples/layout-sizes-test.toml`: 56.8 fps while animating, damaged canvas draws median 0.30 / p95 0.58 / max 1.00 ms, one full draw 1.60 ms, CPU 0.21 of a core. Known limits: HiDPI is unsupported (one warning); a "content" panel hidden at its default length is never measured and stays hidden.

**Requirements**

- Several panels can share an edge and be separated predictably, without hand-computed pixel offsets.
- Each panel can be placed by **alignment slot** (`start`, `center`, `end` of the edge), with an **order** within a slot and a configurable **gap** between neighbours. Explicit `pos` stays available as an override.
- Overlap is detected and reported (log plus notification, like config errors) instead of silently stacking; the shell still runs.
- Panels keep their own length and depth; the layout only decides the position along the edge.
- Corner interaction: the length available to an edge is the monitor extent minus the corner radius on each end, so slotted panels never run into the screen corners.

**Design implications (for the future plan)**

- Config: panel entries gain `align` (default `center`) and optionally `order`; a per-edge/per-monitor `gap` setting; `pos` remains and wins when present.
- Layout: a pure function (as built: `layout_edge` / `layout_monitor` in `shell/panel_layout.py`, no GTK) computes the positions per edge, so it is unit-testable like the geometry; `EdgePanel` takes a resolved `PanelGeometry`.
- Reload: reordering or changing `align`/`gap` moves panels, which today means rebuilding the affected panels' windows (their surface margin changes); the diff gains a `panel-move` change kind if rebuild flicker proves annoying.
- Handle placement (section 15) should be relative to the panel body, independent of the slot.
- The settings window (section 13) exposes slot, order and gap, and shows the overlap warning.

## 17. Implemented: panel anchoring, sizing and corner behaviour

Raised by Phil after Gate G of the core plan; the three choices below were decided with Phil. This extends section 16 and, with it, replaces today's `pos`-only placement.

**Behaviour of the core plan as built (for reference)**

- A panel attaches to one edge and is placed by `pos`: pixels from the **start** of the edge (left for top/bottom, top for left/right). There is no end-anchoring.
- `length` is a fixed pixel count. Depth grows only perpendicular to the edge, away from it.
- If `pos + length` runs past the end of the edge, the surface is shifted inward to stay on screen. If the panel is longer than the edge, it overhangs the far end and the screen clips it (untested). The only length bound is absolute (4000 px), unrelated to the monitor.
- Content is centred at its natural size; there is no fill, content-fit, percentage, or min/max.
- Panels have no corner awareness: the frame's rounded corner pieces are separate R x R windows, and a panel placed within about R + T of a screen corner overlaps them. Corner-spanning (L-shaped) panels are not built (superseded: corner panels are rectangles, see section 19).

**Decisions**

1. **Anchoring: `align` + `offset`.** `align = start | center | end` and `offset` is the distance in pixels from **that** end (default 0). A bottom-right bar is `edge = "bottom"`, `align = "end"`, `offset = 0`. This subsumes `pos` (start-aligned offset) and composes with the slot/order/gap layout of section 16.
2. **Sizing: `length` accepts a pixel number, `"fill"`, `"content"`, or a percentage** (e.g. `"50%"`), with optional `min_length` / `max_length`. `"fill"` spans the available span between the corner zones (minus gaps and neighbours); `"content"` wraps the widget's natural size; percentages are of the available span. Depth stays in pixels. Growth along the edge is from the anchored end toward the free side (an end-aligned panel grows toward the start).
3. **Overflow and corners: clamp to the free span.**
   - The **free span** of an edge is the monitor extent minus a corner clearance at each end (`T + R`, so panels never run into the rounded corner pieces; now `T + R + r`, see the Implemented note).
   - A requested length larger than the free span is **shrunk to fit**, with a log warning (and a notification on config reload); content that no longer fits is clipped. It is never a load-time error, so smaller or hot-plugged monitors keep working.
   - Offsets that would push a panel past the free span are clamped inward.
   - **Minimum geometry rules (found by the shape-canvas spike):** the single-outline renderer self-intersects (fills overlap, about 20-30 wrong pixels) when two curves collide. Two cases: (a) a panel whose concave fillet lands inside a screen-corner arc, so the **corner clearance is `pos - r >= T + R`** where `r = min(R, depth/2)` is the current join radius; (b) neighbouring panels on one edge whose fillets overlap, so the **minimum gap between adjacent panels is `r1 + r2`** (up to `2R` = 28 px at full depth). The layout resolver enforces both (clamping, with a warning); a panel exactly at the clearance renders correctly.
   - **Implemented (2026-10-13, layout plan):** the free span is `T + R + r` from each end; `length` takes px, `"fill"` (equal shares of what the neighbours, offsets and spacing leave), `"content"` (the content's natural size plus 12 px each side, measured once after build in an idle callback, the widget's default until then; a one-off startup rebuild of content panels, an in-place resize is planned only if a flash is observed) or a percentage of the free span, then `min_length`/`max_length` and a 60 px floor; too long is shrunk with a warning and the content is clipped (not scrolled) at the body edge and kept centred, never drawn over the joins and frame. `MonitorShell` re-lays out on the monitor's `notify::geometry` (debounced 250 ms; a zero geometry while unplugging is ignored), so centred, percentage and fill panels follow resolution changes. Two panels meeting at a shared screen corner collide at offset 0 (one needs an offset of at least the other's depth + r - R); a panel hidden by an overlap keeps its slot space; a re-layout the shell starts itself that fails is logged and rebuilds that monitor once, with a "Panels rebuilt" notification.
   - **Corner-spanning panels** (the original `widget_panel`, now `summary`: one free-edge join plus one join on the adjacent frame) are a separate widget type with their own geometry (`corner`, width, height), implemented, section 19; they are the only panels that meet two edges.

**Design implications (for the future plan)**

- Pure layout module (as built: `layout_edge` / `layout_monitor`, planned as `layout_edge(panels, extent, gap, radius, thickness) -> {panel: (offset, length)}`) resolving align/offset/length/fill/content/percent/min/max and the free span for each edge; no GTK, headless tests. `"content"` needs the widget's natural size, which comes from GTK, so the layout takes it as an input (measured once after build, re-measured on rebuild) and the pure function stays testable with fake sizes.
- Done: `anchor_and_margin` takes the resolved start; `EdgePanel` receives a resolved `PanelGeometry` (pos and length in px).
- Models: `PanelConfig` gains `align`, `offset`, `length: int | "fill" | "content" | str-percent`, `min_length`, `max_length`; `pos` is kept as a deprecated alias for start-aligned offset until removed.
- The free span depends on the monitor extent, so geometry/scale changes must trigger a re-layout; the same hook should handle that known gap.
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
- **Layout.** Corner panels first, one per corner (a second one in the same corner is hidden
  with a "Panels adjusted" notification), shrunk to fit beside each other (`along` at least
  max(T + 60, T + R + r); a corner panel hidden by an overlap takes no clearance); edge panels
  keep `along + r_c + gap + r` from a corner panel on their edge and `T + R + depth + r` from
  one on the neighbouring edge; the overlap check runs corners first. Corner panels take
  precedence over edge panels.
- **Config.** In `[[monitors.X.panels]]` with `panel = "corner"` (section 20; before it the
  kind came from the widget); keys `corner`, `edge`, `width`, `height`; mixing kinds is
  rejected with the key path. Reload: `panel-state`, `panel-handle` in place; size or corner
  changes rebuild.
- **Content.** `summary` (was `widget_panel`): time, date, CPU, RAM.
- **Decision recorded at Gate A.** Option A: at full depth the neighbouring edge panel on the
  other edge has no straight piece of frame between its fillet and the lifted corner arc (a
  stepped silhouette, valid geometry). Option B (an 8 px gap on the other edge too) was offered
  and not chosen; it stays open. Its cost: a `corner_clearance` condition, an extra `+ gap` in
  the corner layout's across check, and about 4 expected numbers (including Gate B's y 362-662
  becoming 354-654).

**Results.**

- **Gate A** (Phil, the PNG review sheets, no shell): passed; option A confirmed (see above).
- **Gate B** (Phil, live on HDMI-A-1): passed ("Gate B Passes"). From his log: the shell
  started with 5 panels built; restyle (effects) and panel-handle reloads applied in place (no
  `building panel` lines); `panel-state` in place; a width change rebuilt only panel 0
  (`widget_panel`, now `summary`) and panel 2 (clock); a width of 3000 shrank to 1882 and hid the dock and
  clock with warnings; invalid keys were rejected with key paths
  (`panels[0].align: widget_panel is a corner panel ...`,
  `panels[1].width: dock is an edge panel ...`, bad `state` and `align` values); a sixth entry
  in the same corner gave the "already holds ... not shown" warning; the resolution change to
  1280x720 logged `re-laying out HDMI-A-1 for 1280x720` with the system bar shrunk to 264
  ("Panels adjusted"), and back at 1920x1080. Per-item observations beyond the log, and the
  stacking check (item 12), were not recorded.
- **`--stats 10`** on `examples/corner-test.toml`: fps while animating 55.4; canvas damaged
  draws median 6.04 ms, p95 9.70 ms, max 10.82 ms; one full draw 15.13 ms; every panel 531-535
  ticks in step with one skipped; CPU 0.57 of a core. **The p95 is above the 8 ms target by
  1.7 ms.** The run's config copy still had the sixth same-corner entry and, judging by the 6 ms
  median (the headless run with border and shadow gave p95 6.5-7.1 ms; without effects the
  median is 0.29 ms and the p95 0.33 ms), border and shadow were probably still enabled. Phil accepted the result.
- **Performance attribution** (headless, 1920x1080, all panels toggling, border 2, elevation
  50). `examples/corner-test.toml` animates five panels (two corner, three edge) against three
  in `examples/panels-test.toml`: p95 6.5 against 4.2 ms. Its three edge panels alone give p95
  4.4 ms and its two corner panels alone 2.1 ms, about 0.95 ms per corner shape against about
  1.4 ms per edge panel. Per shape a corner panel costs no more than an edge panel; the p95
  rose with the number of animating panels. Phil's live p95 was 9.70 ms, 1.7 ms over the 8 ms
  target, accepted. Follow-up options, not done: the shadow strokes the whole outline path once
  per reach level (about 24 strokes), so the cost is mostly fixed per draw; drawing each
  damaged clip rectangle into its own small group, instead of one group over the bounding
  extents, cut the effects run by about 13 % in a scratch test (median 6.18 to 5.39 ms) with
  the damage contract holding; a tighter corner damage box alone gained only about 4 %, so it
  is not worth doing first.
- **Known limitations.** The summary block's (was `widget_panel`) first stats appear after
  about 1 s (`invoke_repeater` initial call). Corner widgets read `/proc` per instance (no
  shared sysinfo service). Edge widgets (clock, dock) in corners are deferred. A corner request
  with a height below T + 16 is hidden with a warning that names the height. The settings window must use the corner
  contract (`registry.widget_kind`, since removed in section 20; `registry.defaults`, `SHARED_KEYS`, `EDGE_ONLY_KEYS`,
  `CORNER_ONLY_KEYS`, `CORNERS`, `corner.split('-')`, `default_edge`, `corner_has_edge`); the
  settings plan (branch `feat/settings-window`, plan commit 427b1cd) already depends on it.


## 20. Implemented: the panel/widget model

Spec: `docs/superpowers/specs/2026-10-14-panel-widget-model-design.md` (sections 3-5). Plan:
`docs/superpowers/plans/2026-10-14-panel-widget-model.md`.

- **Entries.** Every `[[monitors.X.panels]]` entry has `panel` (edge | corner | float; float is
  reserved and rejected), `name` (1-40 characters, no control characters, no leading or
  trailing whitespace, unique per monitor)
  and `widget`. Other keys are the panel kind's keys or the widget's properties, flat in the
  same table; `PanelConfig` collects the latter in `widget_props` and
  `registry.validate_widgets` checks them against the widget's model. No aliases, no migration
  tool: the old format fails with one line saying what to add.
- **Widgets.** `Widget` classes (`shell/widget.py`) with a `WidgetProps` model, registered with
  `register_widget(id, title=, props=, edge=PanelDefaults|None, corner=CornerDefaults|None)`;
  `request_for` picks the defaults by `cfg.panel`; requests carry `name` and the validated
  props. Built in: `dock`, `clock`, `system_bar` (edge) and `summary` (corner; was
  `widget_panel`). The clock's `format` uses a fixed token table (`services/clock_format.py`:
  HH mm ss H h a ddd dd MMM MM yyyy, plus 'quoted text'), never strftime on user text; `font`
  (checked like the theme fonts) and `font_size` (6-96 pt) go into a provider on the clock's
  label. A property type the settings window cannot show is refused at registration. Every
  panel error writes the index in brackets (`monitors.X.panels[0].name: ...`).
- **Shell.** `MonitorShell` builds `EdgePanel` or `CornerPanel` by kind with a new widget
  instance; a change of name or props rebuilds that panel; a widget that fails to build is
  logged and left out, and the app sends "Panel not shown" naming it; it is tried again only
  when its entry (kind, widget, name or props) changes.
- **Settings window.** Panel titles use `name`; the add list shows widget titles and writes
  `{panel, name, widget}` with a free name; a Panel type row for widgets of several kinds
  (float greyed out); a Widget frame generated from the widget's property model; switching
  widget or kind is one edit that drops the keys the new one does not take.

**Results.** Gate (Phil, live on HDMI-A-1, 2026-10-14): all 13 checklist items, counted by Phil as 21 steps with the eight error cases of item 4 (a-h), passed with no failures: the start state and its four `building panel` lines (each panel built once, the clock at a fixed 320 px); the clock's `format`, quoted text, `font` and `font_size` by hand (one `panel-rebuild` each); a rename by hand; the eight error cases keeping the previous layout with the quoted notification texts; the settings window's panel list, Widget frame and add list; adding panels with free names (`Clock`, `Clock 2`); widget properties from the window; names in the window; switching the widget; Revert all; a hand edit while the window is open; `examples/corner-test.toml`; DP-1 untouched. The deferred-rebuild click fix (panel buttons keep the focus where it is) was not reported as a problem. Not checked live (covered by tests): a widget whose build raises and is not retried until its entry changes, a widget property type the window cannot show refused at registration, the Panel type row and the greyed-out `float` row (no built-in widget supports two panel kinds). Known limits: the duplicate-name error under a renamed row names the later entry's index in its path prefix (the message names both entries); a live theme-font change leaves an existing clock's font fallback until the panel is rebuilt.
