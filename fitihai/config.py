"""Runtime configuration, read from environment variables (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so the project runs without python-dotenv."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


ROOT = Path(__file__).resolve().parent.parent
_load_dotenv(ROOT / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # Which provider runs the AI steps (router, answer, analysis, OCR): "gemini" or "claude".
    llm_provider: str = field(default_factory=lambda: os.environ.get("FITIH_LLM_PROVIDER", "gemini").lower())

    # Gemini models (GEMINI_API_KEY). Reasoning = answers + document analysis; fast = routing.
    gemini_reasoning_model: str = field(default_factory=lambda: os.environ.get("FITIH_GEMINI_REASONING_MODEL", "gemini-2.5-flash"))
    gemini_fast_model: str = field(default_factory=lambda: os.environ.get("FITIH_GEMINI_FAST_MODEL", "gemini-2.5-flash-lite"))
    gemini_ocr_model: str = field(default_factory=lambda: os.environ.get("FITIH_GEMINI_OCR_MODEL", "gemini-2.5-flash"))

    # Claude models (ANTHROPIC_API_KEY).
    claude_reasoning_model: str = field(default_factory=lambda: os.environ.get("FITIH_CLAUDE_REASONING_MODEL", "claude-sonnet-5"))
    claude_fast_model: str = field(default_factory=lambda: os.environ.get("FITIH_CLAUDE_FAST_MODEL", "claude-haiku-4-5"))
    claude_ocr_model: str = field(default_factory=lambda: os.environ.get("FITIH_CLAUDE_OCR_MODEL", "claude-sonnet-5"))

    # Semantic search for RAG: "gemini" (gemini-embedding-001) or "none" (keyword search only).
    embeddings: str = field(default_factory=lambda: os.environ.get("FITIH_EMBEDDINGS", "gemini").lower())
    embedding_model: str = field(default_factory=lambda: os.environ.get("FITIH_EMBEDDING_MODEL", "gemini-embedding-001"))
    embedding_dim: int = field(default_factory=lambda: _int("FITIH_EMBEDDING_DIM", 768))

    db_path: Path = field(default_factory=lambda: Path(os.environ.get("FITIH_DB", str(ROOT / "data" / "fitihai.db"))))
    corpus_dir: Path = field(default_factory=lambda: Path(os.environ.get("FITIH_CORPUS_DIR", str(ROOT / "corpus" / "laws"))))

    top_k: int = field(default_factory=lambda: _int("FITIH_TOP_K", 8))
    session_ttl_minutes: int = field(default_factory=lambda: _int("FITIH_SESSION_TTL_MINUTES", 30))
    max_history_turns: int = field(default_factory=lambda: _int("FITIH_MAX_HISTORY_TURNS", 6))
    max_upload_mb: int = field(default_factory=lambda: _int("FITIH_MAX_UPLOAD_MB", 10))
    # Freemium: document analyses per user per calendar month. 0 = unlimited.
    free_analyses_per_month: int = field(default_factory=lambda: _int("FITIH_FREE_ANALYSES_PER_MONTH", 0))
    # Salt for hashing user identifiers in usage counters (never store raw IDs).
    usage_salt: str = field(default_factory=lambda: os.environ.get("FITIH_USAGE_SALT", "change-me"))

    telegram_token: str = field(default_factory=lambda: os.environ.get("TELEGRAM_BOT_TOKEN", ""))

    # Admin console (/admin). Empty = admin console disabled.
    admin_token: str = field(default_factory=lambda: os.environ.get("FITIH_ADMIN_TOKEN", ""))
    # Requests per minute per client for /api/ask and /api/analyze. 0 = no limit.
    rate_limit_per_minute: int = field(default_factory=lambda: _int("FITIH_RATE_LIMIT_PER_MINUTE", 20))
    # Behind a reverse proxy (Railway, Render, nginx) set to 1 so X-Forwarded-For identifies clients.
    trust_proxy: bool = field(default_factory=lambda: os.environ.get("FITIH_TRUST_PROXY", "0") == "1")


settings = Settings()
