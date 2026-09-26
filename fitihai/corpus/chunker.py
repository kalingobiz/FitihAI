"""Split the text of a law into article-level chunks.

Corpus files are UTF-8 text/Markdown with a small front-matter header::

    ---
    id: labour-1156-2019
    title: Labour Proclamation
    proclamation: 1156/2019
    year: 2019
    jurisdiction: federal
    domain: labor
    language: en
    source: https://...
    ---
    Article 1. Short Title
    This Proclamation may be cited as ...

Article headings are recognised in English ("Article 12", "Art. 12") and
Amharic/Tigrinya ("አንቀጽ 12", "አንቀጽ ፲፪"), with Arabic or Ge'ez numerals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

REQUIRED_META = ("id", "title", "domain", "language")

GEEZ_UNITS = {"፩": 1, "፪": 2, "፫": 3, "፬": 4, "፭": 5, "፮": 6, "፯": 7, "፰": 8, "፱": 9}
GEEZ_TENS = {"፲": 10, "፳": 20, "፴": 30, "፵": 40, "፶": 50, "፷": 60, "፸": 70, "፹": 80, "፺": 90}
GEEZ_DIGITS = "".join(GEEZ_UNITS) + "".join(GEEZ_TENS) + "፻፼"

ARTICLE_RE = re.compile(
    rf"^\s*(?:#+\s*)?(?:Article|ARTICLE|Art\.|አንቀጽ|አንቀፅ|ዓንቀጽ)\s*"
    rf"(?P<num>\d+[a-zA-Z]?|[{GEEZ_DIGITS}]+)\s*[.:\-–—)]?\s*(?P<heading>.*)$"
)


def geez_to_int(s: str) -> int:
    """Convert a Ge'ez numeral (e.g. ፻፳፫ = 123) to an int."""
    total, current = 0, 0
    for ch in s:
        if ch in GEEZ_UNITS:
            current += GEEZ_UNITS[ch]
        elif ch in GEEZ_TENS:
            current += GEEZ_TENS[ch]
        elif ch == "፻":
            current = (current or 1) * 100
        elif ch == "፼":
            total = (total + current or 1) * 10000
            current = 0
        else:
            raise ValueError(f"not a Ge'ez numeral: {s!r}")
    return total + current


def normalize_article_number(raw: str) -> str:
    raw = raw.strip()
    if raw and raw[0] in GEEZ_DIGITS:
        return str(geez_to_int(raw))
    return raw


@dataclass
class Article:
    number: str
    heading: str
    text: str


@dataclass
class LawDocument:
    meta: dict[str, str]
    articles: list[Article] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.meta["id"]


def parse_front_matter(raw: str) -> tuple[dict[str, str], str]:
    raw = raw.lstrip("﻿")
    if not raw.startswith("---"):
        raise ValueError("corpus file must start with a '---' front-matter block")
    _, header, body = raw.split("---", 2)
    meta: dict[str, str] = {}
    for line in header.strip().splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip().lower()] = value.strip()
    missing = [k for k in REQUIRED_META if not meta.get(k)]
    if missing:
        raise ValueError(f"front matter missing required keys: {', '.join(missing)}")
    return meta, body


def split_articles(body: str) -> list[Article]:
    articles: list[Article] = []
    current: Article | None = None
    buf: list[str] = []

    def flush() -> None:
        if current is not None:
            current.text = "\n".join(buf).strip()
            if current.text or current.heading:
                articles.append(current)

    for line in body.splitlines():
        m = ARTICLE_RE.match(line)
        if m and m["heading"][:1].islower():
            m = None  # "Article 35 of this Proclamation ..." is a cross-reference, not a heading
        if m:
            flush()
            current = Article(normalize_article_number(m["num"]), m["heading"].strip(), "")
            buf = []
        elif current is not None:
            buf.append(line)
    flush()
    return articles


def parse_law(raw: str) -> LawDocument:
    meta, body = parse_front_matter(raw)
    articles = split_articles(body)
    if not articles:
        raise ValueError(f"no articles found in {meta['id']!r}; check the 'Article N' headings")
    return LawDocument(meta=meta, articles=articles)


def numbering_issues(articles: list[Article]) -> list[str]:
    """Report gaps, repeats and out-of-order numbers, a sign that text extraction went wrong."""
    issues: list[str] = []
    prev: int | None = None
    for a in articles:
        if not a.number.isdigit():
            continue
        n = int(a.number)
        if prev is not None:
            if n == prev:
                issues.append(f"Article {n} appears twice in a row")
            elif n < prev:
                issues.append(f"Article {n} follows Article {prev}")
            elif n > prev + 1:
                missing = f"{prev + 1}" if n == prev + 2 else f"{prev + 1}-{n - 1}"
                issues.append(f"Article(s) {missing} missing before Article {n}")
        prev = n
    return issues
