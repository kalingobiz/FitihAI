"""Tests for the product features: admin console, protection, privacy, time, reload, Telegram, evaluation.

All law text used here is FICTIONAL.
"""

from __future__ import annotations

import csv
import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES, FakeModel
from fitihai import pipeline as pipeline_mod
from fitihai.api import create_app
from fitihai.config import settings
from fitihai.corpus.store import CorpusStore
from fitihai.ethiopian_calendar import ethiopian_time_to_24h
from fitihai.evaluation import load_dataset, run, summarize, write_report
from fitihai.i18n import CONSENT, LANGUAGES
from fitihai.pipeline import Advisor, resolve_deadline
from fitihai.ratelimit import RateLimiter
from fitihai.schemas import AnalyzeResponse, AskResponse, Citation, Clause, Deadline, DeadlineOut
from fitihai.telegram_bot import TELEGRAM_LIMIT, _chunks, format_analysis, format_answer

ROOT = Path(__file__).resolve().parent.parent
TOKEN = "test-admin-token"

GAZETTE = """\
Federal Negarit Gazette No. 00
Article 1. Short Title
This fictional Proclamation may be cited as the Admin Test Proclamation.
Article 2. Overtime
Overtime work shall be paid at an increased rate agreed by the parties.
"""


def _deadline(**kw) -> Deadline:
    base = dict(description="Hearing", date_as_written="", calendar="unknown", year=0, month=0, day=0,
                relative_days=0, time_as_written="", clock="none", hour=-1, minute=0, period="unknown")
    return Deadline(**{**base, **kw})


# ---- Ethiopian time ----------------------------------------------------------------
@pytest.mark.parametrize("hour,minute,period,expected", [
    (1, 0, "day", "07:00"), (3, 0, "day", "09:00"), (6, 0, "day", "12:00"), (12, 0, "day", "18:00"),
    (1, 30, "night", "19:30"), (6, 0, "night", "00:00"), (11, 0, "night", "05:00"), (12, 0, "night", "06:00"),
])
def test_ethiopian_time(hour, minute, period, expected):
    assert ethiopian_time_to_24h(hour, minute, period) == expected


def test_ethiopian_time_rejects_bad_values():
    for args in ((0, 0, "day"), (13, 0, "day"), (3, 60, "day"), (3, 0, "evening")):
        with pytest.raises(ValueError):
            ethiopian_time_to_24h(*args)


def test_resolve_deadline_times():
    day = resolve_deadline(_deadline(clock="ethiopian", hour=3, period="day", time_as_written="ከጠዋቱ 3 ሰዓት"))
    assert day.time_24h == "09:00" and day.time_note is None
    unknown = resolve_deadline(_deadline(clock="ethiopian", hour=4, period="unknown"))
    assert unknown.time_24h == "10:00" and "assumed daytime" in unknown.time_note
    intl = resolve_deadline(_deadline(clock="international", hour=14, minute=30))
    assert intl.time_24h == "14:30"
    bad = resolve_deadline(_deadline(clock="ethiopian", hour=15, period="day"))  # OCR misread
    assert bad.time_24h is None
    none = resolve_deadline(_deadline())
    assert none.time_24h is None


# ---- rate limiting and quotas -----------------------------------------------------
def test_rate_limiter_window():
    rl = RateLimiter(2, window_seconds=60)
    assert rl.allow("a", now=0) and rl.allow("a", now=1)
    assert not rl.allow("a", now=2)
    assert rl.allow("b", now=2)            # other clients are unaffected
    assert rl.allow("a", now=61)           # window has moved on
    assert RateLimiter(0).allow("x")       # 0 = unlimited


def _client(advisor) -> TestClient:
    return TestClient(create_app(lambda: advisor))


