"""The corner panel review sheet (spec 19, Gate A): headless, written to a PNG."""

import cairo
import pytest

from shell.canvas import corner_sheet as cs
from shell.canvas.scene import PanelShape, shape_for


def _bytes(surface):
    surface.flush()
    return bytes(surface.get_data())


@pytest.mark.parametrize(("corner", "edge"), cs.ROWS)
def test_every_cell_is_laid_out_without_warnings(corner, edge):
    layout = cs.cell_layout(corner, edge)
    assert layout.warnings == [] and None not in layout.panels
    assert (layout.panels[0].corner, layout.panels[0].edge) == (corner, edge)


@pytest.mark.parametrize(("corner", "edge"), cs.ROWS)
def test_a_collapsed_corner_panel_draws_the_plain_frame(corner, edge):
    shapes = [shape_for(p) for p in cs.cell_layout(corner, edge).panels]
    panels = [(s.edge, s.pos, s.length, s.depth, s.depth) for s in shapes[1:]]
    assert all(isinstance(s, PanelShape) for s in shapes[1:])
    w, h = cs.CELL
    plain = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(plain)
    cr.set_source_rgb(0.55, 0.6, 0.65)
    cr.paint()
    scene = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cs.draw_scene(cairo.Context(scene), w, h, cs.THICKNESS, cs.RADIUS, panels, cs.MASS)
    cr.set_source_surface(scene, 0, 0)
    cr.paint()
    assert _bytes(cs.render_cell(corner, edge, 0.0, False)) == _bytes(plain)
    assert _bytes(cs.render_cell(corner, edge, 1.0, False)) != _bytes(plain)


def test_main_writes_the_sheet(tmp_path, capsys):
    out = tmp_path / "corners.png"
    assert cs.main(["--out", str(out), "--effects"]) == 0
    w, h = cs.CELL
    expected = (
        (w + 2 * cs.PAD) * len(cs.FRACTIONS) * cs.ZOOM,
        (h + 2 * cs.PAD) * len(cs.ROWS) * cs.ZOOM,
    )
    png = cairo.ImageSurface.create_from_png(str(out))
    assert (png.get_width(), png.get_height()) == expected == (4464, 4992)
    assert capsys.readouterr().out == f"wrote {out} (4464x4992)\n"


def test_main_reports_an_unwritable_path(tmp_path, capsys):
    assert cs.main(["--out", str(tmp_path / "missing" / "x.png")]) == 2
    assert "corner_sheet: cannot write" in capsys.readouterr().err
