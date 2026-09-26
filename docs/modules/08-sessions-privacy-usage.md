# Module 08 — Sessions, Privacy and Usage Limits

## 1. Purpose
Support follow-up questions without keeping people's legal problems on file, and
allow fair-use limits without storing who the users are. Privacy by design is a
core promise of Fitih AI. This module is where that promise is implemented.

## 2. Scope
**In scope:** in-memory conversation sessions and their expiry, what is and is not
persisted, the anonymous usage counters, and monthly quotas.
**Out of scope:** what the AI provider does with data (module 03, covered by
provider terms and the paid tier), and hosting logs (module 11).

## 3. Files
| File | Role |
|---|---|
| `fitihai/sessions.py` | `Session`, `SessionStore` (in memory, thread-safe, TTL) |
| `fitihai/corpus/store.py` | `hash_user`, `usage_count`, `increment_usage` (table `usage`) |
| `fitihai/pipeline.py` | `Advisor.check_quota`, `QuotaExceeded` |

## 4. Interfaces
| Item | Description |
|---|---|
| `SessionStore.get(session_id, language)` | Returns the existing session (and updates its language) or creates one with a random ID |
| `SessionStore.append(session, user, assistant)` | Adds a turn; keeps only the last `max_turns` turns |
| `SessionStore.clear(session_id)` | Deletes a session ("New conversation" in the web app, `/new` in Telegram) |
| `DELETE /api/session/{id}` | HTTP version of `clear` |
| `CorpusStore.hash_user(user_id, salt)` | `sha256(salt:user_id)`, first 32 hex characters |
| `Advisor.check_quota(user_key, kind)` | Raises `QuotaExceeded` if this month's count has reached the limit |

## 5. Design and flow

**What is stored where**
| Data | Where | How long |
|---|---|---|
| Uploaded file bytes | Request memory only | Until the request ends |
| Extracted document text | Request memory only | Until the request ends |
| Questions and answers (text) | `SessionStore` in process memory | 30 minutes after last use, or until cleared or restarted |
| Document summary (one line) | `SessionStore` | Same as above |
| Law excerpts sent to the AI | Not stored in history | — |
| Usage counters | SQLite `usage` table: salted user hash, month (`YYYY-MM`), kind, count | Until deleted |
| Law corpus and embeddings | SQLite | Permanent (public data) |

**Sessions**
- Web: a random 16-byte URL-safe ID, created on the first request and held by the page.
- Telegram: `tg-<chat id>`, so a chat continues naturally.
- Expired sessions are removed whenever sessions are accessed. A server restart clears all of them.

**Usage limits**
- Only document analysis is metered (`kind = "analysis"`). Questions are not.
- Limits are off by default (`FITIH_FREE_ANALYSES_PER_MONTH=0`). The citizen tier
  is meant to be free, so the limit is for abuse control and licensed tiers.
- Telegram uses the Telegram user ID as the key. It is hashed with a secret salt
  before storage, so the database cannot be matched back to Telegram accounts
  without the salt.

## 6. Configuration
| Variable | Default | Meaning |
|---|---|---|
| `FITIH_SESSION_TTL_MINUTES` | `30` | Session expiry |
| `FITIH_MAX_HISTORY_TURNS` | `6` | Turns kept per session |
| `FITIH_FREE_ANALYSES_PER_MONTH` | `0` | Monthly limit; 0 = unlimited |
| `FITIH_USAGE_SALT` | `change-me` | **Must be set to a long random secret in production** |

## 7. Data, privacy and security
- Aligned with the **Personal Data Protection Proclamation No. 1321/2024** [verify]:
  data minimisation, no retention of user content, and anonymised counters.
- **Remaining obligations:**
  1. show a consent notice that content is processed by an AI provider abroad;
  2. use the **paid** Gemini tier (or Claude) with real users, because the free
     tier may use content to improve Google's products;
  3. make sure hosting and server logs do not record request bodies;
  4. publish a short privacy notice in all four languages.
- Sessions exist only in memory, so if the server is compromised, only the last
  30 minutes of conversations are exposed.

## 8. Error handling
- `QuotaExceeded` → HTTP 429, or a localised message in Telegram.
- An unknown or expired session ID silently starts a new session.
- The session store uses a lock and is safe for concurrent requests in one process.

## 9. Testing
`test_ask_keeps_session_history`; `test_quota` (the limit is enforced, and raw IDs
are never stored).

## 10. Limitations and next steps
- **Multi-server deployments** need a shared session store. Use Redis with a TTL,
  and keep it in memory only (no persistence).
- **Web quotas are weak:** the web client has no stable user ID (the session ID is
  used, and a new session resets it). Add rate limiting by IP address at the proxy,
  or sign-in for licensed tiers.
- Add an opt-in "anonymous research logging" mode, as described in the proposal,
  with explicit consent and automatic removal of personal details.
- Add a scheduled job that deletes usage rows older than 12 months.
