# edge-shell

A customizable desktop shell for KDE Plasma (KWin Wayland), built with
[Fabric](https://github.com/Fabric-Development/fabric). It draws a thin frame with rounded
inner corners around each configured monitor and grows panels out of that frame. It runs
alongside Plasma and does not replace it.

- [Design spec](docs/superpowers/specs/2026-10-11-edge-shell-design.md)
- [Implementation plan](docs/superpowers/plans/2026-10-11-edge-shell-core.md)

**Status:** early development.

## Features

- Independent frame and rounded corners per monitor, keyed by connector name. Each monitor
  has `shell = "edge" | "plasma" | "both" | "none"`; a monitor not listed gets nothing.
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

## Develop

```bash
scripts/py -m pytest -q                            # display-free tests
scripts/py -m ruff format . && scripts/py -m ruff check .
```

Pure logic lives in `shell/` (config, geometry, drawing, animation); GTK windows are thin
shells over it. New widgets go in `widgets/` and register with `@register`; they never call
cairo or layer-shell directly. CI runs lint and the display-free tests without GTK; tests
that need `gi` or Fabric skip themselves there.

## Known limitations / planned

- Plasma integration (workspaces panel, tray host, hiding Plasma's panel) is not built yet.
- A settings window is not built yet.
- Several panels on one edge are not auto-arranged (use `edge` + `pos`; overlap is not
  detected). Planned, see spec section 16.
- Handle customization (shape, color, size, position) and per-interaction opt-in/out
  (click, hover, drag) are planned, see spec section 15.
- Panel startup includes a brief re-raise about half a second after launch, needed to stack
  panels above the frame strips.
- Changing a connected monitor's resolution or scale does not reflow panels with an explicit
  `pos`; restart the shell or save the config. Planned fix.
