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
- [Settings window plan](docs/superpowers/plans/2026-10-14-settings-window.md)
- [Settings menus plan](docs/superpowers/plans/2026-10-15-settings-menus.md)

**Status:** early development.

## Features

- Independent frame and rounded corners per monitor, keyed by connector name. Each monitor
  has `shell = "edge" | "plasma" | "both" | "none"`; a monitor not listed gets nothing.
- One click-through shape canvas per monitor draws the frame, the rounded corners and every
  panel as one outline, so panels and frame join without seams.
- Optional outer border and soft uniform shadow (`[theme.border]`, `[theme.shadow]`),
  live-reloadable and overridable per monitor.
- Panels and widgets: a panel is the surface (`edge` or `corner`; `float` is reserved), a
  widget is what it shows: `dock` (bottom), `clock` (top; its format, font and font size are
  properties), `system_bar` (right), `summary` (a corner block: time, date, CPU and RAM).
  Every panel has a name, used in logs, notifications and the settings window.
- Corner panels: a rectangular panel in a screen corner, joined to both frame bands.
- Several panels per edge: align slots (start, center, end) with order and offset, a configurable gap, lengths in px, "fill", "content" or a percentage with optional min/max. Panels keep clear of the rounded screen corners and re-lay out when the monitor's resolution changes.
- Panel animation, hover peek, click to toggle, drag to open or close with a 50% snap.
- Live config reload: an invalid edit keeps the last good config and sends a notification.
- Monitor hot-plug, and per-monitor theme overrides scoped to that monitor.

## Requirements

- KDE Plasma 6 on Wayland (KWin implements `wlr-layer-shell`)
- Python 3.12+ with Fabric (from git), PyGObject **below 3.52**, pycairo, Pydantic 2, tomlkit
  (the settings window only: `scripts/py -m pip install 'tomlkit>=0.15'`)
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
scripts/py main.py --config examples/widget-props-test.toml -v  # panel names, clock properties
scripts/py main.py --config examples/panels-test.toml --stats 10  # 10 s measurement, then quit
scripts/py main.py --settings                              # the settings window (user config)
scripts/py main.py --settings --config /tmp/edge.toml      # ... on another file
scripts/py main.py --restore-config                        # put back config.toml.bak (the last Save)
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
panel = "edge"            # edge | corner (float: not implemented yet)
name = "Dock"             # unique on this monitor
widget = "dock"           # dock | clock | system_bar | summary
depth = 80                # edge, length, depth, state, align, offset, order override the defaults
```

### Panels

Each `[[monitors.NAME.panels]]` entry starts with three required keys:

- `panel`: the panel type. `edge` panels sit on one screen edge, `corner` panels in a screen
  corner (see Corner panels). `float` is reserved for later and rejected ("float panels are not
  implemented yet").
- `name`: 1-40 characters, no control characters, no space (or other whitespace) at the
  start or end, unique on its monitor (case-sensitive). It names the panel in logs, notifications and the settings window; panels are still matched by
  their place in the list, so a rename rebuilds the panel.
- `widget`: what the panel shows: `dock`, `clock`, `system_bar` (edge panels) or `summary`
  (corner panels). A widget on a panel type it does not support is rejected
  (`clock cannot be shown in a corner panel (it supports: edge)`).

Every other key is either a key of the panel type (below) or a property of the widget, written
in the same table. The clock's properties:

```toml
[[monitors.HDMI-A-1.panels]]
panel = "edge"
name = "Clock"
widget = "clock"
format = "ddd HH:mm:ss"   # tokens: HH mm ss H h a ddd dd MMM MM yyyy; 'quoted text'
font = "JetBrains Mono"   # a font family (default: the theme's font)
font_size = 14            # points, 6-96 (default: the theme's size)
```

The format takes only the tokens listed: `HH` hour 00-23, `H` 0-23, `h` 1-12, `a` AM/PM, `mm`
minute, `ss` second, `dd` day, `ddd` weekday, `MM` month, `MMM` month name, `yyyy` year.
Text in single quotes is shown as written (`"HH 'h' mm"`), two single quotes (`''`) are one
quote, and a quote that is not closed is an error. Any other ASCII letter is an error naming
its position; digits, spaces, punctuation and `%` are shown as written (never through strftime).

### Errors, failures and reloads

Errors name the entry's index in brackets (`monitors.HDMI-A-1.panels[2].format: ...`). A key
the widget does not have (`format: unknown key for widget 'dock'`), a bad value, a duplicate
name or a missing `panel` is reported with its key path; the shell keeps the previous layout
and sends a "Config not applied" notification.

A panel whose widget fails to build is left out (a "Panel not shown" notification names it);
the monitor's other panels stay, and it is tried again only when its `panel`, `widget`, `name`
or a widget property changes. Those four are also the reload kind `panel-rebuild`: changing
any of them rebuilds that panel (a new name or property value is not applied in place). State
and handle changes apply in place; geometry changes re-lay out the monitor.

The monitor's `shell` mode decides who draws it: `edge` (Edge Shell only), `both` (Edge Shell
and Plasma's own panel), `plasma` (Plasma only) and `none` (nothing). Panels are built only
for `edge` and `both`; the entries of a `plasma` or `none` monitor stay in the file, unused.

### Moving from the old format

A file whose entries have only `widget` (the old format) is refused with one line:
`widget = "..." (an entry with only a widget is the old format; see the README, "Panels")`.
There is no migration tool; add `panel` and `name` to every entry. The old corner widget id
`widget_panel` is now `summary`.

```toml
# before (refused)
[[monitors.HDMI-A-1.panels]]
widget = "clock"

