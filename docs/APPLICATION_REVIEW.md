# Fitih AI — Full Application Review (October 2026)

Scope: the whole repository at commit `6b306db` (`main`): backend (`fitihai/`), web
client (`web/`), Telegram bot, corpus tooling, tests, CI, deployment files and docs.
All 36 tests pass locally (`pytest -q`, Python 3.12). Findings marked
**(verified)** were reproduced with a script, not only read in the code.

The [proposal review](PROPOSAL_REVIEW.md) covered the business case. This document
covers the software.

---

## 1. Verdict

**A well-designed MVP. It is not yet safe to open to the public.**

The core design is right for a legal-information product: answers are grounded in
article-level law text, invented citations are removed by code, the disclaimer is
added by code, and nothing the user sends is written to disk. The code is small
(about 2,900 lines including tests), readable, and well documented.

What stands between this and a public launch is mostly **operational hardening**:
abuse and cost controls, a quota that cannot be bypassed, a corpus process that
cannot let unreviewed law through, and a deployment that works when the web app and
the bot run on different machines. There are also two parser bugs that can silently
corrupt the law library.

| Area | Rating | Comment |
|---|---|---|
| Architecture and design | ★★★★☆ | Clean pipeline, provider interface, hybrid RAG, privacy by design |
| Legal safety (grounding, citations, disclaimer) | ★★★★☆ | Strong. Gaps are in corpus quality control, not in the answer path |
| Correctness | ★★★☆☆ | Calendar is correct; article parser and Telegram chunking have bugs |
| Security and abuse resistance | ★★☆☆☆ | No rate limiting or auth; quota bypassable; client-chosen session IDs |
| Scalability and operations | ★★☆☆☆ | In-memory state, single process, ephemeral SQLite |
| Tests and CI | ★★★☆☆ | Good unit tests with fakes; no bot, chunking or answer-quality tests |
| Documentation | ★★★★★ | Module docs are thorough and honest about limitations |
| Frontend / UX | ★★★☆☆ | Simple, safe DOM rendering, four languages; small UX gaps |

---

## 2. What is done well

- **Grounding with enforcement in code.** `Advisor._citations` (`fitihai/pipeline.py`)
  keeps only article IDs that were actually given to the model. `found_relevant_law`
  is forced to false when no valid citation survives. The model cannot cite a law the
  library does not contain.
- **The disclaimer comes from code, not the model**, in all four languages, on every
  response (`i18n.disclaimer`). A test checks that every language has one.
- **Privacy by design.** Uploaded files are processed in memory and dropped. Sessions
  expire after 30 minutes. Usage counters store only salted hashes. The Gemini
  free-tier data-use risk is documented clearly in the README, `.env.example` and
  the provider module.
- **Retrieval suited to Ethiopic text.** BM25 with folding of Ethiopic homophones
  (ሀ/ሐ/ኀ, ሰ/ሠ, አ/ዐ, ጸ/ፀ) and syllable bigrams, router-generated queries in both
  English and Amharic, Gemini embeddings for cross-language search, and reciprocal
  rank fusion. It falls back to keyword search when embeddings fail. This is a good
  design for a small, multilingual corpus.
- **Ethiopian calendar conversion is correct (verified).** I round-tripped every day
  from 2000-01-01 to 2039-12-31 with no errors. Leap-year Pagume (ጳጉሜ 6, 2015 →
  2023-09-11) is handled.
- **Dates are not converted by the model.** The prompt asks the model to record the
  calendar and numbers, and code does the conversion. This is the right split.
- **Provider abstraction.** `LegalModel` is a Protocol, so tests use a deterministic
  fake and Gemini/Claude can be swapped with one variable.
- **Draft → review → approve workflow** for imported gazettes, with reviewer name and
  date recorded, and numbering-gap warnings to guide the reviewer.
- **Safe frontend rendering.** `web/app.js` builds every node with `textContent`;
  there is no `innerHTML`, so model output cannot inject script.
- **Clear error mapping** in the API: 415, 413, 429, 422 (refusal), 502 (provider down).
- **Documentation.** Twelve module documents with the same structure, each with a
  "limitations" section. Several findings below are already listed there as next steps.

---

## 3. Findings

