# Edge Shell Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a config-driven Edge Shell: a per-monitor frame with rounded corners and animated, draggable panels (dock, clock, system bar) that fuse with the frame, live-reload from a TOML file, and survive monitor hot-plug.

**Architecture:** Pure-Python logic (config models, geometry, drawing, animation, diffing) is built and unit-tested first with no display. GTK/Fabric windows (`FrameEdge`, `ScreenCorner`, `EdgePanel`) are thin shells over that logic. A `ConfigStore` + `diff_configs` turns file edits into minimal window changes. Anything that renders to screen ends in a **visual gate** where Phil (the visual tester) checks the result on `HDMI-A-1`.

**Tech Stack:** Python 3.14 (>=3.12 supported), Fabric 0.0.2, PyGObject 3.50.0 (`<3.52`), pycairo, GtkLayerShell, Pydantic 2, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-10-11-edge-shell-design.md`

**Scope of this plan:** spec milestones 1-6 (config layer, frame, panels, animation, remaining edge panels, drag, live reload, hot-plug). **Not in this plan** (separate follow-up plans): milestone 7 (Plasma integration, workspaces panel, tray, Plasma-panel toggle, and its spike 2) and milestone 8 (corner widget panel, settings window). Spike 1 is already answered (Task 2). Spike 3 is folded into Gates A and B.

## Global Constraints

- Python: use `/home/phil/Projects/pyDev/pyEnvs/global-base` through `scripts/py`. Fabric 0.0.2, PyGObject **3.50.0**, pycairo, Pydantic 2.14 are already installed there.
- **PyGObject must stay `<3.52`** (3.52+ breaks Fabric: `TypeError: Unsupported type: <enum 'Layer'>`).
- Wayland + `wlr-layer-shell` only; no X11. Windows use `fabric.widgets.wayland.WaylandWindow`.
- Frame strips use `exclusivity="auto"`. Corners and panels use `exclusivity="none"` and then `GtkLayerShell.set_exclusive_zone(self, -1)` immediately after `super().__init__()`. `"normal"` is never used (it reserves 1 px).
- Defaults: `T`=10, `R`=14, peek=14, hover zone=16, duration=280 ms, easing `cubic-bezier(.2,.8,.2,1)`, content fade 170 ms starting 110 ms in, click threshold 4 px, snap at 50%.
- Colors: frame `#0b0c0d`, text `#e6e8ea`, secondary `#9ba0a6`, accent `#8fd3b6`, handle `#7b7f84`, handle hover `#e6e8ea`. Font list `["Hack Nerd Font Mono", "JetBrains Mono", "monospace"]`.
- Monitors are keyed by **connector name** (`DP-1`, `HDMI-A-1`), never by index. Gdk monitors map to names by geometry against `kscreen-doctor -j` (`Gdk.Monitor.get_model()` is not a connector name).
- Frames are independent per monitor. Monitor mode `shell` is one of `edge | plasma | both | none`; a monitor absent from the config behaves as `plasma` (Edge Shell builds nothing).
- Pure modules import no GTK/`gi`: `shell/geometry.py`, `shell/draw.py`, `shell/anim.py`, `shell/theme.py`, `shell/panel_state.py`, `shell/panel_spec.py`, `shell/registry.py`, `shell/plan.py`, `shell/outputs.py`, `shell/config/*` (except `watcher.py`).
- `widgets/*` never call cairo or GtkLayerShell. `services/*` never build widgets.
- Never own a D-Bus name Plasma already holds. Do not use `fabric.system_tray`, `fabric.notifications`, `fabric.audio`, `fabric.bluetooth`.
- Windows must be given their monitor as an **integer Gdk index** via `shell.gdk_util.monitor_index(monitor)`. Fabric's `monitor` property is an int; a `Gdk.Monitor` object is silently dropped and KWin then uses its default output (found at Gate A).
- Never touch the Plasma panel on `DP-1` in this plan. All on-screen testing happens on `HDMI-A-1`.
- Every commit message ends with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` (shown as a second `-m` below).
- **VERIFY** (run before every commit): `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`

## Review Focus

Failure modes the spec implies but that are easy to miss. Each has a pinning test in the task named.

1. A config file saved mid-edit (invalid TOML, unknown key, unknown widget) must **keep the last good config** and report the error, never crash. (Task 6)
2. A config naming a monitor that is **not connected** is skipped, not an error. (Task 12)
3. `pos` far beyond the screen is **clamped** so the panel stays on screen. (Task 7)
4. Zero, negative or huge sizes are **rejected with the key path** in the message. (Task 3)
5. When Gdk's monitor order changes but connector names do not, shells stay bound to the right connector; a replugged connector (new Gdk monitor object) is rebuilt. (Task 12)

## File Structure

```
scripts/py                    # runs global-base python (override with EDGE_SHELL_PYTHON)
pyproject.toml                # deps + pytest/ruff config
config.default.toml           # every key + its default
examples/hdmi-test.toml       # runs Edge Shell on HDMI-A-1 only
main.py                       # CLI entry point
shell/__init__.py
shell/config/{__init__,models,loader,store,diff,watcher}.py
shell/{panel_spec,registry,geometry,draw,anim,theme,panel_state,outputs,plan}.py
shell/{frame,monitors,edge_panel,app}.py        # GTK / Fabric
widgets/{__init__,dock,clock,system_bar}.py     # registered panel widgets
services/{__init__,sysinfo}.py
tests/                        # pytest; no display needed
docs/superpowers/findings/    # spike notes
.github/workflows/ci.yml
```

| File | Responsibility |
| --- | --- |
| `shell/config/models.py` | Pydantic models, `ConfigError`; no GTK |
| `shell/config/loader.py` | defaults + user overlay, validation, readable errors |
| `shell/config/store.py` | holds the current config; `reload()` keeps the old one on error |
| `shell/config/diff.py` | old/new config -> list of `Change` |
| `shell/config/watcher.py` | `Gio.FileMonitor` + debounce (only GTK file here) |
| `shell/panel_spec.py` | `PanelDefaults`, `PanelGeometry` dataclasses |
| `shell/registry.py` | `@register`, `resolve_panel`, `panels_for`, `validate_widgets` |
| `shell/geometry.py` | edge maths, rects, anchor/margin (pure) |
| `shell/draw.py` | cairo drawing of panels and screen corners (pure cairo) |
| `shell/anim.py` | easing + `Tween` driven by a frame clock |
| `shell/theme.py` | theme -> CSS string and rgba tuples |
| `shell/panel_state.py` | click/drag/hover state maths |
| `shell/outputs.py` | parse `kscreen-doctor -j`, match Gdk geometry -> connector |
| `shell/plan.py` | which monitors get shells; reconcile active vs desired |
| `shell/frame.py` | `FrameEdge`, `ScreenCorner` windows |
| `shell/edge_panel.py` | `EdgePanel` base window |
| `shell/monitors.py` | Gdk<->connector mapping, `MonitorShell` |
| `shell/app.py` | wires config -> monitors -> windows; reload + hot-plug |

---

### Task 1: Project scaffold and test tooling

**Files:**
- Create: `scripts/py`, `pyproject.toml`, `shell/__init__.py`, `shell/config/__init__.py`, `widgets/__init__.py`, `services/__init__.py`, `tests/test_smoke.py`

**Interfaces:**
- Produces: `scripts/py` (all later commands use it), pytest with `pythonpath = ["."]`, ruff config.

- [ ] **Step 1: Install dev tools into global-base** (this adds two dev packages to the shared venv; Phil approved reviewing this plan, flagged in the handoff)

```bash
uv pip install --python /home/phil/Projects/pyDev/pyEnvs/global-base/bin/python pytest ruff
```
Expected: `Installed 2+ packages` (pytest, ruff and their deps).

- [ ] **Step 2: Create `scripts/py`**

```bash
mkdir -p scripts shell/config widgets services tests examples
cat > scripts/py <<'EOF'
#!/usr/bin/env bash
# Runs the project's Python (the shared global-base venv). Override with EDGE_SHELL_PYTHON.
exec "${EDGE_SHELL_PYTHON:-/home/phil/Projects/pyDev/pyEnvs/global-base/bin/python}" "$@"
EOF
chmod +x scripts/py
touch shell/__init__.py shell/config/__init__.py widgets/__init__.py services/__init__.py
```

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[project]
name = "edge-shell"
version = "0.1.0"
description = "Customizable Fabric desktop shell for KDE Plasma (Wayland)"
requires-python = ">=3.12"
# Fabric (Fabric-Development/fabric) is installed from git into global-base; the PyPI
# package named "fabric" is a different project. PyGObject must stay below 3.52.
dependencies = ["pydantic>=2.6", "PyGObject<3.52", "pycairo"]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
ignore = ["E402"]  # gi.require_version() must precede imports in GTK modules
```

- [ ] **Step 4: Write a smoke test**

```python
# tests/test_smoke.py
def test_shell_package_imports():
    import shell  # noqa: F401
```

- [ ] **Step 5: Run VERIFY**

Run: `scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q`
Expected: `1 passed`

- [ ] **Step 6: Commit**

```bash
git add scripts pyproject.toml shell widgets services tests
git commit -m "chore: project scaffold, pytest and ruff config" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Record spike 1 and amend the spec

**Files:**
- Create: `docs/superpowers/findings/2026-10-11-monitor-names.md`
- Modify: `docs/superpowers/specs/2026-10-11-edge-shell-design.md` (section 5.3 and section 11)

- [ ] **Step 1: Write the findings note**

```markdown
# Finding: Gdk monitors do not expose connector names

Date: 2026-10-11 · Spike 1 (spec section 11)

**Question:** does `Gdk.Monitor.get_model()` return the connector name under GTK3 on KWin Wayland?

**Answer: no.** On this machine both monitors return the panel model, `G24M2020G`
(manufacturer `AMZ`), so it cannot tell them apart.

| Gdk index | model | geometry |
| --- | --- | --- |
| 0 | G24M2020G | 0,0 1920x1080 (= HDMI-A-1) |
| 1 | G24M2020G | 0,1080 1920x1080 (= DP-1) |

**Decision:** map Gdk monitors to connector names by geometry against
`kscreen-doctor -j`, which reports for each output `name`, `enabled`, `pos{x,y}`,
`size{width,height}` and `scale`. Logical size = `round(size / scale)`. Match on
position + logical size, falling back to position alone.
```

- [ ] **Step 2: Amend the spec** (use the Edit tool with these exact strings; the backslashes before backticks below only escape them for this document, so type plain backticks)

In `docs/superpowers/specs/2026-10-11-edge-shell-design.md`:

Replace
`1. Does \`Gdk.Monitor.get_model()\` return the connector name under GTK3 on KWin? If not, use geometry matching against \`kscreen-doctor -j\`.`
with
`1. **Resolved:** \`Gdk.Monitor.get_model()\` returns the panel model, not the connector (both monitors report \`G24M2020G\`). Gdk monitors are mapped to connector names by geometry against \`kscreen-doctor -j\`. See \`docs/superpowers/findings/2026-10-11-monitor-names.md\`.`

Replace
`3. With frame strips, corners and one panel on \`HDMI-A-1\`, do maximized windows stop at the frame and does the panel fuse with it? Phil verifies visually.`
with
`3. **Folded into the build:** frame strips, corners and the dock are built for real in milestones 2-3; Phil's visual gates A and B answer this. If either gate fails, stop and choose the single-canvas fallback in 5.1.`

Replace
`Monitors are keyed by **connector name** (\`DP-1\`, \`HDMI-A-1\`), never by index.`
with
`Monitors are keyed by **connector name** (\`DP-1\`, \`HDMI-A-1\`), never by index. Gdk monitors are mapped to connector names by geometry against \`kscreen-doctor -j\`.`

- [ ] **Step 3: Commit**

```bash
git add docs
git commit -m "docs: record monitor-name spike, amend spec" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Config models

**Files:**
- Create: `shell/config/models.py`, `tests/conftest.py`, `tests/test_config_models.py`

**Interfaces:**
- Produces:
  - `Edge`, `PanelState`, `ShellMode` (Literal types)
  - `ConfigError(Exception)`
  - `Theme` (frozen; fields `frame, text, text_secondary, accent, handle, handle_hover, surface_hover, thickness, radius, peek, hover_zone, duration_ms, font`)
  - `PanelConfig(widget, edge, pos, length, depth, state)` (all but `widget` optional; `pos` may be `"center"`)
  - `MonitorConfig(shell="plasma", theme=ThemeOverride(), panels=[])`
  - `Config(theme, monitors)` with `.monitor(name) -> MonitorConfig` and `.theme_for(name) -> Theme`
  - conftest fixture `make_config(monitors=None, theme=None) -> Config`, constant `THEME`

- [ ] **Step 1: Write conftest and failing tests**

```python
# tests/conftest.py
import pytest

from shell.config.models import Config

THEME = {
    "frame": "#0b0c0d",
    "text": "#e6e8ea",
    "text_secondary": "#9ba0a6",
    "accent": "#8fd3b6",
    "handle": "#7b7f84",
    "handle_hover": "#e6e8ea",
    "surface_hover": "#1d2024",
    "thickness": 10,
    "radius": 14,
    "peek": 14,
    "hover_zone": 16,
    "duration_ms": 280,
    "font": ["Hack Nerd Font Mono", "JetBrains Mono", "monospace"],
}


@pytest.fixture
def make_config():
    def _make(monitors=None, theme=None) -> Config:
        return Config.model_validate(
            {"theme": {**THEME, **(theme or {})}, "monitors": monitors or {}}
        )

    return _make
```

```python
# tests/test_config_models.py
import pytest
from pydantic import ValidationError

from shell.config.models import PanelConfig


def test_valid_minimal(make_config):
    cfg = make_config()
    assert cfg.theme.thickness == 10
    assert cfg.monitors == {}


def test_hex_color_normalized_to_lowercase(make_config):
    assert make_config(theme={"frame": "#0B0C0D"}).theme.frame == "#0b0c0d"


def test_bad_color_rejected_with_key_path(make_config):
    with pytest.raises(ValidationError) as exc:
        make_config(theme={"frame": "red"})
    assert exc.value.errors()[0]["loc"] == ("theme", "frame")


def test_unknown_key_rejected(make_config):
    with pytest.raises(ValidationError) as exc:
        make_config(theme={"bogus": 1})
    assert exc.value.errors()[0]["loc"] == ("theme", "bogus")


@pytest.mark.parametrize(
    ("theme", "field"),
    [
        ({"thickness": 0}, "thickness"),
        ({"radius": 0}, "radius"),
        ({"thickness": 9999}, "thickness"),
        ({"duration_ms": -1}, "duration_ms"),
    ],
)
def test_theme_bounds(make_config, theme, field):
    with pytest.raises(ValidationError) as exc:
        make_config(theme=theme)
    assert exc.value.errors()[0]["loc"] == ("theme", field)


@pytest.mark.parametrize(
    ("panel", "field"),
    [
        ({"widget": "dock", "length": 0}, "length"),
        ({"widget": "dock", "depth": -5}, "depth"),
        ({"widget": "dock", "length": 999999}, "length"),
        ({"widget": "dock", "state": "open"}, "state"),
        ({"widget": "dock", "edge": "middle"}, "edge"),
    ],
)
def test_panel_bounds_report_key_path(make_config, panel, field):
    with pytest.raises(ValidationError) as exc:
        make_config(monitors={"HDMI-A-1": {"shell": "edge", "panels": [panel]}})
    assert exc.value.errors()[0]["loc"][:5] == ("monitors", "HDMI-A-1", "panels", 0, field)


def test_pos_accepts_int_and_center_only():
    assert PanelConfig(widget="dock", pos=600).pos == 600
    assert PanelConfig(widget="dock", pos="center").pos == "center"
    with pytest.raises(ValidationError):
        PanelConfig(widget="dock", pos="middle")


def test_shell_mode_validated(make_config):
    with pytest.raises(ValidationError):
        make_config(monitors={"HDMI-A-1": {"shell": "yes"}})


def test_unlisted_monitor_defaults_to_plasma(make_config):
    assert make_config().monitor("DP-9").shell == "plasma"


def test_monitor_theme_override_merges(make_config):
    cfg = make_config(monitors={"HDMI-A-1": {"shell": "edge", "theme": {"accent": "#d3a68f"}}})
    assert cfg.theme_for("HDMI-A-1").accent == "#d3a68f"
    assert cfg.theme_for("HDMI-A-1").frame == "#0b0c0d"
    assert cfg.theme_for("DP-1").accent == "#8fd3b6"


