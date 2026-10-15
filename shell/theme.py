"""Theme tokens -> CSS string and cairo colors. Pure."""

from __future__ import annotations

import re

from shell.config.models import COLOR_FIELDS, Theme

_GENERIC_FONTS = {"monospace", "sans-serif", "serif", "cursive", "fantasy"}


def hex_to_rgba(value: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    """'#rrggbb' or '#rrggbbaa' -> (r, g, b, a) in 0..1. The colour's own alpha (ff when
    absent) is multiplied by `alpha`, so 6-digit colours behave exactly as before."""
    h = value.lstrip("#")
    if len(h) not in (6, 8):
        raise ValueError(f"invalid colour {value!r}: expected #rrggbb or #rrggbbaa")
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    own = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
    return (r, g, b, own * alpha)


def css_color(value: str) -> str:
    """A theme colour as GTK3 CSS: '#rrggbb' unchanged, '#rrggbbaa' as rgba() (GTK3's CSS
    parser rejects 8-digit hex)."""
    h = value.lstrip("#")
    if len(h) != 8:
        return value
    r, g, b, a = (int(h[i : i + 2], 16) for i in (0, 2, 4, 6))
    return f"rgba({r}, {g}, {b}, {a / 255:.3f})"


def scope_class(monitor: str) -> str:
    """CSS class put on every window of a monitor, so per-monitor themes stay separate."""
    return "mon-" + re.sub(r"[^a-z0-9-]", "-", monitor.lower())


def _font_stack(fonts: list[str]) -> str:
    return ", ".join(f if f in _GENERIC_FONTS else f'"{f}"' for f in fonts)


def to_css(theme: Theme, scope: str) -> str:
    s = f".{scope}"
    c = {name: css_color(getattr(theme, name)) for name in COLOR_FIELDS}
    return f"""\
window{s}, {s} * {{ all: unset; font-family: {_font_stack(theme.font)}; color: {c["text"]}; }}
window{s} {{ background-color: transparent; }}
{s} #handle {{ min-width: 0; min-height: 0; padding: 0; }}
{s} .icon-button {{ min-width: 44px; min-height: 44px; border-radius: 10px; }}
{s} .icon-button:hover {{ background-color: {c["surface_hover"]}; }}
{s} .secondary {{ color: {c["text_secondary"]}; }}
{s} .active {{ color: {c["accent"]}; }}
{s} #clock-time {{ font-size: 20px; font-weight: 500; }}
{s} #summary-time {{ font-size: 32px; font-weight: 500; }}
"""  # noqa: E501