Severity: **Critical** = fix before any public traffic. **High** = fix before launch.
**Medium** = fix soon after launch. **Low** = improvement.

### Critical

#### C1. No rate limiting or authentication on any endpoint
`/api/ask` and `/api/analyze` (`fitihai/api.py`) and every bot handler accept unlimited
anonymous requests. Each request makes 2–3 paid model calls. One script can use up
the Gemini quota (taking the service down for everyone) or create a large bill on
the paid tier. The docs list rate limiting as a "before public launch" item
(`docs/modules/09-web-app.md`), but nothing enforces it.

**Fix:** per-IP limits at the reverse proxy or in the app (e.g. `slowapi`), a per-chat
limit in the bot, a daily global spend ceiling, and a cap on request body size.

#### C2. The document quota can be bypassed on the web
`api.py:85` passes the client-supplied `session_id` as the quota key (`user_key`).
- With no `session_id` (the first upload from every browser), `check_quota` returns
  early and **no limit applies at all**.
- With a `session_id`, the user can start a new conversation to get a new key.

The quota therefore only works on Telegram, where the key is the Telegram user ID.
`.env.example` says "per Telegram user", but `/api/analyze` returns 429 as if the web
were limited too.

**Fix:** either state that the web is unlimited and rely on C1's rate limits, or key the
web quota on something the client does not control (a signed cookie issued by the
server, or a logged-in account).

### High

#### H1. Clients choose their own session IDs; Telegram session IDs are predictable
`SessionStore.get` (`fitihai/sessions.py:42`) creates a session with **whatever ID the
client sends**, and the bot uses `tg-<chat_id>` (`telegram_bot.py:35`). Today the
bot and web app run as separate processes with separate in-memory stores, so the web
cannot reach a Telegram session. But the docs plan to move sessions to Redis for
scaling. If that is done as written, anyone could POST
`{"session_id": "tg-<someone's chat id>"}` to `/api/ask`, have that user's
conversation (including document summaries) loaded as context, and ask the model to
repeat it. They could also `DELETE` it.

**Fix:** issue session IDs only from the server (ignore or reject unknown IDs from the
web), give the bot and the web separate key namespaces, and use a random
`token_urlsafe` for all web sessions.

#### H2. Article parser splits laws at cross-references **(verified)**
`split_articles` (`fitihai/corpus/chunker.py:110`) treats any line that starts with
"Article N" as a new article, unless the next character is lower-case. Two common
cases get through:

```
"Article 35(2) of this Proclamation ..."  → new article 35, heading "(2) of this Proclamation ..."
"አንቀጽ 35 መሠረት ሠራተኛው ..."               → new article 35, heading "መሠረት ሠራተኛው"
```

Amharic has no letter case, so the cross-reference check **never works for Amharic or
Tigrinya text**. PDF line wrapping often puts "Article N" at the start of a line. The
result is that article text is cut short and a fake article with a duplicate number
is created. `upsert_law` then gives it an ID like `law:35-2`, and the model can cite
it as real law.

`numbering_issues` reports these as "out of order" during import, which helps, but
hand-written corpus files never go through import.

**Fix:** require a heading separator (`.` `:` `-` or end of line) right after the number,
reject numbers followed by `(`, and for Ethiopic text require the line to be short or
to end the heading on the same line. Make `ingest` fail (or warn loudly) on numbering
issues. Add the two cases above as tests.

#### H3. Unreviewed law can reach users
The draft gate only applies to files made with `cli import`. In `CorpusStore.upsert_law`
(`fitihai/corpus/store.py`) a file with **no `status` line defaults to `in_force`**,
and nothing checks `reviewed_by`. Also, `approve` does not record a hash of the
reviewed text, so a file edited after approval stays "approved".

For a product whose main promise is "grounded in the article that applies", corpus
integrity is the most important safety property.

**Fix:** default `status` to `draft`. Refuse to ingest `in_force` laws without
`reviewed_by`. Store a `reviewed_sha256` of the body in `approve` and refuse to ingest
when it no longer matches.

#### H4. Deleted or renamed law files stay in the database
`ingest_dir` (`store.py:109`) only upserts. A law file that is removed (for example a
repealed proclamation deleted instead of marked `repealed`) stays `in_force` in SQLite
and is still cited. **Fix:** in `ingest_dir`, delete laws whose files are no longer
present, or mark them `missing`, and print what was removed.