def test_bad_override_color_fails_at_load(make_config):
    with pytest.raises(ValidationError) as exc:
        make_config(monitors={"HDMI-A-1": {"theme": {"accent": "nope"}}})
    assert "monitors.HDMI-A-1.theme" in str(exc.value)
```

- [ ] **Step 2: Run to verify failure**

Run: `scripts/py -m pytest tests/test_config_models.py -q`
Expected: FAIL / ERROR (`ModuleNotFoundError: shell.config.models`)

- [ ] **Step 3: Implement `shell/config/models.py`**

```python
"""Pydantic models for the Edge Shell config. Pure: no GTK imports."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    create_model,
    field_validator,
    model_validator,
)

Edge = Literal["top", "bottom", "left", "right"]
PanelState = Literal["collapsed", "extended"]
ShellMode = Literal["edge", "plasma", "both", "none"]

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_COLOR_FIELDS = (
    "frame",
    "text",
    "text_secondary",
    "accent",
    "handle",
    "handle_hover",
    "surface_hover",
)


class ConfigError(Exception):
    """A config problem; the message names the offending key path."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Theme(_Strict):
    frame: str
    text: str
    text_secondary: str
    accent: str
    handle: str
    handle_hover: str
    surface_hover: str
    thickness: Annotated[int, Field(ge=2, le=64)]
    radius: Annotated[int, Field(ge=1, le=64)]
    peek: Annotated[int, Field(ge=1, le=64)]
    hover_zone: Annotated[int, Field(ge=1, le=64)]
    duration_ms: Annotated[int, Field(ge=0, le=5000)]
    font: Annotated[list[str], Field(min_length=1)]

    @field_validator(*_COLOR_FIELDS)
    @classmethod
    def _hex(cls, value: str) -> str:
        if not _HEX.match(value):
            raise ValueError("must be a #rrggbb hex color")
        return value.lower()


# Same fields as Theme, all optional. Merged over the base theme and re-validated by Theme.
ThemeOverride = create_model(
    "ThemeOverride",
    __base__=_Strict,
    **{name: (field.annotation | None, None) for name, field in Theme.model_fields.items()},
)

Length = Annotated[int, Field(ge=60, le=4000)]
Depth = Annotated[int, Field(ge=16, le=2000)]
Offset = Annotated[int, Field(ge=0, le=20000)]


class PanelConfig(_Strict):
    widget: str
    edge: Edge | None = None
    pos: Offset | Literal["center"] | None = None
    length: Length | None = None
    depth: Depth | None = None
    state: PanelState | None = None


class MonitorConfig(_Strict):
    shell: ShellMode = "plasma"
    theme: ThemeOverride = Field(default_factory=ThemeOverride)
    panels: list[PanelConfig] = Field(default_factory=list)


class Config(_Strict):
    theme: Theme
    monitors: dict[str, MonitorConfig] = Field(default_factory=dict)

    def monitor(self, name: str) -> MonitorConfig:
        return self.monitors.get(name) or MonitorConfig()

    def theme_for(self, name: str) -> Theme:
        override = self.monitor(name).theme.model_dump(exclude_none=True)
        return Theme.model_validate({**self.theme.model_dump(), **override})

    @model_validator(mode="after")
    def _check_overrides(self) -> Config:
        for name in self.monitors:
            try:
                self.theme_for(name)
            except ValidationError as exc:
                detail = "; ".join(
                    f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
                )
                raise ValueError(f"monitors.{name}.theme: {detail}") from None
        return self
```

- [ ] **Step 4: Run to verify pass**

Run: `scripts/py -m pytest tests/test_config_models.py -q`
Expected: all pass

- [ ] **Step 5: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell tests
git commit -m "feat(config): pydantic models with per-monitor theme overrides" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Defaults file and loader

**Files:**
- Create: `config.default.toml`, `shell/config/loader.py`, `tests/test_config_loader.py`

**Interfaces:**
- Consumes: `Config`, `ConfigError` from Task 3.
- Produces: `load_config(user_path: Path | None = USER_PATH, default_path: Path = DEFAULT_PATH) -> Config` (raises `ConfigError`), `parse_config(data: dict) -> Config`, `format_validation_error(err) -> str`, constants `DEFAULT_PATH`, `USER_PATH` (`~/.config/edge-shell/config.toml`).

- [ ] **Step 1: Create `config.default.toml`**

```toml
# Defaults for every key. The user config (~/.config/edge-shell/config.toml) is overlaid on this.
# A monitor that is not listed behaves as shell = "plasma" (Edge Shell builds nothing there).

[theme]
frame = "#0b0c0d"
text = "#e6e8ea"
text_secondary = "#9ba0a6"
accent = "#8fd3b6"
handle = "#7b7f84"
handle_hover = "#e6e8ea"
surface_hover = "#1d2024"
thickness = 10      # T, px
radius = 14         # R, px
peek = 14           # hover peek depth, px
hover_zone = 16     # invisible hover target past the frame, px
duration_ms = 280
font = ["Hack Nerd Font Mono", "JetBrains Mono", "monospace"]
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_config_loader.py
import pytest

from shell.config.loader import load_config
from shell.config.models import ConfigError


def write(path, text):
    path.write_text(text)
    return path


def test_defaults_only_matches_test_theme(make_config):
    assert load_config(None).theme == make_config().theme


def test_missing_user_file_uses_defaults(tmp_path, make_config):
    assert load_config(tmp_path / "nope.toml").theme == make_config().theme


def test_user_overlay_changes_only_given_keys(tmp_path):
    cfg = load_config(write(tmp_path / "c.toml", '[theme]\naccent = "#112233"\n'))
    assert cfg.theme.accent == "#112233"
    assert cfg.theme.frame == "#0b0c0d"


def test_monitor_panels_load_in_order(tmp_path):
    cfg = load_config(
        write(
            tmp_path / "c.toml",
            '[monitors.HDMI-A-1]\nshell = "edge"\n'
            '[[monitors.HDMI-A-1.panels]]\nwidget = "dock"\n'
            '[[monitors.HDMI-A-1.panels]]\nwidget = "clock"\ndepth = 50\n',
        )
    )
    panels = cfg.monitor("HDMI-A-1").panels
    assert [p.widget for p in panels] == ["dock", "clock"]
    assert panels[1].depth == 50


def test_invalid_toml_names_the_file(tmp_path):
    path = write(tmp_path / "c.toml", "[theme\n")
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert str(path) in str(exc.value)


def test_unknown_key_reports_path(tmp_path):
    with pytest.raises(ConfigError) as exc:
        load_config(write(tmp_path / "c.toml", "[theme]\nbogus = 1\n"))
    assert "theme.bogus" in str(exc.value)


def test_bad_color_reports_path(tmp_path):
    with pytest.raises(ConfigError) as exc:
        load_config(write(tmp_path / "c.toml", '[theme]\nframe = "red"\n'))
    assert "theme.frame" in str(exc.value)


def test_panel_bound_reports_full_key_path(tmp_path):
    text = (
        '[monitors.HDMI-A-1]\nshell = "edge"\n'
        '[[monitors.HDMI-A-1.panels]]\nwidget = "dock"\nlength = 0\n'
    )
    with pytest.raises(ConfigError) as exc:
        load_config(write(tmp_path / "c.toml", text))
    assert "monitors.HDMI-A-1.panels.0.length" in str(exc.value)
```

- [ ] **Step 3: Run to verify failure**

Run: `scripts/py -m pytest tests/test_config_loader.py -q`
Expected: ERROR (`shell.config.loader` missing)

- [ ] **Step 4: Implement `shell/config/loader.py`**

```python
"""Load config.default.toml, overlay the user's file, validate."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from shell.config.models import Config, ConfigError

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config.default.toml"
USER_PATH = Path.home() / ".config" / "edge-shell" / "config.toml"


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value  # scalars and lists (e.g. panels) are replaced wholesale
    return out


def format_validation_error(err: ValidationError) -> str:
    lines = []
    for item in err.errors():
        path = ".".join(str(p) for p in item["loc"]) or "config"
        lines.append(f"{path}: {item['msg']}")
    return "\n".join(lines)


def parse_config(data: dict[str, Any]) -> Config:
    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(format_validation_error(exc)) from None


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from None


def load_config(user_path: Path | None = USER_PATH, default_path: Path = DEFAULT_PATH) -> Config:
    data = _read_toml(default_path)
    if user_path is not None and user_path.exists():
        data = _deep_merge(data, _read_toml(user_path))
    return parse_config(data)
```

- [ ] **Step 5: Run to verify pass**

Run: `scripts/py -m pytest tests/test_config_loader.py -q`
Expected: all pass

- [ ] **Step 6: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add config.default.toml shell tests
git commit -m "feat(config): defaults file and layered loader with key-path errors" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Panel spec and widget registry

**Files:**
- Create: `shell/panel_spec.py`, `shell/registry.py`, `tests/test_registry.py`
- Modify: `tests/conftest.py` (add `fake_registry` fixture)

**Interfaces:**
- Consumes: `Edge`, `PanelState`, `PanelConfig`, `Config`, `ConfigError` (Task 3).
- Produces:
  - `PanelDefaults(edge, length, depth, label, pos=None, state="extended")` frozen dataclass
  - `PanelGeometry(widget, edge, pos, length, depth, state, label)` frozen dataclass (`pos=None` means centered)
  - `register(name, defaults)` decorator; `widget_names() -> list[str]`; `widget_class(name) -> type`
  - `resolve_panel(cfg: PanelConfig) -> PanelGeometry` (raises `ConfigError` for unknown widget)
  - `panels_for(config: Config, monitor: str) -> list[PanelGeometry]`
  - `validate_widgets(config: Config) -> None` (raises `ConfigError` listing every bad key path)

- [ ] **Step 1: Add the fixture to `tests/conftest.py`**

```python
# append to tests/conftest.py
from shell import registry
from shell.panel_spec import PanelDefaults


@pytest.fixture
def fake_registry(monkeypatch):
    monkeypatch.setattr(registry, "_WIDGETS", {})
    monkeypatch.setattr(registry, "_DEFAULTS", {})
    registry.register("dock", PanelDefaults(edge="bottom", length=560, depth=64, label="dock"))(
        type("Dock", (), {})
    )
    registry.register("clock", PanelDefaults(edge="top", length=168, depth=46, label="clock"))(
        type("Clock", (), {})
    )
    registry.register(
        "bar", PanelDefaults(edge="right", length=300, depth=56, pos=600, label="bar", state="collapsed")
    )(type("Bar", (), {}))
    return registry
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_registry.py
import pytest

from shell import registry
from shell.config.models import ConfigError, PanelConfig
from shell.panel_spec import PanelDefaults, PanelGeometry


def test_resolve_uses_widget_defaults(fake_registry):
    geo = registry.resolve_panel(PanelConfig(widget="dock"))
    assert geo == PanelGeometry("dock", "bottom", None, 560, 64, "extended", "dock")


def test_overrides_win(fake_registry):
    geo = registry.resolve_panel(PanelConfig(widget="dock", depth=80, edge="top", state="collapsed"))
    assert (geo.depth, geo.edge, geo.state, geo.length) == (80, "top", "collapsed", 560)


def test_pos_default_override_and_center(fake_registry):
    assert registry.resolve_panel(PanelConfig(widget="bar")).pos == 600
    assert registry.resolve_panel(PanelConfig(widget="bar", pos=100)).pos == 100
    assert registry.resolve_panel(PanelConfig(widget="bar", pos="center")).pos is None


def test_unknown_widget_lists_known(fake_registry):
    with pytest.raises(ConfigError) as exc:
        registry.resolve_panel(PanelConfig(widget="nope"))
    assert "nope" in str(exc.value) and "dock" in str(exc.value)


def test_duplicate_registration_rejected(fake_registry):
    with pytest.raises(ValueError):
        registry.register("dock", PanelDefaults("top", 100, 40, "x"))(type("X", (), {}))


def test_widget_names_sorted(fake_registry):
    assert registry.widget_names() == ["bar", "clock", "dock"]


def test_panels_for_keeps_order_and_duplicates(fake_registry, make_config):
    cfg = make_config(
        monitors={
            "HDMI-A-1": {
                "shell": "edge",
                "panels": [{"widget": "dock"}, {"widget": "clock"}, {"widget": "dock", "depth": 70}],
            }
        }
    )
    geos = registry.panels_for(cfg, "HDMI-A-1")
    assert [g.widget for g in geos] == ["dock", "clock", "dock"]
    assert geos[2].depth == 70


def test_validate_widgets_reports_every_bad_path(fake_registry, make_config):
    cfg = make_config(
        monitors={
            "HDMI-A-1": {"panels": [{"widget": "dock"}, {"widget": "ghost"}]},
            "DP-1": {"panels": [{"widget": "phantom"}]},
        }
    )
    with pytest.raises(ConfigError) as exc:
        registry.validate_widgets(cfg)
    text = str(exc.value)
    assert "monitors.HDMI-A-1.panels[1].widget" in text
    assert "monitors.DP-1.panels[0].widget" in text
```

- [ ] **Step 3: Run to verify failure**

Run: `scripts/py -m pytest tests/test_registry.py -q`
Expected: ERROR (modules missing)

- [ ] **Step 4: Implement**

```python
# shell/panel_spec.py
"""Plain data describing a panel. Pure."""

from __future__ import annotations

from dataclasses import dataclass

from shell.config.models import Edge, PanelState


@dataclass(frozen=True)
class PanelDefaults:
    edge: Edge
    length: int
    depth: int
    label: str
    pos: int | None = None  # None = centered along the edge
    state: PanelState = "extended"


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

```python
# shell/registry.py
"""Widget registry: name -> panel class + default geometry. Pure (no GTK)."""

from __future__ import annotations

from collections.abc import Callable

from shell.config.models import Config, ConfigError, PanelConfig
from shell.panel_spec import PanelDefaults, PanelGeometry

_WIDGETS: dict[str, type] = {}
_DEFAULTS: dict[str, PanelDefaults] = {}


def register(name: str, defaults: PanelDefaults) -> Callable[[type], type]:
    def decorate(cls: type) -> type:
        if name in _WIDGETS:
            raise ValueError(f"widget {name!r} is already registered")
        _WIDGETS[name] = cls
        _DEFAULTS[name] = defaults
        return cls

    return decorate


def widget_names() -> list[str]:
    return sorted(_WIDGETS)


def widget_class(name: str) -> type:
    return _WIDGETS[name]


def resolve_panel(cfg: PanelConfig) -> PanelGeometry:
    d = _DEFAULTS.get(cfg.widget)
    if d is None:
        known = ", ".join(widget_names()) or "none"
        raise ConfigError(f"unknown widget {cfg.widget!r} (known: {known})")
    if cfg.pos is None:
        pos = d.pos
    else:
        pos = None if cfg.pos == "center" else cfg.pos
    return PanelGeometry(
        widget=cfg.widget,
        edge=cfg.edge or d.edge,
        pos=pos,
        length=cfg.length or d.length,
        depth=cfg.depth or d.depth,
        state=cfg.state or d.state,
        label=d.label,
    )


def panels_for(config: Config, monitor: str) -> list[PanelGeometry]:
    return [resolve_panel(p) for p in config.monitor(monitor).panels]


def validate_widgets(config: Config) -> None:
    problems = [
        f"monitors.{name}.panels[{i}].widget: unknown widget {panel.widget!r}"
        for name, mon in config.monitors.items()
        for i, panel in enumerate(mon.panels)
        if panel.widget not in _DEFAULTS
    ]
    if problems:
        known = ", ".join(widget_names()) or "none"
        raise ConfigError("\n".join(problems) + f"\nknown widgets: {known}")
```

- [ ] **Step 5: Run to verify pass**

Run: `scripts/py -m pytest tests/test_registry.py -q`
Expected: all pass

- [ ] **Step 6: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell tests
git commit -m "feat: panel spec dataclasses and widget registry" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Config store and diff

**Files:**
- Create: `shell/config/store.py`, `shell/config/diff.py`, `tests/test_config_store.py`, `tests/test_config_diff.py`

**Interfaces:**
- Consumes: `load_config`, `Config`, `ConfigError`, `validate_widgets`, `panels_for`, `PanelGeometry`.
- Produces:
  - `ConfigStore(path: Path | None)` with `.config`, `.last_error: str | None`, `.reload() -> tuple[Config, Config] | None` (returns `(old, new)` only when a valid, different config loaded; `None` otherwise). Raises `ConfigError` from the constructor only.
  - `Change(kind, monitor, index=None)` frozen dataclass, `kind` in `restyle | rebuild-monitor | panel-add | panel-remove | panel-rebuild | panel-state`
  - `diff_configs(old: Config, new: Config) -> list[Change]`

- [ ] **Step 1: Write failing store tests (Review Focus 1)**

```python
# tests/test_config_store.py
import pytest

from shell.config.models import ConfigError
from shell.config.store import ConfigStore

GOOD = '[monitors.HDMI-A-1]\nshell = "edge"\n[[monitors.HDMI-A-1.panels]]\nwidget = "dock"\n'


def test_initial_load_and_failure(tmp_path, fake_registry):
    path = tmp_path / "c.toml"
    path.write_text(GOOD)
    assert ConfigStore(path).config.monitor("HDMI-A-1").shell == "edge"
    path.write_text("[theme\n")
    with pytest.raises(ConfigError):
        ConfigStore(path)


def test_reload_returns_old_and_new(tmp_path, fake_registry):
    path = tmp_path / "c.toml"
    path.write_text(GOOD)
    store = ConfigStore(path)
    path.write_text(GOOD + '[theme]\naccent = "#112233"\n')
    old, new = store.reload()
    assert old.theme.accent == "#8fd3b6" and new.theme.accent == "#112233"
    assert store.config is new and store.last_error is None


def test_reload_unchanged_returns_none(tmp_path, fake_registry):
    path = tmp_path / "c.toml"
    path.write_text(GOOD)
    store = ConfigStore(path)
    assert store.reload() is None and store.last_error is None


@pytest.mark.parametrize(
    "bad",
    [
        "[theme\n",  # invalid TOML (editor saved mid-edit)
        "[theme]\nbogus = 1\n",  # unknown key
        '[theme]\nframe = "red"\n',  # bad color
        '[monitors.HDMI-A-1]\n[[monitors.HDMI-A-1.panels]]\nwidget = "ghost"\n',  # unknown widget
    ],
)
def test_bad_edit_keeps_last_good_config(tmp_path, fake_registry, bad):
    path = tmp_path / "c.toml"
    path.write_text(GOOD)
    store = ConfigStore(path)
    before = store.config
    path.write_text(bad)
    assert store.reload() is None
    assert store.config is before
    assert store.last_error
    path.write_text(GOOD + '[theme]\naccent = "#112233"\n')  # fixing the file recovers
    assert store.reload() is not None and store.last_error is None
```

- [ ] **Step 2: Write failing diff tests**

```python
# tests/test_config_diff.py
from shell.config.diff import Change, diff_configs


def mon(shell="edge", panels=(), theme=None):
    return {"shell": shell, "panels": list(panels), "theme": theme or {}}


def test_identical_is_empty(fake_registry, make_config):
    cfg = make_config(monitors={"HDMI-A-1": mon(panels=[{"widget": "dock"}])})
    assert diff_configs(cfg, cfg) == []


def test_color_change_restyles_edge_monitors_only(fake_registry, make_config):
    old = make_config(monitors={"HDMI-A-1": mon(), "DP-1": mon("plasma")})
    new = make_config(theme={"accent": "#112233"}, monitors={"HDMI-A-1": mon(), "DP-1": mon("plasma")})
    assert diff_configs(old, new) == [Change("restyle", "HDMI-A-1")]


def test_structural_theme_change_rebuilds_monitor(fake_registry, make_config):
    old = make_config(monitors={"HDMI-A-1": mon()})
    new = make_config(theme={"thickness": 12}, monitors={"HDMI-A-1": mon()})
    assert diff_configs(old, new) == [Change("rebuild-monitor", "HDMI-A-1")]


def test_mode_changes(fake_registry, make_config):
    def cfg(shell):
        return make_config(monitors={"HDMI-A-1": mon(shell)})

    assert diff_configs(cfg("plasma"), cfg("edge")) == [Change("rebuild-monitor", "HDMI-A-1")]
    assert diff_configs(cfg("edge"), cfg("none")) == [Change("rebuild-monitor", "HDMI-A-1")]
    assert diff_configs(cfg("edge"), cfg("both")) == []  # windows unchanged
    assert diff_configs(cfg("plasma"), cfg("none")) == []


def test_panel_state_only(fake_registry, make_config):
    old = make_config(monitors={"HDMI-A-1": mon(panels=[{"widget": "dock", "state": "extended"}])})
    new = make_config(monitors={"HDMI-A-1": mon(panels=[{"widget": "dock", "state": "collapsed"}])})
    assert diff_configs(old, new) == [Change("panel-state", "HDMI-A-1", 0)]


def test_panel_geometry_change_rebuilds_that_panel(fake_registry, make_config):
    old = make_config(monitors={"HDMI-A-1": mon(panels=[{"widget": "dock"}, {"widget": "clock"}])})
    new = make_config(
        monitors={"HDMI-A-1": mon(panels=[{"widget": "dock"}, {"widget": "clock", "depth": 50}])}
    )
    assert diff_configs(old, new) == [Change("panel-rebuild", "HDMI-A-1", 1)]


def test_widget_swap_at_same_index_rebuilds(fake_registry, make_config):
    old = make_config(monitors={"HDMI-A-1": mon(panels=[{"widget": "dock"}])})
    new = make_config(monitors={"HDMI-A-1": mon(panels=[{"widget": "clock"}])})
    assert diff_configs(old, new) == [Change("panel-rebuild", "HDMI-A-1", 0)]


def test_add_and_remove_panels(fake_registry, make_config):
    one = make_config(monitors={"HDMI-A-1": mon(panels=[{"widget": "dock"}])})
    three = make_config(
        monitors={"HDMI-A-1": mon(panels=[{"widget": "dock"}, {"widget": "clock"}, {"widget": "bar"}])}
    )
    assert diff_configs(one, three) == [
        Change("panel-add", "HDMI-A-1", 1),
        Change("panel-add", "HDMI-A-1", 2),
    ]
    assert diff_configs(three, one) == [  # highest index first so indexes stay valid
        Change("panel-remove", "HDMI-A-1", 2),
        Change("panel-remove", "HDMI-A-1", 1),
    ]


def test_non_edge_monitor_panel_changes_ignored(fake_registry, make_config):
    old = make_config(monitors={"DP-1": mon("plasma", panels=[{"widget": "dock"}])})
    new = make_config(monitors={"DP-1": mon("plasma", panels=[{"widget": "clock"}])})
    assert diff_configs(old, new) == []
```

- [ ] **Step 3: Run to verify failure**

Run: `scripts/py -m pytest tests/test_config_store.py tests/test_config_diff.py -q`
Expected: ERROR (modules missing)

- [ ] **Step 4: Implement**

```python
# shell/config/store.py
"""Holds the current config. A bad reload never replaces a good config."""

from __future__ import annotations

from pathlib import Path

from shell.config.loader import load_config
from shell.config.models import Config, ConfigError
from shell.registry import validate_widgets


class ConfigStore:
    def __init__(self, path: Path | None):
        self.path = path
        self.last_error: str | None = None
        self.config: Config = self._load()  # raises ConfigError at startup

    def _load(self) -> Config:
        config = load_config(self.path)
        validate_widgets(config)
        return config

    def reload(self) -> tuple[Config, Config] | None:
        """Return (old, new) if a valid, different config was loaded; otherwise None."""
        try:
            new = self._load()
        except ConfigError as exc:
            self.last_error = str(exc)
            return None
        self.last_error = None
        if new == self.config:
            return None
        old, self.config = self.config, new
        return old, new
```

```python
# shell/config/diff.py
"""Turn an old/new config pair into the smallest set of window changes. Pure."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from shell.config.models import Config
from shell.registry import panels_for

