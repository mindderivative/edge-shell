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
