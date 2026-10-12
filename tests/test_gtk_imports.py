import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")


def test_gtk_modules_import():
    import shell.frame  # noqa: F401
    import shell.monitors  # noqa: F401