#### H5. The deployment layout breaks on multi-machine platforms
- `Procfile` runs `web` and `bot` as separate processes. On Heroku-style platforms each
  process type runs on its own machine with its own disk. Only `web` runs `ingest`, so
  **the bot starts with an empty law library** and answers that it has no relevant law.
- `data/fitihai.db` is on the container disk. Every deploy or restart wipes the usage
  counters (the quota resets) and the embedding cache (every article is re-embedded,
  using quota).
- Every start runs `ingest --embed`. If the embedding API is slow or rate-limited, start-up
  is slow; on platforms with a boot timeout the app can fail to start.
- Sessions are in memory, so only one worker can be used (`uvicorn` with `--workers > 1`
  or two instances gives users "lost" conversations).
- The Docker image runs as root.

**Fix:** build the corpus database at image-build time (or on a shared volume) so both
processes use the same file; put usage counters in a persistent store; run the bot in
the same container as the web app, or give it its own `ingest` step; add a non-root
`USER` to the Dockerfile.

#### H6. Long documents fail completely on Gemini
`GeminiLegalModel._generate` raises `RuntimeError` on `MAX_TOKENS`
(`llm_gemini.py:85`), and `transcribe` uses 16,000 output tokens. Ethiopic script uses
many tokens per word, so a multi-page Amharic PDF can go over the limit. The user then
gets a 502 "AI service unavailable" error and no analysis. The Claude provider does the
opposite: it ignores `max_tokens` in `transcribe` and truncates the text silently.

**Fix:** for OCR, keep the partial text and mark legibility `partial`; or transcribe page
by page. Make both providers behave the same, and tell the model when the document was
truncated (`pipeline.py:144` cuts to 60,000 characters without saying so).

### Medium

#### M1. Telegram message splitting can break HTML **(verified)**
`_chunks` (`telegram_bot.py:41`) cuts long paragraphs at exactly 4,000 characters. The
text is already HTML-escaped, so a cut can fall inside an entity (`&a` | `mp;`) or
between `<b>` and `</b>`. Telegram then rejects the message with a "can't parse
entities" error, and the user gets the generic error **after** the answer was paid for.
**Fix:** split before escaping and escape each part, or fall back to plain text when
sending fails.

#### M2. Memory use is not bounded
Every `/api/ask` without a `session_id` creates a session. Sessions are only removed
on the next request, after 30 minutes. With no rate limit (C1), memory grows with
request volume (up to 12 messages of up to 4,000 characters each per session).
**Fix:** cap the number of sessions (evict the oldest), and C1.

#### M3. Shared SQLite connection across threads
`CorpusStore` opens one connection with `check_same_thread=False` (`store.py:78`) and
uses it from FastAPI's thread pool and the bot's `asyncio.to_thread` workers with no
lock. Single-statement writes are mostly safe, but `with self.conn:` transactions from
two threads can interleave. The quota check and increment are also not atomic, so
parallel uploads can go over the limit. **Fix:** a lock around writes, or one connection
per thread; do the quota check and increment in one transaction.

#### M4. Blocking model calls can use up the thread pool
`/api/ask` is a sync endpoint and `/api/analyze` uses `run_in_threadpool`. Each request
holds a thread for the whole model call, including SDK retries with up to 30 s backoff.
The default pool has 40 threads, so 40 slow requests make the whole app, including
`/api/health`, stop responding. **Fix:** use the async clients of the SDKs, or a separate
bounded executor with a timeout for model calls.

#### M5. Model and configuration checks
- Verify that the default Claude model IDs (`claude-sonnet-5`, `claude-haiku-4-5`,
  `config.py:44-46`) are valid with the current API. A wrong ID only fails at the first
  request. Consider calling the provider once at start-up (or in `/api/health`).
- `FITIH_USAGE_SALT` defaults to `change-me` (`config.py:63`). With a known salt, the
  hashed Telegram IDs in `usage` can be reversed by brute force (Telegram IDs are short
  numbers). Refuse to start with the default salt when quotas are on.
- Embeddings are cached by model name only, not by `FITIH_EMBEDDING_DIM`. Changing the
  dimension mixes vector sizes and breaks start-up in `VectorIndex`. Include the
  dimension in the cache key.
