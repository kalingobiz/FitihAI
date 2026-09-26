# Module 09 — Web Application (API + Browser Client)

## 1. Purpose
Provide the full feature set in a browser (phone or desktop), and expose a JSON
API that the web client, partner NGOs and future apps can use.

## 2. Scope
**In scope:** FastAPI endpoints, request validation, upload limits, error-to-HTTP
mapping, static file serving, and the no-build HTML/CSS/JS client (chat, document
upload, analysis view, language switch, print/save).
**Out of scope:** the pipeline logic (04, 05) and the Telegram channel (10).

## 3. Files
| File | Role |
|---|---|
| `fitihai/api.py` | `create_app()`, endpoints, `get_advisor()` (one shared `Advisor`) |
| `web/index.html` | Page layout: header, language select, Ask/Document tabs |
| `web/app.js` | Client logic, web-only labels in 4 languages, safe DOM rendering |
| `web/style.css` | Mobile-first styles, light and dark themes, print styles |

## 4. Interfaces

| Method and path | Request | Response |
|---|---|---|
| `GET /` | — | Web client |
| `GET /static/*` | — | CSS/JS |
| `GET /api/health` | — | `{status, provider, articles_indexed, articles_embedded}` |
| `GET /api/meta` | — | `{languages, ui, disclaimer}` |
| `GET /api/laws` | — | List of laws with article counts |
| `POST /api/ask` | JSON `{question (2–4000 chars), language?, session_id?}` | `AskResponse` (module 04) |
| `POST /api/analyze` | multipart `file`, `language?`, `session_id?` | `AnalyzeResponse` (module 05) |
| `DELETE /api/session/{id}` | — | `{cleared: true}` |

Interactive API docs are generated automatically at `/docs` (FastAPI/OpenAPI).

**Example**
```bash
curl -X POST localhost:8000/api/ask -H 'Content-Type: application/json' \
  -d '{"question":"አሠሪዬ ያለ ማስጠንቀቂያ አሰናበተኝ። መብቴ ምንድን ነው?","language":"am"}'
curl -X POST localhost:8000/api/analyze -F file=@lease.jpg -F language=om
```

## 5. Design and flow
**Server**
- `create_app(advisor_factory)` takes the `Advisor` as a parameter so tests can
  inject one that uses the fake model. In production, `get_advisor()` builds one
  instance per process (provider from module 03, embedder from module 02).
- `ask` is a normal (sync) endpoint, which FastAPI runs in its thread pool.
  `analyze` reads the upload asynchronously and then runs the pipeline in the
  thread pool, so large uploads do not block other users.
- The upload is read with a size cap (`max_upload_mb + 1 byte`). `image/jpg` is
  normalised to `image/jpeg`.

**Client**
- **Ask tab:** chat bubbles; each answer shows an ⚠ banner if urgent, the answer,
  "not in library" when relevant, expandable citations (excerpt and source link),
  follow-up chips, and the disclaimer. Enter sends, and Shift+Enter adds a new line.
- **Document tab:** file picker with image preview → analysis card showing the
  title, type/domain, legibility warning, summary, parties, colour-coded clauses
  (🔴🟡🟢), deadlines with the Gregorian date, lawyer questions, citations, the
  disclaimer, and **Print / save as PDF**. This replaces "shareable links", so
  nothing has to be stored on the server.
- The language choice is remembered in `localStorage`, wrapped in try/catch so
  private browsing still works.
- **Safe rendering:** all text is inserted as text nodes (`el()` / `fill()`),
  never as HTML, so AI or document content cannot inject scripts.
- No build step and no framework. The page works on low-end Android browsers. Fonts:
  Noto Sans Ethiopic / Noto Sans (Google Fonts), falling back to system fonts.

## 6. Configuration
`FITIH_MAX_UPLOAD_MB` (10). Run with `uvicorn fitihai.api:app --host 0.0.0.0 --port 8000`.

## 7. Data, privacy and security
- The client holds the session ID in memory only. Reloading the page starts a new session.
- Uploads are never stored (module 08).
- Error responses never include stack traces or provider messages. Details are
  written only to the server log.
- **Before public launch:** serve over HTTPS, add rate limiting (per IP) at the
  reverse proxy, restrict CORS if the API is opened to partners, and add the AI
  processing consent notice to the page.

## 8. Error handling
| Status | When |
|---|---|
| 400 | Empty file, or unsupported type reached the model |
| 413 | File larger than the limit |
| 415 | Type not JPEG/PNG/WebP/GIF/PDF/TXT |
| 422 | Invalid request body, or the AI refused |
| 429 | Monthly document quota reached |
| 502 | AI provider or network failure |

The client shows the localised "something went wrong" text plus the server's
short message.

## 9. Testing
`test_api_ask`, `test_api_analyze_rejects_bad_type`, `test_api_analyze_text`,
`test_api_health_and_index_page` (FastAPI `TestClient` with the fake model).
The client was also exercised in headless Chromium at phone width (390 px): ask →
answer with citations, and upload → colour-coded analysis.

## 10. Limitations and next steps
- No streaming: users wait for the complete answer. Add server-sent events.
- No accessibility audit yet (screen readers, contrast in all themes).
- Add a consent banner and a privacy page.
- An offline-capable PWA would help on unstable connections.
- Add an NGO dashboard (usage by language and domain, with no content) for licensed partners.
