"""The viewer (docs/reporter, V104): a page of blocks, each a grid of labelled panels, for browsing.

`page(target, title, blocks)` writes one HTML file: a sticky bar of block links with sizes (S | M | L |
Full) and columns (2 | 3 | 4), ← → between blocks, a panel by its PNG (an image) or its PDF (the
browser's viewer, reloaded to refit after a change of layout), light and dark, a block per printed page.
It keeps no state between visits. Paths are written relative to the page.
"""

from __future__ import annotations

import html
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Shown:
    """A block as the viewer shows it: its panels (label, file) and, when made, its composite."""
    name: str
    title: str
    panels: list[tuple[str, Path]]
    composite: Path | None = None
    notes: list[str] = field(default_factory=list)


STYLE = """\
  :root { --bg:#f6f6f3; --card:#ffffff; --ink:#1d1d1b; --muted:#6b6b66; --line:#deddd6;
          --pdf:#b4472f; --png:#2f6db4; --accent:#1d1d1b; }
  @media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
          --bg:#161615; --card:#1f1f1d; --ink:#ecebe6; --muted:#9a9992; --line:#33332f;
          --pdf:#e0785f; --png:#6fa3e6; --accent:#ecebe6; } }
  :root[data-theme="dark"] { --bg:#161615; --card:#1f1f1d; --ink:#ecebe6; --muted:#9a9992; --line:#33332f;
          --pdf:#e0785f; --png:#6fa3e6; --accent:#ecebe6; }
  * { box-sizing:border-box; }
  html { scroll-behavior:smooth; }
  body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
  .top { position:sticky; top:0; z-index:5; background:var(--bg); border-bottom:1px solid var(--line);
         padding:10px 16px; display:flex; gap:14px; align-items:center; flex-wrap:wrap; }
  .top h1 { font-size:16px; margin:0 8px 0 0; }
  .top nav { display:flex; gap:6px; flex-wrap:wrap; }
  .top nav a { color:var(--muted); text-decoration:none; font-size:13px; padding:3px 8px;
               border:1px solid var(--line); border-radius:999px; }
  .top nav a.on, .top nav a:hover { color:var(--ink); border-color:var(--accent); }
  .controls { display:flex; gap:12px; align-items:center; margin-left:auto; }
  .seg { display:inline-flex; align-items:center; gap:2px; font-size:12px; color:var(--muted); }
  .seg span { margin-right:4px; }
  .seg button { font:inherit; color:var(--muted); background:transparent; border:1px solid var(--line); padding:2px 9px; cursor:pointer; }
  .seg button:first-of-type { border-radius:999px 0 0 999px; }
  .seg button:last-of-type { border-radius:0 999px 999px 0; }
  .seg button + button { border-left:0; }
  .seg button[aria-pressed="true"] { color:var(--bg); background:var(--accent); border-color:var(--accent); }
  .hint { color:var(--muted); font-size:12px; }
  .block { min-height:100vh; padding:20px 16px 32px; scroll-margin-top:var(--top, 60px); margin:0 auto; max-width:var(--width, 1500px); }
  .block header { display:flex; align-items:baseline; gap:12px; margin:0 0 12px; }
  .block h2 { margin:0; font-size:22px; }
  .block header .more { color:var(--muted); font-size:13px; }
  .block header .more a { color:var(--muted); }
  .count { margin-left:auto; color:var(--muted); font-size:13px; font-variant-numeric:tabular-nums; }
  .grid { display:grid; grid-template-columns:repeat(var(--cols, 2), minmax(0,1fr)); gap:14px; }
  .cell { margin:0; background:var(--card); border:1px solid var(--line); border-radius:10px; overflow:hidden; display:flex; flex-direction:column; }
  .cell figcaption { display:flex; gap:10px; align-items:center; padding:8px 12px; border-bottom:1px solid var(--line); font-size:13px; min-width:0; }
  .cell figcaption a { color:var(--muted); text-decoration:none; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .cell figcaption a:hover { color:var(--ink); text-decoration:underline; }
  .tag { font-weight:600; font-size:12px; padding:1px 8px; border-radius:999px; color:#fff; flex:none; }
  .tag.pdf { background:var(--pdf); } .tag.png { background:var(--png); }
  .view { aspect-ratio: 336 / 303; background:#fff; }
  .view object, .view img { width:100%; height:100%; border:0; display:block; object-fit:contain; }
  @media (max-width: 760px) { .grid { grid-template-columns:1fr; } .hint, .seg.cols { display:none; } }
  @media print { .top { display:none; } .block { min-height:auto; break-after:page; } }"""

