"""Download official law PDFs from the web and import them as drafts.

Two steps:

1. ``discover(url)`` lists the PDF links on a page (for example a gazette index
   page), so an editor can build a *sources list*.
2. ``fetch_sources(rows, ...)`` downloads every PDF in the sources list and
   imports it with the gazette importer. Every imported law is a **draft**: it is
   never searched or cited until a lawyer approves it.

The fetcher is polite: it obeys robots.txt, waits between requests to the same
site, identifies itself, and caches downloads so nothing is fetched twice.
"""

from __future__ import annotations

import csv
import hashlib
import re
import tempfile
import time
import urllib.error
import urllib.request
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

from .chunker import parse_front_matter
from .importer import OcrFn, import_law

LAW_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,80}$")
DOMAINS = {"labor", "land", "commercial", "family", "criminal", "tax", "civil_procedure", "administrative", "other"}
LANGUAGES = {"am", "en", "om", "ti"}
SOURCE_COLUMNS = ["id", "title", "proclamation", "year", "domain", "language", "jurisdiction", "url", "source"]
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024


class FetchError(Exception):
    pass


# ---- HTTP ---------------------------------------------------------------------------
class Fetcher:
    def __init__(self, delay_seconds: float = 2.0, timeout: float = 60.0, contact: str = "",
                 cache_dir: Path | None = None):
        self.delay = delay_seconds
        self.timeout = timeout
        self.user_agent = "FitihAI-corpus-fetcher/1.0" + (f" (+{contact})" if contact else "")
        self.cache_dir = cache_dir
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.requests_made = 0

    def _robots_for(self, url: str) -> urllib.robotparser.RobotFileParser | None:
        parts = urlparse(url)
        root = f"{parts.scheme}://{parts.netloc}"
        if root not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                raw = self._raw_get(f"{root}/robots.txt", check_robots=False)[0]
                rp.parse(raw.decode("utf-8", errors="replace").splitlines())
            except FetchError:
                rp = None  # no robots.txt: allowed
            self._robots[root] = rp
        return self._robots[root]

    def allowed(self, url: str) -> bool:
        rp = self._robots_for(url)
        return True if rp is None else rp.can_fetch(self.user_agent, url)

    def _wait_turn(self, url: str) -> None:
        host = urlparse(url).netloc
        wait = self.delay - (time.monotonic() - self._last_request.get(host, -1e9))
        if wait > 0:
            time.sleep(wait)
        self._last_request[host] = time.monotonic()

    def _raw_get(self, url: str, check_robots: bool = True) -> tuple[bytes, str]:
        if urlparse(url).scheme not in ("http", "https"):
            raise FetchError(f"not an http(s) URL: {url}")
        if check_robots and not self.allowed(url):
            raise FetchError(f"robots.txt does not allow fetching {url}")
        self._wait_turn(url)
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                self.requests_made += 1
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = resp.read(MAX_DOWNLOAD_BYTES + 1)
                    if len(data) > MAX_DOWNLOAD_BYTES:
                        raise FetchError(f"file larger than {MAX_DOWNLOAD_BYTES // 2**20} MB: {url}")
                    return data, resp.headers.get_content_type()
            except urllib.error.HTTPError as exc:
                if exc.code < 500 and exc.code != 429:
                    raise FetchError(f"HTTP {exc.code} for {url}") from exc
                last_error = exc
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                last_error = exc
            time.sleep(min(2 ** attempt * max(self.delay, 0.5), 30))
        raise FetchError(f"could not download {url}: {last_error}")

    def get(self, url: str) -> tuple[bytes, str]:
        """Download ``url`` (from the cache if already downloaded)."""
        cached = None
        if self.cache_dir is not None:
            cached = self.cache_dir / hashlib.sha256(url.encode()).hexdigest()
            if cached.exists():
                data = cached.read_bytes()
                return data, "application/pdf" if data[:5] == b"%PDF-" else ""
        data, content_type = self._raw_get(url)
        if cached is not None:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(data)
        return data, content_type


# ---- discovery ----------------------------------------------------------------------
class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None


