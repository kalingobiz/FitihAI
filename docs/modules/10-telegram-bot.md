# Module 10 — Telegram Bot

## 1. Purpose
Reach people where they already are. Telegram is widely used in Ethiopia, works
on low-end phones and slow connections, and needs no new app. Users simply
photograph a document and send it.

## 2. Scope
**In scope:** bot commands, language selection, text questions, photo and PDF
analysis, message formatting and splitting, and user-facing errors.
**Out of scope:** the pipeline (04, 05) and voice recognition (not built yet).

## 3. Files
| File | Role |
|---|---|
| `fitihai/telegram_bot.py` | Handlers, formatting, `build_application`, `main` |
| `fitihai/i18n.py` | Localised bot messages (module 07) |

## 4. Interfaces

| User action | Bot behaviour |
|---|---|
| `/start` or `/lang` | Shows buttons for አማርኛ · Afaan Oromoo · ትግርኛ · English |
| Tap a language | Saves it for this user and shows the welcome message in that language |
| `/new` | Clears the conversation ("Nothing from it is kept.") |
| Text message | Legal Q&A (module 04) → answer, sources, disclaimer |
| Photo | Document analysis (largest photo size) |
| PDF / JPEG / PNG / WebP / GIF sent as a file | Document analysis |
| Other file types | Replies with the accepted formats |
| Voice or audio | "Voice messages are not supported yet. Please type your question." |

Run: `TELEGRAM_BOT_TOKEN=… python -m fitihai.telegram_bot` (long polling).

## 5. Design and flow
```
update ─► handler ─► asyncio.to_thread(advisor.ask / advisor.analyze_document) ─► format ─► send in chunks
```
- The pipeline code is synchronous, so it runs in a worker thread. The bot keeps
  responding to other users meanwhile.
- **Session ID** = `tg-<chat id>`: each chat has one ongoing conversation.
- **Quota key** = Telegram user ID, hashed before storage (module 08).
- The user sees immediate feedback: a "typing…" indicator, and for documents a
  localised "Reading and analysing… up to a minute" message.
- **Formatting:** Telegram HTML mode. All AI and user text is HTML-escaped first.
  - Answer: text → **Sources** (bullet citations) → *disclaimer* (italic).
  - Analysis: **title**, summary, then each clause as 🔴/🟡/🟢 *"quote"* + explanation,
    **⏰ Deadlines** (as written → Gregorian), **❓ Questions to ask a lawyer**,
    **Sources**, *disclaimer*.
- **Splitting:** Telegram's limit is 4,096 characters, so messages are split at
  4,000 on line boundaries (very long lines are cut hard).
- The downloaded file bytes are deleted (`del data`) as soon as the analysis finishes.

## 6. Configuration
| Variable | Meaning |
|---|---|
| `TELEGRAM_BOT_TOKEN` | From @BotFather (required) |
| `FITIH_MAX_UPLOAD_MB` | Size check for documents (Telegram photos are already compressed) |
| `FITIH_FREE_ANALYSES_PER_MONTH` | Monthly document limit per Telegram user (0 = unlimited) |

The bot runs as a separate process from the web server (`bot:` line in the `Procfile`).

## 7. Data, privacy and security
- The language preference is kept in the bot's in-memory `user_data` and is lost on restart.
- No messages, files or Telegram IDs are written to disk. Only the salted hash is
  stored, in the usage counters.
- Telegram itself stores the chat on its servers, as with any Telegram
  conversation. Mention this in the privacy notice.
- Keep the bot token secret. If it leaks, rotate it with @BotFather.

## 8. Error handling
| Situation | User sees |
|---|---|
| Any pipeline or provider error | Localised "Sorry, something went wrong. Please try again." (details logged) |
| Quota reached | Localised "You have used all free document analyses for this month." |
| Unsupported file | Accepted formats |
| File too large | "Max N MB" |
| Missing token at start-up | Process exits with "Set TELEGRAM_BOT_TOKEN" |

## 9. Testing
There are no automated bot tests yet. The formatting functions (`format_answer`,
`format_analysis`, `_chunks`) are pure and easy to unit-test. Adding those tests is
the next step. Manual test script:
1. `/start` → pick አማርኛ → welcome message in Amharic.
2. Ask a labour question → answer + sources + Amharic disclaimer.
3. Ask a follow-up → it uses context.
4. Send a photo of a sample contract → 🔴🟡🟢 analysis.
5. `/new` → confirmation; the next question has no context.
6. Send a voice note → "not supported" message.

## 10. Limitations and next steps
- The language preference is lost on restart. Consider persisting it (it is not
  sensitive) or asking again.
- Albums (several photos) are analysed one photo at a time. Group them into one
  document.
- Voice input needs an Amharic/Oromo speech-recognition provider (planned for Phase 4).
- Use webhooks instead of polling for production hosting.
- Add inline "Ask a follow-up" buttons that use `follow_up_suggestions`.
