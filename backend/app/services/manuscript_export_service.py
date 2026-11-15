"""Export Stage 5 manuscript drafts to PDF and Word (.docx) with figures."""

from __future__ import annotations

import html
import io
import re
import zipfile
from typing import Any
from xml.sax.saxutils import escape as xml_escape

_LATEX_SYMBOL_MAP: tuple[tuple[str, str], ...] = (
    (r"\times", "×"),
    (r"\cdot", "·"),
    (r"\leq", "≤"),
    (r"\le", "≤"),
    (r"\geq", "≥"),
    (r"\ge", "≥"),
    (r"\neq", "≠"),
    (r"\approx", "≈"),
    (r"\infty", "∞"),
    (r"\sum", "∑"),
    (r"\prod", "∏"),
    (r"\sqrt", "√"),
    (r"\pm", "±"),
    (r"\rightarrow", "→"),
    (r"\to", "→"),
    (r"\in", "∈"),
    (r"\forall", "∀"),
    (r"\exists", "∃"),
    (r"\alpha", "α"),
    (r"\beta", "β"),
    (r"\gamma", "γ"),
    (r"\delta", "δ"),
    (r"\epsilon", "ε"),
    (r"\varepsilon", "ε"),
    (r"\theta", "θ"),
    (r"\lambda", "λ"),
    (r"\mu", "μ"),
    (r"\sigma", "σ"),
    (r"\tau", "τ"),
    (r"\phi", "φ"),
    (r"\omega", "ω"),
    (r"\Delta", "Δ"),
    (r"\Sigma", "Σ"),
    (r"\Omega", "Ω"),
)


def _format_math_readable(expr: str) -> str:
    """Convert common LaTeX math commands into clean readable Unicode text for PDF/DOCX."""
    out = expr.strip()
    out = re.sub(r"\\text\{([^}]*)\}", r"\1", out)
    out = re.sub(r"\\mathrm\{([^}]*)\}", r"\1", out)
    out = re.sub(r"\\mathbf\{([^}]*)\}", r"\1", out)
    out = re.sub(r"\\mathbb\{([^}]*)\}", r"\1", out)
    out = re.sub(r"\\frac\{([^}]*)\}\{([^}]*)\}", r"(\1)/(\2)", out)
    for src, dst in _LATEX_SYMBOL_MAP:
        out = out.replace(src, dst)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def _strip_inline_markdown(text: str) -> str:
    """Strip Markdown inline wrappers and format inline math cleanly."""
    cleaned = re.sub(r"\$([^$\n]+)\$", lambda m: _format_math_readable(m.group(1)), text)
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    return cleaned


def _inline_markdown_to_html(text: str) -> str:
    """Escape HTML and convert basic inline Markdown + inline math to HTML."""
    escaped = html.escape(text)
    escaped = re.sub(
        r"\$([^$\n]+)\$",
        lambda m: f'<span class="math-inline">{_format_math_readable(m.group(1))}</span>',
        escaped,
    )
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped


def _parse_markdown_blocks(markdown_text: str) -> list[dict[str, Any]]:
    """Parse Markdown into structured blocks (heading, math, table, list, paragraph)."""
    lines = (markdown_text or "").splitlines()
    blocks: list[dict[str, Any]] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # Block math $$ ... $$
        if stripped.startswith("$$"):
            if stripped.endswith("$$") and len(stripped) > 4:
                blocks.append({"type": "math", "text": stripped[2:-2].strip()})
                i += 1
                continue
            math_lines: list[str] = []
            rest = stripped[2:].strip()
            if rest:
                math_lines.append(rest)
            i += 1
            while i < n:
                cur = lines[i].strip()
                if cur.endswith("$$"):
                    tail = cur[:-2].strip()
                    if tail:
                        math_lines.append(tail)
                    i += 1
                    break
                math_lines.append(cur)
                i += 1
            blocks.append({"type": "math", "text": "\n".join(math_lines).strip()})
            continue

        # Headings
        heading_match = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if heading_match:
            blocks.append(
                {
                    "type": "heading",
                    "level": len(heading_match.group(1)),
                    "text": heading_match.group(2).strip(),
                }
            )
            i += 1
            continue

        # Markdown tables
        if "|" in stripped and i + 1 < n and re.match(r"^\s*\|?[\s:-]+\|[\s|:-]*$", lines[i + 1]):
            table_rows: list[list[str]] = []
            header_cells = [c.strip() for c in stripped.strip("|").split("|")]
            table_rows.append(header_cells)
            i += 2
            while i < n and "|" in lines[i]:
                row_cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                table_rows.append(row_cells)
                i += 1
            blocks.append({"type": "table", "rows": table_rows})
            continue

        # Bullet / numbered list
        if re.match(r"^([-*+]|\d+\.)\s+", stripped):
            items: list[str] = []
            ordered = bool(re.match(r"^\d+\.\s+", stripped))
            while i < n:
                cur = lines[i].strip()
                m = re.match(r"^(?:[-*+]|\d+\.)\s+(.*)$", cur)
                if not m:
                    break
                items.append(m.group(1).strip())
                i += 1
            blocks.append({"type": "list", "ordered": ordered, "items": items})
            continue

        # Paragraph
        para_lines = [stripped]
        i += 1
        while i < n:
            nxt = lines[i].strip()
            if (
                not nxt
                or nxt.startswith("#")
                or nxt.startswith("$$")
                or re.match(r"^([-*+]|\d+\.)\s+", nxt)
                or ("|" in nxt and i + 1 < n and re.match(r"^\s*\|?[\s:-]+\|[\s|:-]*$", lines[i + 1]))
            ):
                break
            para_lines.append(nxt)
            i += 1
        blocks.append({"type": "paragraph", "text": " ".join(para_lines)})

    return blocks


