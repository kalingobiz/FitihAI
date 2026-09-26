from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from fitihai.api import create_app
from fitihai.corpus.chunker import geez_to_int, parse_law, split_articles
from fitihai.ethiopian_calendar import ethiopian_to_gregorian, gregorian_to_ethiopian
from fitihai.i18n import DISCLAIMER, LANGUAGES
from fitihai.pipeline import QuotaExceeded
from fitihai.retrieval import BM25Index, fold_ethiopic, tokenize


# ---- corpus ------------------------------------------------------------------------
def test_geez_numerals():
    assert geez_to_int("፩") == 1
    assert geez_to_int("፲፪") == 12
    assert geez_to_int("፻፳፫") == 123
    assert geez_to_int("፪፻፶") == 250


def test_split_articles_english_and_amharic():
    arts = split_articles("Article 1. Title\nbody one\nArt. 2 - Second\nbody two\nአንቀጽ ፲፪. ሊዝ\nጽሑፍ")
    assert [(a.number, a.heading) for a in arts] == [("1", "Title"), ("2", "Second"), ("12", "ሊዝ")]
    assert arts[1].text == "body two"


def test_parse_law_requires_front_matter():
    with pytest.raises(ValueError):
        parse_law("Article 1. no header")
    with pytest.raises(ValueError):
        parse_law("---\nid: x\n---\nArticle 1. t\nb")  # missing title/domain/language


def test_ingest(store):
    laws = {law["id"]: law for law in store.list_laws()}
    assert laws["test-labour"]["article_count"] == 4
    assert laws["test-land-am"]["article_count"] == 3
    assert any(a.id == "test-land-am:12" for a in store.all_articles())


# ---- retrieval -------------------------------------------------------------------
def test_ethiopic_homophones_fold():
    assert fold_ethiopic("ሠራተኛ") == fold_ethiopic("ሰራተኛ")
    assert fold_ethiopic("ፀሐይ") == fold_ethiopic("ጸሀይ")
    assert "ሰራ" in tokenize("ሠራተኛ")  # bigrams emitted for Ethiopic


def test_bm25_finds_relevant_article(store):
    index = BM25Index(store.all_articles())
    top = index.search(["severance pay after termination"], top_k=1)[0]
    assert top.article.id == "test-labour:3"
    top_am = index.search(["የሊዝ ክፍያ"], top_k=1)[0]
    assert top_am.article.id == "test-land-am:12"


# ---- calendar ----------------------------------------------------------------------
def test_ethiopian_calendar():
    assert ethiopian_to_gregorian(2017, 1, 1) == date(2024, 9, 11)
    assert ethiopian_to_gregorian(2016, 1, 1) == date(2023, 9, 12)
    assert gregorian_to_ethiopian(date(2026, 9, 26)) == (2019, 1, 16)
    with pytest.raises(ValueError):
        ethiopian_to_gregorian(2016, 13, 6)  # 2016 E.C. is not a leap year


# ---- pipeline --------------------------------------------------------------------
def test_ask_filters_hallucinated_citations(advisor, fake_model):
    res = advisor.ask("I was fired without notice", language="am")
    assert [c.id for c in res.citations] == ["test-labour:3"]
    assert res.disclaimer == DISCLAIMER["am"]
    answer_prompt = next(c for kind, c in fake_model.calls if kind == "answer")
    assert 'id="test-labour:3"' in answer_prompt
    assert "Amharic" in answer_prompt


def test_ask_keeps_session_history(advisor):
    first = advisor.ask("question one", language="en")
    advisor.ask("follow up", session_id=first.session_id)
    session = advisor.sessions.get(first.session_id)
    assert [m["role"] for m in session.history] == ["user", "assistant", "user", "assistant"]
    assert session.language == "en"


def test_no_citations_means_not_found(advisor, fake_model):
    fake_model.cite = ["invented:1"]
    res = advisor.ask("anything", language="en")
    assert res.citations == [] and res.found_relevant_law is False


def test_analyze_document(advisor, fake_model):
    res = advisor.analyze_document(b"\x89PNG...", "image/png", language="ti", user_key="u1")
    assert ("transcribe", "image/png") in fake_model.calls
    assert [c.severity for c in res.clauses] == ["danger", "standard"]  # most severe first
    assert res.clauses[0].cited_article_ids == ["test-labour:3"]
    assert res.deadlines[0].gregorian_date == "2026-09-26"
    assert res.disclaimer == DISCLAIMER["ti"]
    analyze_prompt = next(c for kind, c in fake_model.calls if kind == "analyze")
    assert "<user_document>" in analyze_prompt and "waives severance" in analyze_prompt


def test_quota(advisor):
    for _ in range(2):
        advisor.analyze_document(b"text", "text/plain", user_key="same-user")
    with pytest.raises(QuotaExceeded):
        advisor.analyze_document(b"text", "text/plain", user_key="same-user")
    # counters store only salted hashes, never the raw id
    rows = advisor.store.conn.execute("SELECT user_hash FROM usage").fetchall()
    assert all("same-user" not in r[0] for r in rows)


def test_disclaimer_in_every_language():
    assert set(DISCLAIMER) == set(LANGUAGES)


# ---- HTTP API --------------------------------------------------------------------
@pytest.fixture
def client(advisor):
    return TestClient(create_app(lambda: advisor))


def test_api_ask(client):
    r = client.post("/api/ask", json={"question": "fired without notice", "language": "om"})
    assert r.status_code == 200
    body = r.json()
    assert body["language"] == "om" and body["citations"][0]["id"] == "test-labour:3"


def test_api_analyze_rejects_bad_type(client):
    r = client.post("/api/analyze", files={"file": ("x.exe", b"MZ", "application/x-msdownload")})
    assert r.status_code == 415


def test_api_analyze_text(client):
    r = client.post("/api/analyze", files={"file": ("c.txt", "contract".encode(), "text/plain")},
                    data={"language": "en"})
    assert r.status_code == 200, r.text
    assert r.json()["clauses"][0]["severity"] == "danger"


def test_api_health_and_index_page(client):
    assert client.get("/api/health").json()["articles_indexed"] == 7
    assert "ፍትህ AI" in client.get("/").text