def test_api_rate_limit(store, fake_model, tmp_path):
    adv = Advisor(replace(settings, db_path=tmp_path / "t.db", rate_limit_per_minute=2), store, fake_model)
    c = _client(adv)
    codes = [c.post("/api/ask", json={"question": "fired without notice"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_web_document_quota_per_client(store, fake_model, tmp_path):
    adv = Advisor(replace(settings, free_analyses_per_month=1, rate_limit_per_minute=0), store, fake_model)
    c = _client(adv)
    upload = {"file": ("c.txt", b"contract text", "text/plain")}
    assert c.post("/api/analyze", files=upload).status_code == 200
    # A new session does not reset the monthly limit: it is tied to the (hashed) client.
    assert c.post("/api/analyze", files=upload, data={"session_id": "new"}).status_code == 429


# ---- consent and privacy ------------------------------------------------------------
def test_meta_has_consent_in_every_language(advisor):
    body = _client(advisor).get("/api/meta").json()
    assert set(body["consent"]) == set(LANGUAGES) == set(CONSENT)
    assert "Google Gemini" in body["consent"]["en"] and "30 minutes" in body["consent"]["en"]
    assert body["provider"] == "Google Gemini"


def test_privacy_page_is_filled_in(advisor):
    html = _client(advisor).get("/privacy").text
    assert "{{" not in html and "Google Gemini" in html
    assert 'id="am"' in html and 'id="om"' in html and 'id="ti"' in html and 'id="en"' in html


def test_index_page_has_consent_banner(advisor):
    html = _client(advisor).get("/").text
    assert 'id="consent"' in html and 'href="/privacy"' in html


# ---- admin console ------------------------------------------------------------------
@pytest.fixture
def admin(tmp_path):
    corpus = tmp_path / "laws"
    corpus.mkdir()
    s = replace(settings, db_path=tmp_path / "admin.db", corpus_dir=corpus, admin_token=TOKEN,
                rate_limit_per_minute=0)
    adv = Advisor(s, CorpusStore(s.db_path), FakeModel())
    client = _client(adv)
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    return client, adv, corpus


def _import(client, law_id="admin-test-en", **extra):
    form = {"id": law_id, "title": "FICTIONAL Admin Test Proclamation", "domain": "labor", "language": "en",
            "proclamation": "0000/2000", **extra}
    return client.post("/api/admin/import", data=form, files={"file": ("gazette.txt", GAZETTE.encode(), "text/plain")})


def test_admin_disabled_without_token(advisor):
    assert _client(advisor).get("/api/admin/laws").status_code == 404


def test_admin_rejects_wrong_token(admin):
    client, _, _ = admin
    assert client.get("/api/admin/laws", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/api/admin/laws", headers={"Authorization": ""}).status_code == 401


def test_admin_full_workflow(admin):
    client, adv, corpus = admin
    r = _import(client)
    assert r.status_code == 200, r.text
    assert r.json() == {"id": "admin-test-en", "article_count": 2, "issues": [], "status": "draft"}
    assert _import(client).status_code == 409                       # no silent overwrite
    assert _import(client, overwrite="true").status_code == 200

    law = client.get("/api/admin/laws").json()["laws"][0]
    assert law["status"] == "draft" and law["published"] is False

    # Publishing a draft makes nothing searchable.
    assert client.post("/api/admin/publish").json()["articles_searchable"] == 0

    # Approve, then publish: now it is live.
    assert client.post("/api/admin/laws/admin-test-en/approve", json={"reviewer": "Test Lawyer"}).json()["status"] == "in_force"
    pub = client.post("/api/admin/publish").json()
    assert pub["articles_searchable"] == 2 and pub["laws_loaded"] == 1
    assert client.get("/api/health").json()["articles_indexed"] == 2
    assert [l["id"] for l in client.get("/api/laws").json()] == ["admin-test-en"]
    assert client.delete("/api/admin/laws/admin-test-en").status_code == 409   # approved laws are not deleted

    # Editing the text puts it back to draft and clears the approval.
    detail = client.get("/api/admin/laws/admin-test-en").json()
    assert [a["number"] for a in detail["articles"]] == ["1", "2"]
    edited = detail["content"].replace("increased rate", "increased rate of pay")
    saved = client.put("/api/admin/laws/admin-test-en", json={"content": edited}).json()
    assert saved["status"] == "draft" and saved["reviewed_by"] == ""
    assert client.post("/api/admin/publish").json()["articles_searchable"] == 0

    # Broken text is refused and the file is left unchanged.
    assert client.put("/api/admin/laws/admin-test-en", json={"content": "no front matter at all"}).status_code == 422
    other_id = edited.replace("id: admin-test-en", "id: something-else")
    assert client.put("/api/admin/laws/admin-test-en", json={"content": other_id}).status_code == 422

    # Repeal after re-approval; then only drafts can be deleted.
    client.post("/api/admin/laws/admin-test-en/approve", json={"reviewer": "Test Lawyer"})
    assert client.post("/api/admin/laws/admin-test-en/repeal").json()["status"] == "repealed"
    assert client.post("/api/admin/publish").json()["articles_searchable"] == 0
    assert client.get("/api/laws").json() == []

    download = client.get("/api/admin/laws/admin-test-en/download")
    assert download.status_code == 200 and "status: repealed" in download.text


def test_admin_delete_draft_and_prune(admin):
    client, adv, corpus = admin
    _import(client, law_id="to-delete")
    client.post("/api/admin/publish")
    assert [l["id"] for l in adv.store.list_laws()] == ["to-delete"]
    assert client.delete("/api/admin/laws/to-delete").json() == {"deleted": "to-delete"}
    client.post("/api/admin/publish")
    assert adv.store.list_laws() == []          # publish mirrors the folder
    assert not any(corpus.iterdir())


def test_admin_validates_input(admin):
    client, _, _ = admin
    assert _import(client, law_id="../../etc/passwd").status_code == 400
    assert _import(client, law_id="Bad Id").status_code == 400
    assert _import(client, domain="astrology").status_code == 400
    assert _import(client, language="fr").status_code == 400
    bad_type = client.post("/api/admin/import", data={"id": "x-law", "title": "t", "domain": "labor", "language": "en"},
                           files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert bad_type.status_code == 415
    no_articles = client.post("/api/admin/import", data={"id": "x-law", "title": "t", "domain": "labor", "language": "en"},
                              files={"file": ("x.txt", b"just some text without headings", "text/plain")})
    assert no_articles.status_code == 422
    assert client.get("/api/admin/laws/..%2F..%2Fsecret").status_code in (400, 404)
    assert client.get("/admin").status_code == 200


# ---- corpus version and auto-reload ---------------------------------------------------
def test_other_process_changes_are_picked_up(tmp_path, monkeypatch):
    corpus = tmp_path / "laws"
    shutil.copytree(FIXTURES, corpus)
    db = tmp_path / "shared.db"
    web_store = CorpusStore(db)
    bot = Advisor(replace(settings, db_path=db), CorpusStore(db), FakeModel())   # e.g. the Telegram process
    assert len(bot.index) == 0

    v1 = web_store.corpus_version()
    web_store.ingest_dir(corpus, prune=True)                                     # e.g. admin "Publish"
    assert web_store.corpus_version() != v1

    monkeypatch.setattr(pipeline_mod, "RELOAD_CHECK_SECONDS", 0)
    assert bot.refresh_if_changed() is True
    assert len(bot.index) == 7
    assert bot.refresh_if_changed() is False                                     # nothing new


# ---- Telegram formatting ---------------------------------------------------------------
def _ask_response(answer="Answer <b>bold?</b> & more") -> AskResponse:
    return AskResponse(session_id="s", language="en", domain="labor", answer=answer,
                       citations=[Citation(id="x:1", citation="Test Law, Art. 1", heading="", excerpt="", source="")],
                       found_relevant_law=True, follow_up_suggestions=[], urgent=False, disclaimer="Not legal advice.")


def test_telegram_answer_is_escaped():
    text = format_answer(_ask_response(), "en")
    assert "&lt;b&gt;bold?&lt;/b&gt; &amp; more" in text
    assert "• Test Law, Art. 1" in text and "<i>Not legal advice.</i>" in text


def test_telegram_analysis_formatting():
    d = DeadlineOut(**_deadline(date_as_written="መስከረም 16, 2019", calendar="ethiopian", year=2019, month=1, day=16,
                                time_as_written="ከጠዋቱ 3 ሰዓት", clock="ethiopian", hour=3, period="day").model_dump(),
                    gregorian_date="2026-09-26", time_24h="09:00")
    res = AnalyzeResponse(session_id="s", language="en", document_type="lease", domain="land", title="Lease",
                          summary="Summary", parties=[], deadlines=[d], lawyer_questions=["Is it fair?"],
                          clauses=[Clause(quote="pay <all>", explanation="bad", severity="danger", cited_article_ids=[])],
                          legibility="good", citations=[], disclaimer="Not legal advice.")
    text = format_analysis(res, "en")
    assert "🔴" in text and "pay &lt;all&gt;" in text
    assert "መስከረም 16, 2019, ከጠዋቱ 3 ሰዓት → 2026-09-26 09:00" in text
    assert "Is it fair?" in text


def test_telegram_chunks_respect_limit():
    text = "\n".join(f"line {i} " + "x" * 90 for i in range(200)) + "\n" + "y" * 9000
    parts = _chunks(text)
    assert all(len(p) <= TELEGRAM_LIMIT + 1 for p in parts)
    assert "".join(parts).replace("\n", "") == text.replace("\n", "")


# ---- evaluation ---------------------------------------------------------------------------
def test_evaluation_on_example_datasets(advisor, tmp_path):
    items = (load_dataset(ROOT / "eval/datasets/example_qa.jsonl")
             + load_dataset(ROOT / "eval/datasets/example_documents.jsonl"))
    assert [i["id"] for i in items] == ["ex-q1", "ex-q2", "ex-q3", "ex-d1"]
    results = run(advisor, items)
    summary = summarize(results)
    assert summary["items"] == 4 and summary["errors"] == 0
    assert summary["retrieval_recall"] == 1.0
    assert summary["citation_precision"] == 1.0          # the invented citation was dropped before scoring
    assert summary["refusal_to_invent"] == 0.0           # the fake model always claims to have found law
    assert summary["deadline_accuracy"] == 1.0           # 2026-09-26 09:00 from Ethiopian date and time
    assert summary["danger_flag_recall"] == 0.0          # fake flags "no severance", expected "waives severance"

    run_dir = write_report(results, summary, tmp_path, "test")
    assert "retrieval_recall | 100.0% ✅" in (run_dir / "report.md").read_text(encoding="utf-8")
    rows = list(csv.reader(open(run_dir / "grading.csv", encoding="utf-8-sig")))
    assert rows[0][7].startswith("grade") and len(rows) == 5
    assert json.loads((run_dir / "summary.json").read_text())["items"] == 4


def test_evaluation_records_errors(advisor, tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id": "missing-file", "kind": "document", "file": "nope.jpg"}\n', encoding="utf-8")
    results = run(advisor, load_dataset(bad))
    assert results[0].error.startswith("FileNotFoundError")
    assert summarize(results)["errors"] == 1
    bad.write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        load_dataset(bad)


# ---- runs before an AI key is configured ----------------------------------------------
def test_app_works_without_ai_key(tmp_path, monkeypatch):
    """Staff must be able to set up the law library before the AI key is configured."""
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    from fitihai.embeddings import build_embedder
    from fitihai.llm import build_model

    s = replace(settings, db_path=tmp_path / "nokey.db", corpus_dir=tmp_path, admin_token=TOKEN)
    adv = Advisor(s, CorpusStore(s.db_path), build_model(s), build_embedder(s))   # real providers, no key
    c = _client(adv)
    health = c.get("/api/health").json()
    assert health["status"] == "ok" and health["ai_key_configured"] is False
    assert c.get("/api/laws").status_code == 200
    assert c.get("/api/admin/laws", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200
    assert c.post("/api/ask", json={"question": "anything"}).status_code == 502   # clear error, no crash
