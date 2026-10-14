# edge-shell

A customizable desktop shell for KDE Plasma (KWin Wayland), built with
[Fabric](https://github.com/Fabric-Development/fabric). It draws a thin frame with rounded
inner corners around each configured monitor and grows panels out of that frame. It runs
alongside Plasma and does not replace it.

- [Design spec](docs/superpowers/specs/2026-10-11-edge-shell-design.md)
- [Implementation plan](docs/superpowers/plans/2026-10-11-edge-shell-core.md)
- [Shape canvas plan](docs/superpowers/plans/2026-10-13-shape-canvas-and-effects.md)
- [Layout and anchoring plan](docs/superpowers/plans/2026-10-13-layout-anchoring.md)
- [Handle customization plan](docs/superpowers/plans/2026-10-13-handle-customization.md)
- [Corner panel plan](docs/superpowers/plans/2026-10-14-corner-panel.md)

**Status:** early development.

## Features

- Independent frame and rounded corners per monitor, keyed by connector name. Each monitor
  has `shell = "edge" | "plasma" | "both" | "none"`; a monitor not listed gets nothing.
- One click-through shape canvas per monitor draws the frame, the rounded corners and every
  panel as one outline, so panels and frame join without seams.
- Optional outer border and soft uniform shadow (`[theme.border]`, `[theme.shadow]`),
  live-reloadable and overridable per monitor.
- Panels: `dock` (bottom), `clock` (top), `system_bar` (right).
- Corner panels: a rectangular panel in a screen corner, joined to both frame bands (`widget_panel`: time, date, CPU and RAM in the bottom-left corner).
- Several panels per edge: align slots (start, center, end) with order and offset, a configurable gap, lengths in px, "fill", "content" or a percentage with optional min/max. Panels keep clear of the rounded screen corners and re-lay out when the monitor's resolution changes.
- Panel animation, hover peek, click to toggle, drag to open or close with a 50% snap.
- Live config reload: an invalid edit keeps the last good config and sends a notification.
- Monitor hot-plug, and per-monitor theme overrides scoped to that monitor.

## Requirements

- KDE Plasma 6 on Wayland (KWin implements `wlr-layer-shell`)
- Python 3.12+ with Fabric (from git), PyGObject **below 3.52**, pycairo, Pydantic 2
- `gtk-layer-shell`, `kscreen-doctor`; fonts Hack Nerd Font Mono and JetBrains Mono

PyGObject must stay below 3.52: Fabric 0.0.2 breaks on newer versions
(`TypeError: Unsupported type for GtkLayerShell.Layer`).

## Run

```bash
scripts/py main.py --list-outputs                          # monitors and connector names
scripts/py main.py --config examples/hdmi-test.toml -v     # frame only, on HDMI-A-1
scripts/py main.py --config examples/dock-test.toml -v     # frame + dock
scripts/py main.py --config examples/panels-test.toml -v   # frame + dock, clock, system bar
scripts/py main.py --config examples/effects-test.toml -v  # with border and shadow
scripts/py main.py --config examples/layout-test.toml -v        # several panels per edge
scripts/py main.py --config examples/layout-sizes-test.toml -v  # fill, content, percent
scripts/py main.py --config examples/corner-test.toml -v      # corner panels next to edge panels
scripts/py main.py --config examples/panels-test.toml --stats 10  # 10 s measurement, then quit
```

`scripts/py` runs the shared venv; override it with `EDGE_SHELL_PYTHON=/path/to/python`.
Only one instance can run (Fabric names the app `edge-shell`). Quit a backgrounded copy
with `fg`, then Ctrl+C.

## Configure

`config.default.toml` lists every key. Your config (`~/.config/edge-shell/config.toml`, or
`--config PATH`) is overlaid on it and reloads live when saved.

```toml
[monitors.HDMI-A-1]
shell = "edge"            # edge | plasma | both | none

[monitors.HDMI-A-1.theme]
accent = "#d3a68f"        # overrides the global theme for this monitor only

[[monitors.HDMI-A-1.panels]]
widget = "dock"           # dock | clock | system_bar
depth = 80                # edge, length, depth, state, align, offset, order override the defaults
```

Panels are placed per edge in three slots and sized in one of four ways:

```toml
[[monitors.HDMI-A-1.panels]]
widget = "clock"
edge = "bottom"
align = "end"             # start | center (default) | end of the edge
offset = 0                # px from that end (centre: shifts the centre group); for a later panel in the slot: extra space before it
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
with `align` or `offset`, and every config load or reload logs one line listing the entries
that use it. A lone `pos = N` equals `align = "start"`, `offset = N - 38` at the default theme
(38 = `thickness + radius + join radius`; 32-38 px depending on the panel's depth). The system
bar's own default moved from `pos = 600` to `align = "end"`, `offset = 142`. That is the same
place as `pos = 600` only on a 1080 px tall monitor with `edge` right (or left), `length` 300,
`depth` of at least 28 and the default thickness and radius (y = 600). An entry that overrides
`edge`, `length` or `depth` without `pos`/`align`/`offset` now moves (at 1080p: `edge = "top"`
moves x from 600 to about 1440, `length = 524` moves y from 518 to 376, `depth = 20` gives 604,
`thickness = 20` gives 590); add `pos = 600` to keep the old place at 1080p. Each config load
logs one INFO line listing such entries. On other monitors the bar sits 142 px from the end of
the free span (y = 960 at 1440 px, y = 240 at 720 px, where `pos = 600` gave 600 and, clamped,
382).

Colours are `#rrggbb` or `#rrggbbaa`. Border and shadow are off unless enabled:

```toml
[theme.border]
enabled = true
width = 2                 # px, drawn outside the frame and panels (on the desktop side)
color = "#8fd3b6ff"

[theme.shadow]
enabled = true
elevation = 50            # 0-100 %; 100 % reaches 48 px
color = "#00000080"       # the alpha is the strength

[monitors.HDMI-A-1.theme.shadow]
elevation = 80            # per monitor; the other shadow keys still come from [theme.shadow]
```

The border adds to the overall size: the frame band keeps its thickness (a 10 px frame with
a 4 px border occupies 14 px), the shadow is measured from the outer border edge, and the
frame strips reserve thickness plus border width while the border is enabled.

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
The handle sits at a fixed inset from the body's inner edge (5 px; centred in the band on a
frame thinner than 10 px) and keeps a constant size on a thick frame: a shape is drawn at
most 6 px across the band (4 to 0 px on frames of 8 px and thinner), so a larger `weight`, or
a chevron taller than that, is drawn smaller across, never over the band's edges. The hit
target is 14 px across at any frame thickness and rides the inner edge; with `hover` off on a
thick frame only that target toggles, the rest of the band is click-through.
A panel with all three interactions off opens and closes only through `state`; it draws no
handle unless its own entry (or its widget) sets a shape, and each config load logs one INFO
line naming such panels. Handle and interaction changes apply in place on reload.
`scripts/py -m shell.handle_draw --sheet /tmp/handles.png` renders every shape for a look
without starting the shell.

