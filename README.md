# ፍትህ AI — Fitih AI

**Ethiopian law, explained in the language you speak, grounded in the article that applies.**
Amharic · Afaan Oromo · Tigrinya · English — on Telegram and the web.

- 📄 **Document analysis:** send a photo, scan or PDF of a lease, contract, summons or
  notice. You get a summary, 🔴🟡🟢 clause risk flags, deadlines (Ethiopian ↔ Gregorian
  calendar), questions to ask a lawyer, and cited articles.
- 💬 **Legal Q&A:** ask about your rights, with follow-up questions in the same session.
  Answers cite specific proclamations and articles.
- ✅ **Safeguards:** citations are checked against the retrieved law text (invented
  ones are dropped), urgent cases are routed to first steps, and the disclaimer is
  appended by code on every response.
- 🔒 **Privacy:** documents and conversations are never written to disk. Sessions
  expire after 30 minutes.

📑 Docs: [Module documentation](docs/modules/README.md) · [Proposal review](docs/PROPOSAL_REVIEW.md) · [Revised proposal (v2)](docs/PROPOSAL_v2.md) · [Corpus format](corpus/laws/README.md)

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env              # add GEMINI_API_KEY (free at aistudio.google.com) and TELEGRAM_BOT_TOKEN

# 1. Add official law texts to corpus/laws/ (see corpus/laws/README.md), then:
python -m fitihai.cli ingest --embed     # --embed builds the semantic (RAG) index with Gemini

# 2. Web app + API  → http://localhost:8000
uvicorn fitihai.api:app --reload

# 3. Telegram bot (separate process)
python -m fitihai.telegram_bot

# Tests (no API key needed; they use fake models and a fictional law)
pytest
```

> The corpus ships **empty**. Fitih AI will only cite law you load into it. Until
> you add laws, it will answer that its library does not contain the relevant law.

## AI providers

| | **Gemini (default)** | Claude (optional) |
|---|---|---|
| Switch | `FITIH_LLM_PROVIDER=gemini` | `FITIH_LLM_PROVIDER=claude` |
| Router | `gemini-2.5-flash-lite` | `claude-haiku-4-5` |
| Answers / analysis | `gemini-2.5-flash` | `claude-sonnet-5` |
| OCR | `gemini-2.5-flash` | `claude-sonnet-5` |
| Free tier | Yes, rate-limited | No |

Embeddings for RAG always use Gemini (`gemini-embedding-001`) when `FITIH_EMBEDDINGS=gemini`,
whichever LLM provider you pick. Model names are configurable in `.env`.

> ⚠️ **Free-tier privacy:** on the Gemini API free tier, Google may use prompts and
> responses to improve its products. That is fine for development, and for the public law
> text in the corpus. **Enable billing (paid tier) before real users send personal
> documents or questions.** Check the current terms and limits in Google AI Studio.

## How it works

```
question / document
   │
   ├─ OCR (Gemini Flash / Claude vision)                                  [documents only]
   ├─ Router (fast model): domain, jurisdiction, urgency,
   │           search queries in English AND Amharic
   ├─ Hybrid retrieval (RAG) over the article-level corpus (SQLite):
   │     keyword  — BM25, Ethiopic homophone folding (ሀ/ሐ/ኀ, ሰ/ሠ, አ/ዐ, ጸ/ፀ) + syllable bigrams
   │     semantic — Gemini embeddings (cross-language: Amharic question ↔ English article)
   │     merged with reciprocal rank fusion; falls back to keyword-only if embeddings fail
   ├─ Reasoning (Gemini Flash / Claude Sonnet): structured JSON output, cites article IDs
   └─ Post-processing — drop citations not in the retrieved set, convert E.C. dates,
                        sort clauses by severity, append disclaimer
```

| Path | What |
|---|---|
| `fitihai/pipeline.py` | The two flows (`Advisor.ask`, `Advisor.analyze_document`) |
| `fitihai/llm_gemini.py` | Gemini provider (router, answer, analysis, OCR) |
| `fitihai/llm.py` | Provider interface, Claude provider, `build_model()` switch |
| `fitihai/embeddings.py` | Gemini embeddings, vector index, embedding cache |
| `fitihai/prompts.py` | System prompts |
| `fitihai/retrieval.py` | BM25 index, Ethiopic tokenisation, rank fusion |
| `fitihai/corpus/` | Law file parser (Ge'ez numerals) and SQLite store |
| `fitihai/ethiopian_calendar.py` | E.C. ↔ Gregorian conversion |
| `fitihai/i18n.py` | Languages, disclaimers, UI strings |
| `fitihai/api.py` | FastAPI: `/api/ask`, `/api/analyze`, `/api/laws`, `/api/health` |
| `fitihai/telegram_bot.py` | Telegram bot (`/start`, `/lang`, `/new`, text, photos, PDFs) |
| `web/` | No-build web client |

## API

```bash
curl -X POST localhost:8000/api/ask -H 'Content-Type: application/json' \
  -d '{"question": "አሠሪዬ ያለ ማስጠንቀቂያ አሰናበተኝ። መብቴ ምንድን ነው?", "language": "am"}'

curl -X POST localhost:8000/api/analyze -F file=@lease.jpg -F language=om
```

## Deploy

`Dockerfile` and `Procfile` (web + bot processes) are included for Railway/Render.
Mount or bake `corpus/laws/` into the image. The database is rebuilt from it on start.

## Before public launch (see the review)

1. Load the Layer-1 federal laws from official gazette text, with lawyer sign-off.
2. Build the lawyer-graded evaluation set and meet the targets in `docs/PROPOSAL_v2.md` §9.
3. Have native speakers review the Oromo and Tigrinya UI strings and disclaimers
   (`fitihai/i18n.py`, `web/app.js`).
4. Add an AI-processing consent notice (Personal Data Protection Proclamation).
