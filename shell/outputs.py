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
    outputs = []
    for o in json.loads(text).get("outputs", []):
        if not o.get("enabled"):
            continue
        scale = float(o.get("scale") or 1.0)
        outputs.append(
            Output(
                name=o["name"],
                x=o["pos"]["x"],
                y=o["pos"]["y"],
                width=round(o["size"]["width"] / scale),
                height=round(o["size"]["height"] / scale),
            )
        )
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