- `/api/health` and `/api/laws` are public and show the provider, draft laws and
  reviewer names. This is low risk but worth a decision.

#### M6. Relative deadlines are never resolved
`resolve_deadline` supports "within N days" deadlines only when `today` is passed, but
`analyze_document` (`pipeline.py:180`) never passes it, so that branch is dead code. This
is arguably correct (the start date is usually the date of receipt, not today), but then
the UI should say so ("15 days from the date you received this"). Decide which you want
and remove the unused branch or use it.

### Low

- **Jurisdiction slugs are not normalised.** The router returns slugs like `addis_ababa`;
  `_retrieve` compares them to the corpus `jurisdiction` with `.lower()` only. A corpus
  file with `jurisdiction: Addis Ababa` never matches. Normalise both sides
  (lower-case, spaces → `_`).
- **Telegram:** the file download (`telegram_bot.py:144`) is outside the `try`, so a
  download error gives the user no reply. Photo size is not checked. `found_relevant_law`
  and `urgent` are not shown in Telegram (the web shows both).
- **Web UX:** the urgent marker is a bare "⚠" with no text; it should say what to do
  ("Act now — see the first steps below"). `URL.createObjectURL` previews are never
  revoked (`web/app.js:139`). Tabs lack `aria-selected` / `aria-controls`. Google Fonts
  (`index.html:10`) adds a third-party request and slows the first load on 2G/3G; a
  self-hosted Noto Sans Ethiopic subset would be faster and more private.
- **Prompt injection.** User documents are fenced in `<user_document>` with an explicit
  "data, not instructions" rule, and citations are checked in code, which limits the
  damage. The question itself is not covered by that rule; add `<question>` to rule 7.
- **Logging.** `log.exception` on provider errors may include request details from the
  SDK. Check that no user text reaches logs in production, given the privacy promise.
- **Dependencies** use open lower bounds (`fastapi>=0.115`, `google-genai>=1.30`). Pin
  them with a lock file so a new release cannot break a deploy.

---

## 4. Tests and CI

The suite (36 tests, about 2 s, no API keys) is good for an MVP: parser, retrieval,
calendar, citation filtering, quota, Gemini request shape and safety handling, importer
workflow, and API status codes.

Gaps worth filling, in order:
1. Regression tests for H2 (sub-article and Amharic cross-references) and M1 (chunking).
2. Bot handlers (`format_answer`, `format_analysis`, `_chunks`) — currently untested.
3. Session behaviour: expiry, unknown/client-chosen IDs (H1), the session cap (M2).
4. The Claude provider (`ClaudeLegalModel`) has no tests; only provider selection is tested.
5. An **answer-quality evaluation set**: 50–100 real questions in each language, graded
   by Ethiopian lawyers for correctness, citation accuracy and harmful advice.
   `docs/modules/12-testing-evaluation.md` describes this; it is the most important test
   for this product and it does not exist yet.
6. CI: add `ruff` (lint) and a coverage report; a Docker build check.

---

## 5. Launch checklist (in priority order)

1. Rate limits and a spend ceiling (C1).
2. Server-issued session IDs; decide and fix the web quota (C2, H1).
3. Fix the article parser and make `ingest` fail on numbering problems (H2).
4. Default corpus status to `draft`; require `reviewed_by` and a content hash (H3, H4).
5. Fix deployment: shared corpus database, persistent usage store, non-root image (H5).
6. Handle long documents without failing (H6); safe Telegram splitting (M1).
7. Paid Gemini tier (or Claude) before real users send personal documents — already
   documented; make it a hard deployment requirement.
8. Native-speaker legal review of all Amharic, Afaan Oromo and Tigrinya strings and
   disclaimers (already flagged in `i18n.py`).
9. Run the lawyer-graded evaluation and publish the results before a public launch.

---

## 6. Summary

Fitih AI has the right foundations: retrieval over the real law text, citations checked
in code, a disclaimer added in code, and real attention to privacy and Ethiopian
language and calendar details. Most of the work left is the hardening any public AI
service needs (abuse limits, server-controlled sessions, persistent state). The parts
specific to this product are the parser bugs and corpus review gaps (H2–H4). They matter
most, because a wrong or unreviewed article is cited with the same confidence as a
correct one.