[[monitors.HDMI-A-1.panels]]
widget = "widget_panel"
corner = "bottom-left"

# after
[[monitors.HDMI-A-1.panels]]
panel = "edge"
name = "Clock"
widget = "clock"

[[monitors.HDMI-A-1.panels]]
panel = "corner"
name = "Summary"
widget = "summary"
corner = "bottom-left"
```

### Edge panels

Panels are placed per edge in three slots and sized in one of four ways:

```toml
[[monitors.HDMI-A-1.panels]]
panel = "edge"
name = "Bottom clock"
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
panel = "corner"
name = "Summary"
widget = "summary"           # a widget registered with corner defaults
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
`pos`, `align`, `offset`, `order`, `length`, `min_length`, `max_length` and `depth` do not apply to corner panels, and `corner`,
`width` and `height` do not apply to edge panels: both are rejected with the key path.

### Handles and interactions

Each panel's handle and its three interactions can be set per panel entry; every key is
optional (a missing one comes from the theme):

```toml
[[monitors.HDMI-A-1.panels]]
panel = "edge"
name = "Clock"
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

### Settings window

`scripts/py main.py --settings` opens a normal window that edits your config file (the
`--config` file if given, else `~/.config/edge-shell/config.toml`; it is created on the first
change). A right-click on any panel handle (edge or corner panel) opens it too, on the
running shell's config file. There is one settings window per config file: opening it again on
the same file brings it forward; `--config` with another file opens a second window for that
file.

- **Menus.** **File**: New… (Ctrl+N), Open… (Ctrl+O), Save (Ctrl+S), Save As… (Shift+Ctrl+S),
  Close (Ctrl+W), Exit (Ctrl+Q). **Edit**: Undo (Ctrl+Z), Redo (Shift+Ctrl+Z or Ctrl+Y), Cut,
  Copy, Paste (Ctrl+X, Ctrl+C, Ctrl+V: in the focused text field; greyed out elsewhere),
  Revert all. **Help**: About Edge Shell (name, version, website, authors and the MIT licence).
  The Undo and Revert all buttons stay above the pages. Ctrl+Z in a text field undoes the last
  change to the file (the typed text is applied first); Ctrl+X/C/V work in text fields as
  everywhere in GTK.
- **Saving.** Changes still apply at once (the shell follows them). **Save** marks the file as
  it is now as saved and copies it to `config.toml.bak` (what `--restore-config` puts back);
  the title shows the file with a `*` while it has changes since the last save (or since it was
  opened). Close, Exit, New, Open and the window's close button ask **Save / Discard / Cancel**
  when there are such changes: Discard puts the file back as it was last saved (the shell
  follows; if the text it replaces is an invalid hand edit made while the window was open, that
  text is first kept as `config.toml.before-revert`; the file as it was when the window opened
  is not copied, it is the file as opened), Cancel stays.
  Undo back to the saved state is not a change. A hand edit made while the window is open
  counts as saved (it was saved in your editor): Discard never writes over it.
- **Files.** One window per config file. Open and New show the chosen file in its own window
  and close this one (after the question above). New writes a file with no keys (every value is
  a default), adds `.toml` to the name and never replaces an existing file. Save As writes the
  current settings to the chosen file (a file it replaces is kept as `NAME.before-save-as`,
  `.2`, `.3`, ..., next to the resolved file when NAME is a symlink), puts this file back as it was last saved, and shows the copy in its own
  window. Close leaves an empty window with New and Open; `main.py --settings` on its file (or
  a right-click on a panel handle) shows the file again. The shell reads only its own config
  (`~/.config/edge-shell/config.toml`, or its `--config` file): a window on another file says
  so once.
- **File dialogs** start in `~/.config/edge-shell` and are KDE's own, through the desktop
  portal (the settings process sets `GTK_USE_PORTAL=1` unless it is already set; start it with
  `GTK_USE_PORTAL=0 scripts/py main.py --settings` for GTK's own dialog).

- **Theme** page: every theme key, the border, the shadow, the handle style and the layout gap.
  One page per monitor (connected monitors and the ones in your config): the shell mode
  (`edge`, `plasma`, `both`, `none`), the panels (add, remove, move up or down; every panel key
  including the handle and interactions), a preview of the layout warnings the shell would
  give, and per-monitor theme and layout overrides.
- Each panel is listed by its name. The add list shows the widgets by their display names
  (Clock, Dock, Summary, System bar); a new panel gets the widget's first panel type
  and a name made from its display name that is free on that monitor (`Clock`, `Clock 2`).
  The rows start with Name, Widget and, for a widget that can be shown in more than one panel
  type, Panel type (float is listed and greyed out). A widget with properties gets a
  **Widget** frame with one row per property (the clock: Format, Font, Font size).
- Corner panels (for example `summary`) are in the same panel list. Their rows are corner,
  edge (only the corner's two edges), width and height instead of align, offset, length and
  depth. Switching a panel's widget, or its panel type, removes the keys the new kind or
  widget does not take in the same change (the name stays); moving a corner panel to a corner
  without its edge removes that edge. A name already used on the monitor is refused under the
  Name row.
- Each row shows the value in effect and where it comes from (`your config`, `default`,
  `global theme`, `widget default`, ...). The reset button removes the key from your file, so
  the value is inherited again.
- Changes apply at once (spin buttons 0.4 s after the last change; closing the window applies
  a pending one); the running shell reloads them like a hand edit. A change the shell would
  reject is not saved: the reason (with the key path) shows under the row. The mouse wheel
  scrolls the page and never changes a value, so scrolling past a monitor's mode cannot switch
  it.
- **Undo** (Ctrl+Z) steps back one change; **Revert all** puts the file back as it was when
  the window opened, or after your last hand edit. Before its first change, and at every Save,
  the window copies the file to `config.toml.bak` (same permissions); `scripts/py main.py --restore-config` puts
  that copy back (the replaced file is kept as `config.toml.before-restore`, or `.2`, `.3`, ...
  after an earlier restore). A hand edit that left the file invalid is not a starting point:
  Revert all then returns to the last valid state and keeps the invalid text as
  `config.toml.before-revert` (`.2`, `.3`, ... for later ones); the dialog says so.
- Your comments and formatting are kept: the window edits the file in place (tomlkit) and
  refuses a change it could not make without touching other keys or without losing a comment
  that sits above a table (`[monitors.DP-1]` and the like): edit the file by hand then. A
  comment run directly above a table header is that table's label and stays attached to it,
  also when keys or panels are added, moved or removed in the table before it. The comments
  directly above a `[[panels]]` entry are its label: they move and are removed with that
  panel. Adding a panel to an inline `panels = [{ ... }]` list is refused (add it by hand).
  If you edit the file by hand while the window is open, it re-reads it and tells you; it
  never writes over a hand edit, and Revert all never goes back past a valid one (an invalid
  one it replaces is saved as `.before-revert`). An invalid file opens read-only with
  the error until it is fixed; a folder it cannot write to is reported in the window.
- A symlinked config (for example from a dotfiles repository) keeps its link; the shell also
  watches the file it points to, so window changes and edits of that file reload the shell.

**Keyboard shortcut (KDE):** System Settings > Keyboard > Shortcuts > Add New > Command or
Script, command `/path/to/edge-shell/scripts/py /path/to/edge-shell/main.py --settings` on one
line, with `/path/to/edge-shell` replaced by the folder of your checkout (it must contain
`scripts/py`; check with `ls /path/to/edge-shell/scripts/py`). Append `--config FILE` if the
shell runs on another config. Then assign a key (suggested: Meta+Alt+E; any free key works).

`plasma` and `none` both leave a monitor to Plasma for now: hiding or showing Plasma's own
panel from the window is deferred (it needs the Plasma integration, spec section 7).

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
shells over it. New widgets go in `widgets/`: a `shell.widget.Widget` subclass (`build(props)`
returns its Gtk content, `destroy()` stops its timers) registered with
`@register_widget(id, title=..., props=..., edge=PanelDefaults(...), corner=CornerDefaults(...))`;
the property model (a `WidgetProps` subclass) gives the config keys and the settings window's
Widget rows. A property must be `str`, `int`, `bool`, a `Literal` of strings, or one of these
`| None` (the types the settings window has a row for): any other type, or a property named like
a panel key, is refused at import. Widgets never call cairo or layer-shell directly. CI runs lint and the display-free tests without GTK; tests
that need `gi` or Fabric skip themselves there.

## Known limitations / planned

- Plasma integration (workspaces panel, tray host, hiding Plasma's panel) is not built yet.
- Settings window: no Plasma panel toggle yet (hiding or showing Plasma's panel is deferred), no
  tray icon, no drag-and-drop layout; `pos` (deprecated) is shown and can be removed, not
  edited; a panel with click, hover and drag all off takes no input while collapsed, so its
  handle cannot open the window (use another handle, the shortcut or `--settings`); KWin
  chooses the window's monitor; inline `panels = [...]` lists are edited by hand.
- Settings window, editing limits: unsetting a whole table leaves that table's own label comment
  behind (not reachable from the window, which only resets single keys); after an edit a CRLF
  file may have `\n` endings on the lines the window writes (the session reads with universal
  newlines, so the first write rewrites CRLF as LF; the `.bak` stays byte-exact); a comment
  inside a multi-line array is dropped when that array is set.
- Settings window, start and close: at start `kscreen-doctor` is asked for the connected
  monitors and may delay the window by up to 5 s (if it fails, only the configured monitors are
  shown); `--config=~/x` is not expanded (use `--config ~/x`, or an absolute path, so the shell
  expands it); the first instance imports the widgets, which loads Fabric's typelibs (no layer
  surface is created); closing the window while the last write failed keeps it open once, so
  the error is seen, and the next close closes it; a right-click on a handle opens the window.
- Settings window, files: New, Open and Save As start a new settings process for the chosen
  file (the window may take a few seconds to appear: `kscreen-doctor`); this window closes as
  soon as it is started, so a window that fails to start shows nothing (run
  `scripts/py main.py --settings --config FILE` in a terminal to see why). Revert all and
  Discard cannot be undone; Revert all still goes back to the file as the window opened it
  (not to the last Save).
- The shell no longer exposes Fabric's D-Bus `Execute` / `Evaluate` methods (its D-Bus client
  is switched off, so `fabric-cli` cannot run code in it).
- Corner panels: one per corner; only widgets registered for corners (`summary`) can sit in a corner; no "content" length; a corner panel's sizes are fixed px (no percentages). Edge widgets (clock, dock) in corners are deferred. A corner request with a height below `T + 16` is hidden with a warning that names the height.
- Corner panels, Gate B (live, HDMI-A-1, Phil): passed. `--stats 10` on `examples/corner-test.toml` gave a damaged-draw p95 of 9.70 ms (median 6.04, max 10.82), above the 8 ms target by 1.7 ms. The run's config copy still had the sixth same-corner entry and border and shadow were probably still enabled; Phil accepted it. Where the cost comes from (headless, 1920x1080, all panels toggling, border 2 and elevation 50): `examples/corner-test.toml` animates five panels (two corner, three edge) against three in `examples/panels-test.toml`, so its p95 is 6.5 ms against 4.2 ms. Its three edge panels alone give p95 4.4 ms and its two corner panels alone 2.1 ms: about 0.95 ms per corner shape against about 1.4 ms per edge panel. Per shape a corner panel costs no more than an edge panel; the p95 rose with the number of animating panels. (0.29 ms is the median without effects; the no-effects p95 is 0.33 ms.)
- Performance follow-up options, not done: the shadow strokes the whole outline path once per reach level (about 24 strokes), so the cost is mostly fixed per draw. Drawing each damaged clip rectangle into its own small group, instead of one group over the bounding extents, cut the effects run by about 13% in a scratch test (median 6.18 to 5.39 ms) with the damage contract holding. A tighter corner damage box alone gained only about 4%, so it is not worth doing first.
- Corner panel watch items: the `summary` block's first stats appear after about 1 s (`invoke_repeater` initial call); corner widgets read `/proc` per instance (no shared sysinfo service); option B (an 8 px gap on the other edge too, so the neighbouring edge panel no longer meets the lifted corner arc without a straight piece of frame) was offered at Gate A and not chosen; it would cost a `corner_clearance` condition, an extra `+ gap` in the corner layout's across check, and about 4 expected numbers (including Gate B's y 362-662 becoming 354-654).
- Panel/widget model: float panels are reserved, not built; only the clock has properties so
  far; widget properties are limited to `str`, `int`, `bool` and string `Literal`s (no lists or
  floats yet); a renamed panel is rebuilt, not renamed in place.
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

## Licence

MIT (see `LICENSE`). Help > About in the settings window shows it.
