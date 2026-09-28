"""Turn an official gazette PDF (or text export) into a corpus file for review.

Imported laws are written with ``status: draft``. Draft laws are never
retrieved or cited. A reviewer checks the text against the gazette and then
runs ``fitihai.cli approve``, which sets ``status: in_force`` and records who
approved it and when.

Federal Negarit Gazette issues print Amharic and English side by side. With
``language`` set, lines in the other script are dropped, so each language
becomes its own corpus file.
"""

from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path
from typing import Callable

# OCR function: (file bytes, media type) -> transcribed text. The AI providers'
# ``transcribe`` method has this shape.
OcrFn = Callable[[bytes, str], str]
OCR_PAGES_PER_CALL = 4

from .chunker import numbering_issues, parse_front_matter, parse_law

_ETHIOPIC = re.compile(r"[ሀ-፿]")
_LATIN = re.compile(r"[A-Za-z]")

# Running headers, footers and page numbers printed on every gazette page.
_NOISE = [
    re.compile(r"^\s*\d{1,6}\s*$"),                                   # bare page number
    re.compile(r"^\s*(page|ገጽ)\s*\d+\s*$", re.I),
    re.compile(r"federal\s+negarit\s+ga[zs]ett?e", re.I),
    re.compile(r"ፌዴራል\s*ነጋሪት\s*ጋዜጣ"),
    re.compile(r"^\s*negarit\s+g\.?\s*box", re.I),
    re.compile(r"^\s*unit\s+price", re.I),
]

FRONT_MATTER_ORDER = [
    "id", "title", "proclamation", "year", "jurisdiction", "domain", "language",
    "source", "source_sha256", "fetched_on", "text_source", "status", "reviewed_by", "reviewed_on",
]


def _pdf_chunks(data: bytes, pages_per_chunk: int) -> list[bytes]:
    """Split a PDF into small PDFs of a few pages each, so OCR output stays within limits."""
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:  # pragma: no cover - listed in requirements.txt
        return [data]
    reader = PdfReader(io.BytesIO(data))
    chunks = []
    for start in range(0, len(reader.pages), pages_per_chunk):
        writer = PdfWriter()
        for page in reader.pages[start : start + pages_per_chunk]:
            writer.add_page(page)
        buf = io.BytesIO()
        writer.write(buf)
        chunks.append(buf.getvalue())
    return chunks or [data]


def extract_text_with_source(path: Path, ocr: OcrFn | None = None) -> tuple[str, str]:
    """Return (text, how it was obtained: 'pdf_text', 'ocr' or 'text_file')."""
    if path.suffix.lower() != ".pdf":
        return path.read_text(encoding="utf-8"), "text_file"
    try:
        from pdfminer.high_level import extract_text as pdf_text
    except ImportError as exc:  # pragma: no cover - listed in requirements.txt
        raise RuntimeError("PDF import needs `pip install pdfminer.six`") from exc
    text = pdf_text(str(path))
    if len(text.strip()) >= 200:
        return text, "pdf_text"
    if ocr is None:
        raise ValueError(f"{path.name} has little or no text layer; it is probably a scan. "
                         "Import it with OCR (--ocr) or OCR it first.")
    parts = [ocr(chunk, "application/pdf") for chunk in _pdf_chunks(path.read_bytes(), OCR_PAGES_PER_CALL)]
    text = "\n".join(p.strip() for p in parts if p and p.strip())
    if len(text.strip()) < 200:
        raise ValueError(f"OCR found almost no text in {path.name}; check that it is the right file.")
    return text, "ocr"


def extract_text(path: Path, ocr: OcrFn | None = None) -> str:
    """Read a .pdf (text layer, or OCR when ``ocr`` is given) or a .txt/.md file."""
    return extract_text_with_source(path, ocr)[0]


def _script_share(line: str) -> tuple[float, float]:
    eth = len(_ETHIOPIC.findall(line))
    lat = len(_LATIN.findall(line))
    total = eth + lat
    return (eth / total, lat / total) if total else (0.0, 0.0)


def clean_gazette_text(text: str, language: str | None = None) -> str:
    """Remove page furniture, keep one language, and repair broken lines."""
    lines: list[str] = []
    for raw in text.replace("\x0c", "\n").splitlines():
        line = raw.strip()
        if any(p.search(line) for p in _NOISE):
            continue
        if language and line:
            eth, lat = _script_share(line)
            if language == "en" and eth > 0.5:
                continue
            if language in ("am", "ti") and lat > 0.5:
                continue
        lines.append(line)

    out: list[str] = []
    for line in lines:
        # Re-join words hyphenated across a line break: "employ-" + "ment".
        if out and out[-1].endswith("-") and line[:1].islower():
            out[-1] = out[-1][:-1] + line
        else:
            out.append(line)
    cleaned = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip() + "\n"


def render(meta: dict[str, str], body: str) -> str:
    keys = [k for k in FRONT_MATTER_ORDER if meta.get(k)] + sorted(
        k for k in meta if k not in FRONT_MATTER_ORDER and meta[k]
    )
    header = "\n".join(f"{k}: {meta[k]}" for k in keys)
    return f"---\n{header}\n---\n{body.lstrip()}"


def import_law(src: Path, out: Path, meta: dict[str, str], overwrite: bool = False,
               ocr: OcrFn | None = None) -> tuple[int, list[str]]:
    """Write a draft corpus file from ``src``.

    Returns the number of articles found and a list of numbering issues for the reviewer.
    Scanned PDFs are transcribed with ``ocr`` when given; the file then records
    ``text_source: ocr`` so the reviewer knows to check it closely.
    """
    if out.exists() and not overwrite:
        raise FileExistsError(f"{out} exists; pass --overwrite to replace it")
    text, text_source = extract_text_with_source(src, ocr)
    body = clean_gazette_text(text, meta.get("language"))
    meta = {**meta, "text_source": text_source, "status": "draft"}
    content = render(meta, body)
    law = parse_law(content)  # validates front matter and article headings
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    return len(law.articles), numbering_issues(law.articles)


def approve(path: Path, reviewer: str, on: date | None = None) -> dict[str, str]:
    """Mark a reviewed corpus file as in force, recording the reviewer."""
    if not reviewer.strip():
        raise ValueError("reviewer name is required")
    meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
    parse_law(render(meta, body))  # refuse to approve a file that does not parse
    meta.update(status="in_force", reviewed_by=reviewer.strip(), reviewed_on=(on or date.today()).isoformat())
    path.write_text(render(meta, body), encoding="utf-8")
    return meta
