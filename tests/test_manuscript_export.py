import io
import zipfile

from docx import Document
import fitz

from app.services.manuscript_export_service import (
    render_manuscript_docx,
    render_manuscript_pdf,
)

SAMPLE_MD = """# 基于文献的量化策略研究

## Abstract
本文评估动量与风险平价策略在样本外的稳健性 [Doc_1_Page_1]。

## 3. Methodology
收益定义如下：

$$
R_t = \\frac{P_t - P_{t-1}}{P_{t-1}} - c \\cdot |\\Delta w_t|
$$

| 指标 | 基线 | 改进方案 |
| --- | --- | --- |
| 约束检查 | PASS | PASS |
"""

SAMPLE_FIGURES = [
    {
        "title": "Figure 1: Pipeline",
        "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 60"><rect width="200" height="60" fill="#eef"/><text x="10" y="30">Stage 1-5</text></svg>',
        "caption": "Workflow overview.",
    }
]


def test_render_manuscript_pdf_outputs_valid_pdf():
    pdf_bytes = render_manuscript_pdf(
        title="测试论文",
        markdown_text=SAMPLE_MD,
        figures=SAMPLE_FIGURES,
    )
    assert pdf_bytes.startswith(b"%PDF-")
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        assert len(doc) >= 1
        text = "".join(page.get_text() for page in doc)
        assert "量化策略研究" in text
        assert "Figure 1" in text


def test_render_manuscript_docx_outputs_valid_docx():
    docx_bytes = render_manuscript_docx(
        title="测试论文",
        markdown_text=SAMPLE_MD,
        figures=SAMPLE_FIGURES,
    )
    assert zipfile.is_zipfile(io.BytesIO(docx_bytes))
    doc = Document(io.BytesIO(docx_bytes))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert "量化策略研究" in full_text
    assert len(doc.tables) == 1
    assert len(doc.inline_shapes) == 1