SCRIPT = """\
  const blocks = [...document.querySelectorAll(".block")];
  const links = [...document.querySelectorAll(".top nav a")];
  const bar = document.querySelector(".top");
  const root = document.documentElement;
  const SIZES = ["900", "1200", "1500", "full"];
  const view = { size: "1500", cols: "2" };
  const current = () => {
    let i = 0;
    const line = (bar.offsetHeight || 60) + 80;                   // just under the bar
    blocks.forEach((b, j) => { if (b.getBoundingClientRect().top <= line) i = j; });
    return i;
  };
  const mark = () => { const i = current(); links.forEach((a, j) => a.classList.toggle("on", j === i)); };
  const fit = () => root.style.setProperty("--top", bar.offsetHeight + 8 + "px");
  const apply = () => {
    root.style.setProperty("--width", view.size === "full" ? "none" : view.size + "px");
    root.style.setProperty("--cols", view.cols);
    document.querySelectorAll("[data-size]").forEach(b => b.setAttribute("aria-pressed", b.dataset.size === view.size));
    document.querySelectorAll("[data-cols]").forEach(b => b.setAttribute("aria-pressed", b.dataset.cols === view.cols));
  };
  // The browser's PDF viewer fits a page once, when it loads: after a change of layout each PDF is
  // loaded again, so it fits its new panel.
  const refit = () => document.querySelectorAll(".view object").forEach(o => o.replaceWith(o.cloneNode(true)));
  const keep = change => {                                         // keep the current block in place
    const i = current(); change(); apply(); fit();
    requestAnimationFrame(() => { blocks[i].scrollIntoView({ behavior: "instant" }); refit(); mark(); });
  };
  document.querySelectorAll("[data-size]").forEach(b => b.addEventListener("click", () => keep(() => view.size = b.dataset.size)));
  document.querySelectorAll("[data-cols]").forEach(b => b.addEventListener("click", () => keep(() => view.cols = b.dataset.cols)));
  apply(); fit(); mark();
  addEventListener("resize", fit);
  addEventListener("scroll", mark, { passive: true });
  addEventListener("keydown", e => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (["2", "3", "4"].includes(e.key)) { keep(() => view.cols = e.key); return; }
    const grow = { "+": 1, "=": 1, "-": -1, "_": -1 }[e.key];
    if (grow) {
      const j = Math.max(0, Math.min(SIZES.length - 1, SIZES.indexOf(view.size) + grow));
      keep(() => view.size = SIZES[j]); return;
    }
    const step = { ArrowRight: 1, PageDown: 1, ArrowLeft: -1, PageUp: -1 }[e.key];
    if (!step) return;
    e.preventDefault();
    blocks[Math.max(0, Math.min(blocks.length - 1, current() + step))].scrollIntoView({ behavior: "smooth" });
  });"""


def _href(path: Path, where: Path) -> str:
    return html.escape(os.path.relpath(path, where).replace(os.sep, "/"), quote=True)


def _cell(label: str, path: Path, where: Path) -> str:
    href, kind = _href(path, where), "png" if path.suffix.lower() == ".png" else "pdf"
    if kind == "png":
        shown = f'<img src="{href}" alt="{html.escape(label, quote=True)}" loading="lazy">'
    else:
        shown = f'<object data="{href}#view=Fit&amp;toolbar=0&amp;navpanes=0&amp;scrollbar=0" type="application/pdf"><a href="{href}">{href}</a></object>'
    return (f'<figure class="cell"><figcaption><span class="tag {kind}">{html.escape(label) or kind.upper()}</span>'
            f'<a href="{href}" target="_blank">{html.escape(path.name)}</a></figcaption><div class="view">{shown}</div></figure>')


def page(target: Path, title: str, blocks: list[Shown]) -> Path:
    """`target`: the viewer of these blocks, its paths relative to it."""
    where = target.parent
    nav = "\n      ".join(f'<a href="#{html.escape(b.name, quote=True)}">{html.escape(b.title)}</a>' for b in blocks)
    sections = []
    for number, block in enumerate(blocks, 1):
        more = [f'composite <a href="{_href(block.composite, where)}" target="_blank">{html.escape(block.composite.name)}</a>']\
            if block.composite else []
        more += [html.escape(n) for n in block.notes]
        cells = "\n      ".join(_cell(label, path, where) for label, path in block.panels)
        sections.append(
            f'  <section class="block" id="{html.escape(block.name, quote=True)}">\n'
            f'    <header><h2>{html.escape(block.title)}</h2><span class="more">{" · ".join(more)}</span>'
            f'<span class="count">{number} / {len(blocks)}</span></header>\n'
            f'    <div class="grid">\n      {cells}\n    </div>\n  </section>')
    text = (f'<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>{html.escape(title)}</title>\n'
            f'<style>\n{STYLE}\n</style>\n</head>\n<body>\n  <div class="top">\n    <h1>{html.escape(title)}</h1>\n'
            f'    <nav>\n      {nav}\n    </nav>\n    <div class="controls">\n'
            '      <div class="seg size" role="group" aria-label="Panel size"><span>Size</span>'
            '<button data-size="900">S</button><button data-size="1200">M</button><button data-size="1500">L</button>'
            '<button data-size="full">Full</button></div>\n'
            '      <div class="seg cols" role="group" aria-label="Columns"><span>Columns</span>'
            '<button data-cols="2">2</button><button data-cols="3">3</button><button data-cols="4">4</button></div>\n'
            '      <span class="hint">← →: block · 2/3/4: columns · + −: size</span>\n    </div>\n  </div>\n'
            + "\n".join(sections) + f"\n<script>\n{SCRIPT}\n</script>\n</body>\n</html>\n")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target
