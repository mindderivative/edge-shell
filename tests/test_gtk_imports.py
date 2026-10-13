import pytest

pytest.importorskip("gi")
pytest.importorskip("fabric")


def test_gtk_modules_import():
    import shell.canvas.canvas  # noqa: F401
    import shell.edge_panel  # noqa: F401
    import shell.frame  # noqa: F401
    import shell.monitors  # noqa: F401
    import widgets  # noqa: F401
    import widgets.clock  # noqa: F401
    import widgets.system_bar  # noqa: F401
