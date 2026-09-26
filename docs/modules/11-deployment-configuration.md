# Module 11 — Deployment and Configuration

## 1. Purpose
Describe how to install, configure, run and operate Fitih AI in development, in a
pilot and in production, with all settings in one place.

## 2. Scope
**In scope:** environment variables, local setup, Docker and Procfile deployment,
processes, the corpus and embedding steps at start-up, environments, operational
checks, and secrets.
**Out of scope:** the internals of each module (see modules 01–10).

## 3. Files
| File | Role |
|---|---|
| `fitihai/config.py` | `Settings` dataclass; reads the environment and a local `.env` file |
| `.env.example` | Template with every variable and explanatory comments |
| `requirements.txt` / `requirements-dev.txt` | Runtime and test dependencies |
| `Dockerfile` | Container image for the web server |
| `Procfile` | `web` and `bot` processes for Railway/Render/Heroku-style hosts |
| `pytest.ini` | Test configuration |

## 4. Interfaces — all settings
| Variable | Default | Module |
|---|---|---|
| `FITIH_LLM_PROVIDER` | `gemini` | 03 |
| `GEMINI_API_KEY` | — | 02, 03 |
| `ANTHROPIC_API_KEY` | — | 03 (Claude only) |
| `FITIH_GEMINI_REASONING_MODEL` | `gemini-2.5-flash` | 03 |
| `FITIH_GEMINI_FAST_MODEL` | `gemini-2.5-flash-lite` | 03 |
| `FITIH_GEMINI_OCR_MODEL` | `gemini-2.5-flash` | 03 |
| `FITIH_CLAUDE_REASONING_MODEL` | `claude-sonnet-5` | 03 |
| `FITIH_CLAUDE_FAST_MODEL` | `claude-haiku-4-5` | 03 |
| `FITIH_CLAUDE_OCR_MODEL` | `claude-sonnet-5` | 03 |
| `FITIH_EMBEDDINGS` | `gemini` | 02 |
| `FITIH_EMBEDDING_MODEL` | `gemini-embedding-001` | 02 |
| `FITIH_EMBEDDING_DIM` | `768` | 02 |
| `FITIH_TOP_K` | `8` | 02 |
| `FITIH_DB` | `data/fitihai.db` | 01 |
| `FITIH_CORPUS_DIR` | `corpus/laws` | 01 |
| `FITIH_SESSION_TTL_MINUTES` | `30` | 08 |
| `FITIH_MAX_HISTORY_TURNS` | `6` | 08 |
| `FITIH_MAX_UPLOAD_MB` | `10` | 05, 09 |
| `FITIH_FREE_ANALYSES_PER_MONTH` | `0` | 08 |
| `FITIH_USAGE_SALT` | `change-me` | 08 |
| `TELEGRAM_BOT_TOKEN` | — | 10 |

Real environment variables take precedence over `.env`.

## 5. Design and flow

### Local development
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                        # set GEMINI_API_KEY, TELEGRAM_BOT_TOKEN
python -m fitihai.cli ingest --embed        # load corpus/laws + build embeddings
uvicorn fitihai.api:app --reload            # http://localhost:8000
python -m fitihai.telegram_bot              # in a second terminal
pytest                                      # no keys needed
```

### Hosted (Railway / Render)
- `Procfile`
  - `web: python -m fitihai.cli ingest --embed && uvicorn fitihai.api:app --host 0.0.0.0 --port $PORT`
  - `bot: python -m fitihai.telegram_bot`
- Start-up rebuilds the database from `corpus/laws/` (committed to git), so the
  database can be temporary storage. Embeddings are cached in the same database.
  On a temporary disk they are recomputed at each deploy. Mount a persistent
  volume at `data/` to avoid this.
- If embedding fails at start-up, a warning is printed and the server still starts
  with keyword search only.

### Docker
```bash
docker build -t fitihai .
docker run -p 8000:8000 --env-file .env -v $PWD/data:/app/data fitihai
```

### Environments
| Environment | AI tier | Data allowed |
|---|---|---|
| Development | Gemini free tier | Fictional or test documents, public law |
| Pilot | Gemini **paid** tier | Real users, with a consent notice |
| Production | Gemini paid or Claude (chosen by evaluation) | Real users |

### Operations checklist
- `GET /api/health`: `articles_indexed` should equal the corpus size, and
  `articles_embedded` should match it.
- After changing laws: commit the files, then redeploy (or run `ingest --embed`)
  and restart the processes.
- Rotate `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` and `TELEGRAM_BOT_TOKEN` if exposed.
- Set a billing budget alert in Google Cloud / the Anthropic console.

## 6. Configuration
See §4.

## 7. Data, privacy and security
- Secrets live only in environment variables or the host's secret store. `.env`
  is git-ignored.
- `FITIH_USAGE_SALT` must be a long random value in every non-development environment.
- Serve over HTTPS (the hosting platform or a reverse proxy). Do not log request bodies.
- Check data residency and the provider's data-processing terms before scaling
  (Personal Data Protection Proclamation).

## 8. Error handling
- A missing `GEMINI_API_KEY` makes the first AI request fail (HTTP 502), and the
  cause appears in the log. `/api/health` reports the provider in use.
- A corpus file with an error stops `ingest` with a clear message, so a bad law file
  cannot be deployed silently.
- An unknown provider value raises `ValueError` at start-up.

## 9. Testing
Run `pytest` before every deploy (28 tests at the time of writing). After deploying,
check `GET /api/health`, ask one question, and upload one test document.

## 10. Limitations and next steps
- Add CI (GitHub Actions) to run `pytest` on every push.
- There is one process per role. To scale out, share sessions (Redis, in memory
  only) and move to PostgreSQL + pgvector.
- Add structured logging with request IDs and token usage (no content), plus an uptime monitor.
- Add a staging environment that uses test documents only.
