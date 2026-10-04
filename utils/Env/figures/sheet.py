"""utils/Env/figures/sheet.py — a sheet figure's files (V89): drawn pages tiled in a grid, as drawn.

Each pad of a sheet is the page as its backend drew it alone, so the two never disagree:

* pdf: the pages' PDFs, placed by pdflatex (graphicx) on one page `columns` wide, vector as they are;
* png: the pages' PNGs pasted by PIL on one image, each cell the largest page's size, white between.

Other formats are not tiled. `tile(files, target, columns)` writes `<target>.<format>` for the formats
every page has; the formats made. Errors are ValueError, with what is wrong.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

TILED = ("pdf", "png")


def _pdf(files: list[Path], target: Path, columns: int) -> None:
    if not shutil.which("pdflatex"):
        raise ValueError("a sheet's PDF is made by pdflatex, which is not on PATH")
    rows = -(-len(files) // columns)
    width = 1.0 / columns
    cells = []
    for number, path in enumerate(files):
        cells.append(rf"\includegraphics[width={width:.6f}\paperwidth]{{{path}}}")
        cells.append(r"\\" if (number + 1) % columns == 0 else r"%")
    body = "\n".join(cells)
    first = files[0]
    with tempfile.TemporaryDirectory() as work:
        size = subprocess.run(["pdfinfo", str(first)], capture_output=True, text=True).stdout if shutil.which("pdfinfo") else ""
        line = next((l for l in size.splitlines() if l.startswith("Page size:")), "")
        try:
            w, h = (float(v) for v in line.split(":")[1].split("pts")[0].split("x"))
        except (IndexError, ValueError):
            w, h = 336.0, 303.0                                   # base.toml's 4.67 × 4.21 in
        tex = Path(work) / "sheet.tex"
        tex.write_text(
            "\\documentclass{article}\n"
            f"\\usepackage[paperwidth={w * columns:.2f}pt,paperheight={h * rows:.2f}pt,margin=0pt]{{geometry}}\n"
            "\\usepackage{graphicx}\n\\pagestyle{empty}\n\\setlength{\\parindent}{0pt}\n"
            "\\setlength{\\lineskip}{0pt}\\setlength{\\baselineskip}{0pt}\n"
            f"\\begin{{document}}\n\\offinterlineskip\n{body}\n\\end{{document}}\n", encoding="utf-8")
        done = subprocess.run(["pdflatex", "-interaction=batchmode", "-halt-on-error", "sheet.tex"],
                              cwd=work, capture_output=True, text=True)
        made = Path(work) / "sheet.pdf"
        if done.returncode != 0 or not made.is_file():
            log = (Path(work) / "sheet.log").read_text(errors="replace") if (Path(work) / "sheet.log").is_file() else done.stdout
            raise ValueError(f"pdflatex could not tile the sheet: {log.strip().splitlines()[-1] if log.strip() else done.returncode}")
        shutil.copyfile(made, target)


def _png(files: list[Path], target: Path, columns: int) -> None:
    from PIL import Image
    images = [Image.open(path).convert("RGB") for path in files]
    cw, ch = max(i.width for i in images), max(i.height for i in images)
    rows = -(-len(images) // columns)
    sheet = Image.new("RGB", (cw * columns, ch * rows), "white")
    for number, image in enumerate(images):
        sheet.paste(image, ((number % columns) * cw, (number // columns) * ch))
    sheet.save(target)


def tile(files: dict[str, list[Path]], target: Path, columns: int) -> list[str]:
    """`files`: format → the pages' files, in order; `<target>.<format>` for each format all pages have."""
    target.parent.mkdir(parents=True, exist_ok=True)
    made = []
    for fmt, paths in files.items():
        if fmt not in TILED or not paths or not all(p.is_file() for p in paths):
            continue
        out = target.with_name(f"{target.name}.{fmt}")
        (_pdf if fmt == "pdf" else _png)(paths, out, columns)
        made.append(fmt)
    return made
