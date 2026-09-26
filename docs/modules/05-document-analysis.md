# Module 05 — Document Analysis ("What does this document mean?")

## 1. Purpose
Help a person understand a legal document they received or are asked to sign
(lease, employment contract, court summons, eviction notice, loan agreement, land
certificate) *before* they act. It highlights harmful clauses and deadlines and
gives them questions to ask a lawyer.

## 2. Scope
**In scope:** the `Advisor.analyze_document` flow: text extraction (OCR), routing,
retrieval, analysis, risk ordering, citation filtering, deadline conversion, quota
checks, and the response format.
**Out of scope:** calendar maths (module 06), provider details (03), upload
limits and rendering (09, 10).

## 3. Files
| File | Role |
|---|---|
| `fitihai/pipeline.py` | `Advisor.analyze_document`, `resolve_deadline` |
| `fitihai/prompts.py` | `ANALYZE_SYSTEM`, `OCR_SYSTEM` |
| `fitihai/schemas.py` | `DocumentAnalysis`, `Clause`, `Deadline`, `DeadlineOut`, `AnalyzeResponse` |

## 4. Interfaces
```python
Advisor.analyze_document(data: bytes, media_type: str, session_id=None, language=None,
                         user_key=None) -> AnalyzeResponse
```
HTTP: `POST /api/analyze` (multipart: `file`, `language`, `session_id`).
Accepted types: JPEG, PNG, WebP, GIF, PDF, plain text. Maximum 10 MB by default.

**`AnalyzeResponse` fields**
| Field | Meaning |
|---|---|
| `document_type`, `domain`, `title` | e.g. `eviction_notice`, `land` |
| `summary`, `parties[]` | Plain-language summary and who is involved |
| `clauses[]` | `{quote, explanation, severity: danger/attention/standard, cited_article_ids}`, sorted most severe first |
| `deadlines[]` | `{description, date_as_written, calendar, year, month, day, relative_days, gregorian_date, ethiopian_date}` |
| `lawyer_questions[]` | Questions to ask before signing or responding |
| `legibility` | `good` / `partial` / `poor`; the clients ask for a clearer photo if not good |
| `citations[]` | Verified citations, as in module 04 |
| `disclaimer` | Mandatory notice |

## 5. Design and flow
```
1. quota check (only if user_key given and a monthly limit is set)          → module 08
2. text = file is text/* ? decode : model.transcribe(bytes)                  → OCR, original script
3. text = first 60,000 characters
4. route = model.route("Legal document received…" + first 4,000 chars)
5. articles = retrieve(first 1,500 chars + router queries; semantic on first 2,000 chars)
6. prompt = <law_excerpts> + "write in <language>" + <user_document>text</user_document>
7. result = model.analyze(prompt)
8. keep only citations to retrieved articles; strip invalid IDs from each clause
9. sort clauses: danger → attention → standard
10. resolve deadlines to both calendars (module 06)
11. add a one-line summary to session history, so follow-up questions work
12. increment the usage counter; return response + disclaimer
```

**Risk levels (defined in the prompt)**
| Level | Meaning |
|---|---|
| 🔴 `danger` | Could cause serious legal or financial harm, or appears to fall below a legal minimum in the excerpts |
| 🟡 `attention` | Unusual, one-sided, ambiguous, or missing something the reader should ask about |
| 🟢 `standard` | Ordinary; no concern identified |

The model is told to focus on clauses that matter, not to list all boilerplate,
and to quote a short verbatim excerpt for each clause so the user can find it.

**Deadlines:** the model records the date *as written*, with the calendar and
numeric parts, and is told **not** to convert it. Code converts it
deterministically (module 06). A relative window ("within 15 days") is not turned
into a date, because the starting day (the day of receipt) is unknown.

## 6. Configuration
`FITIH_MAX_UPLOAD_MB` (10), `FITIH_FREE_ANALYSES_PER_MONTH` (0 = unlimited),
`MAX_DOCUMENT_CHARS` (60,000, constant), and the models in module 03.

## 7. Data, privacy and security
- File bytes are held in memory for the request only. They are **never written
  to disk or to the database**.
- The image or PDF and its text are sent to the AI provider, and the first 2,000
  characters to the embedding API.
- Only a one-line summary is kept in the in-memory session, and it expires after 30 minutes.
- Prompt injection: the document is wrapped in `<user_document>` and treated as data.

## 8. Error handling
| Situation | HTTP result |
|---|---|
| Wrong file type | 415 |
| File too large | 413 |
| Empty file | 400 |
| Monthly quota used | 429 (Telegram shows a localised message) |
| Provider refusal / safety block | 422 |
| Unsupported type reaches the provider | 400 |
| Provider failure | 502 |
| Implausible OCR date (e.g. month 14) | Left as written, not converted |

## 9. Testing
`tests/test_core.py`: `test_analyze_document` (OCR called, clauses sorted, invalid
citation removed, E.C. deadline converted, disclaimer language),
`test_quota`, `test_api_analyze_rejects_bad_type`, `test_api_analyze_text`.

## 10. Limitations and next steps
- Multi-page photos must currently be sent as one PDF. Telegram albums are
  processed one photo at a time.
- OCR quality on handwritten Ge'ez is unmeasured. Benchmark it (module 12).
- Clause "quote" text is not checked against the transcription. Add a fuzzy
  match to catch misquotes.
- Add document-type-specific checklists (e.g. what every lease must contain) to
  make 🟡 "missing clause" findings more consistent.
