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
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=f"config file; must exist when given (default: {USER_PATH}, optional)",
    )
    parser.add_argument(
        "--list-outputs", action="store_true", help="print monitors and connector names"
    )
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
        store = ConfigStore(args.config or USER_PATH, required=args.config is not None)
    except ConfigError as exc:
        print(f"config error:\n{exc}", file=sys.stderr)
        return 2

    from shell.app import EdgeShellApp

    return EdgeShellApp(store).run()


if __name__ == "__main__":
    sys.exit(main())
