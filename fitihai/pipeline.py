"""The two Fitih AI flows: legal Q&A and document analysis."""

from __future__ import annotations

import logging
import threading
from datetime import date, timedelta

from .config import Settings
from .corpus.store import ArticleRecord, CorpusStore
from .ethiopian_calendar import ethiopian_to_gregorian, format_ethiopian, gregorian_to_ethiopian
from .i18n import LANGUAGE_NAMES_EN, disclaimer
from .llm import LegalModel
from .prompts import format_excerpts, language_instruction
from .embeddings import Embedder, VectorIndex, load_vector_index
from .retrieval import BM25Index, reciprocal_rank_fusion
from .schemas import AnalyzeResponse, AskResponse, Citation, DeadlineOut, Deadline
from .sessions import Session, SessionStore

MAX_DOCUMENT_CHARS = 60_000
CANDIDATES = 30  # per retriever, before fusion

log = logging.getLogger("fitihai.pipeline")


class QuotaExceeded(Exception):
    pass


class Advisor:
    def __init__(self, settings: Settings, store: CorpusStore, model: LegalModel,
                 embedder: Embedder | None = None):
        self.s = settings
        self.store = store
        self.model = model
        self.embedder = embedder
        self.sessions = SessionStore(settings.session_ttl_minutes, settings.max_history_turns)
        self._index_lock = threading.Lock()
        self.reload_index()

    def reload_index(self) -> None:
        articles = self.store.all_articles()
        index = BM25Index(articles)
        vectors = load_vector_index(self.store, self.embedder, articles) if self.embedder else VectorIndex([], [])
        with self._index_lock:
            self.index = index
            self.vectors = vectors
            self._by_id = {a.id: a for a in articles}

    # ---- shared helpers -------------------------------------------------------------
    def _retrieve(self, queries: list[str], domain: str, jurisdiction: str,
                  semantic_text: str) -> list[ArticleRecord]:
        """Hybrid RAG retrieval: keyword (BM25) + semantic (embeddings), fused by rank."""
        juris = [] if jurisdiction in ("", "unknown", "federal") else [jurisdiction]
        keyword = [h.article.id for h in self.index.search(queries, top_k=CANDIDATES, domains=[domain],
                                                             jurisdictions=juris)]
        rankings = [keyword]
        if self.embedder and len(self.vectors):
            try:
                qv = self.embedder.embed_query(semantic_text)
                rankings.append([aid for aid, _ in self.vectors.search(qv, CANDIDATES)])
            except Exception:
                log.warning("semantic search unavailable; using keyword search only", exc_info=True)
        out = []
        for aid, _ in reciprocal_rank_fusion(rankings):
            a = self._by_id[aid]
            j = a.jurisdiction.lower()
            if juris and j != "federal" and j not in juris:
                continue
            out.append(a)
            if len(out) == self.s.top_k:
                break
        return out

    def _citations(self, ids: list[str], allowed: list[ArticleRecord]) -> list[Citation]:
        """Keep only citations that point at articles we actually showed the model."""
        allowed_ids = {a.id for a in allowed}
        out, seen = [], set()
        for art_id in ids:
            if art_id in allowed_ids and art_id not in seen:
                seen.add(art_id)
                a = self._by_id[art_id]
                excerpt = a.text if len(a.text) <= 400 else a.text[:400] + " …"
                out.append(Citation(id=a.id, citation=a.citation, heading=a.heading, excerpt=excerpt, source=a.source))
        return out

    def check_quota(self, user_key: str | None, kind: str) -> str | None:
        if not user_key or self.s.free_analyses_per_month <= 0:
            return None
        user_hash = CorpusStore.hash_user(user_key, self.s.usage_salt)
        if self.store.usage_count(user_hash, kind) >= self.s.free_analyses_per_month:
            raise QuotaExceeded(kind)
        return user_hash

    # ---- Q&A ---------------------------------------------------------------------
    def ask(self, question: str, session_id: str | None = None, language: str | None = None) -> AskResponse:
        session = self.sessions.get(session_id, language)
        lang_name = LANGUAGE_NAMES_EN[session.language]

        route = self.model.route(question, session.history)
        queries = [question, *route.search_queries_en, *route.search_queries_am]
        articles = (self._retrieve(queries, route.domain, route.jurisdiction, question)
                    if route.is_legal_question else [])

        user_content = (
            f"{format_excerpts(articles)}\n\n"
            f"{language_instruction(lang_name)}\n"
            f"Classified domain: {route.domain}. Urgent: {'yes' if route.urgent else 'no'}.\n\n"
            f"<question>\n{question}\n</question>"
        )
        result = self.model.answer(user_content, session.history)
        citations = self._citations(result.cited_article_ids, articles)
        self.sessions.append(session, question, result.answer)

        return AskResponse(
            session_id=session.id,
            language=session.language,
            domain=route.domain,
            answer=result.answer,
            citations=citations,
            found_relevant_law=result.found_relevant_law and bool(citations),
            follow_up_suggestions=result.follow_up_suggestions,
            urgent=route.urgent,
            disclaimer=disclaimer(session.language),
        )

    # ---- document analysis ---------------------------------------------------------
    def analyze_document(
        self,
        data: bytes,
        media_type: str,
        session_id: str | None = None,
        language: str | None = None,
        user_key: str | None = None,
    ) -> AnalyzeResponse:
        user_hash = self.check_quota(user_key, "analysis")
        session = self.sessions.get(session_id, language)
        lang_name = LANGUAGE_NAMES_EN[session.language]

        if media_type.startswith("text/"):
            text = data.decode("utf-8", errors="replace")
        else:
            text = self.model.transcribe(data, media_type)
        text = text[:MAX_DOCUMENT_CHARS]
        # `data` goes out of scope here; nothing about the document is stored.

        route = self.model.route(f"Legal document received by the user:\n{text[:4000]}", [])
        queries = [text[:1500], *route.search_queries_en, *route.search_queries_am]
        articles = self._retrieve(queries, route.domain, route.jurisdiction, text[:2000])

        user_content = (
            f"{format_excerpts(articles)}\n\n"
            f"{language_instruction(lang_name)}\n\n"
            f"<user_document>\n{text}\n</user_document>"
        )
        result = self.model.analyze(user_content)

        cited = [i for c in result.clauses for i in c.cited_article_ids]
        citations = self._citations(cited, articles)
        allowed = {c.id for c in citations}
        clauses = [c.model_copy(update={"cited_article_ids": [i for i in c.cited_article_ids if i in allowed]})
                   for c in result.clauses]
        order = {"danger": 0, "attention": 1, "standard": 2}
        clauses.sort(key=lambda c: order[c.severity])

        summary_for_history = f"[Document analysed: {result.title}] {result.summary}"
        self.sessions.append(session, "I uploaded a legal document for analysis.", summary_for_history)
        if user_hash:
            self.store.increment_usage(user_hash, "analysis")

        return AnalyzeResponse(
            session_id=session.id,
            language=session.language,
            document_type=result.document_type,
            domain=result.domain,
            title=result.title,
            summary=result.summary,
            parties=result.parties,
            clauses=clauses,
            deadlines=[resolve_deadline(d) for d in result.deadlines],
            lawyer_questions=result.lawyer_questions,
            legibility=result.legibility,
            citations=citations,
            disclaimer=disclaimer(session.language),
        )


def resolve_deadline(d: Deadline, today: date | None = None) -> DeadlineOut:
    """Convert a deadline to both calendars where the date is fully known."""
    out = DeadlineOut(**d.model_dump())
    try:
        if d.calendar == "ethiopian" and d.year and d.month and d.day:
            g = ethiopian_to_gregorian(d.year, d.month, d.day)
            out.gregorian_date = g.isoformat()
            out.ethiopian_date = format_ethiopian(d.year, d.month, d.day)
        elif d.calendar == "gregorian" and d.year and d.month and d.day:
            g = date(d.year, d.month, d.day)
            out.gregorian_date = g.isoformat()
            out.ethiopian_date = format_ethiopian(*gregorian_to_ethiopian(g))
        elif d.calendar == "relative" and d.relative_days and today:
            g = today + timedelta(days=d.relative_days)
            out.gregorian_date = g.isoformat()
            out.ethiopian_date = format_ethiopian(*gregorian_to_ethiopian(g))
    except ValueError:
        pass  # implausible date from OCR; leave as written
    return out
