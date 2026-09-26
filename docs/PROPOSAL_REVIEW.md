# Review of the Fitih AI Proposal (April 2026)

The idea is strong and the problem is real. There is a clear gap in legal
literacy, a working delivery channel (Telegram), and a technically sound core
(retrieval over the actual text of the law, with citations). Most of what
follows fixes credibility problems a competition judge or funder would catch,
plus design choices that would cause trouble once the system is built.

Findings are ordered by how much damage they would do if left as is.

---

## 1. Claims that will not survive scrutiny

| Claim in proposal | Problem | Fix |
|---|---|---|
| **"Under 1 ETB per query"** | Not achievable with the stated stack. At current Claude prices (Sonnet 5: $2 in / $10 out per million tokens; Haiku 4.5: $1 / $5) and about **150 ETB/USD**, a grounded Q&A costs about **$0.02–0.03 (3–4 ETB)**. A 1–2 page photographed document (OCR + analysis) costs about **$0.06–0.10 (9–15 ETB)**. See the cost table in `PROPOSAL_v2.md`. | Say "3–15 ETB, 50–500× cheaper than a 500–2,000 ETB consultation". That is still a very strong claim, and an honest one. |
| "60–70% of rural Ethiopians have low legal literacy (World Bank)", "2M+ active land disputes", "10M+ Telegram users" | No citations, and I could not match these figures to a specific publication. One unsupported number undermines every other number. | Cite the exact report and page, or replace with sourced figures (e.g. the World Justice Project's Ethiopia data, Ethiopian Federal Supreme Court case-load statistics, DataReportal's Ethiopia social-media figures). |
| "No comparable tool covers Amharic, Afaan Oromo, Tigrinya and English" | General-purpose AI assistants already answer in these languages, and there are Ethiopian law databases online. | Change the claim to what really is different: **grounded in the Ethiopian statute text, cited to the article, verified, and delivered on Telegram**. Add a short competitor scan. |
| "Handles handwritten Ethiopic script" | Not measured. Handwritten Ge'ez OCR quality varies a lot between models. | Present it as a hypothesis with a benchmark plan (50 real documents, character error rate per model). |
| Tigrinya for the "Eritrean diaspora" | Ethiopian law does not apply to Eritrea, so this audience does not fit. | Justify Tigrinya by Tigray region users instead. |

## 2. Internal contradictions

- **"No document storage" vs. "shareable analysis links" and "full session history".**
  A shareable link means storing the analysis. *MVP resolution:* sessions live in
  memory only and expire after 30 minutes. Sharing is done by "Print / save as PDF"
  on the user's own device.
- **FastAPI backend + "Vue 3 + Inertia.js".** Inertia needs a server-side adapter
  (usually Laravel/Rails), so it is not a natural fit with FastAPI. *MVP:* a
  no-build static web client served by FastAPI. Use Vue later if the team prefers it.
- **MySQL for sessions + Qdrant/pgvector for vectors.** That is two databases for a
  prototype. *MVP:* one SQLite file. For scale: PostgreSQL + pgvector (one database).
- **Freemium "3 free analyses per month"** while the primary users are people who
  cannot afford a lawyer. A paywall on the core harm-prevention feature works
  against the mission. Keep the citizen tier free, funded by NGO, government and
  law-firm licences. Quotas stay available only to control abuse (implemented,
  off by default).

## 3. Outdated technical choices

- `claude-sonnet-4` → current is **`claude-sonnet-5`** (configurable).
- `gemini-1.5-flash` has been retired, and `text-embedding-004` has been superseded.
- **The dual-API design is not required.** Claude reads images and PDFs directly,
  so the MVP runs on a single provider with a single bill and a single data
  processing agreement. Gemini stays as an optional OCR provider
  (`FITIH_OCR_PROVIDER=gemini`), so the Ethiopic OCR question can be settled by
  benchmark rather than assumption.
- **Embeddings are not the first thing to build.** An Amharic question often
  needs to match an English statute, and embeddings are weak there too. The MVP
  uses (a) a cheap router call that writes search queries in both English and
  Amharic legal vocabulary, and (b) a BM25 index with Ethiopic-specific
  normalisation (folding homophone letters ሀ/ሐ/ኀ, ሰ/ሠ, አ/ዐ, ጸ/ፀ, plus
  syllable bigrams). Add embeddings once the evaluation set shows where BM25 fails.
- **Voice-to-text** is listed as a feature without a speech-recognition provider.
  Amharic/Oromo ASR is a separate project. Mark it as Phase 4.

