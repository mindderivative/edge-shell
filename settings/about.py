"""What Help > About shows. Pure (no GTK): read from the checkout's pyproject.toml at run time
(the shell runs from its checkout, not installed), with the installed package's metadata as
the fallback for the version."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "Edge Shell"
WEBSITE = "https://github.com/mindderivative/edge-shell"
AUTHORS = ("mindderivative",)  # the repository owner; pyproject [project].authors wins
NO_LICENSE = "No licence has been chosen for Edge Shell yet."


@dataclass(frozen=True)
class AboutInfo:
    name: str
    version: str
    comments: str
    website: str
    authors: tuple[str, ...]
    license: str


def about_info(root: Path = ROOT) -> AboutInfo:
    try:
        project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, KeyError):
        project = {}
    if not isinstance(project, dict):  # [project] that is not a table
        project = {}
    raw = project.get("authors")
    entries = raw if isinstance(raw, list) else []
    # a malformed entry (a string, a table without a name) is ignored
    authors = tuple(a["name"] for a in entries if isinstance(a, dict) and a.get("name")) or AUTHORS
    description = project.get("description")
    lines = [description] if description and isinstance(description, str) else []
    return AboutInfo(
        name=NAME,
        version=_version(project.get("version")),
        comments="\n".join([*lines, "Built with Fabric (Python, GTK 3)."]),
        website=WEBSITE,
        authors=authors,
        license=_license(root, project.get("license")),
    )


def _version(declared) -> str:
    return declared if declared and isinstance(declared, str) else _installed_version()


def _installed_version() -> str:
    try:
        return metadata.version("edge-shell")
    except metadata.PackageNotFoundError:
        return "unknown"


def _license(root: Path, declared) -> str:
    """The licence text: a LICENSE file next to pyproject.toml, else pyproject's `license`
    (an SPDX string or a {text = ...} table), else the installed package's License-Expression
    or License, else NO_LICENSE."""
    for name in ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING"):
        try:
            return (root / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    if isinstance(declared, str) and declared:
        return declared
    if isinstance(declared, dict) and declared.get("text"):
        return declared["text"]
    try:  # the installed package's metadata
        info = metadata.metadata("edge-shell")
    except metadata.PackageNotFoundError:
        return NO_LICENSE
    return info.get("License-Expression") or info.get("License") or NO_LICENSE
