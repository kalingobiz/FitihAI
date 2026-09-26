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
    # Claude models. Reasoning = answers + document analysis; fast = routing/classification.
    reasoning_model: str = field(default_factory=lambda: os.environ.get("FITIH_REASONING_MODEL", "claude-sonnet-5"))
    fast_model: str = field(default_factory=lambda: os.environ.get("FITIH_FAST_MODEL", "claude-haiku-4-5"))
    ocr_model: str = field(default_factory=lambda: os.environ.get("FITIH_OCR_MODEL", "claude-sonnet-5"))
    # "claude" (default) or "gemini" (requires google-genai + GEMINI_API_KEY).
    ocr_provider: str = field(default_factory=lambda: os.environ.get("FITIH_OCR_PROVIDER", "claude"))
    gemini_ocr_model: str = field(default_factory=lambda: os.environ.get("FITIH_GEMINI_OCR_MODEL", "gemini-2.5-flash"))

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


settings = Settings()
