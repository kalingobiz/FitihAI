# Evaluation

Automated tests prove the software works. This folder checks that **the legal
output is correct and safe**. Run it before launch, and again after any change to
the model, the prompts or the corpus.

```bash
python -m fitihai.cli eval eval/datasets/qa.jsonl eval/datasets/documents.jsonl --label gemini-flash
```

Each run writes `eval/results/<time>-<label>/`:

| File | What it is |
|---|---|
| `report.md` | Automatic metrics against the launch targets (✅ / ❌) |
| `grading.csv` | One row per item for lawyers: grade (correct / minor / wrong), harmful (yes / no), notes |
| `results.jsonl` | Full detail: retrieved and cited articles, outputs, errors |
| `summary.json` | The metrics, for comparing runs |

## Metrics and launch targets

| Metric | Meaning | Target |
|---|---|---|
| `retrieval_recall` | Correct article is among those retrieved | ≥ 90% |
| `citation_precision` | Cited articles are among the expected ones | ≥ 95% |
| `refusal_to_invent` | Out-of-library questions answered "not in library" | ≥ 98% |
| `deadline_accuracy` | Expected deadlines found with the right Gregorian date (and time) | ≥ 95% |
| `danger_flag_recall` | Clauses lawyers marked dangerous were flagged 🔴 | ≥ 80% |
| Lawyer grade (in `grading.csv`) | Correct & safe | ≥ 85%, and **zero harmful** |

## Building the datasets (with the legal lead)

**Questions** — `eval/datasets/qa.jsonl`, one JSON object per line:
```json
{"id": "lab-001", "language": "am", "question": "…", "expected_articles": ["labour-1156-2019-am:39"], "in_corpus": true}
```
- Aim for about 300: 6 domains × 4 languages, using real questions from legal-aid intake (anonymised).
- Add about 50 with `"in_corpus": false`. These are questions the library cannot answer, where the correct behaviour is to say so.
- `expected_articles` use the corpus ids shown in the admin console (`<law id>:<article>`).

**Documents** — `eval/datasets/documents.jsonl`:
```json
{"id": "doc-001", "kind": "document", "language": "am", "file": "docs/lease-001.jpg",
 "expected_deadlines": [{"gregorian_date": "2026-10-01", "time_24h": "09:00"}],
 "expected_danger": ["short verbatim phrase from the dangerous clause"]}
```
- About 100 real documents. **Remove names, ID numbers and addresses first**, and collect them with consent.
- Put files under `eval/datasets/docs/`, which is git-ignored. Never commit real documents.
- **Never run evaluation documents through a free AI tier.**

The `example_*.jsonl` files run against the fictional test laws and only show the format.
