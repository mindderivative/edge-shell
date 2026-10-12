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
