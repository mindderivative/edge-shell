"""Edge Shell entry point."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from shell.config.loader import USER_PATH
from shell.config.models import ConfigError
from shell.config.store import ConfigStore

MAX_STATS_SECONDS = 10  # live probes draw on the user's screen: keep them short


def _stats_seconds(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
    if not 0 < value <= MAX_STATS_SECONDS:
        raise argparse.ArgumentTypeError(f"must be in (0, {MAX_STATS_SECONDS}]")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="edge-shell")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=f"config file; must exist when given (default: {USER_PATH}, optional)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--list-outputs", action="store_true", help="print monitors and connector names"
    )
    mode.add_argument(
        "--settings",
        action="store_true",
        help="open the settings window on the config file (works with or without a running "
        "shell; the file need not exist yet)",
    )
    mode.add_argument(
        "--restore-config",
        action="store_true",
        help="put back the config as it was at the last File > Save in the settings window, "
        "or before that window's first change (config.toml.bak; the replaced file is kept as "
        "config.toml.before-restore)",
    )
    parser.add_argument(
        "--stats",
        type=_stats_seconds,
        default=None,
        metavar="SECONDS",
        help="measure for SECONDS (max 10): toggle every panel every 300 ms, then print frame "
        "pacing, canvas draw cost, canvas/panel cadence and CPU, and quit",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    if args.stats is not None and (args.settings or args.restore_config):
        parser.error("--stats only applies when running the shell")
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.list_outputs:
        from shell.monitors import describe_monitors

        print("\n".join(describe_monitors()))
        return 0

    path = args.config or USER_PATH
    if args.restore_config:
        from settings.files import restore_backup

        try:
            print(restore_backup(path))
        except (ConfigError, OSError) as exc:
            print(exc, file=sys.stderr)
            return 1
        return 0

    if args.settings:
        # Native file dialogs (File > New, Open, Save As): GTK 3 asks the desktop portal (on
        # Plasma: KDE's own dialog) only when told to, before GTK starts. GTK_USE_PORTAL=0 in
        # the environment keeps GTK's own dialog.
        os.environ.setdefault("GTK_USE_PORTAL", "1")
        # Before the ConfigStore: the window must open even when the file is invalid. It
        # imports the widgets itself, only when it is the first instance on this file.
        from settings.app import run_settings

        return run_settings(path)

    import widgets  # noqa: F401  (registers the built-in panels before the config is validated)

    try:
        store = ConfigStore(path, required=args.config is not None)
    except ConfigError as exc:
        print(f"config error:\n{exc}", file=sys.stderr)
        return 2

    from shell.app import EdgeShellApp

    return EdgeShellApp(store, stats_seconds=args.stats).run()


if __name__ == "__main__":
    sys.exit(main())
