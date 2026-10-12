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
