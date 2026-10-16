"""settings.about: what Help > About shows, read from pyproject.toml at run time (pure)."""

import tomllib
from importlib import metadata

import settings.about as about
from settings.about import AUTHORS, NO_LICENSE, ROOT, WEBSITE, about_info


def test_about_reads_this_checkouts_pyproject():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    info = about_info()
    assert info.name == "Edge Shell" and info.version == project["version"]
    assert info.comments.startswith(project["description"])
    assert info.comments.endswith("Built with Fabric (Python, GTK 3).")
    assert info.website == WEBSITE == "https://github.com/mindderivative/edge-shell"
    assert info.authors == AUTHORS and info.license


def test_this_checkout_is_mit_licensed():
    info = about_info()  # the real LICENSE file and pyproject.toml
    assert info.license.startswith("MIT License")
    assert "Copyright (c) 2026 Phil Hodgins" in info.license
    assert info.license != NO_LICENSE


def test_declared_authors_and_licence_are_used(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "edge-shell"\nversion = "2.0.0"\ndescription = "d"\n'
        'license = "MIT"\nauthors = [{ name = "Phil" }, { email = "x@y" }]\n'
    )
    info = about_info(tmp_path)
    assert (info.version, info.authors, info.license) == ("2.0.0", ("Phil",), "MIT")


def test_a_licence_file_wins(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1"\nlicense = "MIT"\n')
    (tmp_path / "LICENSE").write_text("Full licence text\n")
    assert about_info(tmp_path).license == "Full licence text\n"


def test_without_a_pyproject_the_installed_version_or_unknown(tmp_path, monkeypatch):
    def missing(_name):
        raise metadata.PackageNotFoundError("edge-shell")

    monkeypatch.setattr(about.metadata, "version", missing)
    monkeypatch.setattr(about.metadata, "metadata", missing)
    info = about_info(tmp_path)  # no pyproject.toml here
    assert info.version == "unknown" and info.license == NO_LICENSE
    assert info.authors == AUTHORS
    monkeypatch.setattr(about.metadata, "version", lambda _n: "0.9")
    assert about_info(tmp_path).version == "0.9"


def test_thin_metadata_gives_clean_fallbacks(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nversion = "1"\nauthors = ["Phil", { email = "x@y" }, { name = "Ann" }]\n'
    )
    monkeypatch.setattr(about.metadata, "metadata", lambda _n: {"License-Expression": "Apache-2.0"})
    info = about_info(tmp_path)  # no description, no LICENSE file, malformed authors
    assert info.comments == "Built with Fabric (Python, GTK 3)."
    assert info.authors == ("Ann",)
    assert info.license == "Apache-2.0"  # the installed metadata, before NO_LICENSE


def test_installed_metadata_licence_field_is_the_second_fallback(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1"\n')
    monkeypatch.setattr(about.metadata, "metadata", lambda _n: {"License": "BSD-3-Clause"})
    assert about_info(tmp_path).license == "BSD-3-Clause"

    def missing(_name):
        raise metadata.PackageNotFoundError("edge-shell")

    monkeypatch.setattr(about.metadata, "metadata", missing)
    assert about_info(tmp_path).license == NO_LICENSE


def test_a_malformed_pyproject_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(about.metadata, "version", lambda _n: "0.9")
    (tmp_path / "pyproject.toml").write_text('project = "x"\n')
    assert about_info(tmp_path).version == "0.9"
    (tmp_path / "pyproject.toml").write_text("[project]\nversion = 1\nauthors = 3\nlicense = 4\n")
    info = about_info(tmp_path)
    assert info.version == "0.9" and info.authors == about.AUTHORS
