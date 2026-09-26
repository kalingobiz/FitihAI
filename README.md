# ፍትህ AI — Fitih AI

**Ethiopian law, explained in the language you speak, grounded in the article that applies.**
Amharic · Afaan Oromo · Tigrinya · English, on Telegram and the web.

| For citizens | For your team |
|---|---|
| 📄 **Document analysis:** photo, scan or PDF → summary, 🔴🟡🟢 clause risk flags, deadlines converted from the Ethiopian calendar *and* Ethiopian time, questions to ask a lawyer | 🗂 **Admin console** (`/admin`): upload gazette PDFs, review and correct the text, approve, publish. No developer needed |
| 💬 **Legal Q&A:** answers that cite the exact article, with follow-up questions | 📊 **Evaluation tool:** measures accuracy against lawyer-written test sets and produces a grading sheet |
| 🔒 **Privacy:** consent notice, privacy page, nothing stored, sessions expire | 🐳 **One-command deployment:** `docker compose up -d` |

📑 Docs: [Module documentation](docs/modules/README.md) · [Revised proposal](docs/PROPOSAL_v2.md) · [Proposal review](docs/PROPOSAL_REVIEW.md) · [Law library guide](corpus/laws/README.md) · [Evaluation guide](eval/README.md)

## Go live in five steps

```bash
# 1. Configure
cp .env.example .env
#    GEMINI_API_KEY      from aistudio.google.com (enable billing before real users)
#    FITIH_ADMIN_TOKEN   python -c "import secrets; print(secrets.token_urlsafe(32))"
#    FITIH_USAGE_SALT    another random secret
#    TELEGRAM_BOT_TOKEN  from @BotFather (for the Telegram bot)

# 2. Start (web app + admin console on http://localhost:8000)
docker compose up -d
docker compose --profile telegram up -d        # also start the Telegram bot

# 3. Load the law: open http://localhost:8000/admin, sign in with FITIH_ADMIN_TOKEN, then
#    Import (gazette PDF) → Review → Approve (licensed lawyer) → Publish changes

# 4. Check accuracy (see eval/README.md)
docker compose exec web python -m fitihai.cli eval eval/datasets/qa.jsonl

# 5. Open to the public once the launch checklist below is complete
```

> **The law library starts empty.** Fitih AI only cites law that your team has
> imported from the official gazette and a lawyer has approved. Until then it
> answers that its library does not yet contain the relevant law. It never
> invents law.

### Without Docker
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python -m fitihai.cli ingest --embed
uvicorn fitihai.api:app                 # web + admin: http://localhost:8000
python -m fitihai.telegram_bot          # second terminal
pytest                                  # tests: no API keys needed
```

## Loading laws

| In the browser (`/admin`) | On the command line |
|---|---|
| **Import**: upload the gazette PDF, choose the language | `python -m fitihai.cli import gazette.pdf --id labour-1156-2019-en --title "Labour Proclamation" --domain labor --language en` |
| **Review**: numbering checks, article list, editable text | edit `corpus/laws/<id>.md` |
| **Approve**: reviewer name + confirmation | `python -m fitihai.cli approve corpus/laws/<id>.md --by "Name"` |
| **Publish changes** | `python -m fitihai.cli ingest --embed` |

Safety rules are enforced by the server, not just the page:
- imports start as **draft** and are never searched or cited;
- any edit puts a law back to draft;
- approved laws can't be deleted, only repealed.

The web app and the Telegram bot pick up published changes within 15 seconds.
Law files live in `corpus/laws/`. Commit them to git as your record of what was published.

## AI providers

| | **Gemini (default)** | Claude (optional) |
|---|---|---|
| Switch | `FITIH_LLM_PROVIDER=gemini` | `FITIH_LLM_PROVIDER=claude` |
| Router | `gemini-2.5-flash-lite` | `claude-haiku-4-5` |
| Answers / analysis / OCR | `gemini-2.5-flash` | `claude-sonnet-5` |
| Free tier | Yes, rate-limited | No |

Semantic search uses Gemini embeddings (`gemini-embedding-001`) when `FITIH_EMBEDDINGS=gemini`,
whichever provider answers. All model names are configurable in `.env`.

> ⚠️ **Free-tier privacy:** on the Gemini free tier, Google may use prompts and responses
> to improve its products. **Enable billing before real users send documents or questions.**

## How it works

```
question / document
   ├─ OCR (Gemini Flash / Claude vision)                                  [documents only]
   ├─ Router: domain, jurisdiction, urgency, search queries in English AND Amharic
   ├─ Hybrid retrieval over approved articles:
   │     keyword (BM25, Ethiopic spelling normalisation) + semantic (Gemini embeddings)
   │     merged by reciprocal rank fusion; keyword-only if embeddings fail
   ├─ Reasoning: structured JSON output that cites article ids
   └─ Post-processing (code, not AI): drop citations that weren't retrieved,
        convert E.C. dates and Ethiopian time, sort clauses by severity, add the disclaimer