Kind = Literal[
    "restyle", "rebuild-monitor", "panel-add", "panel-remove", "panel-rebuild", "panel-state"
]
_STRUCTURAL = ("thickness", "radius", "peek", "hover_zone", "duration_ms")


@dataclass(frozen=True)
class Change:
    kind: Kind
    monitor: str
    index: int | None = None


def _has_windows(config: Config, name: str) -> bool:
    return config.monitor(name).shell in ("edge", "both")


def diff_configs(old: Config, new: Config) -> list[Change]:
    changes: list[Change] = []
    for name in sorted(set(old.monitors) | set(new.monitors)):
        was, now = _has_windows(old, name), _has_windows(new, name)
        if not was and not now:
            continue
        if was != now:
            changes.append(Change("rebuild-monitor", name))
            continue
        old_theme, new_theme = old.theme_for(name), new.theme_for(name)
        if any(getattr(old_theme, k) != getattr(new_theme, k) for k in _STRUCTURAL):
            changes.append(Change("rebuild-monitor", name))
            continue
        if old_theme != new_theme:
            changes.append(Change("restyle", name))
        changes.extend(_diff_panels(name, panels_for(old, name), panels_for(new, name)))
    return changes


def _diff_panels(name, old, new) -> list[Change]:
    changes: list[Change] = []
    removed: list[Change] = []
    for i in range(max(len(old), len(new))):
        if i >= len(old):
            changes.append(Change("panel-add", name, i))
        elif i >= len(new):
            removed.append(Change("panel-remove", name, i))
        elif old[i] == new[i]:
            continue
        elif replace(old[i], state=new[i].state) == new[i]:
            changes.append(Change("panel-state", name, i))
        else:
            changes.append(Change("panel-rebuild", name, i))
    return changes + removed[::-1]
```

- [ ] **Step 5: Run to verify pass**

Run: `scripts/py -m pytest tests/test_config_store.py tests/test_config_diff.py -q`
Expected: all pass

- [ ] **Step 6: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell tests
git commit -m "feat(config): ConfigStore (keeps last good config) and config diffing" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Geometry (pure edge maths)

**Files:**
- Create: `shell/geometry.py`, `tests/test_geometry.py`

**Interfaces:**
- Consumes: `Edge` (Task 3).
- Produces (all pure):
  - `is_horizontal(edge) -> bool`
  - `surface_size(edge, length, depth, thickness, radius) -> (w, h)`
  - `join_radius(d, radius) -> float`
  - `to_canvas(edge, u, v, along, across) -> (x, y)` (canonical bottom-edge coords -> surface coords)
  - `cairo_matrix(edge, across) -> cairo.Matrix`
  - `body_rect(edge, length, depth, d, thickness, radius) -> (x, y, w, h)`
  - `input_rect(edge, length, depth, d, thickness, radius, hover_zone) -> (x, y, w, h)`
  - `anchor_and_margin(edge, pos, along, radius, extent) -> (anchor, margin)`

Reference numbers (length=560, depth=64, T=10, R=14): `along=588`, `across=74`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_geometry.py
import pytest

from shell import geometry as g

L, D, T, R = 560, 64, 10, 14


@pytest.mark.parametrize(
    ("edge", "size"),
    [("bottom", (588, 74)), ("top", (588, 74)), ("left", (74, 588)), ("right", (74, 588))],
)
def test_surface_size(edge, size):
    assert g.surface_size(edge, L, D, T, R) == size


def test_join_radius_grows_from_zero_and_caps_at_R():
    assert g.join_radius(7, R) == 7
    assert g.join_radius(30, R) == 14
    assert g.join_radius(-3, R) == 0


@pytest.mark.parametrize(
    ("edge", "u", "v", "expected"),
    [
        ("bottom", 14, 0, (14, 0)),
        ("top", 14, 0, (14, 74)),
        ("left", 14, 0, (74, 14)),
        ("right", 14, 0, (0, 14)),
        ("left", 14, 74, (0, 14)),
        ("right", 14, 74, (74, 14)),
    ],
)
def test_to_canvas(edge, u, v, expected):
    assert g.to_canvas(edge, u, v, 588, 74) == expected


@pytest.mark.parametrize("edge", ["top", "bottom", "left", "right"])
def test_cairo_matrix_agrees_with_to_canvas(edge):
    m = g.cairo_matrix(edge, 74)
    for u, v in [(0, 0), (14, 3), (300, 60), (588, 74)]:
        assert m.transform_point(u, v) == pytest.approx(g.to_canvas(edge, u, v, 588, 74))


@pytest.mark.parametrize(
    ("edge", "d", "rect"),
    [
        ("bottom", 64, (14, 0, 560, 74)),
        ("top", 64, (14, 0, 560, 74)),
        ("left", 64, (0, 14, 74, 560)),
        ("right", 64, (0, 14, 74, 560)),
        ("bottom", 0, (14, 64, 560, 10)),
        ("top", 0, (14, 0, 560, 10)),
        ("left", 0, (0, 14, 10, 560)),
        ("right", 0, (64, 14, 10, 560)),
        ("bottom", 3.5, (14, 60, 560, 14)),  # fractional depth rounds outward
    ],
)
def test_body_rect(edge, d, rect):
    assert g.body_rect(edge, L, D, d, T, R) == rect


def test_input_rect_grows_collapsed_hover_zone():
    assert g.input_rect("bottom", L, D, 0, T, R, 16) == (14, 48, 560, 26)
    assert g.input_rect("bottom", L, D, 64, T, R, 16) == (14, 0, 560, 74)
    # a shallow panel cannot have a hover zone deeper than itself
    assert g.input_rect("bottom", L, 10, 0, T, R, 16) == g.body_rect("bottom", L, 10, 10, T, R)


def test_anchor_centered_has_single_edge_and_no_margin():
    assert g.anchor_and_margin("bottom", None, 588, R, 1920) == ("bottom", "0px 0px 0px 0px")


@pytest.mark.parametrize(
    ("edge", "pos", "expected"),
    [
        ("right", 600, ("right top", "586px 0px 0px 0px")),
        ("left", 150, ("left top", "136px 0px 0px 0px")),
        ("bottom", 0, ("bottom left", "0px 0px 0px 0px")),
        ("top", 200, ("top left", "0px 0px 0px 186px")),
    ],
)
def test_anchor_positioned(edge, pos, expected):
    # body starts at pos, so the surface starts R earlier (never negative)
    assert g.anchor_and_margin(edge, pos, 328, R, 1080 if edge in ("left", "right") else 1920) == expected


def test_pos_beyond_screen_is_clamped():  # Review Focus 3
    assert g.anchor_and_margin("right", 5000, 328, R, 1080) == ("right top", "752px 0px 0px 0px")
    assert g.anchor_and_margin("bottom", 99999, 588, R, 1920) == ("bottom left", "0px 0px 0px 1332px")


def test_panel_longer_than_screen_does_not_go_negative():
    assert g.anchor_and_margin("bottom", 500, 3000, R, 1920) == ("bottom left", "0px 0px 0px 0px")
```

- [ ] **Step 2: Run to verify failure**

Run: `scripts/py -m pytest tests/test_geometry.py -q`
Expected: ERROR (`shell.geometry` missing)

- [ ] **Step 3: Implement `shell/geometry.py`**

