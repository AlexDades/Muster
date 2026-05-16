from __future__ import annotations
from pathlib import Path
import pypdf
import docx


def parse_pdf(path: str | Path) -> str:
    reader = pypdf.PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def parse_docx(path: str | Path) -> str:
    doc = docx.Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def parse_document(path: str | Path) -> dict:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = parse_pdf(path)
    elif suffix in (".docx", ".doc"):
        text = parse_docx(path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")
    return {
        "text": text,
        "filename": path.name,
        "path": str(path.resolve()),
    }
