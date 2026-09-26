# Module 04 — Question Answering ("What are my rights?")

## 1. Purpose
Let a citizen ask a legal question in their own language and get a clear,
grounded answer that cites the articles it relies on, with follow-up questions
supported in the same conversation.

## 2. Scope
**In scope:** the `Advisor.ask` flow: routing, retrieval, the grounded answer,
citation verification, urgency, session history, and the response format.
**Out of scope:** how retrieval ranks articles (02), provider details (03), and
channel formatting (09, 10).

## 3. Files
| File | Role |
|---|---|
| `fitihai/pipeline.py` | `Advisor.ask`, `Advisor._citations` |
| `fitihai/prompts.py` | `ANSWER_SYSTEM`, `ROUTER_SYSTEM`, `format_excerpts`, `language_instruction` |
| `fitihai/schemas.py` | `Route`, `Answer`, `AskResponse`, `Citation` |

## 4. Interfaces
```python
Advisor.ask(question: str, session_id: str | None = None, language: str | None = None) -> AskResponse
```
HTTP: `POST /api/ask` with `{"question": "...", "language": "am", "session_id": null}`.

**`AskResponse` fields**
| Field | Meaning |
|---|---|
| `session_id` | Send back with the next question to continue the conversation |
| `language` | `am` / `om` / `ti` / `en` |
| `domain` | labor, land, commercial, family, criminal, tax, civil_procedure, administrative, other |
| `answer` | Plain-language answer in the chosen language |
| `citations[]` | `{id, citation, heading, excerpt (≤400 chars), source}`: verified only |
| `found_relevant_law` | `false` if the library had nothing usable |
| `follow_up_suggestions[]` | Suggested next questions |
| `urgent` | `true` for imminent hearings, arrest, eviction or violence |
| `disclaimer` | Mandatory notice in the user's language |

## 5. Design and flow
```
1. session  = sessions.get(session_id, language)
2. route    = model.route(question, history)          → domain, jurisdiction, urgency, EN+AM queries
3. articles = retrieve(question + queries)             → up to 8 articles   (skipped if not a legal question)
4. prompt   = <law_excerpts>…</law_excerpts> + "write in <language>" + domain/urgency + <question>
5. result   = model.answer(prompt, history)            → answer, cited_article_ids, found_relevant_law
6. citations = only IDs that were among the retrieved articles       ← citation verifier
7. found_relevant_law = model said so AND at least one valid citation remains
8. history += (question, answer)                       → excerpts are not stored in history
9. return AskResponse + disclaimer(language)
```

**Key safeguards**
- **Citation verifier (step 6).** The model can only cite articles it was shown.
  Invented or mistyped IDs are silently removed. If nothing valid remains, the
  answer is marked "not found", and the clients display "the library does not yet
  contain this law".
- **Honest fallback.** When the excerpts do not cover the question, the prompt
  requires the model to say so and give only general orientation (which office or
  court, what to bring), not invented rules.
- **Urgency.** Urgent answers start with what to do first and by when, plus free
  legal-aid contacts (university legal-aid centres, the Ethiopian Women Lawyers
  Association, the Ethiopian Human Rights Commission).
- **Follow-ups.** The last 6 turns (question + answer text only) are sent with the
  next question. The router also sees recent turns, so "and what about my
  overtime?" is routed correctly.

## 6. Configuration
`FITIH_TOP_K` (8), `FITIH_MAX_HISTORY_TURNS` (6), `FITIH_SESSION_TTL_MINUTES` (30), and the model settings in module 03.

## 7. Data, privacy and security
- The question goes to the AI provider (module 03) and, for semantic search, to the
  embedding API (module 02).
- History is kept in memory only, and expires after 30 minutes (module 08).
- Nothing about the question is written to the database.

## 8. Error handling
| Situation | Result |
|---|---|
| Question shorter than 2 or longer than 4,000 characters | HTTP 422 (request validation) |
| Provider refusal | HTTP 422 "The assistant could not answer this request." |
| Provider or network failure | HTTP 502 "The AI service is unavailable. Please try again." |
| Semantic search fails | Keyword-only retrieval; the answer still works |
| Not a legal question | No retrieval; the model answers briefly with no citations |

## 9. Testing
`tests/test_core.py`: `test_ask_filters_hallucinated_citations` (a real and an
invented citation, where only the real one survives), `test_ask_keeps_session_history`,
`test_no_citations_means_not_found`, `test_api_ask`.

## 10. Limitations and next steps
- Evaluate against the gold question set (module 12) before public launch.
- Answers cite whole articles, not sub-articles.
- There is no check that the *text* of the answer matches the cited article. It is
  only checked that the article was retrieved. Consider a lightweight "entailment"
  check on high-stakes statements (deadlines, amounts).
- Add a directory of legal-aid contacts per city (Dire Dawa first) to replace the
  generic suggestions.