def discover(fetcher: Fetcher, page_url: str, match: str | None = None) -> list[tuple[str, str]]:
    """Return (absolute url, link text) for every PDF linked from ``page_url``."""
    data, _ = fetcher._raw_get(page_url)
    parser = _LinkParser()
    parser.feed(data.decode("utf-8", errors="replace"))
    pattern = re.compile(match, re.I) if match else None
    seen, out = set(), []
    for href, text in parser.links:
        url = urljoin(page_url, href.strip())
        if urlparse(url).scheme not in ("http", "https") or url in seen:
            continue
        is_pdf = urlparse(url).path.lower().endswith(".pdf")
        if (pattern and (pattern.search(url) or pattern.search(text))) or (not pattern and is_pdf):
            seen.add(url)
            out.append((url, text))
    return out


def write_sources_skeleton(links: list[tuple[str, str]], path: Path) -> None:
    """Write discovered links as a sources list for an editor to complete."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SOURCE_COLUMNS)
        w.writeheader()
        for url, text in links:
            w.writerow({"url": url, "title": text, "jurisdiction": "federal"})


# ---- sources list -> drafts ---------------------------------------------------------
def read_sources(path: Path) -> list[dict[str, str]]:
    lines = [line for line in path.read_text(encoding="utf-8-sig").splitlines() if not line.lstrip().startswith("#")]
    rows = []
    for row in csv.DictReader(lines):
        rows.append({k: (v or "").strip() for k, v in row.items() if k})
    return rows


def validate_row(row: dict[str, str]) -> str | None:
    """Return an error message, or None if the row can be fetched."""
    if not LAW_ID_RE.match(row.get("id", "")):
        return "id must be lowercase letters, digits, '-' or '_'"
    if not row.get("title"):
        return "title is required"
    if row.get("domain") not in DOMAINS:
        return f"domain must be one of {', '.join(sorted(DOMAINS))}"
    if row.get("language") not in LANGUAGES:
        return f"language must be one of {', '.join(sorted(LANGUAGES))}"
    return None


@dataclass
class FetchResult:
    id: str
    status: str            # imported | exists | no-url | invalid | failed
    url: str = ""
    articles: int = 0
    issues: list[str] = field(default_factory=list)
    text_source: str = ""
    message: str = ""


def fetch_sources(rows: list[dict[str, str]], corpus_dir: Path, fetcher: Fetcher,
                  ocr: OcrFn | None = None, overwrite: bool = False) -> list[FetchResult]:
    results: list[FetchResult] = []
    for row in rows:
        law_id, url = row.get("id", ""), row.get("url", "")
        if not url:
            results.append(FetchResult(law_id, "no-url", message="add the PDF link in the url column"))
            continue
        error = validate_row(row)
        if error:
            results.append(FetchResult(law_id, "invalid", url, message=error))
            continue
        out = corpus_dir / f"{law_id}.md"
        if out.exists() and not overwrite:
            results.append(FetchResult(law_id, "exists", url, message="already in the library (use --overwrite)"))
            continue
        try:
            data, content_type = fetcher.get(url)
            if data[:5] != b"%PDF-":
                raise FetchError(f"not a PDF (got {content_type or 'unknown content'}); link to the PDF itself")
            meta = {
                "id": law_id, "title": row["title"], "proclamation": row.get("proclamation", ""),
                "year": row.get("year", ""), "jurisdiction": row.get("jurisdiction") or "federal",
                "domain": row["domain"], "language": row["language"], "source": row.get("source") or url,
                "source_sha256": hashlib.sha256(data).hexdigest(), "fetched_on": date.today().isoformat(),
            }
            with tempfile.TemporaryDirectory() as tmp:
                src = Path(tmp) / "download.pdf"
                src.write_bytes(data)
                count, issues = import_law(src, out, meta, overwrite=overwrite, ocr=ocr)
            text_source = parse_front_matter(out.read_text(encoding="utf-8"))[0].get("text_source", "")
            results.append(FetchResult(law_id, "imported", url, count, issues, text_source))
        except Exception as exc:  # one bad source (download, OCR, parsing) must not stop the rest
            results.append(FetchResult(law_id, "failed", url, message=f"{exc.__class__.__name__}: {exc}"
                                       if not isinstance(exc, (FetchError, ValueError)) else str(exc)))
    return results
