"""FastAPI app: JSON API + the static web client.

Run:  uvicorn fitihai.api:app --reload
"""

from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .config import ROOT, settings
from .corpus.store import CorpusStore
from .i18n import DISCLAIMER, LANGUAGES, UI
from .embeddings import build_embedder
from .llm import IMAGE_TYPES, PDF_TYPE, ModelRefusal, build_model
from .pipeline import Advisor, QuotaExceeded
from .schemas import AnalyzeResponse, AskResponse

log = logging.getLogger("fitihai")
ALLOWED_UPLOADS = IMAGE_TYPES | {PDF_TYPE, "text/plain"}


@lru_cache(maxsize=1)
def get_advisor() -> Advisor:
    return Advisor(settings, CorpusStore(settings.db_path), build_model(settings), build_embedder(settings))


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    language: str | None = None
    session_id: str | None = None


def create_app(advisor_factory=get_advisor) -> FastAPI:
    app = FastAPI(title="Fitih AI", version="0.1.0")

    @app.get("/api/health")
    def health():
        advisor = advisor_factory()
        return {"status": "ok", "provider": advisor.s.llm_provider, "articles_indexed": len(advisor.index),
                "articles_embedded": len(advisor.vectors)}

    @app.get("/api/meta")
    def meta():
        return {"languages": LANGUAGES, "ui": UI, "disclaimer": DISCLAIMER}

    @app.get("/api/laws")
    def laws():
        return advisor_factory().store.list_laws()

    @app.post("/api/ask", response_model=AskResponse)
    def ask(req: AskRequest):
        try:
            return advisor_factory().ask(req.question, req.session_id, req.language)
        except ModelRefusal:
            raise HTTPException(422, "The assistant could not answer this request.")
        except Exception:
            log.exception("ask failed")
            raise HTTPException(502, "The AI service is unavailable. Please try again.")

    @app.post("/api/analyze", response_model=AnalyzeResponse)
    async def analyze(
        file: UploadFile = File(...),
        language: str | None = Form(None),
        session_id: str | None = Form(None),
    ):
        media_type = (file.content_type or "").split(";")[0].strip().lower()
        if media_type == "image/jpg":
            media_type = "image/jpeg"
        if media_type not in ALLOWED_UPLOADS:
            raise HTTPException(415, "Upload a JPEG/PNG/WebP photo, a PDF, or a .txt file.")
        data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
        if len(data) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(413, f"File too large (max {settings.max_upload_mb} MB).")
        if not data:
            raise HTTPException(400, "Empty file.")
        try:
            return await run_in_threadpool(
                advisor_factory().analyze_document, data, media_type, session_id, language, session_id
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

    web_dir = ROOT / "web"
    app.mount("/static", StaticFiles(directory=web_dir), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(web_dir / "index.html")

    return app


app = create_app()
