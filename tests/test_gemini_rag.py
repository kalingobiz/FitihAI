"""Tests for the Gemini provider and hybrid (keyword + semantic) retrieval. No network calls."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from fitihai.config import settings
from fitihai.embeddings import VectorIndex, embed_corpus, load_vector_index
from fitihai.llm import ClaudeLegalModel, ModelRefusal, build_model
from fitihai.llm_gemini import GeminiLegalModel, to_contents
from fitihai.pipeline import Advisor
from fitihai.retrieval import reciprocal_rank_fusion
from fitihai.schemas import Route

# Concept dimensions shared across languages: a toy "multilingual" embedding.
CONCEPTS = {
    "severance": 0, "የስንብት": 0, "compensation": 0,
    "lease": 1, "ሊዝ": 1, "የሊዝ": 1,
    "leave": 2, "ፈቃድ": 2,
    "notice": 3, "ማስጠንቀቂያ": 3,
}


class FakeEmbedder:
    model = "fake-embed"

    def __init__(self):
        self.document_calls = 0
        self.query_calls = 0

    def _vec(self, text):
        v = [0.0] * (len(CONCEPTS) + 1)
        for word in text.lower().replace(".", " ").replace(",", " ").split():
            if word in CONCEPTS:
                v[CONCEPTS[word]] += 1
        v[-1] = 0.01
        return v

    def embed_documents(self, texts):
        self.document_calls += 1
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        self.query_calls += 1
        return self._vec(text)


def test_rrf_prefers_items_ranked_by_both():
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["d", "b", "e"]])
    assert fused[0][0] == "b"
    assert {i for i, _ in fused} == {"a", "b", "c", "d", "e"}


def test_vector_index_cosine():
    idx = VectorIndex(["x", "y"], [[1, 0], [0, 3]])
    assert idx.search([0, 1], top_k=1)[0][0] == "y"
    assert VectorIndex([], []).search([1, 0]) == []


def test_embeddings_are_cached_by_text(store):
    emb = FakeEmbedder()
    articles = store.all_articles()
    assert embed_corpus(store, emb, articles) == len(articles)
    assert embed_corpus(store, emb, articles) == 0  # nothing re-embedded
    assert emb.document_calls == 1
    assert len(load_vector_index(store, emb, articles)) == len(articles)


def test_semantic_search_bridges_languages(store, fake_model, tmp_path):
    emb = FakeEmbedder()
    embed_corpus(store, emb, store.all_articles())
    adv = Advisor(replace(settings, top_k=3), store, fake_model, emb)
    # An Amharic-only query has no keyword overlap with the English labour article...
    assert not adv.index.search(["የስንብት"], top_k=3) or \
        adv.index.search(["የስንብት"], top_k=3)[0].article.id != "test-labour:3"
    # ...but hybrid retrieval finds it through the embedding.
    got = adv._retrieve(["የስንብት"], "labor", "federal", "የስንብት")
    assert got[0].id == "test-labour:3"
    assert emb.query_calls == 1


def test_semantic_failure_falls_back_to_keywords(store, fake_model):
    emb = FakeEmbedder()
    embed_corpus(store, emb, store.all_articles())

    def boom(text):
        raise RuntimeError("429 rate limited")

    emb.embed_query = boom
    adv = Advisor(settings, store, fake_model, emb)
    got = adv._retrieve(["severance pay"], "labor", "federal", "severance pay")
    assert got[0].id == "test-labour:3"


# ---- Gemini provider with a fake client ------------------------------------------
class FakeGeminiModels:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def _response(parsed=None, text="", finish="STOP", block=None):
    return SimpleNamespace(
        parsed=parsed, text=text,
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=finish))],
        prompt_feedback=SimpleNamespace(block_reason=block) if block else None,
    )


ROUTE = Route(is_legal_question=True, domain="land", jurisdiction="dire_dawa",
              search_queries_en=["lease"], search_queries_am=["ሊዝ"], urgent=False)


def test_gemini_route_request_shape():
    models = FakeGeminiModels(_response(parsed=ROUTE))
    m = GeminiLegalModel(settings, client=SimpleNamespace(models=models))
    assert m.route("my lease", [{"role": "user", "content": "hi"}]) == ROUTE
    call = models.calls[0]
    assert call["model"] == settings.gemini_fast_model
    assert call["config"].response_mime_type == "application/json"
    assert call["config"].response_schema is Route


def test_gemini_parses_json_text_when_parsed_missing():
    models = FakeGeminiModels(_response(parsed=None, text=ROUTE.model_dump_json()))
    m = GeminiLegalModel(settings, client=SimpleNamespace(models=models))
    assert m.route("x", []) == ROUTE


def test_gemini_safety_block_raises_refusal():
    for resp in (_response(finish="SAFETY"), _response(block="OTHER")):
        m = GeminiLegalModel(settings, client=SimpleNamespace(models=FakeGeminiModels(resp)))
        with pytest.raises(ModelRefusal):
            m.route("x", [])


def test_gemini_history_roles():
    contents = to_contents([{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}], "next")
    assert [c.role for c in contents] == ["user", "model", "user"]


def test_gemini_transcribe_rejects_unknown_type():
    m = GeminiLegalModel(settings, client=SimpleNamespace(models=FakeGeminiModels(_response(text="x"))))
    with pytest.raises(ValueError):
        m.transcribe(b"x", "application/zip")


def test_build_model_selects_provider(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    assert isinstance(build_model(replace(settings, llm_provider="gemini")), GeminiLegalModel)
    assert isinstance(build_model(replace(settings, llm_provider="claude")), ClaudeLegalModel)
    with pytest.raises(ValueError):
        build_model(replace(settings, llm_provider="other"))