```python
"""Edge geometry. Panels are drawn in a canonical *bottom-edge* space: u runs along the
edge, v runs from the far (screen-interior) side at 0 to the screen edge at `across`.
`to_canvas` / `cairo_matrix` rotate that space onto the real edge. Pure: no GTK."""

from __future__ import annotations

import math

import cairo

from shell.config.models import Edge

Rect = tuple[int, int, int, int]


def is_horizontal(edge: Edge) -> bool:
    return edge in ("top", "bottom")


def surface_size(edge: Edge, length: int, depth: int, thickness: int, radius: int) -> tuple[int, int]:
    along = length + 2 * radius
    across = thickness + depth
    return (along, across) if is_horizontal(edge) else (across, along)


def join_radius(d: float, radius: int) -> float:
    return min(float(radius), max(0.0, float(d)))


def to_canvas(edge: Edge, u: float, v: float, along: float, across: float) -> tuple[float, float]:
    if edge == "bottom":
        return (u, v)
    if edge == "top":
        return (u, across - v)
    if edge == "left":
        return (across - v, u)
    return (v, u)  # right


def cairo_matrix(edge: Edge, across: float) -> cairo.Matrix:
    if edge == "bottom":
        return cairo.Matrix(1, 0, 0, 1, 0, 0)
    if edge == "top":
        return cairo.Matrix(1, 0, 0, -1, 0, across)
    if edge == "left":
        return cairo.Matrix(0, 1, -1, 0, across, 0)
    return cairo.Matrix(0, 1, 1, 0, 0, 0)  # right


def _bounds(edge: Edge, u1, v1, u2, v2, along, across) -> Rect:
    x1, y1 = to_canvas(edge, u1, v1, along, across)
    x2, y2 = to_canvas(edge, u2, v2, along, across)
    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))
    x, y = math.floor(left), math.floor(top)
    return (x, y, max(1, math.ceil(right) - x), max(1, math.ceil(bottom) - y))


def body_rect(
    edge: Edge, length: int, depth: int, d: float, thickness: int, radius: int
) -> Rect:
    along = length + 2 * radius
    across = thickness + depth
    return _bounds(
        edge, radius, across - thickness - d, radius + length, across, along, across
    )


def input_rect(
    edge: Edge, length: int, depth: int, d: float, thickness: int, radius: int, hover_zone: int
) -> Rect:
    """Where the panel takes input. A collapsed panel keeps an invisible hover zone."""
    effective = max(d, min(hover_zone, depth))
    return body_rect(edge, length, depth, effective, thickness, radius)


def anchor_and_margin(
    edge: Edge, pos: int | None, along: int, radius: int, extent: int
) -> tuple[str, str]:
    """Layer-shell anchor string and margin string. `pos=None` centers along the edge."""
    if pos is None:
        return edge, "0px 0px 0px 0px"
    offset = max(0, pos - radius)  # the body starts `radius` into the surface
    offset = min(offset, max(0, extent - along))  # keep the surface on screen
    if is_horizontal(edge):
        return f"{edge} left", f"0px 0px 0px {offset}px"
    return f"{edge} top", f"{offset}px 0px 0px 0px"
```

- [ ] **Step 4: Run to verify pass**

Run: `scripts/py -m pytest tests/test_geometry.py -q`
Expected: all pass

- [ ] **Step 5: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell tests
git commit -m "feat: pure edge geometry (rotation, rects, anchor/margin with clamping)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Cairo drawing (panels and screen corners)

**Files:**
- Create: `shell/draw.py`, `tests/test_draw.py`

**Interfaces:**
- Consumes: `shell.geometry` (`cairo_matrix`, `join_radius`, `surface_size`, `to_canvas`).
- Produces:
  - `draw_panel(cr, edge, length, depth, d, thickness, radius, rgba) -> None` (body + two curved joins, rotated onto the edge)
  - `draw_screen_corner(cr, corner, radius, rgba) -> None` (`corner` is `"top-left"` etc.; fills the `R x R` square outside a quarter circle)

- [ ] **Step 1: Write failing pixel tests**

```python
# tests/test_draw.py
import cairo
import pytest

from shell import geometry as g
from shell.draw import draw_panel, draw_screen_corner

L, DEPTH, T, R = 100, 50, 10, 14
RGBA = (0.04, 0.05, 0.05, 1.0)
EDGES = ["top", "bottom", "left", "right"]


def render_panel(edge, d):
    w, h = g.surface_size(edge, L, DEPTH, T, R)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surface)
    draw_panel(cr, edge, L, DEPTH, d, T, R, RGBA)
    surface.flush()
    return surface


def alpha(surface, x, y):
    stride = surface.get_stride()
    return surface.get_data()[int(y) * stride + int(x) * 4 + 3]


def canon_alpha(surface, edge, u, v):
    """Alpha at canonical (u, v) in the panel's bottom-edge space."""
    x, y = g.to_canvas(edge, u, v, L + 2 * R, T + DEPTH)
    return alpha(surface, x, y)


FILLED, EMPTY = 200, 20


@pytest.mark.parametrize("edge", EDGES)
def test_extended_panel(edge):
    s = render_panel(edge, DEPTH)  # canonical: x0=14, body x 14..114, y 0..60, join y 36..50
    assert canon_alpha(s, edge, 64.5, 30.5) > FILLED  # body
    assert canon_alpha(s, edge, 64.5, 55.5) > FILLED  # frame strip under the body
    assert canon_alpha(s, edge, 64.5, 0.5) > FILLED  # straight top edge
    assert canon_alpha(s, edge, 14.5, 0.5) < EMPTY  # rounded top-left corner cut away
    assert canon_alpha(s, edge, 113.5, 0.5) < EMPTY  # rounded top-right corner cut away
    assert canon_alpha(s, edge, 2.5, 2.5) < EMPTY  # far outside


@pytest.mark.parametrize("edge", EDGES)
def test_curved_joins_are_concave_fillets(edge):
    s = render_panel(edge, DEPTH)
    assert canon_alpha(s, edge, 13.5, 49.5) > FILLED  # left join, corner against the frame
    assert canon_alpha(s, edge, 0.5, 36.5) < EMPTY  # left join, circle centre stays clear
    assert canon_alpha(s, edge, 114.5, 49.5) > FILLED  # right join
    assert canon_alpha(s, edge, 127.5, 36.5) < EMPTY
    assert canon_alpha(s, edge, 5.5, 55.5) < EMPTY  # frame strip is another window


@pytest.mark.parametrize("edge", EDGES)
def test_collapsed_panel_is_just_the_frame_strip(edge):
    s = render_panel(edge, 0)
    assert canon_alpha(s, edge, 64.5, 55.5) > FILLED
    assert canon_alpha(s, edge, 64.5, 45.5) < EMPTY
    assert canon_alpha(s, edge, 5.5, 45.5) < EMPTY  # no joins at depth 0
    assert canon_alpha(s, edge, 5.5, 55.5) < EMPTY


@pytest.mark.parametrize("edge", EDGES)
def test_shallow_panel_joins_shrink_to_its_depth(edge):
    s = render_panel(edge, 7)  # join radius 7: square x 7..14, y 43..50
    assert canon_alpha(s, edge, 13.5, 49.5) > FILLED
    assert canon_alpha(s, edge, 7.5, 43.5) < EMPTY
    assert canon_alpha(s, edge, 3.5, 46.5) < EMPTY  # nothing sticks out past the shallow join


@pytest.mark.parametrize(
    ("corner", "outer", "inner"),
    [
        ("top-left", (0, 0), (13, 13)),
        ("top-right", (13, 0), (0, 13)),
        ("bottom-left", (0, 13), (13, 0)),
        ("bottom-right", (13, 13), (0, 0)),
    ],
)
def test_screen_corner(corner, outer, inner):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, R, R)
    draw_screen_corner(cairo.Context(surface), corner, R, RGBA)
    surface.flush()
    assert alpha(surface, *outer) > FILLED  # the desktop's outer corner is frame-colored
    assert alpha(surface, *inner) < EMPTY  # the rounded desktop area is clear
```

- [ ] **Step 2: Run to verify failure**

Run: `scripts/py -m pytest tests/test_draw.py -q`
Expected: ERROR (`shell.draw` missing)

- [ ] **Step 3: Implement `shell/draw.py`**

```python
"""Cairo drawing for panels and screen corners. Pure cairo: renders to any context."""

from __future__ import annotations

import math

import cairo

from shell import geometry

RGBA = tuple[float, float, float, float]


def draw_panel(
    cr: cairo.Context,
    edge: str,
    length: int,
    depth: int,
    d: float,
    thickness: int,
    radius: int,
    rgba: RGBA,
) -> None:
    """Draw the panel body plus both curved joins with one radius, at current depth `d`."""
    across = thickness + depth
    r = geometry.join_radius(d, radius)
    height = float(across)
    x0, y0 = float(radius), height - thickness - d  # body top-left (canonical)
    right = x0 + length

    cr.save()
    cr.transform(geometry.cairo_matrix(edge, across))
    cr.set_source_rgba(*rgba)

    # body: a rectangle whose two inner corners are rounded by r
    cr.new_path()
    cr.move_to(x0, height)
    cr.line_to(x0, y0 + r)
    if r > 0:
        cr.arc(x0 + r, y0 + r, r, math.pi, 1.5 * math.pi)
    cr.line_to(right - r, y0)
    if r > 0:
        cr.arc(right - r, y0 + r, r, 1.5 * math.pi, 2 * math.pi)
    cr.line_to(right, height)
    cr.close_path()
    cr.fill()

    if r >= 0.5:
        # joins: frame color outside a quarter circle, sitting on the frame's inner edge
        jy = height - thickness
        cr.new_path()
        cr.move_to(x0, jy)
        cr.line_to(x0, jy - r)
        cr.arc(x0 - r, jy - r, r, 0, 0.5 * math.pi)
        cr.close_path()
        cr.move_to(right, jy)
        cr.line_to(right, jy - r)
        cr.arc_negative(right + r, jy - r, r, math.pi, 0.5 * math.pi)
        cr.close_path()
        cr.fill()
    cr.restore()


def draw_screen_corner(cr: cairo.Context, corner: str, radius: int, rgba: RGBA) -> None:
    """Fill the radius x radius square outside a quarter circle (the rounded desktop corner)."""
    vertical, horizontal = corner.split("-")
    cx = radius if horizontal == "left" else 0
    cy = radius if vertical == "top" else 0
    cr.save()
    cr.set_source_rgba(*rgba)
    cr.rectangle(0, 0, radius, radius)
    cr.clip()
    cr.new_path()
    cr.rectangle(0, 0, radius, radius)
    cr.new_sub_path()
    cr.arc(cx, cy, radius, 0, 2 * math.pi)
    cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    cr.fill()
    cr.restore()
```

- [ ] **Step 4: Run to verify pass**

Run: `scripts/py -m pytest tests/test_draw.py -q`
Expected: all pass. If a join assertion fails, check the canonical-space comment in the test first (join square is `x0-r..x0` by `jy-r..jy`, with `jy = across - T`).

- [ ] **Step 5: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell tests
git commit -m "feat: cairo drawing for fused panels and rounded screen corners" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Animation (easing and Tween)

**Files:**
- Create: `shell/anim.py`, `tests/test_anim.py`

**Interfaces:**
- Produces:
  - `cubic_bezier(x1, y1, x2, y2) -> Callable[[float], float]`; `EASE_OUT = cubic_bezier(.2, .8, .2, 1)`
  - `Tween(widget, on_value, duration_ms=280, delay_ms=0, easing=EASE_OUT)` with `.value`, `.running`, `.jump_to(target)`, `.animate_to(target)`. `widget` needs `add_tick_callback(cb) -> int` / `remove_tick_callback(id)`; the callback is `cb(widget, frame_clock) -> bool` and `frame_clock.get_frame_time()` returns microseconds.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_anim.py
import pytest

from shell.anim import EASE_OUT, Tween, cubic_bezier


class FakeClock:
    now = 0

    def get_frame_time(self):
        return self.now


class FakeWidget:
    def __init__(self):
        self.callbacks = {}
        self._next = 1
        self.clock = FakeClock()

    def add_tick_callback(self, cb):
        cid, self._next = self._next, self._next + 1
        self.callbacks[cid] = cb
        return cid

    def remove_tick_callback(self, cid):
        self.callbacks.pop(cid, None)

    def frame(self, advance_ms):
        self.clock.now += int(advance_ms * 1000)
        for cid, cb in list(self.callbacks.items()):
            if not cb(self, self.clock):
                self.callbacks.pop(cid, None)


def test_easing_endpoints_and_fast_out():
    assert EASE_OUT(0) == 0 and EASE_OUT(1) == 1
    assert EASE_OUT(0.5) == pytest.approx(0.946, abs=0.02)  # fast out of the frame
    xs = [i / 50 for i in range(51)]
    ys = [EASE_OUT(x) for x in xs]
    assert ys == sorted(ys)  # monotonic


def test_linear_bezier_is_identity():
    linear = cubic_bezier(0, 0, 1, 1)
    assert linear(0.3) == pytest.approx(0.3, abs=1e-3)


def test_animate_reaches_target_and_stops():
    w, seen = FakeWidget(), []
    t = Tween(w, seen.append, duration_ms=280)
    t.animate_to(100)
    w.frame(0)  # first tick starts the clock
    w.frame(140)
    assert seen[-1] == pytest.approx(94.6, abs=2)
    w.frame(200)
    assert seen[-1] == 100 and t.value == 100
    assert not w.callbacks and not t.running


def test_retarget_midflight_starts_from_current_value():
    w = FakeWidget()
    t = Tween(w, lambda v: None, duration_ms=280)
    t.animate_to(100)
    w.frame(0)
    w.frame(100)
    mid = t.value
    t.animate_to(0)
    w.frame(0)  # first tick of the new tween: no jump
    assert t.value == pytest.approx(mid)
    w.frame(300)
    assert t.value == 0


def test_jump_cancels_and_sets():
    w, seen = FakeWidget(), []
    t = Tween(w, seen.append)
    t.animate_to(50)
    t.jump_to(7)
    assert t.value == 7 and seen[-1] == 7 and not w.callbacks


def test_delay_holds_value_then_animates():
    w = FakeWidget()
    t = Tween(w, lambda v: None, duration_ms=100, delay_ms=100)
    t.animate_to(1.0)
    w.frame(0)
    w.frame(50)
    assert t.value == 0  # still inside the delay
    w.frame(100)  # 150 ms in: 50 ms into the animation
    assert 0 < t.value < 1
    w.frame(100)
    assert t.value == 1


def test_animate_to_current_value_is_a_noop():
    w = FakeWidget()
    t = Tween(w, lambda v: None)
    t.animate_to(0)
    assert not w.callbacks


def test_zero_duration_snaps():
    w = FakeWidget()
    t = Tween(w, lambda v: None, duration_ms=0)
    t.animate_to(10)
    w.frame(0)
    assert t.value == 10 and not w.callbacks
```

- [ ] **Step 2: Run to verify failure**

Run: `scripts/py -m pytest tests/test_anim.py -q`
Expected: ERROR (`shell.anim` missing)

- [ ] **Step 3: Implement `shell/anim.py`**

```python
"""Easing and a frame-clock driven Tween. Pure: the widget is duck-typed."""

from __future__ import annotations

from collections.abc import Callable

Easing = Callable[[float], float]


def cubic_bezier(x1: float, y1: float, x2: float, y2: float) -> Easing:
    """CSS-style cubic-bezier easing, solved by bisection (x1, x2 within [0, 1])."""

    def axis(a: float, b: float, s: float) -> float:
        return 3 * (1 - s) ** 2 * s * a + 3 * (1 - s) * s**2 * b + s**3

    def ease(t: float) -> float:
        if t <= 0:
            return 0.0
        if t >= 1:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(40):
            mid = (lo + hi) / 2
            if axis(x1, x2, mid) < t:
                lo = mid
            else:
                hi = mid
        return axis(y1, y2, (lo + hi) / 2)

    return ease


EASE_OUT = cubic_bezier(0.2, 0.8, 0.2, 1.0)


class Tween:
    def __init__(
        self,
        widget,
        on_value: Callable[[float], None],
        duration_ms: int = 280,
        delay_ms: int = 0,
        easing: Easing = EASE_OUT,
    ):
        self._widget = widget
        self._on_value = on_value
        self._duration_us = duration_ms * 1000
        self._delay_us = delay_ms * 1000
        self._easing = easing
        self.value = 0.0
        self._from = self._to = 0.0
        self._start_us: int | None = None
        self._tick_id = 0

    @property
    def running(self) -> bool:
        return bool(self._tick_id)

    def jump_to(self, target: float) -> None:
        if self._tick_id:
            self._widget.remove_tick_callback(self._tick_id)
            self._tick_id = 0
        self.value = self._from = self._to = float(target)
        self._on_value(self.value)

    def animate_to(self, target: float) -> None:
        target = float(target)
        if self._tick_id:
            if target == self._to:
                return
        elif abs(target - self.value) < 1e-9:
            return
        # Retargeting mid-flight starts from the current value, so there is never a jump.
        self._from, self._to, self._start_us = self.value, target, None
        if not self._tick_id:
            self._tick_id = self._widget.add_tick_callback(self._tick)

    def _tick(self, _widget, clock) -> bool:
        now = clock.get_frame_time()
        if self._start_us is None:
            self._start_us = now
        elapsed = now - self._start_us - self._delay_us
        if self._duration_us <= 0:
            t = 1.0 if elapsed >= 0 else 0.0
        else:
            t = 0.0 if elapsed <= 0 else min(1.0, elapsed / self._duration_us)
        self.value = self._from + (self._to - self._from) * self._easing(t)
        self._on_value(self.value)
        if t >= 1.0:
            self._tick_id = 0
            return False  # remove the tick callback
        return True
