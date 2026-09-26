"""Tests for the gazette importer. All text here is FICTIONAL, not real law."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from fitihai.cli import main as cli_main
from fitihai.corpus.chunker import parse_law
from fitihai.corpus.importer import approve, clean_gazette_text, import_law
from fitihai.corpus.store import CorpusStore

# Imitates a bilingual gazette page: running header, Amharic and English lines
# side by side, a page number, and a word hyphenated across a line break.
GAZETTE = """\
ፌዴራል ነጋሪት ጋዜጣ ቁጥር 00 Federal Negarit Gazette No. 00
አንቀጽ 1. አጭር ርዕስ
Article 1. Short Title
ይህ አዋጅ የሙከራ አዋጅ ተብሎ ሊጠቀስ ይችላል።
This fictional Proclamation may be cited as the Test Proclamation.
1234
Article 2. Wages
An employer shall pay wages to the em-
ployee on the agreed day.
አንቀጽ 2. ደመወዝ
አሠሪው ደመወዝ በተስማሙበት ቀን መክፈል አለበት።
"""

META = {"id": "test-gazette-en", "title": "FICTIONAL Test Proclamation", "domain": "labor",
        "language": "en", "proclamation": "0000/2000", "jurisdiction": "federal", "source": "test"}


def _minimal_pdf(lines: list[str]) -> bytes:
    """Build a tiny valid PDF with one page of Helvetica text (no extra dependencies)."""
    ops = ["BT", "/F1 11 Tf", "14 TL", "50 780 Td"]
    for line in lines:
        ops.append("(" + line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj T*")
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def test_clean_keeps_one_language_and_drops_page_furniture():
    en = clean_gazette_text(GAZETTE, "en")
    assert "Negarit" not in en and "1234" not in en
    assert "አንቀጽ" not in en
    assert "employee on the agreed day" in en  # hyphenation repaired
    am = clean_gazette_text(GAZETTE, "am")
    assert "Article" not in am and "አንቀጽ 2. ደመወዝ" in am


def test_import_writes_draft_that_is_not_searchable(tmp_path):
    src = tmp_path / "gazette.txt"
    src.write_text(GAZETTE, encoding="utf-8")
    out = tmp_path / "laws" / "test-gazette-en.md"
    assert import_law(src, out, META) == (2, [])
    law = parse_law(out.read_text(encoding="utf-8"))
    assert law.meta["status"] == "draft"
    assert [a.heading for a in law.articles] == ["Short Title", "Wages"]

    store = CorpusStore(tmp_path / "db.sqlite")
    store.ingest_dir(out.parent)
    assert store.list_laws()[0]["status"] == "draft"
    assert store.all_articles() == []  # drafts are never retrieved or cited

    with pytest.raises(FileExistsError):
        import_law(src, out, META)


def test_approve_records_reviewer_and_makes_law_searchable(tmp_path):
    src = tmp_path / "gazette.txt"
    src.write_text(GAZETTE, encoding="utf-8")
    out = tmp_path / "laws" / "test-gazette-en.md"
    import_law(src, out, META)
    meta = approve(out, "Test Reviewer", on=date(2026, 9, 26))
    assert meta["status"] == "in_force"
    text = out.read_text(encoding="utf-8")
    assert "reviewed_by: Test Reviewer" in text and "reviewed_on: 2026-09-26" in text

    store = CorpusStore(tmp_path / "db.sqlite")
    store.ingest_dir(out.parent)
    assert {a.id for a in store.all_articles()} == {"test-gazette-en:1", "test-gazette-en:2"}
    with pytest.raises(ValueError):
        approve(out, "  ")


def test_import_from_pdf(tmp_path):
    lines = [
        "Federal Negarit Gazette No. 00",
        "Article 1. Short Title",
        "This fictional Proclamation may be cited as the Test Proclamation for importer tests.",
        "Article 2. Wages",
        "An employer shall pay wages to the employee on the agreed day, in cash or by bank transfer.",
        "Article 3. Working Hours",
        "Normal hours of work shall be set by agreement between the employer and the employee.",
    ]
    pdf = tmp_path / "gazette.pdf"
    pdf.write_bytes(_minimal_pdf(lines))
    out = tmp_path / "laws" / "x.md"
    assert import_law(pdf, out, META) == (3, [])
    assert "Negarit" not in out.read_text(encoding="utf-8")


def test_scanned_pdf_is_rejected(tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(_minimal_pdf(["x"]))
    with pytest.raises(ValueError, match="scan"):
        import_law(pdf, tmp_path / "out.md", META)


def test_cli_import_and_approve(tmp_path, capsys):
    src = tmp_path / "gazette.txt"
    src.write_text(GAZETTE, encoding="utf-8")
    out = tmp_path / "laws" / "cli.md"
    cli_main(["import", str(src), "--id", "cli-test", "--title", "FICTIONAL", "--domain", "labor",
              "--language", "en", "--out", str(out)])
    assert "status: draft" in capsys.readouterr().out
    cli_main(["approve", str(out), "--by", "Reviewer"])
    assert "status: in_force" in out.read_text(encoding="utf-8")


def test_cross_reference_is_not_a_heading():
    from fitihai.corpus.chunker import split_articles

    arts = split_articles("Article 1. Scope\nThe rules in\nArticle 35 of this Proclamation apply.\nArticle 2. Definitions\nx")
    assert [a.number for a in arts] == ["1", "2"]
    assert "Article 35 of this Proclamation apply." in arts[0].text


def test_numbering_issues_reported():
    from fitihai.corpus.chunker import numbering_issues, split_articles

    arts = split_articles("Article 1. A\nx\nArticle 2. B\nx\nArticle 5. C\nx\nArticle 4. D\nx")
    assert numbering_issues(arts) == ["Article(s) 3-4 missing before Article 5", "Article 4 follows Article 5"]
