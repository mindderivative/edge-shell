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
"""  # noqa: E501
