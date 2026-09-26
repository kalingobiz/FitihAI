from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from fitihai.config import settings
from fitihai.corpus.store import CorpusStore
from fitihai.pipeline import Advisor
from fitihai.schemas import Answer, Clause, Deadline, DocumentAnalysis, Route

FIXTURES = Path(__file__).parent / "fixtures"


class FakeModel:
    """Deterministic stand-in for Claude. Records what it was sent."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.cite = ["test-labour:3", "made-up:99"]  # one real, one hallucinated

    def route(self, message, history):
        self.calls.append(("route", message))
        return Route(
            is_legal_question=True, domain="labor", jurisdiction="federal",
            search_queries_en=["severance pay termination"], search_queries_am=["የስንብት ክፍያ"],
            urgent=False,
        )

    def answer(self, user_content, history):
        self.calls.append(("answer", user_content))
        return Answer(answer="You may be entitled to severance pay.", cited_article_ids=self.cite,
                      found_relevant_law=True, follow_up_suggestions=["How is it calculated?"])

    def analyze(self, user_content):
        self.calls.append(("analyze", user_content))
        return DocumentAnalysis(
            document_type="employment_contract", domain="labor", title="Employment contract",
            summary="A fixed-term contract.", parties=["Employer", "Worker"],
            clauses=[
                Clause(quote="no notice", explanation="ok", severity="standard", cited_article_ids=[]),
                Clause(quote="no severance", explanation="bad", severity="danger",
                       cited_article_ids=["test-labour:3", "ghost:1"]),
            ],
            deadlines=[Deadline(description="Sign by", date_as_written="መስከረም 16 2019", calendar="ethiopian",
                                year=2019, month=1, day=16, relative_days=0,
                                time_as_written="ከጠዋቱ 3 ሰዓት", clock="ethiopian", hour=3, minute=0,
                                period="day")],
            lawyer_questions=["Is this legal?"], legibility="good",
        )

    def transcribe(self, data, media_type):
        self.calls.append(("transcribe", media_type))
        return "EMPLOYMENT CONTRACT. The worker waives severance pay."


@pytest.fixture
def store(tmp_path):
    s = CorpusStore(tmp_path / "test.db")
    s.ingest_dir(FIXTURES)
    return s


@pytest.fixture
def fake_model():
    return FakeModel()


@pytest.fixture
def advisor(store, fake_model, tmp_path):
    return Advisor(replace(settings, db_path=tmp_path / "test.db", free_analyses_per_month=2), store, fake_model)
