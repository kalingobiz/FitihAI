"""Evaluation harness: measure answer quality against lawyer-written test sets.

Two dataset types (JSON Lines, one item per line):

Questions (``kind`` omitted or ``"qa"``)::

    {"id": "q1", "question": "...", "language": "am",
     "expected_articles": ["labour-1156-2019-en:39"], "in_corpus": true}

Documents (``"kind": "document"``)::

    {"id": "d1", "kind": "document", "language": "en", "file": "docs/lease1.jpg",   # or "text": "..."
     "expected_deadlines": [{"gregorian_date": "2026-10-01", "time_24h": "09:00"}],
     "expected_danger": ["waives severance"]}

Automatic metrics are computed here. Correctness and safety still need a lawyer:
``write_report`` also produces a CSV grading sheet for that.
"""

from __future__ import annotations

import csv
import json
import mimetypes
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .pipeline import Advisor


@dataclass
class ItemResult:
    id: str
    kind: str
    language: str
    input: str
    output: str = ""
    cited: list[str] = field(default_factory=list)
    retrieved: list[str] = field(default_factory=list)
    expected: list[str] = field(default_factory=list)
    in_corpus: bool = True
    found_relevant_law: bool | None = None
    retrieval_hit: bool | None = None
    citations_correct: int = 0
    deadlines_expected: int = 0
    deadlines_matched: int = 0
    danger_expected: int = 0
    danger_matched: int = 0
    error: str = ""


def load_dataset(path: Path) -> list[dict]:
    items = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name} line {n}: invalid JSON ({exc.msg})") from exc
        if "id" not in item:
            raise ValueError(f"{path.name} line {n}: every item needs an 'id'")
        item["_base"] = str(path.parent)
        items.append(item)
    return items


def _run_question(advisor: Advisor, item: dict) -> ItemResult:
    r = ItemResult(id=item["id"], kind="qa", language=item.get("language", "en"), input=item["question"],
                   expected=list(item.get("expected_articles", [])), in_corpus=bool(item.get("in_corpus", True)))
    response, articles = advisor.ask_traced(item["question"], language=r.language)
    r.output = response.answer
    r.cited = [c.id for c in response.citations]
    r.retrieved = [a.id for a in articles]
    r.found_relevant_law = response.found_relevant_law
    if r.in_corpus and r.expected:
        r.retrieval_hit = any(a in r.retrieved for a in r.expected)
        r.citations_correct = sum(1 for c in r.cited if c in r.expected)
    return r


def _run_document(advisor: Advisor, item: dict) -> ItemResult:
    if "text" in item:
        data, media_type, label = item["text"].encode("utf-8"), "text/plain", item["text"][:200]
    else:
        path = Path(item["_base"]) / item["file"]
        data = path.read_bytes()
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        label = item["file"]
    r = ItemResult(id=item["id"], kind="document", language=item.get("language", "en"), input=label)
    res = advisor.analyze_document(data, media_type, language=r.language)
    r.output = res.summary
    r.cited = [c.id for c in res.citations]

    expected_deadlines = item.get("expected_deadlines", [])
    r.deadlines_expected = len(expected_deadlines)
    for exp in expected_deadlines:
        if any(d.gregorian_date == exp.get("gregorian_date")
               and (not exp.get("time_24h") or d.time_24h == exp["time_24h"]) for d in res.deadlines):
            r.deadlines_matched += 1

    expected_danger = [q.lower() for q in item.get("expected_danger", [])]
    r.danger_expected = len(expected_danger)
    flagged = [c.quote.lower() for c in res.clauses if c.severity == "danger"]
    for q in expected_danger:
        if any(q in f or f in q for f in flagged if f):
            r.danger_matched += 1
    return r


def run(advisor: Advisor, items: list[dict]) -> list[ItemResult]:
    results = []
    for item in items:
        runner = _run_document if item.get("kind") == "document" else _run_question
        try:
            results.append(runner(advisor, item))
        except Exception as exc:  # record failures as their own category; never skip silently
            results.append(ItemResult(id=item["id"], kind=item.get("kind", "qa"),
                                      language=item.get("language", "en"),
                                      input=item.get("question") or item.get("file") or "",
                                      error=f"{exc.__class__.__name__}: {exc}"))
    return results


def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


def summarize(results: list[ItemResult]) -> dict:
    qa = [r for r in results if r.kind == "qa" and not r.error]
    in_corpus = [r for r in qa if r.in_corpus and r.expected]
    out_corpus = [r for r in qa if not r.in_corpus]
    docs = [r for r in results if r.kind == "document" and not r.error]
    cited_total = sum(len(r.cited) for r in in_corpus)
    return {
        "items": len(results),
        "errors": sum(1 for r in results if r.error),
        "retrieval_recall": _ratio(sum(1 for r in in_corpus if r.retrieval_hit), len(in_corpus)),
        "citation_precision": _ratio(sum(r.citations_correct for r in in_corpus), cited_total),
        "answered_with_expected_article": _ratio(sum(1 for r in in_corpus if r.citations_correct), len(in_corpus)),
        "refusal_to_invent": _ratio(sum(1 for r in out_corpus if r.found_relevant_law is False), len(out_corpus)),
        "deadline_accuracy": _ratio(sum(r.deadlines_matched for r in docs), sum(r.deadlines_expected for r in docs)),
        "danger_flag_recall": _ratio(sum(r.danger_matched for r in docs), sum(r.danger_expected for r in docs)),
    }


TARGETS = {
    "retrieval_recall": 0.90,
    "citation_precision": 0.95,
    "refusal_to_invent": 0.98,
    "deadline_accuracy": 0.95,
    "danger_flag_recall": 0.80,
}


def write_report(results: list[ItemResult], summary: dict, out_dir: Path, label: str = "") -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = out_dir / f"{stamp}{'-' + label if label else ''}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (run_dir / "results.jsonl").write_text(
        "\n".join(json.dumps(asdict(r), ensure_ascii=False) for r in results) + "\n", encoding="utf-8")

    lines = [f"# Evaluation run {stamp}", "", "| Metric | Value | Launch target |", "|---|---|---|"]
    for key, value in summary.items():
        target = TARGETS.get(key)
        shown = "n/a" if value is None else (f"{value:.1%}" if isinstance(value, float) else str(value))
        flag = "" if target is None or value is None else (" ✅" if value >= target else " ❌")
        lines.append(f"| {key} | {shown}{flag} | {'' if target is None else f'≥ {target:.0%}'} |")
    failures = [r for r in results if r.error]
    if failures:
        lines += ["", "## Errors", ""] + [f"- `{r.id}`: {r.error}" for r in failures]
    lines += ["", "Correctness and safety must be graded by a lawyer in `grading.csv`.", ""]
    (run_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")

    with open(run_dir / "grading.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "kind", "language", "input", "output", "cited", "expected",
                    "grade (correct/minor/wrong)", "harmful? (yes/no)", "notes"])
        for r in results:
            w.writerow([r.id, r.kind, r.language, r.input, r.error or r.output, " ".join(r.cited),
                        " ".join(r.expected), "", "", ""])
    return run_dir
