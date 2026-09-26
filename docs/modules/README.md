# Fitih AI — Module Documentation

This folder describes the Fitih AI system one module at a time. Every document
uses the same structure so that modules are easy to compare and review.

## Standard structure

| # | Section | What it answers |
|---|---|---|
| 1 | **Purpose** | Why the module exists; what problem it solves |
| 2 | **Scope** | What is in and out of the module's responsibility |
| 3 | **Files** | Where the code lives |
| 4 | **Interfaces** | Public functions, classes, endpoints, inputs and outputs |
| 5 | **Design and flow** | How it works, step by step, with the key design decisions |
| 6 | **Configuration** | Environment variables and constants that change behaviour |
| 7 | **Data, privacy and security** | What data is touched, stored or sent elsewhere |
| 8 | **Error handling** | What can fail and how the module responds |
| 9 | **Testing** | Automated tests that cover the module, and how to check it by hand |
| 10 | **Limitations and next steps** | Known gaps, risks and planned work |

## Modules

| # | Module | Summary |
|---|---|---|
| 01 | [Corpus and law library](01-corpus.md) | Law file format, parsing into articles, SQLite storage, versioning |
| 02 | [Search / RAG](02-search-rag.md) | Hybrid keyword + semantic retrieval with rank fusion |
| 03 | [AI providers](03-ai-providers.md) | Gemini (default) and Claude behind one interface |
| 04 | [Question answering](04-question-answering.md) | The "What are my rights?" flow |
| 05 | [Document analysis](05-document-analysis.md) | OCR, clause risk flags, deadlines, questions for a lawyer |
| 06 | [Ethiopian calendar](06-ethiopian-calendar.md) | E.C. ↔ Gregorian conversion for deadlines |
| 07 | [Languages and disclaimers](07-languages-disclaimers.md) | Four languages, UI strings, the mandatory disclaimer |
| 08 | [Sessions, privacy and usage limits](08-sessions-privacy-usage.md) | In-memory sessions, no document storage, hashed quotas |
| 09 | [Web application](09-web-app.md) | FastAPI endpoints and the browser client |
| 10 | [Telegram bot](10-telegram-bot.md) | The main low-bandwidth channel |
| 11 | [Deployment and configuration](11-deployment-configuration.md) | Settings, Docker/Procfile, environments, operations |
| 12 | [Testing and evaluation](12-testing-evaluation.md) | Automated tests and the lawyer-graded quality evaluation |

## System overview

```
            ┌──────────────┐     ┌──────────────┐
 Citizens → │ 10 Telegram  │     │  09 Web app  │ ← Citizens, NGOs
            └──────┬───────┘     └──────┬───────┘
                   └─────────┬──────────┘
                             ▼
      ┌──────────────── Advisor (pipeline) ────────────────┐
      │  04 Question answering     05 Document analysis    │
      │        │                        │                  │
      │        └──── 02 Search / RAG ◄──┘                  │
      │                  │                                 │
      │   03 AI providers (router · answer · analyse · OCR │
      │                    · embeddings)                    │
      │   06 Ethiopian calendar   07 Languages/disclaimer  │
      │   08 Sessions · privacy · usage limits             │
      └──────────────────────────┬─────────────────────────┘
                                 ▼
                     01 Corpus (SQLite law library)

 11 Deployment/configuration and 12 Testing/evaluation apply to every module.
```

## Conventions

- Paths are relative to the repository root.
- "Article ID" means `<law id>:<article number>`, for example `labour-1156-2019:39`.
- Proclamation numbers in examples must be verified against the Negarit Gazeta
  before they are used in the real corpus.
