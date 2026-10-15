"""Starting a settings window on a config file in its own process: from the shell (a
right-click on a panel handle) and from the settings window itself (File > New, Open and Save
As open the chosen file in its own window: one window per file, each with its own
single-instance application id). No GTK at import time, no Fabric: the shell and the settings
process both import it."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

MAIN_PATH = Path(__file__).resolve().parents[1] / "main.py"


def settings_command(config_path: Path | None) -> list[str]:
    """The command that opens the settings window on a config file (None: the default one),
    with this process's own interpreter (the venv that has Fabric and tomlkit)."""
    command = [sys.executable, str(MAIN_PATH), "--settings"]
    if config_path is not None:
        command += ["--config", str(config_path)]
    return command


def spawn_settings(config_path: Path) -> None:
    """Start the settings window on `config_path` in a new session (it outlives this window).
    If that file already has a window, it only comes forward. The child is reaped by a GLib
    child watch, so a window that stays open leaves no zombie. Raises OSError when the
    interpreter cannot be started."""
    from gi.repository import GLib

    proc = subprocess.Popen(
        settings_command(config_path.absolute()),
        start_new_session=True,
        stdin=subprocess.DEVNULL,
    )
    GLib.child_watch_add(GLib.PRIORITY_DEFAULT, proc.pid, _reaped, proc)


def _reaped(_pid: int, status: int, proc: subprocess.Popen) -> None:
    proc.returncode = os.waitstatus_to_exitcode(status)  # GLib passes the raw wait status
    if proc.returncode != 0:
        log.warning("a settings window exited with status %d", proc.returncode)
