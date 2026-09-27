"""Render a stock-lists document (Markdown + landscape-A4 PDF) from builder scripts.

The renderer behind the stock lists v2 (2026-09-26) and v3 / v3.1 (2026-09-27),
committed so the next version does not have to rebuild it.

A builder is a Python file run with `runpy.run_path`, in the order given, each
one starting from the globals the previous one left (a shared namespace). The
parts append blocks to a module-level list `doc` and may fill a dict `stats`:

    ("h1" | "h2" | "h3", "heading text")
    ("p", "paragraph; <b>bold</b>, <i>italic</i>, <br/> allowed")
    ("table", (headers, rows, col_width_fractions, compact: bool))
    ("pb", None)                      # page break (a '---' rule in the Markdown)

Usage:
    python -m scripts.stock_lists_pdf --parts build.py part2.py ... \
        --pdf C:/Users/<me>/Downloads/AEGIS_stock_lists_<date>.pdf \
        --md docs/research_notes/<date>/stock_lists_<date>.md \
        --title "AEGIS stock lists <version> <date>"

Offline, $0: no network and no LLM. Fonts: Windows Arial (a glyph Arial lacks
prints as '?' and is counted in the output as `missing glyphs`).
"""
from __future__ import annotations

import argparse
import html
import re
import runpy
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def run_parts(parts: list[str]) -> dict:
    """Run the builder files in order, threading one namespace through them."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    g: dict = {}
    for p in parts:
        g = runpy.run_path(str(p), init_globals=g, run_name="stock_lists_builder")
    if not isinstance(g.get("doc"), list):
        raise SystemExit("the builder parts did not define a `doc` list")
    return g


def render(doc: list, out_pdf: Path, out_md: Path, *, title: str, footer: str) -> dict:
    from reportlab.lib import colors
    from reportlab.lib.fonts import addMapping
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    F = r"C:\Windows\Fonts"
    pdfmetrics.registerFont(TTFont("Ar", F + r"\arial.ttf"))
    pdfmetrics.registerFont(TTFont("ArB", F + r"\arialbd.ttf"))
    pdfmetrics.registerFont(TTFont("ArI", F + r"\ariali.ttf"))
    pdfmetrics.registerFont(TTFont("ArBI", F + r"\arialbi.ttf"))
    addMapping("Ar", 0, 0, "Ar"); addMapping("Ar", 1, 0, "ArB"); addMapping("Ar", 0, 1, "ArI"); addMapping("Ar", 1, 1, "ArBI")
    cmap = set(TTFont("tmp", F + r"\arial.ttf").face.charToGlyph.keys())
    missing: dict = {}

    def safe(s: str) -> str:
        out = []
        for ch in s:
            if ord(ch) < 128 or ord(ch) in cmap:
                out.append(ch)
            else:
                missing[ch] = missing.get(ch, 0) + 1
                out.append("?")
        return "".join(out)

    def esc(s) -> str:
        return safe(html.escape(str(s), quote=False))

    def markup(s: str) -> str:
        return safe(re.sub(r"&(?!amp;|lt;|gt;|#)", "&amp;", s))

    PW, PH = landscape(A4)
    M = 10 * mm
    AW = PW - 2 * M
    navy = colors.HexColor("#1f3a5f")
    st = {
        "h1": ParagraphStyle("h1", fontName="ArB", fontSize=15, leading=18, spaceBefore=4, spaceAfter=6, textColor=navy),
        "h2": ParagraphStyle("h2", fontName="ArB", fontSize=11, leading=14, spaceBefore=8, spaceAfter=4, textColor=navy),
        "h3": ParagraphStyle("h3", fontName="ArB", fontSize=9, leading=11, spaceBefore=6, spaceAfter=2),
        "p": ParagraphStyle("p", fontName="Ar", fontSize=8, leading=10, spaceAfter=4),
        "c": ParagraphStyle("c", fontName="Ar", fontSize=7, leading=8.4),
        "cs": ParagraphStyle("cs", fontName="Ar", fontSize=6.5, leading=7.6),
        "hd": ParagraphStyle("hd", fontName="ArB", fontSize=7, leading=8.4, textColor=colors.white),
    }
    story, md = [], []

    def md_cell(s) -> str:
        return str(s).replace("|", "\\|").replace("\n", " ")

    def md_text(s: str) -> str:
        return (s.replace("<br/>", "  \n").replace("<b>", "**").replace("</b>", "**")
                .replace("<i>", "`").replace("</i>", "`"))

    for kind, payload in doc:
        if kind == "pb":
            story.append(PageBreak())
            md.append("\n---\n")
        elif kind in ("h1", "h2", "h3"):
            story.append(Paragraph(markup(esc(payload)), st[kind]))
            md.append("\n" + "#" * int(kind[1]) + " " + payload + "\n")
        elif kind == "p":
            story.append(Paragraph(markup(payload), st["p"]))
            md.append(md_text(payload) + "\n")
        elif kind == "table":
            headers, rows, widths, compact = payload
            cs = st["cs"] if compact else st["c"]
            data = [[Paragraph(esc(h), st["hd"]) for h in headers]]
            data += [[Paragraph(esc(c), cs) for c in r] for r in rows]
            t = Table(data, colWidths=[w * AW for w in widths], repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), navy),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef2f7")]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#b0b8c4")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
            ]))
            story.append(t)
            story.append(Spacer(1, 4))
            md.append("| " + " | ".join(md_cell(h) for h in headers) + " |")
            md.append("|" + "---|" * len(headers))
            md.extend("| " + " | ".join(md_cell(c) for c in r) + " |" for r in rows)
            md.append("")
        else:
            raise SystemExit(f"unknown block kind {kind!r}")

    def on_page(canvas, d):
        canvas.saveState()
        canvas.setFont("Ar", 7)
        canvas.setFillColor(colors.grey)
        canvas.drawString(M, 6 * mm, footer)
        canvas.drawRightString(PW - M, 6 * mm, f"page {d.page}")
        canvas.restoreState()

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(out_pdf), pagesize=landscape(A4), leftMargin=M, rightMargin=M, topMargin=M,
                      bottomMargin=12 * mm, title=title, author="Aegis-Finance (generated for Murat)").build(
        story, onFirstPage=on_page, onLaterPages=on_page)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(md), encoding="utf-8")
    pages = None
    try:
        import fitz                                            # PyMuPDF, optional: page count only
        pages = fitz.open(str(out_pdf)).page_count
    except ImportError:
        pass
    return {"pdf": str(out_pdf), "pdf_bytes": out_pdf.stat().st_size, "md": str(out_md),
            "md_bytes": out_md.stat().st_size, "pages": pages, "missing_glyphs": missing}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--parts", nargs="+", required=True, help="builder .py files, run in order")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--md", required=True)
    ap.add_argument("--title", default="AEGIS stock lists")
    ap.add_argument("--footer", default="Aegis-Finance - stock lists - hypothesis/research lists, not investment advice; see §17 caveat")
    a = ap.parse_args(argv)
    g = run_parts(a.parts)
    md = Path(a.md)
    res = render(g["doc"], Path(a.pdf), md if md.is_absolute() else REPO / md, title=a.title, footer=a.footer)
    print(res)
    print(g.get("stats", {}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
