"""Admin console API: manage the law library from the browser.

Every endpoint requires ``Authorization: Bearer <FITIH_ADMIN_TOKEN>``. When the
token is not configured, the admin API is disabled (404).

Safety rules enforced here, not just in the UI:
- imported laws start as ``draft`` (never searched or cited);
- any edit to a law's text puts it back to ``draft`` and clears the approval;
- only drafts can be deleted; approved laws are repealed instead, keeping a record.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .corpus.chunker import numbering_issues, parse_front_matter, parse_law
from .corpus.importer import approve, import_law, render
from .i18n import LANGUAGES

log = logging.getLogger("fitihai.admin")

LAW_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,80}$")
DOMAINS = {"labor", "land", "commercial", "family", "criminal", "tax", "civil_procedure", "administrative", "other"}
MAX_IMPORT_MB = 50


class LawEdit(BaseModel):
    content: str = Field(min_length=10, max_length=5_000_000)


class Approval(BaseModel):
    reviewer: str = Field(min_length=2, max_length=120)


def _files(corpus_dir: Path) -> dict[str, Path]:
    """Map law id -> file. Files that cannot be parsed are keyed by file name."""
    out: dict[str, Path] = {}
    if not corpus_dir.is_dir():
        return out
    for path in sorted(corpus_dir.rglob("*")):
        if path.suffix.lower() not in {".md", ".txt"} or path.name.lower() == "readme.md":
            continue
        try:
            meta, _ = parse_front_matter(path.read_text(encoding="utf-8"))
            out[meta["id"]] = path
        except (ValueError, UnicodeDecodeError):
            out[f"!{path.name}"] = path
    return out


def _summary(key: str, path: Path) -> dict:
    info: dict = {"id": key, "file": path.name}
    try:
        law = parse_law(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        return {**info, "status": "error", "error": str(exc), "article_count": 0, "issues": []}
    m = law.meta
    return {
        **info,
        "title": m.get("title", ""), "language": m.get("language", ""), "domain": m.get("domain", ""),
        "proclamation": m.get("proclamation", ""), "jurisdiction": m.get("jurisdiction", "federal"),
        "status": m.get("status", "in_force"), "reviewed_by": m.get("reviewed_by", ""),
        "reviewed_on": m.get("reviewed_on", ""), "source": m.get("source", ""),
        "text_source": m.get("text_source", ""),
        "article_count": len(law.articles), "issues": numbering_issues(law.articles), "error": "",
    }


def build_admin_router(get_advisor: Callable) -> APIRouter:
    router = APIRouter(prefix="/api/admin", tags=["admin"])

    def settings():
        return get_advisor().s

    def require_admin(authorization: str = Header(default="")):
        token = settings().admin_token
        if not token:
            raise HTTPException(404, "Admin console is disabled. Set FITIH_ADMIN_TOKEN to enable it.")
        supplied = authorization.removeprefix("Bearer ").strip()
        if not hmac.compare_digest(supplied.encode(), token.encode()):
            raise HTTPException(401, "Wrong admin token.")

    def law_path(law_id: str) -> Path:
        if not LAW_ID_RE.match(law_id):
            raise HTTPException(400, "Invalid law id.")
        path = _files(settings().corpus_dir).get(law_id)
        if path is None:
            raise HTTPException(404, f"No law with id {law_id!r}.")
        return path

    auth = [Depends(require_admin)]

    @router.get("/laws", dependencies=auth)
    def list_laws():
        corpus = settings().corpus_dir
        indexed = {row["id"]: row for row in get_advisor().store.list_laws()}
        laws = []
        for key, path in _files(corpus).items():
            item = _summary(key, path)
            item["published"] = key in indexed and indexed[key]["status"] == item.get("status")
            laws.append(item)
        return {"corpus_dir": str(corpus), "laws": laws,
                "articles_searchable": len(get_advisor().index), "languages": list(LANGUAGES)}

    @router.post("/import", dependencies=auth)
    async def import_file(
        file: UploadFile | None = File(None),
        url: str = Form(""),
        id: str = Form(...), title: str = Form(...), domain: str = Form(...), language: str = Form(...),
        proclamation: str = Form(""), year: str = Form(""), jurisdiction: str = Form("federal"),
        source: str = Form(""), overwrite: bool = Form(False), ocr: bool = Form(False),
    ):
        if not LAW_ID_RE.match(id):
            raise HTTPException(400, "Law id: lowercase letters, digits, '-' or '_' (e.g. labour-1156-2019-en).")
        if domain not in DOMAINS:
            raise HTTPException(400, f"Domain must be one of: {', '.join(sorted(DOMAINS))}.")
        if language not in LANGUAGES:
            raise HTTPException(400, f"Language must be one of: {', '.join(LANGUAGES)}.")
        s = settings()
        meta = {"id": id, "title": title.strip(), "proclamation": proclamation.strip(), "year": year.strip(),
                "jurisdiction": jurisdiction.strip() or "federal", "domain": domain, "language": language,
                "source": source.strip()}
        url = url.strip()
        if url:
            # Download from a link (polite: robots.txt, identified User-Agent, cached).
            from .corpus.fetcher import FetchError, Fetcher

            fetcher = Fetcher(s.fetch_delay_seconds, contact=s.fetch_contact, cache_dir=s.download_cache_dir)
            try:
                data, _ = await run_in_threadpool(fetcher.get, url)
            except FetchError as exc:
                raise HTTPException(422, f"Download failed: {exc}")
            if data[:5] != b"%PDF-":
                raise HTTPException(422, "The link did not return a PDF. Link to the PDF file itself.")
            suffix = ".pdf"
            meta["source"] = meta["source"] or url
            meta["source_sha256"] = hashlib.sha256(data).hexdigest()
            meta["fetched_on"] = date.today().isoformat()
        elif file is not None:
            suffix = Path(file.filename or "").suffix.lower()
            if suffix not in {".pdf", ".txt", ".md"}:
                raise HTTPException(415, "Upload the gazette as a PDF, or as a .txt/.md text export.")
            data = await file.read(MAX_IMPORT_MB * 1024 * 1024 + 1)
            if len(data) > MAX_IMPORT_MB * 1024 * 1024:
                raise HTTPException(413, f"File too large (max {MAX_IMPORT_MB} MB).")
        else:
            raise HTTPException(400, "Choose a file or give a link to the gazette PDF.")
        existing = _files(s.corpus_dir).get(id)
        out = existing or s.corpus_dir / f"{id}.md"
        ocr_fn = get_advisor().model.transcribe if ocr else None
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / f"upload{suffix}"
            src.write_bytes(data)
            try:
                count, issues = await run_in_threadpool(import_law, src, out, meta, overwrite, ocr_fn)
            except FileExistsError:
                raise HTTPException(409, f"A law with id {id!r} already exists. Tick 'replace' to overwrite it.")
            except ValueError as exc:
                raise HTTPException(422, str(exc))
            except Exception as exc:  # OCR provider failure
                log.warning("import of %s failed", id, exc_info=True)
                raise HTTPException(502, f"Import failed while reading the scan: {exc.__class__.__name__}. Try again.")
        log.info("imported %s (%d articles) as draft", id, count)
        text_source = parse_front_matter(out.read_text(encoding="utf-8"))[0].get("text_source", "")
        return {"id": id, "article_count": count, "issues": issues, "status": "draft", "text_source": text_source}

    @router.get("/laws/{law_id}", dependencies=auth)
    def get_law(law_id: str):
        path = law_path(law_id)
        content = path.read_text(encoding="utf-8")
        law = parse_law(content)
        return {
            **_summary(law_id, path),
            "content": content,
            "articles": [{"number": a.number, "heading": a.heading, "chars": len(a.text),
                          "preview": a.text[:160]} for a in law.articles],
        }

    @router.put("/laws/{law_id}", dependencies=auth)
    def save_law(law_id: str, edit: LawEdit):
        path = law_path(law_id)
        try:
            meta, body = parse_front_matter(edit.content)
            parse_law(edit.content)
        except ValueError as exc:
            raise HTTPException(422, f"Not saved: {exc}")
        if meta["id"] != law_id:
            raise HTTPException(422, "Not saved: the id in the front matter cannot be changed here.")
        old = path.read_text(encoding="utf-8")
        if edit.content != old:
            # Any change to the text needs a fresh review before it can be cited.
            meta["status"] = "draft"
            meta.pop("reviewed_by", None)
            meta.pop("reviewed_on", None)
            path.write_text(render(meta, body), encoding="utf-8")
            log.info("edited %s; status reset to draft", law_id)
        return _summary(law_id, path)

    @router.post("/laws/{law_id}/approve", dependencies=auth)
    def approve_law(law_id: str, body: Approval):
        path = law_path(law_id)
        try:
            meta = approve(path, body.reviewer)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        log.info("approved %s by %s", law_id, meta["reviewed_by"])
        return _summary(law_id, path)

    @router.post("/laws/{law_id}/repeal", dependencies=auth)
    def repeal_law(law_id: str):
        path = law_path(law_id)
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        meta["status"] = "repealed"
        path.write_text(render(meta, body), encoding="utf-8")
        log.info("repealed %s", law_id)
        return _summary(law_id, path)

    @router.delete("/laws/{law_id}", dependencies=auth)
    def delete_law(law_id: str):
        path = law_path(law_id)
        status = _summary(law_id, path).get("status")
        if status not in ("draft", "error"):
            raise HTTPException(409, "Only drafts can be deleted. Repeal an approved law instead.")
        path.unlink()
        log.info("deleted draft %s", law_id)
        return {"deleted": law_id}

    @router.get("/laws/{law_id}/download", dependencies=auth)
    def download_law(law_id: str):
        path = law_path(law_id)
        return FileResponse(path, media_type="text/markdown; charset=utf-8", filename=path.name)

    @router.post("/publish", dependencies=auth)
    async def publish():
        """Load the corpus folder into the search index (approved laws become searchable)."""
        advisor = get_advisor()

        def run():
            results = advisor.store.ingest_dir(settings().corpus_dir, prune=True)
            embedded, warning = 0, ""
            if advisor.embedder is not None:
                from .embeddings import embed_corpus

                try:
                    embedded = embed_corpus(advisor.store, advisor.embedder, advisor.store.all_articles())
                except Exception as exc:  # keyword search still works
                    warning = f"Semantic search not updated ({exc.__class__.__name__}); keyword search is live."
                    log.warning("embedding during publish failed", exc_info=True)
            advisor.reload_index()
            return results, embedded, warning

        try:
            results, embedded, warning = await run_in_threadpool(run)
        except ValueError as exc:
            raise HTTPException(422, f"Not published: {exc}")
        return {"laws_loaded": len(results), "articles_searchable": len(advisor.index),
                "newly_embedded": embedded, "warning": warning}

    return router