```

- [ ] **Step 4: Run to verify pass**

Run: `scripts/py -m pytest tests/test_anim.py -q`
Expected: all pass

- [ ] **Step 5: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell tests
git commit -m "feat: cubic-bezier easing and frame-clock Tween with delay and retarget" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Theme to CSS and colors

**Files:**
- Create: `shell/theme.py`, `tests/test_theme.py`

**Interfaces:**
- Consumes: `Theme` (Task 3).
- Produces: `hex_to_rgba(hex, alpha=1.0) -> (r, g, b, a)`, `scope_class(monitor_name) -> str` (e.g. `"mon-hdmi-a-1"`), `to_css(theme, scope) -> str` (every rule is scoped under `.scope`, so per-monitor themes do not leak).

- [ ] **Step 1: Write failing tests**

```python
# tests/test_theme.py
import pytest

from shell.theme import hex_to_rgba, scope_class, to_css


def test_hex_to_rgba():
    assert hex_to_rgba("#0b0c0d") == (11 / 255, 12 / 255, 13 / 255, 1.0)
    assert hex_to_rgba("#ffffff", 0.5) == (1.0, 1.0, 1.0, 0.5)


@pytest.mark.parametrize(
    ("name", "scope"),
    [("HDMI-A-1", "mon-hdmi-a-1"), ("DP-1", "mon-dp-1"), ("eDP_1", "mon-edp-1")],
)
def test_scope_class(name, scope):
    assert scope_class(name) == scope


def test_css_font_stack_quotes_names_but_not_generics(make_config):
    css = to_css(make_config().theme, "mon-x")
    assert 'font-family: "Hack Nerd Font Mono", "JetBrains Mono", monospace;' in css


def test_css_is_scoped_and_uses_theme_colors(make_config):
    css = to_css(make_config(theme={"frame": "#112233"}).theme, "mon-x")
    assert ".mon-x #frame-strip { background-color: #112233; }" in css
    assert "window.mon-x" in css
    for line in css.splitlines():
        if "{" in line and not line.startswith("}"):
            assert "mon-x" in line, line  # nothing unscoped


def test_two_monitors_do_not_share_rules(make_config):
    cfg = make_config(monitors={"HDMI-A-1": {"theme": {"frame": "#111111"}}})
    a = to_css(cfg.theme_for("HDMI-A-1"), scope_class("HDMI-A-1"))
    b = to_css(cfg.theme_for("DP-1"), scope_class("DP-1"))
    assert "#111111" in a and "#111111" not in b
```

- [ ] **Step 2: Run to verify failure**

Run: `scripts/py -m pytest tests/test_theme.py -q`
Expected: ERROR (`shell.theme` missing)

- [ ] **Step 3: Implement `shell/theme.py`**

```python
"""Theme tokens -> CSS string and cairo colors. Pure."""

from __future__ import annotations

import re

from shell.config.models import Theme

_GENERIC_FONTS = {"monospace", "sans-serif", "serif", "cursive", "fantasy"}


