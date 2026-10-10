"""utils/Env/figures/layout.py (V102): panels laid out in a grid, as one PDF by pdflatex and its PNG
rendered from it by pdftoppm; a sheet's tiling (V89) and a deck's composites. Panels are made here by
PIL, in tmp_path."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from runner import plugins

REPO = Path(__file__).resolve().parents[2]
TOOLS = all(shutil.which(t) for t in ("pdflatex", "pdftoppm", "pdfinfo"))
needs_tools = pytest.mark.skipif(not TOOLS, reason="pdflatex and poppler (pdftoppm, pdfinfo) lay out the figures")


@pytest.fixture(scope="module")
def layout():
    return plugins.load(REPO / "utils" / "Env" / "figures" / "layout.py", "layout")


def page(path: Path, size=(336, 303), colour="white") -> Path:
    """A panel: a PDF of `size` bp, or a PNG of size × 300/72 pixels at 300 dpi."""
    from PIL import Image
    if path.suffix == ".pdf":
        Image.new("RGB", size, colour).save(path, "PDF", resolution=72)
    else:
        Image.new("RGB", (round(size[0] * 300 / 72), round(size[1] * 300 / 72)), colour).save(path, dpi=(300, 300))
    return path


def pdf_size(path: Path) -> tuple[float, float]:
    info = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True).stdout
    w, h = info.split("Page size:")[1].split("pts")[0].split("x")
    return float(w), float(h)


def test_the_grid_shows_the_panels_largest(layout):
    full, aspect = layout.SIZES["full"], 336 / 303
    shapes = {n: layout.grid(n, full, aspect)[:2] for n in range(1, 7)}
    assert shapes[1] == (1, 1) and shapes[2] == (2, 1) and shapes[3] == (3, 1) and shapes[6] == (3, 2)
    for n, (columns, rows) in shapes.items():
        assert columns * rows >= n and (columns - 1) * rows < n           # no empty column
    assert layout.grid(2, layout.SIZES["half"], aspect)[:2] == (1, 2)     # a tall box stacks them
    assert layout.grid(4, full, aspect, columns=4)[:2] == (4, 1)          # columns, when given, are kept
    columns, rows, cw, ch = layout.grid(6, full, aspect, label=10, title=20)
    assert cw * columns + 4 * (columns - 1) <= full[0] + 1e-6
    assert (ch + 10) * rows + 4 * (rows - 1) <= full[1] - 20 + 1e-6
    with pytest.raises(ValueError, match="do not fit"):
        layout.grid(3, (5, 10), aspect, columns=3)                        # 3 columns and their gaps exceed 5 bp


def test_text_is_escaped_for_latex_and_math_kept(layout):
    assert layout.tex("d01_x01 10% & #2") == r"d01\_x01 10\% \& \#2"
    assert layout.tex(r"$\sqrt{s}$ = 63.2 GeV") == r"$\sqrt{s}$ = 63.2 GeV"
    assert layout.tex("costs $5") == r"costs \$5"                          # one $ is not math


def test_a_page_shows_its_rotation(layout):
    upright = "Page size:       336.24 x 303.12 pts\nPage rot:        0\n"
    turned = "Page size:       303 x 336 pts\nPage rot:        90\n"
    assert layout._pdf_size(upright) == (336.24, 303.12)
    assert layout._pdf_size(turned) == (336.0, 303.0)


@needs_tools
def test_a_composite_fills_its_box(layout, tmp_path):
    panels = [(page(tmp_path / f"p{i}.pdf"), f"{n}M") for i, n in enumerate((1, 10, 50))]
    panels.append((page(tmp_path / "extra.png", colour="lightblue"), "AB"))
    pdf, png = layout.composite(panels, tmp_path / "out" / "zeus-d01", "full", title="ZEUS d01 · PDFs", dpi=72)
    w, h = pdf_size(pdf)
    assert abs(w - 400) < 0.5 and abs(h - 222) < 0.5
    from PIL import Image
    assert Image.open(png).size == (400, 222)                              # the PDF, rendered at 72 dpi
    half, _ = layout.composite(panels[:2], tmp_path / "half", "half", labels=False)
    assert abs(pdf_size(half)[0] - 196) < 0.5
    with pytest.raises(ValueError, match="no size 'wide'"):
        layout.composite(panels, tmp_path / "x", "wide")
    with pytest.raises(ValueError, match="no such panel"):
        layout.composite([(tmp_path / "gone.pdf", "")], tmp_path / "x")


@needs_tools
def test_a_sheet_tiles_pages_at_their_own_size(layout, tmp_path):
    pdfs = [page(tmp_path / f"d{i}.pdf") for i in range(3)]
    pngs = [page(tmp_path / f"d{i}.png") for i in range(3)]
    assert layout.tile({"pdf": pdfs, "png": pngs}, tmp_path / "sheets" / "grid", 2) == ["pdf", "png"]
    w, h = pdf_size(tmp_path / "sheets" / "grid.pdf")
    assert abs(w - 2 * 336) < 0.5 and abs(h - 2 * 303) < 0.5
    from PIL import Image
    one = Image.open(pngs[0]).size
    assert Image.open(tmp_path / "sheets" / "grid.png").size == (2 * one[0], 2 * one[1])
    # PDFs alone: the PNG is still made, rendered at Paint's 300 dpi (V102); no page needs a PNG
    assert layout.tile({"pdf": pdfs}, tmp_path / "pdf_only", 3) == ["pdf", "png"]
    made = Image.open(tmp_path / "pdf_only.png").size
    assert abs(made[0] - 3 * 336 * 300 / 72) <= 1 and abs(made[1] - 303 * 300 / 72) <= 1   # pdftoppm rounds
    assert layout.tile({"pdf": [pdfs[0], tmp_path / "gone.pdf"]}, tmp_path / "none", 2) == []
