"""Semantic search for RAG: Gemini embeddings + an in-memory vector index.

Embeddings let an Amharic or Afaan Oromo question match an English article
(and the other way round). Keyword search cannot do that. Article vectors are
cached in SQLite by content hash, so re-ingesting unchanged laws costs nothing.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Protocol, Sequence

import numpy as np

from .config import Settings
from .corpus.store import ArticleRecord

log = logging.getLogger("fitihai.embeddings")

BATCH_SIZE = 100
MAX_EMBED_CHARS = 8000


class Embedder(Protocol):
    model: str

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


def article_text(a: ArticleRecord) -> str:
    return f"{a.law_title}, Article {a.number}. {a.heading}\n{a.text}"[:MAX_EMBED_CHARS]


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class GeminiEmbedder:
    def __init__(self, settings: Settings, client=None):
        from google import genai
        from google.genai import types

        from .llm_gemini import RETRY

        self._types = types
        self.model = settings.embedding_model
        self.dim = settings.embedding_dim
        self._genai, self._retry = genai, RETRY
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = self._genai.Client(http_options=self._types.HttpOptions(retry_options=self._retry))
        return self._client

    def _embed(self, texts: Sequence[str], task_type: str) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), BATCH_SIZE):
            result = self.client.models.embed_content(
                model=self.model,
                contents=list(texts[i : i + BATCH_SIZE]),
                config=self._types.EmbedContentConfig(task_type=task_type, output_dimensionality=self.dim),
            )
            out.extend(list(e.values) for e in result.embeddings)
        return out

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text[:MAX_EMBED_CHARS]], "RETRIEVAL_QUERY")[0]


def build_embedder(settings: Settings) -> Embedder | None:
    if settings.embeddings == "gemini":
        return GeminiEmbedder(settings)
    if settings.embeddings in ("", "none", "off"):
        return None
    raise ValueError(f"unknown FITIH_EMBEDDINGS: {settings.embeddings!r} (use 'gemini' or 'none')")


class VectorIndex:
    """Cosine-similarity search over normalised article vectors."""

    def __init__(self, ids: list[str], vectors: list[list[float]]):
        self.ids = ids
        if ids:
            m = np.asarray(vectors, dtype=np.float32)
            norms = np.linalg.norm(m, axis=1, keepdims=True)
            self.matrix = m / np.where(norms == 0, 1, norms)
        else:
            self.matrix = np.zeros((0, 1), dtype=np.float32)

    def __len__(self) -> int:
        return len(self.ids)

    def search(self, query_vector: Sequence[float], top_k: int = 30) -> list[tuple[str, float]]:
        if not self.ids:
            return []
        q = np.asarray(query_vector, dtype=np.float32)
        q = q / (np.linalg.norm(q) or 1)
        scores = self.matrix @ q
        order = np.argsort(-scores)[:top_k]
        return [(self.ids[i], float(scores[i])) for i in order]


def embed_corpus(store, embedder: Embedder, articles: list[ArticleRecord]) -> int:
    """Embed articles that have no cached vector yet. Returns how many were embedded."""
    texts = {a.id: article_text(a) for a in articles}
    cached = store.load_embeddings(embedder.model)
    missing = [(aid, t) for aid, t in texts.items() if text_hash(t) not in cached]
    if not missing:
        return 0
    vectors = embedder.embed_documents([t for _, t in missing])
    store.save_embeddings(embedder.model, {text_hash(t): v for (_, t), v in zip(missing, vectors)})
    return len(missing)


def load_vector_index(store, embedder: Embedder, articles: list[ArticleRecord]) -> VectorIndex:
    cached = store.load_embeddings(embedder.model)
    ids, vecs = [], []
    for a in articles:
        v = cached.get(text_hash(article_text(a)))
        if v is not None:
            ids.append(a.id)
            vecs.append(v)
    if len(ids) < len(articles):
        log.warning("%d of %d articles have no embedding; run `python -m fitihai.cli embed`",
                    len(articles) - len(ids), len(articles))
    return VectorIndex(ids, vecs)
