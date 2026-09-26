"""Structured-output schemas for Claude calls and API responses."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Domain = Literal[
    "labor", "land", "commercial", "family", "criminal", "tax",
    "civil_procedure", "administrative", "other",
]
Severity = Literal["danger", "attention", "standard"]
Calendar = Literal["ethiopian", "gregorian", "relative", "unknown"]
Clock = Literal["ethiopian", "international", "none"]
Period = Literal["day", "night", "unknown"]


# ---- model outputs ------------------------------------------------------------
class Route(BaseModel):
    """Router output: what is the user asking about, and how should we search?"""

    is_legal_question: bool
    domain: Domain
    jurisdiction: str = Field(description="'federal' or a region/city slug such as 'dire_dawa', 'oromia'; 'unknown' if unclear")
    search_queries_en: list[str] = Field(description="2-4 short English keyword queries for the law library")
    search_queries_am: list[str] = Field(description="2-4 short Amharic keyword queries for the law library")
    urgent: bool = Field(description="True if the user faces an imminent deadline, arrest, eviction, or violence")


class Answer(BaseModel):
    answer: str
    cited_article_ids: list[str]
    found_relevant_law: bool
    follow_up_suggestions: list[str]


class Clause(BaseModel):
    quote: str = Field(description="Short verbatim excerpt of the clause from the document")
    explanation: str
    severity: Severity
    cited_article_ids: list[str]


class Deadline(BaseModel):
    description: str
    date_as_written: str
    calendar: Calendar
    year: int = Field(description="0 if unknown")
    month: int = Field(description="0 if unknown")
    day: int = Field(description="0 if unknown")
    relative_days: int = Field(description="For 'within N days' windows; 0 otherwise")
    time_as_written: str = Field(description="Time of day exactly as written, e.g. 'ከጠዋቱ 3 ሰዓት'; empty if none")
    clock: Clock = Field(description="'ethiopian' (hours counted from 6 a.m./6 p.m.), 'international', or 'none'")
    hour: int = Field(description="Hour as written (1-12 for Ethiopian time, 0-23 for international); -1 if none")
    minute: int = Field(description="Minute as written; 0 if not given")
    period: Period = Field(description="For Ethiopian time: 'day' (ጠዋት/ቀን/ከሰዓት) or 'night' (ምሽት/ማታ/ሌሊት)")


class DocumentAnalysis(BaseModel):
    document_type: str = Field(description="e.g. lease, employment_contract, court_summons, eviction_notice, loan_agreement, land_certificate")
    domain: Domain
    title: str
    summary: str
    parties: list[str]
    clauses: list[Clause]
    deadlines: list[Deadline]
    lawyer_questions: list[str]
    legibility: Literal["good", "partial", "poor"]


# ---- API responses --------------------------------------------------------------
class Citation(BaseModel):
    id: str
    citation: str
    heading: str
    excerpt: str
    source: str


class DeadlineOut(Deadline):
    gregorian_date: str | None = None
    ethiopian_date: str | None = None
    time_24h: str | None = None
    time_note: str | None = None


class AskResponse(BaseModel):
    session_id: str
    language: str
    domain: str
    answer: str
    citations: list[Citation]
    found_relevant_law: bool
    follow_up_suggestions: list[str]
    urgent: bool
    disclaimer: str


class AnalyzeResponse(BaseModel):
    session_id: str
    language: str
    document_type: str
    domain: str
    title: str
    summary: str
    parties: list[str]
    clauses: list[Clause]
    deadlines: list[DeadlineOut]
    lawyer_questions: list[str]
    legibility: str
    citations: list[Citation]
    disclaimer: str
