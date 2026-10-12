# shell/config/store.py
"""Holds the current config. A bad reload never replaces a good config."""

from __future__ import annotations

from pathlib import Path

from shell.config.loader import load_config
from shell.config.models import Config, ConfigError
from shell.registry import validate_widgets


class ConfigStore:
    def __init__(self, path: Path | None, required: bool = False):
        """`required`: the path was given explicitly, so a missing file is an error."""
        self.path = path
        self.required = required
        self.last_error: str | None = None
        self.config: Config = self._load()  # raises ConfigError at startup

    def _load(self) -> Config:
        config = load_config(self.path, required=self.required)
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
