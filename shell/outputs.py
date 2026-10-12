"""Map Gdk monitors to connector names via `kscreen-doctor -j`. Pure except read_kscreen_json."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Output:
    name: str
    x: int
    y: int
    width: int  # logical (scaled) size, as Gdk reports it
    height: int


def parse_kscreen(text: str) -> list[Output]:
    """Parse `kscreen-doctor -j`; any unexpected shape raises ValueError."""
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("outputs", []), list):
        raise ValueError("unexpected kscreen-doctor JSON: expected an object with an outputs list")
    outputs = []
    try:
        for o in data.get("outputs", []):
            if not o.get("enabled"):
                continue
            scale = float(o.get("scale") or 1.0)
            outputs.append(
                Output(
                    name=str(o["name"]),
                    x=int(o["pos"]["x"]),
                    y=int(o["pos"]["y"]),
                    width=round(o["size"]["width"] / scale),
                    height=round(o["size"]["height"] / scale),
                )
            )
    except (KeyError, TypeError, AttributeError, ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"unexpected kscreen-doctor output entry: {exc!r}") from None
    return outputs


def match_geometries(
    geometries: list[tuple[int, int, int, int]], outputs: list[Output]
) -> list[str | None]:
    """Connector name for each Gdk geometry (x, y, w, h): exact match, else by position."""
    names: list[str | None] = []
    for x, y, w, h in geometries:
        exact = next(
            (o.name for o in outputs if (o.x, o.y, o.width, o.height) == (x, y, w, h)), None
        )
        names.append(exact or next((o.name for o in outputs if (o.x, o.y) == (x, y)), None))
    return names


def read_kscreen_json(timeout: float = 5.0) -> str:
    result = subprocess.run(
        ["kscreen-doctor", "-j"], capture_output=True, text=True, timeout=timeout, check=True
    )
    return result.stdout
