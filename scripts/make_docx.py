"""Convert a markdown design doc to .docx, swapping mermaid blocks for docs/img/diagram_<n>.png."""
import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.shared import Inches, Pt
from PIL import Image

MD = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/design.md")
OUT = MD.with_suffix(".docx")
IMG = MD.parent / "img"
MARGIN = Inches(0.75)


def add_inline(par, text):
    """Render **bold**, *italic* and `code` spans."""
    for tok in re.split(r"(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)", text):
        if not tok:
            continue
        if tok.startswith("**"):
            par.add_run(tok[2:-2]).bold = True
        elif tok.startswith("`"):
            r = par.add_run(tok[1:-1])
            r.font.name = "Consolas"
            r.font.size = Pt(9)
        elif tok.startswith("*") and len(tok) > 2:
            par.add_run(tok[1:-1]).italic = True
        else:
            par.add_run(tok)


def set_orientation(doc, landscape):
    sec = doc.sections[-1]
    is_land = sec.orientation == WD_ORIENT.LANDSCAPE
    if landscape == is_land:
        return sec
    sec = doc.add_section(WD_SECTION.NEW_PAGE)
    w, h = sec.page_width, sec.page_height
    if (landscape and w < h) or (not landscape and w > h):
        sec.page_width, sec.page_height = h, w
    sec.orientation = WD_ORIENT.LANDSCAPE if landscape else WD_ORIENT.PORTRAIT
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, MARGIN)
    return sec


def add_picture(doc, path):
    w, h = Image.open(path).size
    sec = set_orientation(doc, w / h > 1.25)
    max_w = sec.page_width - sec.left_margin - sec.right_margin
    max_h = sec.page_height - sec.top_margin - sec.bottom_margin - Inches(0.5)
    scale = min(max_w / w, max_h / h)
    doc.add_picture(str(path), width=int(w * scale))
    set_orientation(doc, False)


def add_table(doc, rows):
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    cells = [r for r in cells if not all(re.fullmatch(r":?-+:?", c) for c in r)]
    ncol = len(cells[0])
    t = doc.add_table(rows=0, cols=ncol)
    t.style = "Light Grid Accent 1"
    for i, r in enumerate(cells):
        row = t.add_row().cells
        for j in range(ncol):
            p = row[j].paragraphs[0]
            add_inline(p, r[j] if j < len(r) else "")
            for run in p.runs:
                run.font.size = Pt(9)
                if i == 0:
                    run.bold = True
    doc.add_paragraph()


def main():
    doc = Document()
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(doc.sections[0], side, MARGIN)
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(10.5)

    lines = MD.read_text(encoding="utf-8").splitlines()
    i, diagram = 0, 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            lang = ln[3:].strip()
            j = i + 1
            while not lines[j].startswith("```"):
                j += 1
            body = lines[i + 1:j]
            if lang == "mermaid":
                diagram += 1
                add_picture(doc, IMG / f"diagram_{diagram}.png")
            else:
                p = doc.add_paragraph()
                r = p.add_run("\n".join(body))
                r.font.name = "Consolas"
                r.font.size = Pt(8.5)
            i = j + 1
            continue
        if ln.startswith("|"):
            j = i
            while j < len(lines) and lines[j].startswith("|"):
                j += 1
            add_table(doc, lines[i:j])
            i = j
            continue
        m = re.match(r"^(#{1,4}) (.*)", ln)
        if m:
            doc.add_heading(m.group(2), level=min(len(m.group(1)) - 1, 3) or 0)
        elif re.match(r"^\s*[-*] ", ln):
            indent = (len(ln) - len(ln.lstrip())) // 2
            style = "List Bullet" if indent == 0 else "List Bullet 2"
            add_inline(doc.add_paragraph(style=style), re.sub(r"^\s*[-*] ", "", ln))
        elif re.match(r"^\s*\d+\. ", ln):
            indent = (len(ln) - len(ln.lstrip())) // 2
            style = "List Number" if indent == 0 else "List Number 2"
            add_inline(doc.add_paragraph(style=style), re.sub(r"^\s*\d+\. ", "", ln))
        elif ln.strip() == "---" or not ln.strip():
            pass
        else:
            add_inline(doc.add_paragraph(), ln)
        i += 1
    doc.save(OUT)
    print(f"saved {OUT} ({diagram} diagrams)")


if __name__ == "__main__":
    main()
