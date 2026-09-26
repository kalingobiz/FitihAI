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

📑 Docs: [Proposal review](docs/PROPOSAL_REVIEW.md) · [Revised proposal (v2)](docs/PROPOSAL_v2.md) · [Corpus format](corpus/laws/README.md)

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env              # add ANTHROPIC_API_KEY (and TELEGRAM_BOT_TOKEN for the bot)

# 1. Add official law texts to corpus/laws/ (see corpus/laws/README.md), then:
python -m fitihai.cli ingest

# 2. Web app + API  → http://localhost:8000
uvicorn fitihai.api:app --reload

# 3. Telegram bot (separate process)
python -m fitihai.telegram_bot

# Tests (no API key needed; they use a fake model and a fictional law)
pytest
```

> The corpus ships **empty**. Fitih AI will only cite law you load into it. Until
> you add laws, it will answer that its library does not contain the relevant law.

## How it works

```
question / document
   │
   ├─ OCR (Claude vision, or Gemini via FITIH_OCR_PROVIDER=gemini)       [documents only]
   ├─ Router — Claude Haiku 4.5: domain, jurisdiction, urgency,
   │           search queries in English AND Amharic
   ├─ Retrieval — BM25 over article-level corpus (SQLite),
   │           Ethiopic homophone folding (ሀ/ሐ/ኀ, ሰ/ሠ, አ/ዐ, ጸ/ፀ) + syllable bigrams
   ├─ Reasoning — Claude Sonnet 5, structured JSON output, cites article IDs
   └─ Post-processing — drop citations not in the retrieved set, convert E.C. dates,
                        sort clauses by severity, append disclaimer
```

| Path | What |
|---|---|
| `fitihai/pipeline.py` | The two flows (`Advisor.ask`, `Advisor.analyze_document`) |
| `fitihai/llm.py` | Claude calls (router, answer, analysis, OCR); optional Gemini OCR |
| `fitihai/prompts.py` | System prompts |
| `fitihai/retrieval.py` | BM25 index + Ethiopic tokenisation |
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
