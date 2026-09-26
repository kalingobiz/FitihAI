# Module 12 — Testing and Evaluation

## 1. Purpose
Prove two different things:
1. **The software works** (automated tests: fast, no API keys, run on every change).
2. **The legal output is correct and safe** (evaluation: lawyer-graded, run before
   launch and after every model, prompt or corpus change).

For a legal-information service, the second matters most. Fitih AI should not go
public until the evaluation targets below are met.

## 2. Scope
**In scope:** the automated test suite, test fixtures and fakes, the evaluation
datasets, metrics, targets, and the process.
**Out of scope:** load testing and security penetration testing (to plan before scale).

## 3. Files
| File | Role |
|---|---|
| `tests/conftest.py` | `FakeModel` (deterministic AI stand-in), `store` and `advisor` fixtures |
| `tests/test_core.py` | Corpus, retrieval, calendar, pipeline, quota and HTTP API tests |
| `tests/test_gemini_rag.py` | Gemini provider (fake client), embeddings, hybrid retrieval, provider switch |
| `tests/fixtures/*.md` | Two **fictional** laws (English labour, Amharic land lease) |
| `pytest.ini` | Test paths |
| `eval/` (to create) | Evaluation datasets and scoring scripts |

## 4. Interfaces
```bash
pytest            # all tests (about 1 second)
pytest -k gemini  # a subset
```

**Automated test coverage (28 tests)**
| Area | Tests |
|---|---|
| Corpus (01) | Ge'ez numerals; English and Amharic headings; front-matter validation; ingest counts |
| Search (02) | Homophone folding; BM25 ranking in English and Amharic; rank fusion; cosine index; embedding cache; cross-language semantic retrieval; fallback when embeddings fail |
| Providers (03) | Gemini request shape and schema; JSON fallback; safety block → refusal; history roles; OCR type check; provider switch |
| Q&A (04) | Invented citations removed; session history; "not found" when no valid citation |
| Documents (05) | OCR call; clause sorting; clause citation filtering; E.C. deadline; quota |
| Calendar (06) | New Year dates; Pagume leap rule |
| Languages (07) | Disclaimer exists for every language; correct language per response |
| API (09) | Ask; analyse text; bad file type; health; index page |

The fakes let tests check *what the pipeline does with* model output (for example,
that it removes invented citations) without paying for API calls or depending on
model behaviour.

## 5. Design and flow — evaluation

### Datasets (to build in Phase 1, with the legal lead)
| Set | Size | Content |
|---|---|---|
| **Q&A gold set** | 300 | 6 domains (labour, land, family, commercial, criminal procedure, tax) × 4 languages × realistic questions from interviews and legal-aid intake, each with the correct article(s) and a model answer written by a lawyer |
| **Out-of-corpus set** | 50 | Questions the library cannot answer, where the correct behaviour is "not in library" |
| **Document set** | 100 | Real, anonymised documents (leases, contracts, summonses, notices), annotated by lawyers: clause severities, deadlines, document type |
| **OCR set** | 100 | 50 printed + 50 handwritten Ethiopic documents with exact transcriptions |

### Metrics and launch targets
| Metric | How it is measured | Target |
|---|---|---|
| Retrieval recall@8 | Correct article among the 8 retrieved (automatic) | ≥ 90% |
| Citation precision | Lawyer: does each cited article support the statement? | ≥ 95% |
| Answer correctness and safety | Lawyer grade: correct & safe / minor issue / wrong or harmful | ≥ 85% correct & safe, **0 harmful** |
| Refusal to invent | Out-of-corpus set answered "not in library" | ≥ 98% |
| 🔴 flag precision / recall | Against lawyer annotations | ≥ 85% / ≥ 80% |
| Deadline extraction | Exact date and calendar match | ≥ 95% |
| OCR character error rate | Per provider (Gemini vs Claude) | Pick the best; aim for < 5% on printed text |
| Language quality | Native-speaker fluency rating 1–5, per language | ≥ 4.0 (below that, the language stays "beta") |

### Process
1. Run the evaluation with automatic metrics (recall, deadlines, CER).
2. Lawyers grade a sample (all harmful-risk categories, plus a random 30%).
3. Record results per model, prompt version and corpus version in `eval/results/`.
4. **Gate:** do not deploy a change that lowers citation precision, raises harmful
   answers above zero, or lowers refusal-to-invent.
5. Compare providers (Gemini free/paid vs Claude) on the same sets before choosing
   the production default.

## 6. Configuration
Tests need no configuration or keys. Evaluation runs use the normal settings
(module 11) with a paid API tier, because datasets may contain real (anonymised)
documents.

## 7. Data, privacy and security
- Test fixtures are fictional and clearly labelled "NOT real law".
- Evaluation documents must be anonymised (names, ID numbers, addresses removed)
  and collected with consent from legal-aid partners.
- **Never run evaluation documents through a free AI tier.**

## 8. Error handling
Tests fail loudly with pytest output. Evaluation scripts should record errors
(provider failures, refusals) as their own category, not silently skip them.

## 9. Testing
This module *is* the testing strategy. The suite currently passes: 28 tests in
about 1 second.

## 10. Limitations and next steps
- **No live-API test has been run yet.** First step: one question and one document
  with a real Gemini key.
- Add unit tests for the Telegram formatting (`format_answer`, `format_analysis`, `_chunks`).
- Add a small set of browser tests (Playwright) for the web client.
- Build the `eval/` datasets and scoring scripts. This is the main Phase 1
  deliverable, together with the corpus.
- Add CI to run tests on every push.
