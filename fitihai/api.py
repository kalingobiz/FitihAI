"""FastAPI app: JSON API, admin console API, and the static web client.

Run:  uvicorn fitihai.api:app --reload
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .admin import build_admin_router
from .config import ROOT, settings
from .corpus.store import CorpusStore
from .embeddings import build_embedder
from .i18n import CONSENT, DISCLAIMER, LANGUAGES, PROVIDER_NAMES, UI, consent
from .llm import IMAGE_TYPES, PDF_TYPE, ModelRefusal, build_model
from .pipeline import Advisor, QuotaExceeded
from .ratelimit import RateLimiter
from .schemas import AnalyzeResponse, AskResponse

log = logging.getLogger("fitihai")
ALLOWED_UPLOADS = IMAGE_TYPES | {PDF_TYPE, "text/plain"}
WEB_DIR = ROOT / "web"


@lru_cache(maxsize=1)
def get_advisor() -> Advisor:
    return Advisor(settings, CorpusStore(settings.db_path), build_model(settings), build_embedder(settings))


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    language: str | None = None
    session_id: str | None = None


def client_id(request: Request, trust_proxy: bool) -> str:
    """Best-effort client identity for rate limits and web quotas (hashed before storage)."""
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def ai_key_configured(s) -> bool:
    if s.llm_provider == "claude":
        return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def create_app(advisor_factory=get_advisor) -> FastAPI:
    app = FastAPI(title="Fitih AI", version="1.0.0")
    limiters: dict[str, RateLimiter] = {}

    def limit(request: Request) -> str:
        """Apply the per-client rate limit; returns the client key for quotas."""
        s = advisor_factory().s
        limiter = limiters.get("api")
        if limiter is None or limiter.per_minute != s.rate_limit_per_minute:
            limiter = limiters["api"] = RateLimiter(s.rate_limit_per_minute)
        key = client_id(request, s.trust_proxy)
        if not limiter.allow(key):
            raise HTTPException(429, "Too many requests. Please wait a minute and try again.")
        return f"web:{key}"

    @app.get("/api/health")
    def health():
        advisor = advisor_factory()
        return {"status": "ok", "provider": advisor.s.llm_provider, "ai_key_configured": ai_key_configured(advisor.s),
                "articles_indexed": len(advisor.index), "articles_embedded": len(advisor.vectors)}

    @app.get("/api/meta")
    def meta():
        s = advisor_factory().s
        return {
            "languages": LANGUAGES, "ui": UI, "disclaimer": DISCLAIMER,
            "consent": {lang: consent(lang, s.llm_provider, s.session_ttl_minutes) for lang in CONSENT},
            "provider": PROVIDER_NAMES.get(s.llm_provider, s.llm_provider),
        }

    @app.get("/api/laws")
    def laws():
        # Public list: only laws that are in force.
        return [law for law in advisor_factory().store.list_laws() if law["status"] == "in_force"]

    @app.post("/api/ask", response_model=AskResponse)
    def ask(req: AskRequest, request: Request):
        limit(request)
        try:
            return advisor_factory().ask(req.question, req.session_id, req.language)
        except ModelRefusal:
            raise HTTPException(422, "The assistant could not answer this request.")
        except Exception:
            log.exception("ask failed")
            raise HTTPException(502, "The AI service is unavailable. Please try again.")

    @app.post("/api/analyze", response_model=AnalyzeResponse)
    async def analyze(
        request: Request,
        file: UploadFile = File(...),
        language: str | None = Form(None),
        session_id: str | None = Form(None),
    ):
        user_key = limit(request)
        s = advisor_factory().s
        media_type = (file.content_type or "").split(";")[0].strip().lower()
        if media_type == "image/jpg":
            media_type = "image/jpeg"
        if media_type not in ALLOWED_UPLOADS:
            raise HTTPException(415, "Upload a JPEG/PNG/WebP photo, a PDF, or a .txt file.")
        data = await file.read(s.max_upload_mb * 1024 * 1024 + 1)
        if len(data) > s.max_upload_mb * 1024 * 1024:
            raise HTTPException(413, f"File too large (max {s.max_upload_mb} MB).")
        if not data:
            raise HTTPException(400, "Empty file.")
        try:
            return await run_in_threadpool(
                advisor_factory().analyze_document, data, media_type, session_id, language, user_key
            )
        except QuotaExceeded:
            raise HTTPException(429, "Free monthly document analyses used up.")
        except ModelRefusal:
            raise HTTPException(422, "The assistant could not analyse this document.")
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        except Exception:
            log.exception("analyze failed")
            raise HTTPException(502, "The AI service is unavailable. Please try again.")

    @app.delete("/api/session/{session_id}")
    def clear_session(session_id: str):
        advisor_factory().sessions.clear(session_id)
        return {"cleared": True}

    app.include_router(build_admin_router(advisor_factory))
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/admin", include_in_schema=False)
    def admin_page():
        return FileResponse(WEB_DIR / "admin.html")

    @app.get("/privacy", include_in_schema=False)
    def privacy_page():
        s = advisor_factory().s
        html = (WEB_DIR / "privacy.html").read_text(encoding="utf-8")
        html = html.replace("{{provider}}", PROVIDER_NAMES.get(s.llm_provider, s.llm_provider))
        html = html.replace("{{minutes}}", str(s.session_ttl_minutes))
        return HTMLResponse(html)

    return app


app = create_app()