```

| Path | What |
|---|---|
| `fitihai/pipeline.py` | The two flows (`Advisor.ask`, `Advisor.analyze_document`), auto-reload |
| `fitihai/admin.py` | Admin console API (import, review, approve, repeal, publish) |
| `fitihai/llm_gemini.py`, `fitihai/llm.py` | Gemini and Claude providers behind one interface |
| `fitihai/embeddings.py`, `fitihai/retrieval.py` | Semantic and keyword search, rank fusion |
| `fitihai/corpus/` | Law file parser, gazette importer, SQLite store |
| `fitihai/ethiopian_calendar.py` | E.C. ↔ Gregorian dates, Ethiopian time → 24-hour |
| `fitihai/evaluation.py` | Evaluation metrics, report and lawyer grading sheet |
| `fitihai/i18n.py` | Languages, disclaimers, consent text, UI strings |
| `fitihai/api.py`, `fitihai/ratelimit.py` | Web API, pages, rate limiting |
| `fitihai/telegram_bot.py` | Telegram bot (`/start`, `/lang`, `/new`, `/privacy`, text, photos, PDFs) |
| `web/` | Public app, admin console, privacy page (no build step) |

## Launch checklist

Everything below is outside the code. Each item needs a person or an account.

- [ ] **Law:** Layer-1 federal laws imported from the official gazette and approved by a licensed lawyer (at minimum Labour 1156/2019, Civil Code, Civil Procedure Code, Urban Land Lease 721/2011, Revised Family Code 213/2000).
- [ ] **Accuracy:** evaluation sets built with lawyers; launch targets met; zero harmful answers (`eval/README.md`).
- [ ] **Languages:** Amharic, Afaan Oromo and Tigrinya texts (disclaimer, consent, privacy page, UI) reviewed by native speakers.
- [ ] **Legal:** privacy page and disclaimer reviewed by counsel; contact address added to `web/privacy.html`; bar or Attorney General informed of the "legal information, not advice" positioning.
- [ ] **AI account:** Gemini billing enabled (paid tier) and a spending alert set.
- [ ] **Secrets:** `FITIH_ADMIN_TOKEN` and `FITIH_USAGE_SALT` set to long random values; HTTPS in front of the app; `FITIH_TRUST_PROXY=1` behind a proxy.
- [ ] **Smoke test:** one real question and one real document on the deployed app and on Telegram.

## API

```bash
curl -X POST localhost:8000/api/ask -H 'Content-Type: application/json' \
  -d '{"question": "አሠሪዬ ያለ ማስጠንቀቂያ አሰናበተኝ። መብቴ ምንድን ነው?", "language": "am"}'
curl -X POST localhost:8000/api/analyze -F file=@lease.jpg -F language=om
```
Interactive API reference: `/docs`.