## Develop

```bash
scripts/py -m pytest -q                            # display-free tests
scripts/py -m ruff format . && scripts/py -m ruff check .
scripts/py -m shell.canvas.simulate --elevation 50 --border 2   # headless canvas benchmark
scripts/py -m shell.canvas.simulate --config examples/layout-test.toml   # a config's layout, headless
scripts/py -m shell.handle_draw --sheet /tmp/handles.png        # every handle shape, enlarged
scripts/py -m shell.canvas.corner_sheet --out /tmp/corners.png       # corner panels in every corner, enlarged
```

`EDGE_SHELL_RAISE_MS=0` disables the startup re-raise of panels (debug switch only; the
re-raise is still needed, see Known limitations).

Pure logic lives in `shell/` (config, geometry, panel layout, animation) and `shell/canvas/`
(outline, effects, scene, damage); GTK windows are thin
shells over it. New widgets go in `widgets/` and register with `@register`; they never call
cairo or layer-shell directly. CI runs lint and the display-free tests without GTK; tests
that need `gi` or Fabric skip themselves there.

## Known limitations / planned

- Plasma integration (workspaces panel, tray host, hiding Plasma's panel) is not built yet.
- A settings window is not built yet. It must use the corner panel contract: `registry.widget_kind`, `registry.defaults`, `SHARED_KEYS` / `EDGE_ONLY_KEYS` / `CORNER_ONLY_KEYS`, `CORNERS`, `corner.split('-')`, `default_edge` and `corner_has_edge` (the settings plan on branch `feat/settings-window` already depends on it).
- Corner panels: one per corner; only corner widgets (`widget_panel`) can sit in a corner; no "content" length; a corner panel's sizes are fixed px (no percentages). Edge widgets (clock, dock) in corners are deferred. A corner request with a height below `T + 16` is hidden as "no room".
- Corner panels, Gate B (live, HDMI-A-1, Phil): passed. `--stats 10` on `examples/corner-test.toml` gave a damaged-draw p95 of 9.70 ms (median 6.04, max 10.82), above the 8 ms target by 1.7 ms. The run's config copy still had the sixth same-corner entry and border and shadow were probably still enabled; Phil accepted it. Corner shapes with border and shadow cost about 50% more per damaged draw than the edge-only example (headless 6.5 ms against 4.2 ms), so the p95 exceeded 8 ms on Phil's machine in the effects configuration.
- Corner panel watch items: the `widget_panel`'s first stats appear after about 1 s (`invoke_repeater` initial call); corner widgets read `/proc` per instance (no shared sysinfo service); option B (an 8 px gap on the other edge too, so the neighbouring edge panel no longer meets the lifted corner arc without a straight piece of frame) was offered at Gate A and not chosen; it would cost a `corner_clearance` condition, an extra `+ gap` in the corner layout's across check, and about 4 expected numbers (including Gate B's y 362-662 becoming 354-654).
- Moving a panel (a layout change on reload or a resolution change) rebuilds its window; there
  is no in-place move yet. "content" panels are built twice at startup (default length, then
  measured); no startup flash was visible with content panels at Gate B, so an in-place resize stays
  unplanned. A "content" panel that is hidden at its default length is never measured and stays
  hidden.
- Handle customization watch items: the chevron's half-pixel parity jump during the morph (within
  1 px, no wobble reported at Gate B); under an RTL locale the along-edge `handle.offset` would
  flip (pre-existing behaviour); hover-only and all-off panels keep an invisible inert button
  over the inner 14 px of the extended body; keyboard activation of the handle cannot be tested
  live (built-in panels use `keyboard_mode = "none"`); the handle-draw and edge-panel tests are
  skipped in CI (no `gi`), the pure tests run.
- Panel startup includes a brief re-raise (`raise_to_top`) about half a second after launch.
  Live testing showed it is still needed: with the raise off, the collapsed handles and the
  extended content (dock icons, clock text, bar labels) were both hidden (Plan 3 Gate B
  item 11, Phil), so the canvas covers the panel windows until the delayed re-raise; drawing
  only the handle on the canvas could not remove the workaround. `EDGE_SHELL_RAISE_MS=0`
  remains a debugging switch.
- One layout gap per monitor (no per-edge gap). Resolution changes re-lay out panels (verified live on
  HDMI-A-1: 1920x1080 to 1280x720 and back, via `notify::geometry`, with no shell reopen and the
  collapsed handle dots intact); a scale change is not verified, and HiDPI drawing is not
  supported yet (see below).
- The frame band is click-through: clicks on the frame reach the desktop.
- HiDPI / fractional scaling: the canvas assumes scale 1 (it logs a warning otherwise).
- `--stats` mixes scene keys across monitors when two or more monitors are configured.
- The "Panels adjusted" notification is not repeated after an unplug and replug that yields
  identical layout warnings.
- On a dark wallpaper the border and shadow are faint; raise the shadow alpha or elevation.