def hex_to_rgba(value: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    h = value.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return (r, g, b, alpha)


def scope_class(monitor: str) -> str:
    """CSS class put on every window of a monitor, so per-monitor themes stay separate."""
    return "mon-" + re.sub(r"[^a-z0-9-]", "-", monitor.lower())


def _font_stack(fonts: list[str]) -> str:
    return ", ".join(f if f in _GENERIC_FONTS else f'"{f}"' for f in fonts)


def to_css(theme: Theme, scope: str) -> str:
    s = f".{scope}"
    return f"""\
window{s}, {s} * {{ all: unset; font-family: {_font_stack(theme.font)}; color: {theme.text}; }}
window{s} {{ background-color: transparent; }}
{s} #frame-strip {{ background-color: {theme.frame}; }}
{s} #handle {{ min-width: 0; min-height: 0; padding: 0; }}
{s} .handle-dot {{ min-width: 3px; min-height: 3px; border-radius: 50%; background-color: {theme.handle}; }}
{s} #handle:hover .handle-dot, {s} #handle:focus .handle-dot {{ background-color: {theme.handle_hover}; }}
{s} .icon-button {{ min-width: 44px; min-height: 44px; border-radius: 10px; }}
{s} .icon-button:hover {{ background-color: {theme.surface_hover}; }}
{s} .secondary {{ color: {theme.text_secondary}; }}
{s} .active {{ color: {theme.accent}; }}
{s} #clock-time {{ font-size: 20px; font-weight: 500; }}
"""
```

Note: if `ruff format` rewraps the long f-string lines, that is fine; they are inside a triple-quoted string and are left untouched.

- [ ] **Step 4: Run to verify pass**

Run: `scripts/py -m pytest tests/test_theme.py -q`
Expected: all pass

- [ ] **Step 5: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell tests
git commit -m "feat: theme to scoped CSS and cairo colors" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Panel state maths (click, drag, hover)

**Files:**
- Create: `shell/panel_state.py`, `tests/test_panel_state.py`

**Interfaces:**
- Produces: `CLICK_THRESHOLD_PX = 4`; `target_depth(extended, hovered, depth, peek) -> float`; `drag_depth(start, delta, depth, edge) -> float` (`delta` is the pointer movement along the depth axis: dy for top/bottom, dx for left/right); `snap_extended(d, depth) -> bool`; `is_click(moved_px) -> bool`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_panel_state.py
import pytest

from shell import panel_state as ps


@pytest.mark.parametrize(
    ("extended", "hovered", "expected"),
    [(True, False, 64), (True, True, 64), (False, True, 14), (False, False, 0)],
)
def test_target_depth(extended, hovered, expected):
    assert ps.target_depth(extended, hovered, 64, 14) == expected


def test_peek_never_exceeds_depth():
    assert ps.target_depth(False, True, 10, 14) == 10


@pytest.mark.parametrize(
    ("edge", "delta", "expected"),
    [
        ("bottom", -30, 30),  # dragging up pulls a bottom panel out
        ("bottom", 20, 0),  # dragging down clamps at collapsed
        ("bottom", -500, 64),  # clamps at full depth
        ("top", 30, 30),
        ("right", -30, 30),
        ("left", 30, 30),
        ("left", -30, 0),
    ],
)
def test_drag_depth(edge, delta, expected):
    assert ps.drag_depth(0, delta, 64, edge) == expected


def test_drag_starts_from_current_depth():
    assert ps.drag_depth(40, -10, 64, "bottom") == 50


def test_snap_threshold_is_half_depth():
    assert ps.snap_extended(32, 64) is True
    assert ps.snap_extended(31.9, 64) is False


def test_click_threshold():
    assert ps.is_click(3.9) is True
    assert ps.is_click(4) is False
```

- [ ] **Step 2: Run to verify failure**

Run: `scripts/py -m pytest tests/test_panel_state.py -q`
Expected: ERROR (`shell.panel_state` missing)

- [ ] **Step 3: Implement `shell/panel_state.py`**

```python
"""Click / drag / hover maths for panels. Pure."""

from __future__ import annotations

CLICK_THRESHOLD_PX = 4

# +1 when moving the pointer in the +x / +y direction deepens the panel.
_SIGN = {"bottom": -1, "top": 1, "right": -1, "left": 1}


def target_depth(extended: bool, hovered: bool, depth: int, peek: int) -> float:
    if extended:
        return float(depth)
    if hovered:
        return float(min(peek, depth))
    return 0.0


def drag_depth(start: float, delta: float, depth: int, edge: str) -> float:
    """Depth after dragging `delta` px along the depth axis, clamped to [0, depth]."""
    return max(0.0, min(float(depth), start + _SIGN[edge] * delta))


def snap_extended(d: float, depth: int) -> bool:
    return d >= depth / 2


def is_click(moved_px: float) -> bool:
    return moved_px < CLICK_THRESHOLD_PX
```

- [ ] **Step 4: Run to verify pass**

Run: `scripts/py -m pytest tests/test_panel_state.py -q`
Expected: all pass

- [ ] **Step 5: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell tests
git commit -m "feat: pure click/drag/hover state maths" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Output mapping and monitor planning

**Files:**
- Create: `shell/outputs.py`, `shell/plan.py`, `tests/test_outputs.py`, `tests/test_plan.py`

**Interfaces:**
- Consumes: `Config` (Task 3).
- Produces:
  - `Output(name, x, y, width, height)` frozen dataclass (logical size)
  - `parse_kscreen(text: str) -> list[Output]` (enabled outputs only; raises `ValueError`/`KeyError` on bad input)
  - `match_geometries(geometries: list[tuple[x, y, w, h]], outputs) -> list[str | None]`
  - `read_kscreen_json(timeout=5.0) -> str` (runs `kscreen-doctor -j`)
  - `desired_shells(config: Config, connected: Iterable[str]) -> list[str]` (sorted connector names that should get an Edge Shell)
  - `reconcile(active: Mapping[str, object], desired: Mapping[str, object]) -> (close: list[str], open: list[str])` (values are Gdk monitor objects compared by identity)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_outputs.py
import json

import pytest

from shell.outputs import Output, match_geometries, parse_kscreen


def out(name, x, y, w, h, scale=1, enabled=True):
    return {
        "name": name,
        "enabled": enabled,
        "pos": {"x": x, "y": y},
        "size": {"width": w, "height": h},
        "scale": scale,
    }


SAMPLE = json.dumps(
    {
        "outputs": [
            out("DP-1", 0, 1080, 1920, 1080),
            out("HDMI-A-1", 0, 0, 1920, 1080),
            out("DP-2", 0, 0, 800, 600, enabled=False),
        ]
    }
)


def test_parse_keeps_enabled_outputs_only():
    assert parse_kscreen(SAMPLE) == [
        Output("DP-1", 0, 1080, 1920, 1080),
        Output("HDMI-A-1", 0, 0, 1920, 1080),
    ]


def test_logical_size_divides_by_scale():
    text = json.dumps({"outputs": [out("A", 0, 0, 3840, 2160, scale=2), out("B", 0, 0, 2880, 1620, scale=1.5)]})
    a, b = parse_kscreen(text)
    assert (a.width, a.height) == (1920, 1080)
    assert (b.width, b.height) == (1920, 1080)


def test_match_by_geometry_regardless_of_gdk_order():
    outs = parse_kscreen(SAMPLE)
    assert match_geometries([(0, 0, 1920, 1080), (0, 1080, 1920, 1080)], outs) == ["HDMI-A-1", "DP-1"]
    assert match_geometries([(0, 1080, 1920, 1080), (0, 0, 1920, 1080)], outs) == ["DP-1", "HDMI-A-1"]


def test_match_falls_back_to_position():
    assert match_geometries([(0, 0, 1280, 720)], parse_kscreen(SAMPLE)) == ["HDMI-A-1"]


def test_unmatched_is_none():
    assert match_geometries([(5000, 5000, 100, 100)], parse_kscreen(SAMPLE)) == [None]


def test_invalid_json_is_a_value_error():
    with pytest.raises(ValueError):
        parse_kscreen("not json")
```

```python
# tests/test_plan.py
from shell.plan import desired_shells, reconcile


def test_only_connected_edge_monitors(make_config):  # Review Focus 2
    cfg = make_config(
        monitors={
            "HDMI-A-1": {"shell": "edge"},
            "DP-1": {"shell": "plasma"},
            "DP-3": {"shell": "edge"},  # configured but not connected
            "DP-4": {"shell": "both"},
        }
    )
    assert desired_shells(cfg, ["HDMI-A-1", "DP-1", "DP-4"]) == ["DP-4", "HDMI-A-1"]


def test_unlisted_connected_monitor_gets_nothing(make_config):
    assert desired_shells(make_config(), ["HDMI-A-1"]) == []


def test_reconcile_is_stable_when_only_gdk_order_changes():  # Review Focus 5
    a, b = object(), object()
    assert reconcile({"A": a, "B": b}, {"B": b, "A": a}) == ([], [])


def test_replugged_connector_is_rebuilt():
    old, new = object(), object()
    assert reconcile({"A": old}, {"A": new}) == (["A"], ["A"])


def test_removed_and_added():
    a, b = object(), object()
    assert reconcile({"A": a}, {"B": b}) == (["A"], ["B"])
    assert reconcile({}, {"B": b}) == ([], ["B"])
    assert reconcile({"A": a}, {}) == (["A"], [])
```

- [ ] **Step 2: Run to verify failure**

Run: `scripts/py -m pytest tests/test_outputs.py tests/test_plan.py -q`
Expected: ERROR (modules missing)

- [ ] **Step 3: Implement**

```python
# shell/outputs.py
"""Map Gdk monitors to connector names via `kscreen-doctor -j`. Pure except read_kscreen_json."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Output:
    name: str
    x: int
    y: int
    width: int  # logical (scaled) size, as Gdk reports it
    height: int


def parse_kscreen(text: str) -> list[Output]:
    outputs = []
    for o in json.loads(text).get("outputs", []):
        if not o.get("enabled"):
            continue
        scale = float(o.get("scale") or 1.0)
        outputs.append(
            Output(
                name=o["name"],
                x=o["pos"]["x"],
                y=o["pos"]["y"],
                width=round(o["size"]["width"] / scale),
                height=round(o["size"]["height"] / scale),
            )
        )
    return outputs


def match_geometries(
    geometries: list[tuple[int, int, int, int]], outputs: list[Output]
) -> list[str | None]:
    """Connector name for each Gdk geometry (x, y, w, h): exact match, else by position."""
    names: list[str | None] = []
    for x, y, w, h in geometries:
        exact = next((o.name for o in outputs if (o.x, o.y, o.width, o.height) == (x, y, w, h)), None)
        names.append(exact or next((o.name for o in outputs if (o.x, o.y) == (x, y)), None))
    return names


def read_kscreen_json(timeout: float = 5.0) -> str:
    result = subprocess.run(
        ["kscreen-doctor", "-j"], capture_output=True, text=True, timeout=timeout, check=True
    )
    return result.stdout
```

```python
# shell/plan.py
"""Which monitors get an Edge Shell, and how to move from the current set to the wanted set."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from shell.config.models import Config


def desired_shells(config: Config, connected: Iterable[str]) -> list[str]:
    """Connected monitors whose mode builds Edge Shell windows. Unconnected names are ignored."""
    return sorted(n for n in connected if config.monitor(n).shell in ("edge", "both"))


def reconcile(
    active: Mapping[str, object], desired: Mapping[str, object]
) -> tuple[list[str], list[str]]:
    """(names to close, names to open). A connector whose Gdk monitor object changed is both."""
    close = sorted(n for n, mon in active.items() if n not in desired or desired[n] is not mon)
    open_ = sorted(n for n, mon in desired.items() if n not in active or active[n] is not mon)
    return close, open_
```

- [ ] **Step 4: Run to verify pass**

Run: `scripts/py -m pytest tests/test_outputs.py tests/test_plan.py -q`
Expected: all pass

- [ ] **Step 5: Sanity-check the real kscreen output against the parser**

Run: `scripts/py -c "from shell.outputs import *; print(parse_kscreen(read_kscreen_json()))"`
Expected: two `Output` entries, `HDMI-A-1` at (0, 0) and `DP-1` at (0, 1080), each 1920x1080.

- [ ] **Step 6: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell tests
git commit -m "feat: kscreen output mapping and monitor reconcile planning" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Frame windows and monitor shell (GTK)

**Files:**
- Create: `shell/frame.py`, `shell/monitors.py`, `tests/test_gtk_imports.py`

**Interfaces:**
- Consumes: `draw_screen_corner`, `hex_to_rgba`, `scope_class`, `Theme`, `Config`, `match_geometries`, `parse_kscreen`, `read_kscreen_json`.
- Produces:
  - `EDGES`, `CORNERS` tuples; `FrameEdge(edge, monitor, theme, scope)`; `ScreenCorner(corner, monitor, theme, scope)` with `.set_theme(theme)`
  - `gdk_monitors() -> list[Gdk.Monitor]`, `monitors_by_name() -> dict[str, Gdk.Monitor]`, `describe_monitors() -> list[str]`
  - `MonitorShell(name, monitor, config, register_window)` with `.name`, `.monitor`, `.windows`, `.close()`. (Panels are added to it in Task 15.)

- [ ] **Step 1: Write the import smoke test** (skipped where GTK is absent, e.g. CI)

```python
# tests/test_gtk_imports.py
import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")


def test_gtk_modules_import():
    import shell.frame  # noqa: F401
    import shell.monitors  # noqa: F401
```

- [ ] **Step 2: Create `shell/frame.py`**

```python
"""Frame strips and rounded screen corners (GTK / Fabric windows)."""

from __future__ import annotations

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from fabric.widgets.box import Box
from fabric.widgets.wayland import WaylandWindow
from gi.repository import Gtk, GtkLayerShell

from shell.config.models import Theme
from shell.draw import draw_screen_corner
from shell.theme import hex_to_rgba

EDGES = ("top", "bottom", "left", "right")
CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")

_STRIP_ANCHOR = {
    "top": "top left right",
    "bottom": "bottom left right",
    "left": "left top bottom",
    "right": "right top bottom",
}


class FrameEdge(WaylandWindow):
    """One side of the frame. The only surface that reserves screen space."""

    def __init__(self, edge: str, monitor, theme: Theme, scope: str):
        horizontal = edge in ("top", "bottom")
        t = theme.thickness
        super().__init__(
            layer="top",
            anchor=_STRIP_ANCHOR[edge],
            exclusivity="auto",  # NOT "normal": that reserves 1 px
            keyboard_mode="none",
            monitor=monitor,
            title=f"edge-shell-frame-{edge}",
            style_classes=[scope],
            child=Box(name="frame-strip", size=(-1, t) if horizontal else (t, -1)),
            all_visible=True,
        )


class ScreenCorner(WaylandWindow):
    """The rounded desktop corner: click-through, placed just inside the frame."""

    def __init__(self, corner: str, monitor, theme: Theme, scope: str):
        vertical, horizontal = corner.split("-")
        t, r = theme.thickness, theme.radius
        area = Gtk.DrawingArea()
        area.set_size_request(r, r)
        super().__init__(
            layer="top",
            anchor=f"{vertical} {horizontal}",
            margin=f"{t}px {t}px {t}px {t}px",
            exclusivity="none",
            pass_through=True,
            monitor=monitor,
            title=f"edge-shell-corner-{corner}",
            style_classes=[scope],
            child=area,
            all_visible=True,
        )
        GtkLayerShell.set_exclusive_zone(self, -1)  # place by margin, not by other zones
        self._corner = corner
        self._radius = r
        self._rgba = hex_to_rgba(theme.frame)
        self._area = area
        area.connect("draw", self._on_draw)

    def set_theme(self, theme: Theme) -> None:
        self._rgba = hex_to_rgba(theme.frame)
        self._area.queue_draw()

    def _on_draw(self, _area, cr) -> bool:
        cr.save()
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.restore()
        draw_screen_corner(cr, self._corner, self._radius, self._rgba)
        return False
```

- [ ] **Step 3: Create `shell/monitors.py`**

```python
"""Gdk monitor <-> connector name mapping, and the window set for one monitor (GTK)."""

from __future__ import annotations

import logging
import subprocess

import gi

gi.require_version("Gdk", "3.0")
from gi.repository import Gdk

from shell.config.models import Config
from shell.frame import CORNERS, EDGES, FrameEdge, ScreenCorner
from shell.outputs import match_geometries, parse_kscreen, read_kscreen_json
from shell.theme import scope_class

log = logging.getLogger(__name__)


def gdk_monitors() -> list[Gdk.Monitor]:
    display = Gdk.Display.get_default()
    return [display.get_monitor(i) for i in range(display.get_n_monitors())]


def _names_for(monitors: list[Gdk.Monitor]) -> list[str | None]:
    # Gdk's model string is the panel model, not the connector, so match by geometry.
    outputs = parse_kscreen(read_kscreen_json())
    geoms = []
    for m in monitors:
        g = m.get_geometry()
        geoms.append((g.x, g.y, g.width, g.height))
    return match_geometries(geoms, outputs)


def monitors_by_name() -> dict[str, Gdk.Monitor]:
    monitors = gdk_monitors()
    try:
        names = _names_for(monitors)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        log.error("cannot map monitors to connectors via kscreen-doctor: %s", exc)
        return {}
    return {name: mon for name, mon in zip(names, monitors, strict=True) if name}


def describe_monitors() -> list[str]:
    monitors = gdk_monitors()
    try:
        names = _names_for(monitors)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        names = [None] * len(monitors)
        log.error("kscreen-doctor failed: %s", exc)
    lines = []
    for i, (m, name) in enumerate(zip(monitors, names, strict=True)):
        g = m.get_geometry()
        lines.append(f"{i}  {name or '?':<10} {g.x},{g.y} {g.width}x{g.height}  scale {m.get_scale_factor()}")
    return lines


class MonitorShell:
    """Every Edge Shell window for one monitor: 4 frame strips, 4 corners (panels: Task 15)."""

    def __init__(self, name: str, monitor: Gdk.Monitor, config: Config, register_window):
        self.name = name
        self.monitor = monitor
        self._register = register_window
        self.windows: list = []
        self.corners: list[ScreenCorner] = []
        theme = config.theme_for(name)
        scope = scope_class(name)
        for edge in EDGES:
            self._track(FrameEdge(edge, monitor, theme, scope))
        for corner in CORNERS:
            window = ScreenCorner(corner, monitor, theme, scope)
            self.corners.append(window)
            self._track(window)

    def _track(self, window) -> None:
        self.windows.append(window)
        self._register(window)

    def close(self) -> None:
        for window in self.windows:
            try:
                window.destroy()
            except Exception:  # the compositor may already have closed it (monitor unplugged)
                log.exception("failed to destroy window on %s", self.name)
        self.windows.clear()
```

- [ ] **Step 4: Run the import smoke test**

Run: `scripts/py -m pytest tests/test_gtk_imports.py -q`
Expected: 1 passed. A `ModuleNotFoundError` for a Fabric module means a wrong import path in the file above; fix it using `fabric_search_api`.

- [ ] **Step 5: Check the monitor listing**

Run: `scripts/py -c "from shell.monitors import describe_monitors; print(chr(10).join(describe_monitors()))"`
Expected (order may vary):
```
0  HDMI-A-1   0,0 1920x1080  scale 1
1  DP-1       0,1080 1920x1080  scale 1
```

- [ ] **Step 6: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell tests
git commit -m "feat: frame strips, screen corners, and per-monitor window set" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 14: App, CLI entry point, and Gate A (the frame on HDMI-A-1)

**Files:**
- Create: `shell/app.py`, `main.py`, `examples/hdmi-test.toml`

**Interfaces:**
- Consumes: `ConfigStore`, `desired_shells`, `reconcile`, `MonitorShell`, `monitors_by_name`, `to_css`, `scope_class`.
- Produces: `EdgeShellApp(store)` with `.run()`, `.sync_monitors()`, `.register_window(window)`, `.css()`, `.refresh_css()`; `main(argv) -> int` with flags `--config PATH`, `--list-outputs`, `-v`.

- [ ] **Step 1: Create `examples/hdmi-test.toml`**

```toml
# Runs Edge Shell on HDMI-A-1 only; DP-1 keeps its Plasma panel untouched.
#   scripts/py main.py --config examples/hdmi-test.toml
[monitors.HDMI-A-1]
shell = "edge"
```

- [ ] **Step 2: Create `shell/app.py`**

```python
"""Application wiring: config -> monitors -> windows."""

from __future__ import annotations

import logging
import signal

import gi

gi.require_version("Gtk", "3.0")
from fabric import Application

from shell import plan
from shell.config.store import ConfigStore
from shell.monitors import MonitorShell, monitors_by_name
from shell.theme import scope_class, to_css

log = logging.getLogger(__name__)


class EdgeShellApp:
    def __init__(self, store: ConfigStore):
        self.store = store
        self.app: Application | None = None
        self.shells: dict[str, MonitorShell] = {}
        self._early: list = []  # windows created before the Application exists

    @property
    def config(self):
        return self.store.config

    def register_window(self, window) -> None:
        if self.app is None:
            self._early.append(window)
        else:
            self.app.add_window(window)

    def sync_monitors(self) -> None:
        connected = monitors_by_name()
        wanted = plan.desired_shells(self.config, connected)
        desired = {name: connected[name] for name in wanted}
        active = {name: shell.monitor for name, shell in self.shells.items()}
        close, open_ = plan.reconcile(active, desired)
        for name in close:
            log.info("closing Edge Shell on %s", name)
            self.shells.pop(name).close()
        for name in open_:
            log.info("opening Edge Shell on %s", name)
            self.shells[name] = MonitorShell(name, desired[name], self.config, self.register_window)
        if close or open_:
            self.refresh_css()

    def css(self) -> str:
        return "\n".join(
            to_css(self.config.theme_for(name), scope_class(name)) for name in sorted(self.shells)
        )

    def refresh_css(self) -> None:
        if self.app is not None:
            self.app.set_stylesheet_from_string(self.css(), compile=False)

    def run(self) -> None:
        self.sync_monitors()
        self.app = Application("edge-shell", *self._early)
        self._early.clear()
        self.app.set_stylesheet_from_string(self.css(), compile=False)
        self.app.hold()  # stay alive even with no windows (e.g. all monitors set to plasma)
        signal.signal(signal.SIGINT, signal.SIG_DFL)  # Ctrl+C quits
        self.app.run()
```

- [ ] **Step 3: Create `main.py`**

```python
"""Edge Shell entry point."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from shell.config.loader import USER_PATH
from shell.config.models import ConfigError
from shell.config.store import ConfigStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="edge-shell")
    parser.add_argument("--config", type=Path, default=USER_PATH, help="config file (default: %(default)s)")
    parser.add_argument("--list-outputs", action="store_true", help="print monitors and connector names")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.list_outputs:
        from shell.monitors import describe_monitors

        print("\n".join(describe_monitors()))
        return 0

    import widgets  # noqa: F401  (registers the built-in panels before the config is validated)

    try:
        store = ConfigStore(args.config)
    except ConfigError as exc:
        print(f"config error:\n{exc}", file=sys.stderr)
        return 2

    from shell.app import EdgeShellApp

    EdgeShellApp(store).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Check the non-visual paths**

Run: `scripts/py main.py --list-outputs`
Expected: the two-line monitor listing from Task 13.

Run: `scripts/py main.py --config /nonexistent.toml --list-outputs`
Expected: same listing (the config is not read for `--list-outputs`).

Run: `printf '[theme]\nbogus = 1\n' > /tmp/bad.toml && scripts/py main.py --config /tmp/bad.toml; echo "exit=$?"`
Expected: `config error:` followed by `theme.bogus: Extra inputs are not permitted`, then `exit=2`.

- [ ] **Step 5: VERIFY and commit (before the visual gate)**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell main.py examples
git commit -m "feat: app wiring and CLI; Edge Shell frame per configured monitor" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: GATE A: Phil checks the frame on HDMI-A-1**

Start it from a terminal (leave the terminal open; Ctrl+C quits):
```bash
scripts/py main.py --config examples/hdmi-test.toml -v
```
Ask Phil to confirm each item and report anything odd (a `spectacle` screenshot of the top monitor helps):

1. A 10 px dark frame appears on all four edges of the **top** monitor (HDMI-A-1) and **nowhere** on DP-1. DP-1 and its Plasma panel look exactly as before.
2. Inside the frame, the desktop's four corners are visibly **rounded**.
3. **Maximize a window** on HDMI-A-1 (for example Dolphin): it stops at the frame, leaving the frame visible all around.
4. **Click-through:** click a desktop icon or window right at a rounded corner; the click reaches what is underneath.
5. No gaps or hairlines where a strip meets a corner.
6. Ctrl+C in the terminal removes the frame completely.

**If any of 1-5 fails:** stop. Capture the `-v` log and a screenshot, and decide with Phil whether to debug exclusive-zone settings or switch to the single-canvas fallback (spec 5.1) before building panels on top.


---

### Task 15: EdgePanel and the dock, with Gate B (fusion and interaction)

**Files:**
- Create: `shell/edge_panel.py`, `widgets/dock.py`, `examples/dock-test.toml`
- Modify: `widgets/__init__.py`, `shell/monitors.py` (replace `MonitorShell` and its imports)

**Interfaces:**
- Consumes: `geometry`, `panel_state`, `Tween`, `draw_panel`, `hex_to_rgba`, `PanelGeometry`, `PanelDefaults`, `register`, `widget_class`, `panels_for`.
- Produces:
  - `EdgePanel(spec: PanelGeometry, theme: Theme, monitor: Gdk.Monitor, index: int, scope: str)`; subclasses implement `build_content() -> Gtk.Widget`; set class attribute `wants_keyboard = True` for text-input panels.
  - `EdgePanel.toggle()`, `.set_state("collapsed" | "extended")`, `.apply_theme(theme)` (used by live reload in Task 18).
  - `MonitorShell.panels: list[EdgePanel]` (built from the monitor's configured panels).

- [ ] **Step 1: Create `shell/edge_panel.py`**

```python
"""EdgePanel: a layer-shell window that grows out of the frame and fuses with it."""

from __future__ import annotations

import cairo
import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.overlay import Overlay
from fabric.widgets.wayland import WaylandWindow
from gi.repository import Gdk, Gtk, GtkLayerShell

from shell import geometry, panel_state
from shell.anim import Tween
from shell.config.models import Theme
from shell.draw import draw_panel
from shell.gdk_util import monitor_index
from shell.panel_spec import PanelGeometry
from shell.theme import hex_to_rgba

HANDLE_DEPTH = 14  # handle size across the depth axis
HANDLE_LENGTH = 44  # handle size along the edge


class EdgePanel(WaylandWindow):
    """Base class for panels. Subclasses implement build_content()."""

    wants_keyboard = False

    def __init__(self, spec: PanelGeometry, theme: Theme, monitor, index: int, scope: str):
        t, r = theme.thickness, theme.radius
        mon = monitor.get_geometry()
        extent = mon.width if geometry.is_horizontal(spec.edge) else mon.height
        anchor, margin = geometry.anchor_and_margin(
            spec.edge, spec.pos, spec.length + 2 * r, r, extent
        )
        super().__init__(
            layer="top",
            anchor=anchor,
            margin=margin,
            exclusivity="none",
            keyboard_mode="on-demand" if self.wants_keyboard else "none",
            # Fabric's monitor property is an int: a Gdk.Monitor object is silently ignored
            monitor=monitor_index(monitor),
            title=f"edge-shell-{spec.label}-{index}",
            name="edge-panel",
            style_classes=[scope],
            visible=False,
        )
        # Fabric's "none" sets zone 0, which makes KWin push us clear of the frame.
        # -1 lets the panel overlap the frame strip so the two fuse.
        GtkLayerShell.set_exclusive_zone(self, -1)

        self.spec = spec
        self._theme = theme
        self._extended = spec.state == "extended"
        self._hovered = False
        self._d = 0.0
        self._last_rect: tuple[int, int, int, int] | None = None
        self._press: tuple[float, float] | None = None  # drag state (used from Task 17)
        self._press_depth = 0.0
        self._dragging = False
        self._suppress_click = False

        self._canvas = Gtk.DrawingArea()
        self._canvas.connect("draw", self._on_draw)
        self._content = self.build_content()
        self._handle = self._build_handle()
        self.add(Overlay(child=self._canvas, overlays=[self._content, self._handle]))

        # Allocated once at full size; animation never resizes the layer surface.
        w, h = geometry.surface_size(spec.edge, spec.length, spec.depth, t, r)
        self.set_size_request(w, h)
        self._place_content()

        self.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.connect("enter-notify-event", self._on_enter)
        self.connect("leave-notify-event", self._on_leave)

        self._tween = Tween(self, self._apply_depth, theme.duration_ms)
        self._fade = Tween(self, self._content.set_opacity, 170, delay_ms=110)
        self.show_all()
        self._tween.jump_to(spec.depth if self._extended else 0)
        self._fade.jump_to(1.0 if self._extended else 0.0)
        self._sync_handle()

    # ---- override in subclasses ------------------------------------------------
    def build_content(self) -> Gtk.Widget:
        return Box()

    # ---- public ----------------------------------------------------------------
    def toggle(self, *_) -> None:
        self._extended = not self._extended
        self._hovered = False
        self._retarget()

    def set_state(self, state: str) -> None:
        self._extended = state == "extended"
        self._hovered = False
        self._retarget()

    def apply_theme(self, theme: Theme) -> None:
        """Colors only; geometry changes rebuild the panel instead."""
        self._theme = theme
        self._canvas.queue_draw()

    # ---- state -----------------------------------------------------------------
    def _on_enter(self, *_) -> None:
        self._hovered = True
        self._retarget()

    def _on_leave(self, _widget, event) -> None:
        if event.detail == Gdk.NotifyType.INFERIOR:  # pointer moved onto a child widget
            return
        self._hovered = False
        self._retarget()

    def _retarget(self) -> None:
        target = panel_state.target_depth(
            self._extended, self._hovered, self.spec.depth, self._theme.peek
        )
        self._sync_handle()
        self._tween.animate_to(target)
        if self._extended:
            self._fade.animate_to(1.0)  # fades in over the last part of the reveal
        else:
            self._fade.jump_to(0.0)  # fades out at once so text never clips mid-slide

    def _sync_handle(self) -> None:
        self._content.set_sensitive(self._extended)
        name = ("Collapse " if self._extended else "Expand ") + self.spec.label
        self._handle.set_tooltip_text(name)
        self._handle.get_accessible().set_name(name)

    def _on_clicked(self, *_) -> None:
        if self._suppress_click:  # the release that ended a drag
            self._suppress_click = False
            return
        self.toggle()

    # ---- per frame -------------------------------------------------------------
    def _apply_depth(self, d: float) -> None:
        self._d = d
        self._place_handle(d)
        self._update_input_region(d)
        self._canvas.queue_draw()

    def _on_draw(self, _area, cr) -> bool:
        cr.save()
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.restore()
        t = self._theme
        draw_panel(
            cr,
            self.spec.edge,
            self.spec.length,
            self.spec.depth,
            self._d,
            t.thickness,
            t.radius,
            hex_to_rgba(t.frame),
        )
        return False

    def _update_input_region(self, d: float) -> None:
        # Only the body (plus an invisible hover zone while collapsed) takes input.
        t = self._theme
        rect = geometry.input_rect(
            self.spec.edge, self.spec.length, self.spec.depth, d, t.thickness, t.radius, t.hover_zone
        )
        if rect == self._last_rect:
            return
        self._last_rect = rect
        self.input_shape_combine_region(cairo.Region(cairo.RectangleInt(*rect)))

    # ---- layout ----------------------------------------------------------------
    def _build_handle(self) -> Button:
        vertical = self.spec.edge in ("left", "right")
        dots = Box(
            orientation="v" if vertical else "h",
            spacing=3,
            h_align="center",
            v_align="center",
            children=[Box(style_classes="handle-dot") for _ in range(3)],
        )
        size = (HANDLE_DEPTH, HANDLE_LENGTH) if vertical else (HANDLE_LENGTH, HANDLE_DEPTH)
        handle = Button(name="handle", child=dots, size=size, on_clicked=self._on_clicked)
        return handle

    def _place_handle(self, d: float) -> None:
        inset = max(0, int(self._theme.thickness + d - HANDLE_DEPTH))  # rides the inner edge
        h, edge = self._handle, self.spec.edge
        if edge == "bottom":
            h.set_halign(Gtk.Align.CENTER)
            h.set_valign(Gtk.Align.END)
            h.set_margin_bottom(inset)
        elif edge == "top":
            h.set_halign(Gtk.Align.CENTER)
            h.set_valign(Gtk.Align.START)
            h.set_margin_top(inset)
        elif edge == "left":
            h.set_halign(Gtk.Align.START)
            h.set_valign(Gtk.Align.CENTER)
            h.set_margin_start(inset)
        else:
            h.set_halign(Gtk.Align.END)
            h.set_valign(Gtk.Align.CENTER)
            h.set_margin_end(inset)

    def _place_content(self) -> None:
        c, t, s = self._content, self._theme.thickness, self.spec
        if s.edge in ("bottom", "top"):
            c.set_size_request(s.length, s.depth)
            c.set_halign(Gtk.Align.CENTER)
            if s.edge == "bottom":
                c.set_valign(Gtk.Align.END)
                c.set_margin_bottom(t)
            else:
                c.set_valign(Gtk.Align.START)
                c.set_margin_top(t)
        else:
            c.set_size_request(s.depth, s.length)
            c.set_valign(Gtk.Align.CENTER)
            if s.edge == "left":
                c.set_halign(Gtk.Align.START)
                c.set_margin_start(t)
            else:
                c.set_halign(Gtk.Align.END)
                c.set_margin_end(t)
```

- [ ] **Step 2: Create `widgets/dock.py`**

```python
"""Dock: a row of app launchers on the bottom edge."""

from __future__ import annotations

from fabric.utils import exec_shell_command_async
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image

from shell.edge_panel import EdgePanel
from shell.panel_spec import PanelDefaults
from shell.registry import register

APPS = [  # (tooltip, icon name, command)
    ("Terminal", "utilities-terminal-symbolic", "konsole"),
    ("Files", "folder-symbolic", "dolphin"),
    ("Settings", "preferences-system-symbolic", "systemsettings"),
]


@register("dock", PanelDefaults(edge="bottom", length=560, depth=64, label="dock"))
class DockPanel(EdgePanel):
    def build_content(self):
        return Box(
            name="dock",
            orientation="h",
            spacing=8,
            h_align="center",
            v_align="center",
            children=[
                Button(
                    style_classes="icon-button",
                    tooltip_text=tip,
                    child=Image(icon_name=icon, icon_size=20),
                    on_clicked=lambda *_, c=cmd: exec_shell_command_async(c),
                )
                for tip, icon, cmd in APPS
            ],
        )
```

- [ ] **Step 3: Register the widget package and add the test config**

`widgets/__init__.py`:
```python
"""Built-in panel widgets. Importing this package registers them."""

from widgets import dock  # noqa: F401
```

`examples/dock-test.toml`:
```toml
[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]
widget = "dock"
```

- [ ] **Step 4: Give `MonitorShell` its panels** (edit `shell/monitors.py`)

Replace the imports block's `from shell.frame ...` line and everything from `class MonitorShell:` to the end of the file with:

```python
from shell.edge_panel import EdgePanel
from shell.frame import CORNERS, EDGES, FrameEdge, ScreenCorner
from shell.panel_spec import PanelGeometry
from shell.registry import panels_for, widget_class
```
(keep the other imports as they are; the `from shell.frame import ...` line is replaced by the four lines above) and

```python
class MonitorShell:
    """Every Edge Shell window for one monitor: 4 frame strips, 4 corners, N panels."""

    def __init__(self, name: str, monitor: Gdk.Monitor, config: Config, register_window):
        self.name = name
        self.monitor = monitor
        self._register = register_window
        self._scope = scope_class(name)
        self.windows: list = []
        self.corners: list[ScreenCorner] = []
        self.panels: list[EdgePanel] = []
        theme = config.theme_for(name)
        for edge in EDGES:
            self._track(FrameEdge(edge, monitor, theme, self._scope))
        for corner in CORNERS:
            window = ScreenCorner(corner, monitor, theme, self._scope)
            self.corners.append(window)
            self._track(window)
        for index, geo in enumerate(panels_for(config, name)):
            self.panels.append(self._make_panel(index, geo, theme))

    def _make_panel(self, index: int, geo: PanelGeometry, theme) -> EdgePanel:
        panel = widget_class(geo.widget)(geo, theme, self.monitor, index, self._scope)
        self._track(panel)
        return panel

    def _track(self, window) -> None:
        self.windows.append(window)
        self._register(window)

    def close(self) -> None:
        for window in self.windows:
            try:
                window.destroy()
            except Exception:  # the compositor may already have closed it (monitor unplugged)
                log.exception("failed to destroy window on %s", self.name)
        self.windows.clear()
        self.panels.clear()
```

- [ ] **Step 5: Static checks**

Run: `scripts/py -m pytest tests/test_gtk_imports.py -q` (extend the test first: add `import shell.edge_panel  # noqa: F401` and `import widgets  # noqa: F401` inside `test_gtk_modules_import`)
Expected: 1 passed.

Run the Fabric static validator on `shell/edge_panel.py` and `widgets/dock.py` (the `fabric_validate_code` MCP tool, if available) and fix anything it reports about constructor kwargs.

- [ ] **Step 6: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell widgets examples tests
git commit -m "feat: EdgePanel (fused, animated, hover/click) and dock widget" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7: GATE B: Phil checks fusion and interaction**

```bash
scripts/py main.py --config examples/dock-test.toml -v
```
Part 1, fusion (the panel starts extended):
1. The dock sits bottom-centre on HDMI-A-1, about 560 px wide and 64 px above the frame.
2. It looks like **one shape with the frame**: no gap, no line, no colour difference between dock and frame. Both bottom corners where the dock meets the frame curve outward smoothly (concave fillets); the dock's two top corners are rounded.
3. Three icons show (Terminal, Files, Settings); clicking Terminal launches Konsole.

Part 2, interaction:
4. Click the three dots at the dock's top edge: it collapses in about 0.3 s, fast out and soft landing. Icons vanish **immediately**; the fillets shrink to nothing as it goes.
5. Collapsed, only the dots remain, sitting in the bottom frame strip.
6. Move the pointer to the bottom edge, centred: the panel **peeks** about 14 px and the dots brighten. Moving away collapses it again.
7. Click the dots when collapsed: it expands and the icons fade in near the end.
8. While collapsed, a window's title bar or buttons placed just above the bottom edge (more than about 16 px up) still receive clicks.

Report anything that jitters, flickers, leaves a hairline seam, or does not follow the pointer. **If part 1 fails (visible seam or gap):** stop and decide with Phil between debugging (exclusive zone, repaint of the strip under the panel) and the single-canvas fallback (spec 5.1).

---

### Task 16: Clock and system bar, with Gate C (top and right edges)

**Files:**
- Create: `services/sysinfo.py`, `widgets/clock.py`, `widgets/system_bar.py`, `tests/test_sysinfo.py`, `examples/panels-test.toml`
- Modify: `widgets/__init__.py`

**Interfaces:**
- Produces: `parse_meminfo(text) -> float` (percent used), `parse_cpu_times(text) -> (total, idle)`, `cpu_percent(prev, cur) -> float`, `read_meminfo_percent() -> float`, `read_cpu_times() -> (total, idle)`; registered widgets `"clock"` (top, 168x46, centred) and `"system_bar"` (right, 300x56, pos 600).

- [ ] **Step 1: Write failing tests**

```python
# tests/test_sysinfo.py
import pytest

from services.sysinfo import cpu_percent, parse_cpu_times, parse_meminfo

MEMINFO = "MemTotal:       16000000 kB\nMemFree:         1000000 kB\nMemAvailable:    4000000 kB\n"
STAT_A = "cpu  100 0 100 700 100 0 0 0 0 0\ncpu0 50 0 50 350 50 0 0 0 0 0\n"
STAT_B = "cpu  200 0 200 1000 100 0 0 0 0 0\ncpu0 100 0 100 500 50 0 0 0 0 0\n"


def test_parse_meminfo_percent_used():
    assert parse_meminfo(MEMINFO) == pytest.approx(75.0)


def test_parse_cpu_times_total_and_idle():
    assert parse_cpu_times(STAT_A) == (1000, 800)  # idle = idle + iowait


def test_cpu_percent_between_samples():
    assert cpu_percent(parse_cpu_times(STAT_A), parse_cpu_times(STAT_B)) == pytest.approx(40.0)


def test_cpu_percent_no_elapsed_time_is_zero():
    sample = parse_cpu_times(STAT_A)
    assert cpu_percent(sample, sample) == 0.0
```

- [ ] **Step 2: Run to verify failure**

Run: `scripts/py -m pytest tests/test_sysinfo.py -q`
Expected: ERROR (`services.sysinfo` missing)

- [ ] **Step 3: Implement `services/sysinfo.py`**

```python
"""CPU and memory usage from /proc. Pure parsing + two tiny readers."""

from __future__ import annotations

from pathlib import Path


def parse_meminfo(text: str) -> float:
    fields: dict[str, int] = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts:
            fields[key] = int(parts[0])
    return 100.0 * (1 - fields["MemAvailable"] / fields["MemTotal"])


def parse_cpu_times(text: str) -> tuple[int, int]:
    """(total, idle) jiffies from the first line of /proc/stat."""
    values = [int(v) for v in text.splitlines()[0].split()[1:9]]
    return sum(values), values[3] + values[4]  # idle + iowait


def cpu_percent(prev: tuple[int, int], cur: tuple[int, int]) -> float:
    total, idle = cur[0] - prev[0], cur[1] - prev[1]
    return 0.0 if total <= 0 else 100.0 * (1 - idle / total)


def read_meminfo_percent() -> float:
    return parse_meminfo(Path("/proc/meminfo").read_text())


def read_cpu_times() -> tuple[int, int]:
    return parse_cpu_times(Path("/proc/stat").read_text())
```

- [ ] **Step 4: Create the widgets**

```python
# widgets/clock.py
"""Clock: time of day on the top edge."""

from __future__ import annotations

from fabric.widgets.box import Box
from fabric.widgets.datetime import DateTime

from shell.edge_panel import EdgePanel
from shell.panel_spec import PanelDefaults
from shell.registry import register


@register("clock", PanelDefaults(edge="top", length=168, depth=46, label="clock"))
class ClockPanel(EdgePanel):
    def build_content(self):
        return Box(
            name="clock",
            h_align="center",
            v_align="center",
            children=DateTime(formatters=["%H:%M"], interval=10_000, name="clock-time"),
        )
```

```python
# widgets/system_bar.py
"""System bar: CPU and memory on the right edge."""

from __future__ import annotations

from fabric.utils import invoke_repeater
from fabric.widgets.box import Box
from fabric.widgets.label import Label

from services.sysinfo import cpu_percent, read_cpu_times, read_meminfo_percent
from shell.edge_panel import EdgePanel
from shell.panel_spec import PanelDefaults
from shell.registry import register


@register(
    "system_bar",
    PanelDefaults(edge="right", length=300, depth=56, pos=600, label="system bar"),
)
class SystemBarPanel(EdgePanel):
    def build_content(self):
        self._cpu = Label(style_classes="secondary")
        self._mem = Label(style_classes="secondary")
        self._prev = read_cpu_times()
        invoke_repeater(2000, self._refresh)
        return Box(
            name="system-bar",
            orientation="v",
            spacing=12,
            h_align="center",
            v_align="center",
            children=[self._cpu, self._mem],
        )

    def _refresh(self) -> bool:
        cur = read_cpu_times()
        self._cpu.set_label(f"CPU\n{cpu_percent(self._prev, cur):.0f}%")
        self._prev = cur
        self._mem.set_label(f"RAM\n{read_meminfo_percent():.0f}%")
        return True  # keep repeating
```

`widgets/__init__.py`:
```python
"""Built-in panel widgets. Importing this package registers them."""

from widgets import clock, dock, system_bar  # noqa: F401
```

`examples/panels-test.toml`:
```toml
[monitors.HDMI-A-1]
shell = "edge"

[[monitors.HDMI-A-1.panels]]
widget = "dock"

[[monitors.HDMI-A-1.panels]]
widget = "clock"

[[monitors.HDMI-A-1.panels]]
widget = "system_bar"
```

- [ ] **Step 5: Run to verify pass, then VERIFY and commit**

Run: `scripts/py -m pytest tests/test_sysinfo.py -q` -> all pass. Extend `tests/test_gtk_imports.py` to import `widgets.clock` and `widgets.system_bar` too.

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add services widgets tests examples
git commit -m "feat: clock and system bar panels, /proc sysinfo" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: GATE C: Phil checks the top and right edges**

```bash
scripts/py main.py --config examples/panels-test.toml -v
```
1. **Clock** sits top-centre, 46 px deep, showing `HH:MM`. Its fillets curve into the top frame **mirrored correctly** (they open outward where it meets the frame, like the dock's do at the bottom).
2. **System bar** sits on the right edge from about y=600 to y=900 (300 px), 56 px deep. Its fillets curve into the **right** frame at both ends. This proves the rotation maths.
3. CPU and RAM percentages update about every 2 s, and the text is upright and readable.
4. For each panel, collapse (click dots), peek (hover the strip) and re-expand work in the **correct direction** (clock grows downward, system bar grows leftward).
5. All three panels together show no seams and no overlap.

If an edge has wrong-way fillets or a flipped panel, the matrix in `geometry.py` for that edge is the suspect; the render tests only prove the maths is self-consistent, so tell me which edge.

---

### Task 17: Drag to open and close, with Gate D

**Files:**
- Modify: `shell/edge_panel.py`

**Interfaces:**
- Consumes: `panel_state.drag_depth`, `snap_extended`, `is_click`; `EdgePanel._press`, `_press_depth`, `_dragging`, `_suppress_click` (declared in Task 15).

- [ ] **Step 1: Add the import** (edit the top of `shell/edge_panel.py`)

Replace
```python
import cairo
import gi
```
with
```python
import math

import cairo
import gi
```

- [ ] **Step 2: Wire the handle's pointer events** (edit `_build_handle`)

Replace `        return handle` with:

```python
        handle.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        handle.connect("button-press-event", self._on_press)
        handle.connect("motion-notify-event", self._on_motion)
        handle.connect("button-release-event", self._on_release)
        return handle
```

- [ ] **Step 3: Add the drag handlers** (insert before `_place_handle`)

```python
    # ---- drag ------------------------------------------------------------------
    def _on_press(self, _widget, event) -> bool:
        if event.button != 1:
            return False
        self._press = (event.x_root, event.y_root)
        self._press_depth = self._d
        self._dragging = False
        self._suppress_click = False
        return False  # let the button track the press so a plain click still toggles

    def _on_motion(self, _widget, event) -> bool:
        if self._press is None:
            return False
        dx = event.x_root - self._press[0]
        dy = event.y_root - self._press[1]
        if not self._dragging:
            if panel_state.is_click(math.hypot(dx, dy)):
                return False
            self._dragging = True
            self._suppress_click = True
            self._hovered = False
        delta = dy if geometry.is_horizontal(self.spec.edge) else dx
        d = panel_state.drag_depth(self._press_depth, delta, self.spec.depth, self.spec.edge)
        self._tween.jump_to(d)  # follow the pointer exactly; cancels any running animation
        fraction = d / self.spec.depth
        self._fade.jump_to(max(0.0, (fraction - 0.6) / 0.4))
        return True

    def _on_release(self, _widget, event) -> bool:
        was_dragging = self._dragging
        self._press = None
        self._dragging = False
        if not was_dragging:
            return False  # a plain click: the button's "clicked" signal toggles
        self._extended = panel_state.snap_extended(self._d, self.spec.depth)
        self._retarget()
        return True
```

- [ ] **Step 4: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell
git commit -m "feat: drag a panel handle to open/close with 50% snap" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5: GATE D: Phil checks dragging**

```bash
scripts/py main.py --config examples/panels-test.toml -v
```
1. Press on the dock's dots and drag **up/down**: the dock follows the pointer 1:1 and the fillets follow; no jitter.
2. Release **past halfway**: it eases the rest of the way open. Release **below halfway**: it eases closed.
3. A press-release with almost no movement still toggles (no drag).
4. After a drag, the very next plain click toggles normally (nothing stuck).
5. Repeat on the **clock** (drag direction: down opens) and the **system bar** (drag left opens).

**If the panel jitters or does not track the pointer:** the pointer coordinates are probably relative to the moving handle. In `_on_press` and `_on_motion` replace `event.x_root, event.y_root` with surface-relative coordinates:

```python
x, y = self._handle.translate_coordinates(self, event.x, event.y)
```
and use `x, y` in place of `event.x_root, event.y_root`. Re-run the gate.

---

### Task 18: Live reload, with Gate E

**Files:**
- Create: `shell/config/watcher.py`
- Modify: `shell/monitors.py` (add `apply`, `_destroy`), `shell/app.py` (reload, error report, watcher)

**Interfaces:**
- Consumes: `ConfigStore.reload()`, `diff_configs`, `Change`, `MonitorShell`, `panels_for`.
- Produces: `ConfigWatcher(path, on_change, debounce_ms=200)`; `MonitorShell.apply(config, changes)` handling `restyle`, `panel-state`, `panel-rebuild`, `panel-add`, `panel-remove`; `EdgeShellApp.reload()`.

- [ ] **Step 1: Create `shell/config/watcher.py`**

```python
"""Watch the config file and call back, debounced. The only GTK/Gio file in shell/config."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from gi.repository import Gio, GLib

_TRIGGERS = {
    Gio.FileMonitorEvent.CHANGES_DONE_HINT,
    Gio.FileMonitorEvent.CREATED,
    Gio.FileMonitorEvent.MOVED_IN,
    Gio.FileMonitorEvent.RENAMED,
}


class ConfigWatcher:
    def __init__(self, path: Path, on_change: Callable[[], None], debounce_ms: int = 200):
        self._on_change = on_change
        self._debounce_ms = debounce_ms
        self._timer = 0
        gfile = Gio.File.new_for_path(str(path))
        # WATCH_MOVES so editors that save by renaming a temp file over the config still trigger
        self._monitor = gfile.monitor_file(Gio.FileMonitorFlags.WATCH_MOVES, None)
        self._monitor.connect("changed", self._on_event)

    def _on_event(self, _monitor, _file, _other, event) -> None:
        if event not in _TRIGGERS:
            return
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add(self._debounce_ms, self._fire)

    def _fire(self) -> bool:
        self._timer = 0
        self._on_change()
        return GLib.SOURCE_REMOVE
```

- [ ] **Step 2: Add `apply` and `_destroy` to `MonitorShell`** (append inside the class in `shell/monitors.py`; add `from shell.config.diff import Change` to the imports)

```python
    def _destroy(self, window) -> None:
        if window in self.windows:
            self.windows.remove(window)
        try:
            window.destroy()
        except Exception:
            log.exception("failed to destroy window on %s", self.name)

    def apply(self, config: Config, changes: list[Change]) -> None:
        """Apply in-place changes for this monitor (the diff orders adds before removes)."""
        theme = config.theme_for(self.name)
        geos = panels_for(config, self.name)
        for change in changes:
            i = change.index
            if change.kind == "restyle":
                for corner in self.corners:
                    corner.set_theme(theme)
                for panel in self.panels:
                    panel.apply_theme(theme)
            elif change.kind == "panel-state":
                self.panels[i].set_state(geos[i].state)
            elif change.kind == "panel-rebuild":
                self._destroy(self.panels[i])
                self.panels[i] = self._make_panel(i, geos[i], theme)
            elif change.kind == "panel-add":
                self.panels.append(self._make_panel(i, geos[i], theme))
            elif change.kind == "panel-remove":
                self._destroy(self.panels.pop(i))
```

- [ ] **Step 3: Wire reload into `shell/app.py`**

Add to the imports:
```python
import subprocess
from collections import defaultdict

from shell.config.diff import diff_configs
from shell.config.watcher import ConfigWatcher
```
In `__init__` add `self._watcher: ConfigWatcher | None = None`. Add these methods to `EdgeShellApp`:

```python
    def start_watching(self) -> None:
        path = self.store.path
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        self._watcher = ConfigWatcher(path, self.reload)

    def reload(self) -> None:
        result = self.store.reload()
        if result is None:
            if self.store.last_error:
                self._report_error(self.store.last_error)
            return
        old, new = result
        changes = diff_configs(old, new)
        log.info("config reloaded: %d change(s)", len(changes))
        rebuild = {c.monitor for c in changes if c.kind == "rebuild-monitor"}
        for name in rebuild & set(self.shells):
            self.shells.pop(name).close()
        self.sync_monitors()  # opens rebuilt/new monitors with the new config
        grouped: dict[str, list] = defaultdict(list)
        for change in changes:
            if change.monitor not in rebuild:
                grouped[change.monitor].append(change)
        for name, items in grouped.items():
            if name in self.shells:
                self.shells[name].apply(new, items)
        self.refresh_css()

    def _report_error(self, message: str) -> None:
        log.error("config not applied (keeping the previous config):\n%s", message)
        try:
            subprocess.Popen(["notify-send", "-a", "Edge Shell", "Config not applied", message[:400]])
        except OSError:
            pass  # no notify-send; the log line above is enough
```
In `run()`, add `self.start_watching()` right after `self.app.hold()`.

- [ ] **Step 4: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell
git commit -m "feat: live config reload with minimal window changes" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5: GATE E: Phil edits the config while it runs**

```bash
cp examples/panels-test.toml /tmp/edge-live.toml
scripts/py main.py --config /tmp/edge-live.toml -v
```
Then edit `/tmp/edge-live.toml` in any editor, saving after each step, and watch HDMI-A-1:

1. Add at the top `[theme]` then `frame = "#1a2b3c"`: the frame, corners and **all panels recolour together**, with no windows flashing.
2. Under the dock add `depth = 90`: only the dock rebuilds, deeper.
3. Add `state = "collapsed"` to the clock: it collapses smoothly.
4. Remove the system bar's three lines: it disappears. Add them back: it returns.
5. **Typo test:** delete a `]` somewhere and save. The shell keeps running with the previous look, a "Config not applied" notification appears (and the terminal logs the error). Fix the typo: the change applies.
6. Add `thickness = 16` under `[theme]`: the monitor rebuilds with a thicker frame.
7. Set `shell = "none"`: the frame vanishes. Set it back to `"edge"`: it returns.
8. Then also try an **unknown widget** (`widget = "nope"`): rejected with a clear message; nothing changes.

---

### Task 19: Monitor hot-plug, with Gate F

**Files:**
- Modify: `shell/app.py`

**Interfaces:**
- Consumes: `EdgeShellApp.sync_monitors()` (idempotent), Gdk display `monitor-added` / `monitor-removed` signals.

- [ ] **Step 1: Add the display watching to `shell/app.py`**

Add to the imports: `from gi.repository import Gdk, GLib` (after `gi.require_version("Gdk", "3.0")` alongside the existing Gtk one). In `__init__` add `self._sync_timers: list[int] = []`. Add:

```python
    def watch_displays(self) -> None:
        display = Gdk.Display.get_default()
        display.connect("monitor-added", self._schedule_sync)
        display.connect("monitor-removed", self._schedule_sync)

    def _schedule_sync(self, *_) -> None:
        # kscreen-doctor can lag the Gdk signal, so sync twice; sync is idempotent.
        for timer in self._sync_timers:
            GLib.source_remove(timer)
        self._sync_timers = [
            GLib.timeout_add(600, self._sync_once),
            GLib.timeout_add(2500, self._sync_once),
        ]

    def _sync_once(self) -> bool:
        self.sync_monitors()
        return GLib.SOURCE_REMOVE