def _svg_to_png_bytes(svg_text: str) -> bytes | None:
    """Rasterize an SVG string to PNG bytes using PyMuPDF."""
    if not svg_text or "<svg" not in svg_text:
        return None
    try:
        import fitz

        with fitz.open(stream=svg_text.encode("utf-8"), filetype="svg") as doc:
            if len(doc) == 0:
                return None
            pix = doc[0].get_pixmap(dpi=160)
            return pix.tobytes("png")
    except Exception:
        return None


def render_manuscript_pdf(
    *,
    title: str,
    markdown_text: str,
    figures: list[dict[str, Any]] | None = None,
) -> bytes:
    """Render a manuscript (Markdown + readable math + tables + SVG figures) to A4 PDF bytes."""
    import fitz

    blocks = _parse_markdown_blocks(markdown_text)
    body_parts: list[str] = []
    if not any(b.get("type") == "heading" and b.get("level") == 1 for b in blocks):
        body_parts.append(f"<h1>{html.escape(title)}</h1>")

    for block in blocks:
        btype = block["type"]
        if btype == "heading":
            lvl = min(4, max(1, int(block["level"])))
            body_parts.append(f"<h{lvl}>{_inline_markdown_to_html(block['text'])}</h{lvl}>")
        elif btype == "math":
            readable = html.escape(_format_math_readable(block["text"]))
            body_parts.append(f'<div class="math-block">{readable}</div>')
        elif btype == "list":
            tag = "ol" if block.get("ordered") else "ul"
            lis = "".join(
                f"<li>{_inline_markdown_to_html(item)}</li>" for item in block["items"]
            )
            body_parts.append(f"<{tag}>{lis}</{tag}>")
        elif btype == "table":
            rows = block["rows"]
            if rows:
                ths = "".join(f"<th>{_inline_markdown_to_html(c)}</th>" for c in rows[0])
                trs = "".join(
                    "<tr>"
                    + "".join(f"<td>{_inline_markdown_to_html(c)}</td>" for c in r)
                    + "</tr>"
                    for r in rows[1:]
                )
                body_parts.append(f"<table><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table>")
        else:
            body_parts.append(f"<p>{_inline_markdown_to_html(block['text'])}</p>")

    for fig in figures or []:
        if not isinstance(fig, dict):
            continue
        svg_str = fig.get("svg")
        if not isinstance(svg_str, str) or "<svg" not in svg_str:
            continue
        fig_title = html.escape(str(fig.get("title") or "Figure"))
        fig_caption = html.escape(str(fig.get("caption") or ""))
        body_parts.append(
            f'<div class="figure-box">'
            f'<div class="figure-title">{fig_title}</div>'
            f"{svg_str}"
            + (f'<div class="figure-caption">{fig_caption}</div>' if fig_caption else "")
            + "</div>"
        )

    full_html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'><style>"
        "body { font-family: sans-serif; font-size: 10.5pt; line-height: 1.55; color: #1e293b; }"
        "h1 { font-size: 17pt; color: #0f172a; margin: 0 0 12pt 0; border-bottom: 1.5pt solid #cbd5e1; padding-bottom: 6pt; }"
        "h2 { font-size: 13pt; color: #1e3a8a; margin: 14pt 0 6pt 0; }"
        "h3 { font-size: 11.5pt; color: #334155; margin: 10pt 0 4pt 0; }"
        "p { margin: 0 0 7pt 0; text-align: justify; }"
        "ul, ol { margin: 4pt 0 8pt 16pt; }"
        "li { margin-bottom: 3pt; }"
        ".math-inline { font-family: monospace; background: #f1f5f9; padding: 1pt 3pt; }"
        ".math-block { font-family: monospace; background: #f8fafc; border-left: 3pt solid #4f46e5; padding: 8pt 10pt; margin: 8pt 0; font-size: 10pt; }"
        "table { width: 100%; border-collapse: collapse; margin: 8pt 0; font-size: 9.5pt; }"
        "th, td { border: 0.75pt solid #cbd5e1; padding: 5pt 6pt; text-align: left; }"
        "th { background: #f1f5f9; font-weight: bold; }"
        ".figure-box { margin: 12pt 0; padding: 8pt; border: 0.75pt solid #cbd5e1; background: #ffffff; }"
        ".figure-title { font-weight: bold; font-size: 10pt; margin-bottom: 6pt; color: #0f172a; }"
        ".figure-caption { font-size: 9pt; color: #475569; margin-top: 6pt; }"
        "</style></head><body>"
        + "\n".join(body_parts)
        + "</body></html>"
    )

    story = fitz.Story(html=full_html)
    mediabox = fitz.paper_rect("a4")
    where = mediabox + (42, 42, -42, -42)
    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    more = True
    while more:
        dev = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    return buf.getvalue()


