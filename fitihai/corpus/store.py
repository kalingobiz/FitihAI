"""SQLite storage for the legal corpus and anonymous usage counters.

User documents and conversations are never written here.
"""

from __future__ import annotations

import functools
import hashlib
import sqlite3
import threading
import time
from array import array
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .chunker import LawDocument, parse_law

SCHEMA = """
CREATE TABLE IF NOT EXISTS laws (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    proclamation TEXT,
    year TEXT,
    jurisdiction TEXT,
    domain TEXT NOT NULL,
    language TEXT NOT NULL,
    source TEXT,
    status TEXT DEFAULT 'in_force'
);
CREATE TABLE IF NOT EXISTS articles (
    id TEXT PRIMARY KEY,
    law_id TEXT NOT NULL REFERENCES laws(id) ON DELETE CASCADE,
    number TEXT NOT NULL,
    heading TEXT,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_articles_law ON articles(law_id);
CREATE TABLE IF NOT EXISTS embeddings (
    model TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    vector BLOB NOT NULL,
    PRIMARY KEY (model, text_hash)
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usage (
    user_hash TEXT NOT NULL,
    period TEXT NOT NULL,
    kind TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_hash, period, kind)
);
"""


@dataclass(frozen=True)
class ArticleRecord:
    id: str
    law_id: str
    law_title: str
    proclamation: str
    jurisdiction: str
    domain: str
    language: str
    number: str
    heading: str
    text: str
    source: str

    @property
    def citation(self) -> str:
        proc = f" (Proclamation No. {self.proclamation})" if self.proclamation else ""
        return f"{self.law_title}{proc}, Art. {self.number}"


def _locked(method):
    """Serialise access: one sqlite3 connection is shared by the server's threads."""

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class CorpusStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        if str(db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        if str(db_path) != ":memory:":
            # WAL lets the web server and the Telegram bot share one database file.
            self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.executescript(SCHEMA)

    # ---- corpus version (changes whenever laws are loaded, so every process can reload)
    @_locked
    def corpus_version(self) -> str:
        row = self.conn.execute("SELECT value FROM meta WHERE key = 'corpus_version'").fetchone()
        return row["value"] if row else "0"

    @_locked
    def bump_corpus_version(self) -> str:
        version = f"{time.time_ns()}"
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('corpus_version', ?)", (version,))
        return version

    # ---- corpus -----------------------------------------------------------
    @_locked
    def upsert_law(self, law: LawDocument) -> int:
        m = law.meta
        with self.conn:
            self.conn.execute("DELETE FROM articles WHERE law_id = ?", (law.id,))
            self.conn.execute(
                "INSERT OR REPLACE INTO laws (id, title, proclamation, year, jurisdiction, domain, language, source, status)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    law.id, m["title"], m.get("proclamation", ""), m.get("year", ""),
                    m.get("jurisdiction", "federal"), m["domain"].lower(), m["language"].lower(),
                    m.get("source", ""), m.get("status", "in_force"),
                ),
            )
            seen: dict[str, int] = {}
            for a in law.articles:
                # Some laws repeat numbers across parts/schedules; keep IDs unique.
                n = seen.get(a.number, 0)
                seen[a.number] = n + 1
                art_id = f"{law.id}:{a.number}" + (f"-{n + 1}" if n else "")
                self.conn.execute(
                    "INSERT INTO articles (id, law_id, number, heading, text) VALUES (?, ?, ?, ?, ?)",
                    (art_id, law.id, a.number, a.heading, a.text),
                )
        return len(law.articles)

    @_locked
    def ingest_dir(self, directory: Path, prune: bool = False) -> dict[str, int]:
        """Load every law file in ``directory``.

        With ``prune``, laws whose file is no longer in the folder are removed, so the
        database mirrors the corpus folder exactly.
        """
        results: dict[str, int] = {}
        for path in sorted(directory.rglob("*")):
            if path.suffix.lower() not in {".md", ".txt"} or path.name.lower() == "readme.md":
                continue
            law = parse_law(path.read_text(encoding="utf-8"))
            if law.id in results:
                raise ValueError(f"duplicate law id {law.id!r} in {path}")
            results[law.id] = self.upsert_law(law)
        if prune:
            with self.conn:
                for row in self.conn.execute("SELECT id FROM laws").fetchall():
                    if row["id"] not in results:
                        self.conn.execute("DELETE FROM laws WHERE id = ?", (row["id"],))
        self.bump_corpus_version()
        return results

    @_locked
    def all_articles(self) -> list[ArticleRecord]:
        rows = self.conn.execute(
            "SELECT a.id, a.law_id, l.title, l.proclamation, l.jurisdiction, l.domain, l.language,"
            " a.number, a.heading, a.text, l.source"
            " FROM articles a JOIN laws l ON l.id = a.law_id WHERE l.status = 'in_force'"
        ).fetchall()
        return [ArticleRecord(*row) for row in rows]

    @_locked
    def list_laws(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT l.*, COUNT(a.id) AS article_count FROM laws l"
            " LEFT JOIN articles a ON a.law_id = l.id GROUP BY l.id ORDER BY l.domain, l.title"
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- embedding cache (keyed by article text hash, so unchanged articles are never re-embedded)
    @_locked
    def load_embeddings(self, model: str) -> dict[str, list[float]]:
        rows = self.conn.execute("SELECT text_hash, vector FROM embeddings WHERE model = ?", (model,)).fetchall()
        return {r["text_hash"]: array("f", r["vector"]).tolist() for r in rows}

    @_locked
    def save_embeddings(self, model: str, vectors: dict[str, list[float]]) -> None:
        with self.conn:
            self.conn.executemany(
                "INSERT OR REPLACE INTO embeddings (model, text_hash, vector) VALUES (?, ?, ?)",
                [(model, h, array("f", v).tobytes()) for h, v in vectors.items()],
            )

    # ---- anonymous usage counters -------------------------------------------
    @staticmethod
    def hash_user(user_id: str, salt: str) -> str:
        return hashlib.sha256(f"{salt}:{user_id}".encode()).hexdigest()[:32]

    @_locked
    def usage_count(self, user_hash: str, kind: str, period: str | None = None) -> int:
        period = period or date.today().strftime("%Y-%m")
        row = self.conn.execute(
            "SELECT count FROM usage WHERE user_hash = ? AND period = ? AND kind = ?",
            (user_hash, period, kind),
        ).fetchone()
        return row["count"] if row else 0

    @_locked
    def increment_usage(self, user_hash: str, kind: str, period: str | None = None) -> None:
        period = period or date.today().strftime("%Y-%m")
        with self.conn:
            self.conn.execute(
                "INSERT INTO usage (user_hash, period, kind, count) VALUES (?, ?, ?, 1)"
                " ON CONFLICT(user_hash, period, kind) DO UPDATE SET count = count + 1",
                (user_hash, period, kind),
            )
