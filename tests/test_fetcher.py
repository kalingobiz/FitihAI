"""Tests for the law downloader against a local web server. All law text is FICTIONAL."""

from __future__ import annotations

import csv
import io
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from pypdf import PdfWriter

from fitihai.cli import main as cli_main
from fitihai.corpus import importer
from fitihai.corpus.chunker import parse_law
from fitihai.corpus.fetcher import (
    FetchError, Fetcher, discover, fetch_sources, read_sources, validate_row, write_sources_skeleton,
)
from fitihai.corpus.store import CorpusStore
from test_importer import _minimal_pdf

LAW_LINES = [
    "Federal Negarit Gazette No. 00",
    "Article 1. Short Title",
    "This FICTIONAL Proclamation may be cited as the Downloader Test Proclamation for tests.",
    "Article 2. Rest Days",
    "A worker is entitled to a weekly rest day of at least twenty four consecutive hours each week.",
]
OCR_TEXT = ("Article 1. Short Title\nThis FICTIONAL scanned Proclamation may be cited as the Scan Test.\n"
            "Article 2. Leave\nA worker is entitled to paid leave as agreed with the employer in writing, "
            "and the agreement shall state the number of days and the manner of payment.\n")


def _blank_pdf(pages: int) -> bytes:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=612, height=842)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


@pytest.fixture
def site(tmp_path):
    root = tmp_path / "site"
    (root / "gazette").mkdir(parents=True)
    (root / "private").mkdir()
    (root / "gazette" / "law.pdf").write_bytes(_minimal_pdf(LAW_LINES))
    (root / "gazette" / "scan.pdf").write_bytes(_blank_pdf(9))
    (root / "gazette" / "notapdf.pdf").write_text("<html>login page</html>")
    (root / "private" / "secret.pdf").write_bytes(_minimal_pdf(LAW_LINES))
    (root / "robots.txt").write_text("User-agent: *\nDisallow: /private/\n")
    (root / "index.html").write_text(
        '<html><body><a href="gazette/law.pdf">Labour Proclamation</a>'
        '<a href="/gazette/scan.pdf"> Scanned\n law </a><a href="about.html">About</a>'
        '<a href="mailto:x@y.z">mail</a><a href="gazette/law.pdf">duplicate</a></body></html>')
    requests = []

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            requests.append(self.path)
            super().do_GET()

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", requests
    server.shutdown()


def _row(law_id, url, **kw):
    return {"id": law_id, "title": "FICTIONAL Test Law", "domain": "labor", "language": "en",
            "jurisdiction": "federal", "url": url, **kw}


def test_discover_lists_pdf_links(site):
    base, _ = site
    links = discover(Fetcher(0), f"{base}/index.html")
    assert links == [(f"{base}/gazette/law.pdf", "Labour Proclamation"), (f"{base}/gazette/scan.pdf", "Scanned law")]
    assert discover(Fetcher(0), f"{base}/index.html", match="about") == [(f"{base}/about.html", "About")]


def test_robots_txt_is_respected(site):
    base, _ = site
    f = Fetcher(0)
    assert f.allowed(f"{base}/gazette/law.pdf")
    assert not f.allowed(f"{base}/private/secret.pdf")
    with pytest.raises(FetchError, match="robots.txt"):
        f.get(f"{base}/private/secret.pdf")


