"""Load config.default.toml, overlay the user's file, validate."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from shell.config.models import Config, ConfigError, deep_merge

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config.default.toml"
USER_PATH = Path.home() / ".config" / "edge-shell" / "config.toml"


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