## 4. Gaps in the legal corpus plan

The layer list is good, but it is missing laws that the target users need most:

| Missing | Why it matters |
|---|---|
| **Civil Procedure Code (1965)** and **Criminal Procedure Code (1961)** | The proposal promises "procedural guidance for court appointments". Procedure *is* that guidance. |
| **Rural Land Administration and Land Use Proclamation No. 456/2005** plus regional rural land laws | The proposal names smallholder farmers. The Urban Lease law does not apply to them. |
| **Expropriation of Landholdings for Public Purposes Proclamation No. 1161/2019** | "Government acquisition notices" are named as a use case. |
| **Revised Family Code (Proc. 213/2000)** and regional family codes | Family is listed as a domain, but no family law is listed. The federal code applies in Addis Ababa and Dire Dawa. |
| **Commercial Code Proclamation No. 1243/2021** | The 1960 Commercial Code was replaced. Citing the old one would be wrong. |
| **Personal Data Protection Proclamation No. 1321/2024** | Governs the product itself (see §5). |
| **Dire Dawa City Administration Charter (Proc. 416/2004)** | Home market. It defines which body issues which notice. |
| Ministry of Revenues (not "ERCA") directives | ERCA was restructured in 2018. |

Also needed: a process for **sourcing** (official Negarit Gazeta text), for
**versioning amendments** (an article that was replaced must not be cited), and
for recording **which language version is authoritative** (Amharic prevails for
federal law). *Verify every proclamation number above against the Negarit Gazeta
before publishing; this review was written without access to it.*

## 5. Legal and ethical risks not addressed

1. **Unauthorised practice of law.** Ethiopia licenses advocates (Federal Advocacy
   Service Licensing and Administration Proclamation No. 1249/2021 — verify). Frame
   the product as *legal information*, not advice. Build referral paths to licensed
   lawyers and legal-aid clinics. Ask the Federal Attorney General / bar for an
   informal opinion before public launch.
2. **Cross-border data transfer.** Photos of summonses and contracts contain
   personal data and are sent to US-hosted AI APIs. Under the 2024 data protection
   proclamation this needs a lawful basis and user notice/consent. "No storage" on
   Fitih's side does not cover the AI provider's side, so review the provider's
   retention terms and say so in the privacy notice.
3. **Hallucinated citations** are the biggest product risk. A disclaimer does not
   make an invented "Article 39" safe. *MVP:* the model may only cite article IDs
   that were actually retrieved, and the server drops any other citation before
   the user sees it. If nothing valid is left, the answer says the library does
   not contain the law.
4. **Urgent situations** (hearing tomorrow, arrest, domestic violence) need a
   different response: first steps plus legal-aid contacts. *MVP:* the router
   flags urgency and the answer leads with next steps.
5. **Prompt injection through documents.** A document can contain text like
   "ignore previous instructions". *MVP:* document text is wrapped and treated as
   data only.
6. **"Number of risk flags" as an impact metric** rewards over-flagging. Measure
   **flag precision/recall judged by lawyers** instead.

## 6. Missing sections a funder expects

- **Team** (who is the legal lead? A licensed lawyer must own corpus quality).
- **Budget** (API, hosting, lawyer review hours, corpus digitisation).
- **Evaluation plan** with a gold test set and numeric targets.
- **Risks & mitigations** table.
- **Pilot partner** (a named NGO or university legal-aid centre in Dire Dawa).
- **Language fit for the home market:** Dire Dawa's working population speaks
  Amharic, Afaan Oromo and **Somali**. The proposal already lists Somali Regional
  State laws but not the Somali language. Consider Somali before Tigrinya for the
  Dire Dawa pilot.

## 7. What the proposal gets right (keep it)

- Two entry points (document + question) over one knowledge base.
- Telegram-first delivery.
- Article-level corpus with citations.
- Three-level risk flags, deadline extraction, "questions to ask a lawyer".
- The disclaimer on every output. The MVP appends it in code, so it is guaranteed
  rather than left to the model.
- Privacy by design.

## 8. Additions made in the MVP that were not in the proposal

- **Ethiopian-calendar deadline conversion.** Documents are dated in E.C. (ዓ.ም). The
  model extracts the date as written and code converts it to Gregorian, which is
  deterministic and tested.
- **Citation verification** (above).
- **Urgency routing** (above).
- **Ge'ez numeral support** in the corpus parser (አንቀጽ ፲፪ → Article 12).
- **Salted-hash usage counters.** Raw Telegram IDs are never stored.

See `PROPOSAL_v2.md` for the revised proposal text.
