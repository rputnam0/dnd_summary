from __future__ import annotations

from pathlib import Path

from docx import Document


def render_summary_docx(text: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    for paragraph in text.split("\n\n"):
        cleaned = paragraph.strip()
        if not cleaned:
            continue
        doc.add_paragraph(cleaned)
    doc.save(str(output_path))