```
In `run()` call `self.watch_displays()` after `self.start_watching()`.

A removed timer id is already gone once it has fired, so guard the cancel loop against stale ids by wrapping the `GLib.source_remove(timer)` call in `try/except` only if GLib prints a warning during Gate F; otherwise leave it.

- [ ] **Step 2: VERIFY and commit**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add shell
git commit -m "feat: rebuild monitor shells on hot-plug" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 3: GATE F: Phil unplugs HDMI-A-1 (in software)**

Start the shell as in Gate C. Then, from a terminal **on DP-1** (windows may move to the other screen briefly):
```bash
kscreen-doctor output.HDMI-A-1.disable
```
Expected: no crash; the frame leaves with the monitor; the terminal logs `closing Edge Shell on HDMI-A-1`. Then:
```bash
kscreen-doctor output.HDMI-A-1.enable
```
Expected: within about 3 s the frame and panels return on HDMI-A-1 (`opening Edge Shell on HDMI-A-1`). Check the panels are still the configured ones, in the right places.

Never disable DP-1 (the primary). If HDMI-A-1 does not come back, re-enable it with the command above or from System Settings, Display, and report the `-v` log.

---

### Task 20: CI, README, and wrap-up

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `README.md`

- [ ] **Step 1: Create the CI workflow** (runs the display-free tests only)

```yaml
# .github/workflows/ci.yml
name: ci
on:
  push:
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: System libraries for pycairo
        run: sudo apt-get update && sudo apt-get install -y libcairo2-dev pkg-config python3-dev
      - name: Install
        run: pip install "pydantic>=2.6" pycairo pytest ruff
      - run: ruff check .
      - run: ruff format --check .
      - run: pytest -q
