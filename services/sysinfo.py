"""CPU and memory usage from /proc. Pure parsing + two tiny readers."""

from __future__ import annotations

from pathlib import Path


def parse_meminfo(text: str) -> float:
    fields: dict[str, int] = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts:
            fields[key] = int(parts[0])
    return 100.0 * (1 - fields["MemAvailable"] / fields["MemTotal"])


def parse_cpu_times(text: str) -> tuple[int, int]:
    """(total, idle) jiffies from the first line of /proc/stat."""
    values = [int(v) for v in text.splitlines()[0].split()[1:9]]
    return sum(values), values[3] + values[4]  # idle + iowait


def cpu_percent(prev: tuple[int, int], cur: tuple[int, int]) -> float:
    total, idle = cur[0] - prev[0], cur[1] - prev[1]
    return 0.0 if total <= 0 else 100.0 * (1 - idle / total)


def read_meminfo_percent() -> float:
    return parse_meminfo(Path("/proc/meminfo").read_text())


def read_cpu_times() -> tuple[int, int]:
    return parse_cpu_times(Path("/proc/stat").read_text())