def test_fetch_imports_drafts_and_reports_each_source(site, tmp_path):
    base, requests = site
    corpus = tmp_path / "laws"
    ocr_calls = []

    def fake_ocr(data, media_type):
        ocr_calls.append(len(data))
        return OCR_TEXT if len(ocr_calls) == 1 else ""

    rows = [
        _row("dl-text-en", f"{base}/gazette/law.pdf", proclamation="0000/2000"),
        _row("dl-scan-en", f"{base}/gazette/scan.pdf"),
        _row("dl-html-en", f"{base}/gazette/notapdf.pdf"),
        _row("dl-missing-en", f"{base}/gazette/missing.pdf"),
        _row("dl-blocked-en", f"{base}/private/secret.pdf"),
        _row("dl-nourl-en", ""),
        _row("Bad Id", f"{base}/gazette/law.pdf"),
    ]
    fetcher = Fetcher(0, cache_dir=tmp_path / "cache", contact="team@example.org")
    results = {r.id: r for r in fetch_sources(rows, corpus, fetcher, ocr=fake_ocr)}
    assert {k: v.status for k, v in results.items()} == {
        "dl-text-en": "imported", "dl-scan-en": "imported", "dl-html-en": "failed",
        "dl-missing-en": "failed", "dl-blocked-en": "failed", "dl-nourl-en": "no-url", "Bad Id": "invalid",
    }
    assert results["dl-text-en"].articles == 2 and results["dl-text-en"].text_source == "pdf_text"
    assert results["dl-scan-en"].text_source == "ocr" and len(ocr_calls) == 3   # 9 pages in batches of 4
    assert "not a PDF" in results["dl-html-en"].message
    assert "HTTP 404" in results["dl-missing-en"].message
    assert "robots.txt" in results["dl-blocked-en"].message

    law = parse_law((corpus / "dl-text-en.md").read_text(encoding="utf-8"))
    assert law.meta["status"] == "draft" and law.meta["source"] == f"{base}/gazette/law.pdf"
    assert len(law.meta["source_sha256"]) == 64 and law.meta["fetched_on"]
    assert "Negarit" not in (corpus / "dl-text-en.md").read_text(encoding="utf-8")

    # Drafts are stored but never searchable.
    store = CorpusStore(tmp_path / "db.sqlite")
    store.ingest_dir(corpus)
    assert store.all_articles() == []

    # A second run skips what exists and downloads nothing again.
    before = len(requests)
    again = {r.id: r.status for r in fetch_sources(rows[:1], corpus, fetcher)}
    assert again == {"dl-text-en": "exists"} and len(requests) == before
    # With --overwrite it re-imports from the download cache, still without a request.
    assert fetch_sources(rows[:1], corpus, fetcher, overwrite=True)[0].status == "imported"
    assert len(requests) == before


def test_scanned_pdf_without_ocr_fails_clearly(site, tmp_path):
    base, _ = site
    r = fetch_sources([_row("dl-scan-en", f"{base}/gazette/scan.pdf")], tmp_path / "laws", Fetcher(0))[0]
    assert r.status == "failed" and "--ocr" in r.message


def test_ocr_error_does_not_stop_the_run(site, tmp_path):
    base, _ = site

    def broken_ocr(data, media_type):
        raise RuntimeError("AI service unavailable")

    rows = [_row("a-scan-en", f"{base}/gazette/scan.pdf"), _row("b-text-en", f"{base}/gazette/law.pdf")]
    results = fetch_sources(rows, tmp_path / "laws", Fetcher(0), ocr=broken_ocr)
    assert [r.status for r in results] == ["failed", "imported"]
    assert "AI service unavailable" in results[0].message


def test_pdf_chunks():
    assert len(importer._pdf_chunks(_blank_pdf(9), 4)) == 3
    assert len(importer._pdf_chunks(_blank_pdf(2), 4)) == 1


def test_sources_list_round_trip(tmp_path):
    path = tmp_path / "sources.csv"
    write_sources_skeleton([("https://example.org/a.pdf", "Some law")], path)
    rows = read_sources(path)
    assert rows[0]["url"] == "https://example.org/a.pdf" and rows[0]["title"] == "Some law"
    assert validate_row(rows[0])  # id/domain/language still to be filled in

    shipped = read_sources(Path(__file__).resolve().parent.parent / "corpus/sources/federal-core.csv")
    assert len(shipped) == 30 and all(validate_row(r) is None for r in shipped)
    assert all(r["url"] == "" for r in shipped)          # links are added by the team, not guessed


def test_cli_discover_and_fetch(site, tmp_path, monkeypatch, capsys):
    base, _ = site
    from dataclasses import replace
    import fitihai.cli as cli

    monkeypatch.setattr(cli, "settings", replace(cli.settings, corpus_dir=tmp_path / "laws", fetch_delay_seconds=0,
                                                  download_cache_dir=tmp_path / "cache"))
    out = tmp_path / "found.csv"
    cli_main(["discover", f"{base}/index.html", "--out", str(out)])
    assert "2 link(s) found" in capsys.readouterr().out

    rows = list(csv.DictReader(open(out, encoding="utf-8")))
    rows[0].update(id="cli-dl-en", domain="labor", language="en")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    cli_main(["fetch", str(out)])
    printed = capsys.readouterr().out
    assert "imported  cli-dl-en" in printed and "1 imported as draft" in printed
    assert (tmp_path / "laws" / "cli-dl-en.md").exists()