def _build_minimal_docx_fallback(title: str, markdown_text: str) -> bytes:
    """Build a valid minimal OOXML .docx archive using stdlib when python-docx is absent."""
    blocks = _parse_markdown_blocks(markdown_text)
    paragraphs: list[str] = [title]
    for b in blocks:
        if b["type"] == "heading":
            paragraphs.append(b["text"])
        elif b["type"] == "math":
            paragraphs.append(_format_math_readable(b["text"]))
        elif b["type"] == "list":
            for item in b["items"]:
                paragraphs.append(f"- {_strip_inline_markdown(item)}")
        elif b["type"] == "table":
            for row in b["rows"]:
                paragraphs.append(" | ".join(_strip_inline_markdown(c) for c in row))
        else:
            paragraphs.append(_strip_inline_markdown(b["text"]))

    body_xml = "".join(
        f"<w:p><w:r><w:t xml:space=\"preserve\">{xml_escape(p)}</w:t></w:r></w:p>"
        for p in paragraphs
        if p
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body_xml}<w:sectPr/></w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)
    return buf.getvalue()


def render_manuscript_docx(
    *,
    title: str,
    markdown_text: str,
    figures: list[dict[str, Any]] | None = None,
) -> bytes:
    """Render a manuscript (Markdown + readable math + tables + rasterized figures) to .docx bytes."""
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Inches, Pt
    except ImportError:
        return _build_minimal_docx_fallback(title, markdown_text)

    doc = Document()
    normal_style = doc.styles["Normal"]
    normal_style.font.size = Pt(10.5)

    blocks = _parse_markdown_blocks(markdown_text)
    if not any(b.get("type") == "heading" and b.get("level") == 1 for b in blocks):
        doc.add_heading(title, level=0)

    for block in blocks:
        btype = block["type"]
        if btype == "heading":
            lvl = min(3, max(1, int(block["level"])))
            doc.add_heading(_strip_inline_markdown(block["text"]), level=0 if lvl == 1 else lvl - 1)
        elif btype == "math":
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(_format_math_readable(block["text"]))
            run.italic = True
        elif btype == "list":
            style_name = "List Number" if block.get("ordered") else "List Bullet"
            for item in block["items"]:
                doc.add_paragraph(_strip_inline_markdown(item), style=style_name)
        elif btype == "table":
            rows = block["rows"]
            if rows:
                cols = max(len(r) for r in rows)
                table = doc.add_table(rows=len(rows), cols=cols)
                table.style = "Table Grid"
                for r_idx, row_cells in enumerate(rows):
                    for c_idx in range(cols):
                        val = row_cells[c_idx] if c_idx < len(row_cells) else ""
                        table.cell(r_idx, c_idx).text = _strip_inline_markdown(val)
        else:
            doc.add_paragraph(_strip_inline_markdown(block["text"]))

    for fig in figures or []:
        if not isinstance(fig, dict):
            continue
        svg_str = fig.get("svg")
        if not isinstance(svg_str, str):
            continue
        png_bytes = _svg_to_png_bytes(svg_str)
        if not png_bytes:
            continue
        if fig.get("title"):
            p_title = doc.add_paragraph()
            p_title.add_run(str(fig["title"])).bold = True
        doc.add_picture(io.BytesIO(png_bytes), width=Inches(6.0))
        if fig.get("caption"):
            p_cap = doc.add_paragraph(str(fig["caption"]))
            if p_cap.runs:
                p_cap.runs[0].font.size = Pt(9)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
