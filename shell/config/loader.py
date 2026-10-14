"""Load config.default.toml, overlay the user's file, validate."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from shell.config.models import Config, ConfigError, deep_merge

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config.default.toml"
USER_PATH = Path.home() / ".config" / "edge-shell" / "config.toml"


MISSING_PANEL = 'missing; use "edge", "corner" or "float"'
OLD_FORMAT = (
    'panel entries start with panel = "edge" | "corner" | "float", name = "..." and '
    'widget = "..." (an entry with only a widget is the old format; see the README, "Panels")'
)


def key_path(loc: tuple) -> str:
    """A pydantic error location as a key path. A panel entry's index is written in brackets,
    as shell.registry.validate_widgets writes it: monitors.HDMI-A-1.panels[0].name."""
    out = ""
    for i, part in enumerate(loc):
        if isinstance(part, int) and i > 0 and loc[i - 1] == "panels":
            out += f"[{part}]"
        else:
            out += f".{part}" if out else str(part)
    return out or "config"


def _missing_panel(item: dict) -> bool:
    loc = item["loc"]
    return (
        item["type"] == "missing" and len(loc) >= 3 and loc[-1] == "panel" and loc[-3] == "panels"
    )


def format_validation_error(err: ValidationError) -> str:
    lines = []
    old_format = False
    for item in err.errors():
        path = key_path(item["loc"])
        if _missing_panel(item):
            old_format = True
            lines.append(f"{path}: {MISSING_PANEL}")
        else:
            lines.append(f"{path}: {item['msg']}")
    if old_format:  # once per file, however many entries lack it
        lines.append(OLD_FORMAT)
    return "\n".join(lines)


def parse_config(data: dict[str, Any]) -> Config:
    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(format_validation_error(exc)) from None


def _read_toml(path: Path, missing_ok: bool = False) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        if missing_ok:
            return {}
        raise ConfigError(f"{path}: {exc}") from None
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"{path}: {exc}") from None


def load_config(
    user_path: Path | None = USER_PATH,
    default_path: Path = DEFAULT_PATH,
    required: bool = False,
) -> Config:
    """Defaults overlaid with the user file. A missing user file is fine unless `required`.

    No exists() pre-check: on EACCES it can report False and silently fall back to defaults.
    """
    data = _read_toml(default_path)
    if user_path is not None:
        data = deep_merge(data, _read_toml(user_path, missing_ok=not required))
    return parse_config(data)


def load_config_text(user_text: str, default_path: Path = DEFAULT_PATH) -> Config:
    """Defaults overlaid with a user config given as TOML text: the settings window checks an
    edit with this before writing it, by the same rules as load_config."""
    try:
        user = tomllib.loads(user_text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"TOML syntax error: {exc}") from None
    return parse_config(deep_merge(_read_toml(default_path), user))
