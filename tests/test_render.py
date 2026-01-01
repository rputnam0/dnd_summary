from __future__ import annotations

from pathlib import Path

from docx import Document

from dnd_summary.render import render_summary_docx


def test_render_summary_docx_creates_document(tmp_path: Path):
    output = tmp_path / "summary.docx"

    render_summary_docx("First paragraph.\n\nSecond paragraph.", output)

    assert output.exists()
    doc = Document(str(output))
    texts = [para.text for para in doc.paragraphs if para.text]
    assert texts == ["First paragraph.", "Second paragraph."]
