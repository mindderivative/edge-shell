# edge-shell

A customizable desktop shell for KDE Plasma (KWin Wayland), built with
[Fabric](https://github.com/Fabric-Development/fabric). It draws a thin frame with rounded
inner corners around each configured monitor and grows panels out of that frame. It runs
alongside Plasma and does not replace it.

- [Design spec](docs/superpowers/specs/2026-10-11-edge-shell-design.md)
- [Implementation plan](docs/superpowers/plans/2026-10-11-edge-shell-core.md)
- [Shape canvas plan](docs/superpowers/plans/2026-10-13-shape-canvas-and-effects.md)

**Status:** early development.

## Features

- Independent frame and rounded corners per monitor, keyed by connector name. Each monitor
  has `shell = "edge" | "plasma" | "both" | "none"`; a monitor not listed gets nothing.
- One click-through shape canvas per monitor draws the frame, the rounded corners and every
  panel as one outline, so panels and frame join without seams.
- Optional outer border and soft uniform shadow (`[theme.border]`, `[theme.shadow]`),
  live-reloadable and overridable per monitor.
- Panels: `dock` (bottom), `clock` (top), `system_bar` (right).
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
depth = 80                # edge, pos, length, depth, state override the widget's defaults
```

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

## Develop

```bash
scripts/py -m pytest -q                            # display-free tests
scripts/py -m ruff format . && scripts/py -m ruff check .
scripts/py -m shell.canvas.simulate --elevation 50 --border 2   # headless canvas benchmark
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
- A settings window is not built yet.
- Several panels on one edge are not auto-arranged (use `edge` + `pos`). A panel too close
  to a screen corner is moved, one that overlaps an earlier panel (or leaves less than the
  minimum gap between their joins) is hidden; both send a notification. Planned: spec 16-17.
- Handle customization (shape, color, size, position) and per-interaction opt-in/out
  (click, hover, drag) are planned, see spec section 15.
- Panel startup includes a brief re-raise (`raise_to_top`) about half a second after launch.
  Live testing showed it is still needed: without it the collapsed handle dots are hidden
  behind the canvas. `EDGE_SHELL_RAISE_MS=0` turns it off for debugging.
- Changing a connected monitor's resolution or scale does not reflow panels: neither those
  with an explicit `pos` nor, since the shape canvas, centred ones (every position is
  resolved once, when the panel is built). Restart the shell or save a change to the config. Planned fix.
- The frame band is click-through: clicks on the frame reach the desktop.
- HiDPI / fractional scaling: the canvas assumes scale 1 (it logs a warning otherwise).
- `--stats` mixes scene keys across monitors when two or more monitors are configured.
- The "Panels adjusted" notification is not repeated after an unplug and replug that yields
  identical layout warnings.
- On a dark wallpaper the border and shadow are faint; raise the shadow alpha or elevation.