```

- [ ] **Step 2: Replace `README.md`**

````markdown
# edge-shell

A customizable desktop shell for KDE Plasma (KWin Wayland), built with
[Fabric](https://github.com/Fabric-Development/fabric). It draws a thin frame around
each monitor and grows panels out of that frame. It runs alongside Plasma and does not
replace it. See the [design spec](docs/superpowers/specs/2026-10-11-edge-shell-design.md).

**Status:** early development. Frame, dock, clock, system bar, drag, live reload and
monitor hot-plug work. Plasma integration (workspaces, tray, hiding Plasma's panel) and a
settings window are planned.

## Requirements

- KDE Plasma 6 on Wayland (KWin implements `wlr-layer-shell`)
- Python 3.12+ with Fabric (from git), PyGObject **below 3.52**, pycairo, Pydantic 2
- `gtk-layer-shell`, `kscreen-doctor`; fonts Hack Nerd Font Mono and JetBrains Mono

## Run

```bash
scripts/py main.py --list-outputs                         # monitors and connector names
scripts/py main.py --config examples/hdmi-test.toml -v    # frame on HDMI-A-1 only
```

`scripts/py` runs the shared venv; override it with `EDGE_SHELL_PYTHON=/path/to/python`.

## Configure

`config.default.toml` lists every key. Your config (`~/.config/edge-shell/config.toml`, or
`--config PATH`) is overlaid on it and reloads live when saved. A bad edit keeps the
previous config and reports the error. Monitors are keyed by connector name; a monitor not
listed gets no Edge Shell (`shell = "plasma"`).

```toml
[monitors.HDMI-A-1]
shell = "edge"            # edge | plasma | both | none

[[monitors.HDMI-A-1.panels]]
widget = "dock"           # dock | clock | system_bar
depth = 80                # any panel key overrides the widget's default
```

## Develop

```bash
scripts/py -m pytest -q                            # display-free tests
scripts/py -m ruff format . && scripts/py -m ruff check .
```

Pure logic lives in `shell/` (config, geometry, drawing, animation); GTK windows are thin
shells over it. New widgets go in `widgets/` and register with `@register`; they never call
cairo or layer-shell directly.
````

- [ ] **Step 3: VERIFY, commit, push, and check CI**

```bash
scripts/py -m ruff format . && scripts/py -m ruff check --fix . && scripts/py -m pytest -q
git add .github README.md
git commit -m "ci: run lint and display-free tests; document usage" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push
gh run watch --exit-status
```
Expected: the `ci` run passes. If `ruff format --check` fails on CI but passes locally, the local ruff version differs; run `scripts/py -m ruff --version`, pin that version in the workflow's `pip install` line, and push again.

---

## Follow-up plans (not part of this plan)

1. **Plasma integration** (spec milestone 7): spike 2 (does `evaluateScript` hide and restore a Plasma panel cleanly? tested on a temporary panel on HDMI-A-1 first, Phil confirms before DP-1), `services/plasma.py`, workspaces panel, status-notifier host, Plasma-panel toggle with saved restore state and `--restore-plasma`.
2. **Corner panel and settings window** (spec milestone 8): the `CornerPanel` widget panel, then the windowed settings UI generated from the Pydantic schema and the widget registry.

## Self-review notes

- **Spec coverage:** visual spec -> Tasks 3, 7, 8, 10 (tokens, geometry, drawing); interaction model -> Tasks 9, 11, 15, 17 (timing, states, drag); per-monitor model and independent frames -> Tasks 12-14; config, registry, live reload -> Tasks 3-6, 18; hot-plug -> Task 19; testing layers 1-3 -> pure tests plus Gates A-F; risks (seams, exclusive zone, hover size, clamping) -> Gates A-B, Task 7. Deferred on purpose: Plasma integration, corner panel, settings window, keyboard focus on handles (layer-shell `keyboard_mode="none"` panels cannot take focus; revisit with the settings window).
- **Spec deviations to confirm:** spike 3 folded into Gates A-B; plan split after milestone 6; `surface_hover` and `peek`/`hover_zone`/`duration_ms` added as theme tokens; per-monitor CSS scoping via a `mon-<connector>` class.
