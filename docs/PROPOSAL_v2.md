# ፍትህ AI — Fitih AI
### Ethiopian law, explained in the language you speak, grounded in the article that applies
**Innovation Competition Proposal — revised edition (v2)**
Kalingo IT and Communications · Dire Dawa, Ethiopia

> Items marked **[source]** need a citation added before submission. Items marked
> **[verify]** are proclamation numbers to check against the Negarit Gazeta.

---

## 1. Executive summary

Fitih AI (ፍትህ AI, "Justice AI") is a legal-information service for people in
Ethiopia. A user sends a photo of a legal document, or asks a question, on
Telegram or the web. Fitih AI replies in Amharic, Afaan Oromo, Tigrinya or English
with:

- a plain-language explanation,
- the clauses that could harm them (🔴 / 🟡 / 🟢),
- every deadline, converted from the Ethiopian calendar,
- questions to ask a lawyer, and
- **citations to the exact article of Ethiopian law, checked by the server** before
  the user sees them.

A consultation costs 500–2,000 ETB **[source]**. With Google Gemini, development
and the pilot can run on the **free tier**. At paid rates Fitih AI costs roughly
**1 ETB per question and 4 ETB per document** in AI fees, which is 100–2,000×
cheaper. Citizens use it free. NGO, government and law-firm licences pay for it.

**Status: a working prototype exists** (this repository): web app, Telegram bot,
article-level legal search, citation verification, E.C. date conversion, and
automated tests.

## 2. The problem

1. **Documents people cannot read.** Legal Amharic draws on Ge'ez-rooted
   vocabulary that even educated readers struggle with. Leases, summonses, eviction
   notices and loan agreements arrive in a language that is technically the
   citizen's own but is functionally unreadable.
2. **An exploitable information gap.** In peri-urban areas around Dire Dawa, Harar
   and Adama, residents sign documents they do not understand. Middlemen profit by
   "explaining" them **[source: case reports / NGO interviews]**.
3. **No affordable first step.** People go into labour offices, kebele offices and
   courts without knowing their rights, the procedure, or the deadline.

*Evidence to add:* World Justice Project Ethiopia data on legal-needs and access
to justice; Federal Supreme Court case-load figures; DataReportal figures for
Telegram use in Ethiopia **[source]**. Also 10–20 short interviews with
Dire Dawa residents and legal-aid staff. First-hand evidence is persuasive and cheap to collect.

## 3. The solution

### Entry point 1 — "What does this document mean?"
Photo, scan or PDF → transcription (Ethiopic and Latin script, stamps and
handwriting marked) → classification → retrieval of the relevant articles →
analysis:

- summary and parties,
- clause-by-clause risk rating (🔴 dangerous · 🟡 needs attention · 🟢 standard),
- deadlines and response windows, **converted between Ethiopian and Gregorian
  calendars**,
- questions to ask a lawyer before signing or responding,
- a legibility warning when the photo is poor.

### Entry point 2 — "What are my rights?"
Question in any supported language → router (domain, jurisdiction, urgency, and
search terms in English *and* Amharic) → retrieval → answer that cites articles →
follow-up questions in the same session.

### Safeguards built into every response
- **Verified citations:** the model can only cite articles that were actually
  retrieved. Anything else is removed by the server. If no valid source is left,
  the answer says the library does not yet cover this, rather than guessing.
- **Urgency routing:** hearings within days, arrests, evictions or violence →
  first steps and free legal-aid contacts come first.
- **Disclaimer appended by code** on every output, in the user's language. It is
  not left to the model.
- **Document text is treated as data** (protection against prompt injection).

## 4. Languages

| Language | Script | Launch status |
|---|---|---|
| Amharic (አማርኛ) | Ge'ez | Pilot, fully reviewed |
| English | Latin | Pilot |
| Afaan Oromo | Latin (Qubee) | Beta; native lawyer review before GA |
| Tigrinya (ትግርኛ) | Ge'ez | Beta; native lawyer review before GA |
| *Somali (Af-Soomaali)* | Latin | *Proposed for Phase 3. Widely spoken in Dire Dawa* |

The AI works in all of these, but quality in Afaan Oromo and Tigrinya must be
measured, not assumed (see §9).

## 5. Architecture

```
Telegram bot ─┐                         ┌─ Router (Gemini Flash-Lite): domain, jurisdiction,
Web app ──────┼─► FastAPI ─► Pipeline ──┤   urgency, EN+AM search queries
              │                         ├─ Hybrid RAG retrieval over article-level corpus:
              │                         │    keyword (BM25, Ethiopic normalisation)
              │                         │  + semantic (Gemini embeddings, cross-language)
              │                         │  → reciprocal rank fusion
              │                         ├─ Reasoning (Gemini 2.5 Flash): answer / analysis,
              │                         │   structured JSON output
              │                         ├─ OCR (Gemini Flash vision)
              │                         └─ Citation verifier · E.C. date converter · disclaimer
              └─ SQLite: corpus + embedding cache + anonymous usage counters (no user content)
```

| Layer | Choice | Why |
|---|---|---|
| Backend | Python, FastAPI | Async, simple, same language as the AI tooling |
| AI provider | **Google Gemini** (default); Anthropic Claude as a switchable alternative | Gemini's free tier covers development and the pilot. Being able to switch avoids lock-in and allows quality comparison |
| Reasoning | Gemini 2.5 Flash | Multimodal, multilingual, structured outputs, low cost |
| Routing | Gemini 2.5 Flash-Lite | Cheapest model; classification only |
| OCR | Gemini Flash vision | Same provider; benchmark against Claude on Ethiopic |
| Embeddings | gemini-embedding-001 (768-dim) | Multilingual semantic search; free tier; cached per article |
| Retrieval | Hybrid BM25 + embeddings | Keyword precision for article numbers and legal terms, semantic reach across languages |
| Storage | SQLite → PostgreSQL + pgvector at scale | One database |
| Web | Static HTML/JS served by FastAPI | No build step; works on low-end phones |
| Telegram | python-telegram-bot | Photo/PDF intake, language picker |
| Hosting | Railway/Render (pilot) | Zero-config; review data residency before scale |

**Provider strategy.**

| Stage | Tier | Data |
|---|---|---|
| Development and internal testing | Gemini **free tier** | Test documents and public law text only |
| Pilot with real users | Gemini **paid tier** | Paid tier keeps prompts out of Google's product training. Cost is still low (see §10) |
| Production | Gemini paid, or Claude | Chosen by the §9 evaluation, per task |

## 6. Legal knowledge base

**Layer 1 — Federal core** [verify all numbers]
Civil Code (1960) · Revised Family Code (Proc. 213/2000) · Criminal Code
(Proc. 414/2004) · Civil Procedure Code (1965) · Criminal Procedure Code (1961) ·
Labour Proclamation 1156/2019 · Urban Lands Lease Holding Proc. 721/2011 · Rural
Land Administration and Land Use Proc. 456/2005 · Expropriation Proc. 1161/2019 ·
Commercial Code Proc. 1243/2021 · Investment Proc. 1180/2020 · Federal Income Tax
Proc. 979/2016, Tax Administration Proc. 983/2016, current VAT proclamation ·
Personal Data Protection Proc. 1321/2024.

**Layer 2 — Directives:** Ministry of Revenues, National Bank of Ethiopia, Ministry
of Trade and Regional Integration licensing, Ministry of Justice procedures.

**Layer 3 — Regional/city:** Dire Dawa Charter (Proc. 416/2004) and city land and
business regulations; Oromia, Somali, Amhara, Tigray and other regional land and
family laws.

**Corpus governance**
- Source: official Negarit Gazeta / regional gazette text only, with URL or scan
  reference stored per law.
- Each law has a `status` (in force / repealed). Repealed articles are never retrieved.
- Amharic is the authoritative version of federal law. Where both exist, ingest both.
- A licensed lawyer signs off each law before it goes live.

## 7. Target users

**Primary:** peri-urban residents receiving leases, contracts, summonses and eviction
notices; people with upcoming hearings; workers in wage or dismissal disputes;
smallholders facing lease renewals, boundary disputes or expropriation notices.

**Secondary:** legal-aid NGOs and paralegals (field triage), law students, small
businesses (licensing, tax), researchers.

## 8. Privacy, ethics and regulation

- **Nothing stored by Fitih AI:** documents are processed in memory. Conversations
  live in memory for 30 minutes and are then gone. Usage counters hold only salted hashes.
- **Consent for AI processing:** users are told their document is sent to an AI
  provider outside Ethiopia. Provider retention terms are reviewed and disclosed, in
  line with the Personal Data Protection Proclamation.
- **No free-tier AI for real user data:** on the Gemini free tier, Google may use
  content to improve its products. The free tier is used only for development and
  public law text. The paid tier is enabled before any real user data is processed.
- **Legal information, not legal advice:** positioned and worded as such. There are
  referral paths to licensed advocates and legal-aid centres, and the bar / Attorney
  General is consulted before public launch.
- **Access equity:** the citizen tier is free, Telegram works on low-end phones,
  and Amharic is the default.

## 9. Evaluation (how we will know it works)

| Metric | How measured | Target before public launch |
|---|---|---|
| Citation precision | Lawyer checks: does the cited article support the statement? | ≥ 95% |
| Answer correctness | Gold set of 300 questions (6 domains × 4 languages), lawyer-graded | ≥ 85% "correct & safe" |
| Risk-flag precision / recall | 100 real documents annotated by lawyers | ≥ 85% / ≥ 80% on 🔴 |
| Deadline extraction | Same 100 documents | ≥ 95% exact |
| OCR character error rate | 50 printed + 50 handwritten Ethiopic docs, per provider | Choose best provider |
| Refusal to invent | Questions outside the corpus → says "not in library" | ≥ 98% |
| Language quality | Native-speaker fluency rating (1–5) per language | ≥ 4.0 |

Impact metrics: monthly active users by channel and language; document types
analysed; user-reported outcome ("did this help you act?"); NGO field-worker adoption.

## 10. Costs

Assumptions **[verify current prices]**: Gemini 2.5 Flash about $0.30 / $2.50 per
million input/output tokens, Flash-Lite about $0.10 / $0.40, gemini-embedding-001
about $0.15 per million tokens, and 1 USD ≈ 150 ETB. Claude figures are shown for comparison.

| Operation | Tokens (in / out, approx.) | Gemini paid | Claude (Sonnet 5 + Haiku) |
|---|---|---|---|
| Question (router + embedding + grounded answer) | 5.7k / 1.8k | ~$0.006 (**~1 ETB**) | ~$0.024 (~3.6 ETB) |
| Document, 1–2 page photo (OCR + router + analysis) | 13k / 8k | ~$0.025 (**~4 ETB**) | ~$0.08 (~12 ETB) |
| Embedding the whole Layer-1 corpus once (~5,000 articles) | ~3M | ~$0.45, or free tier | — |

**Free tier:** within Google's daily and per-minute limits, development and a small
pilot cost **$0 in AI fees**. The limits change, so check AI Studio. The app retries
automatically on rate-limit errors, and search falls back to keyword-only if
embedding is throttled.

**Pilot budget (6 months, indicative):**

| Item | Estimate |
|---|---|
| AI API (10k questions + 2k documents / month) | ~$110 / month on Gemini paid tier (~$400 on Claude); $0 on free tier during development |
| Hosting | ~$30 / month |
| Lawyer review (corpus sign-off + evaluation grading) | largest line item; budget by hours |
| Corpus digitisation (typing / OCR QA of gazettes) | per-page contract |
| Community outreach in Dire Dawa | per NGO partner plan |

## 11. Roadmap

| Phase | Months | Deliverables |
|---|---|---|
| 0 — Done | — | Working prototype: web, Telegram, retrieval, citation verification, E.C. dates, tests |
| 1 — Corpus & evaluation | 1–2 | Layer-1 laws ingested and lawyer-verified; gold evaluation set; OCR benchmark |
| 2 — Pilot | 3–4 | Amharic + English pilot with one legal-aid partner in Dire Dawa; feedback loop |
| 3 — Languages & regions | 4–5 | Oromo and Tigrinya lawyer-reviewed; Somali evaluation; Dire Dawa, Oromia and Somali regional laws |
| 4 — Launch & scale | 6 | Public Telegram launch; NGO dashboard; embeddings if evaluation shows retrieval gaps; voice (ASR) research |

## 12. Sustainability

| Stream | Model |
|---|---|
| Citizens | **Free**, with a fair-use limit only to prevent abuse |
| NGOs / INGOs | Annual licence for field teams: usage dashboard, priority support |
| Government | White-label for woreda citizen-service centres and land offices |
| Law firms | Client intake tool: clients pre-analyse documents before paid consultations |
| API | Paid access to the verified, article-level corpus for legal-tech builders |

## 13. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Wrong or invented legal information | Server-side citation verification; "not in library" fallback; lawyer-graded evaluation gate |
| Outdated law | Status field per law; amendment monitoring; lawyer sign-off |
| Unauthorised-practice concerns | Information-only framing; referrals; early regulator engagement |
| Privacy / cross-border data | Nothing stored; consent notice; provider terms reviewed |
| Poor quality in lower-resource languages | Per-language evaluation; beta labelling until targets are met |
| Poor photos | Legibility rating; request a clearer photo |
| API cost or availability | Two providers behind one interface (switch with one setting); usage caps; licence revenue |
| Free-tier data use | Free tier only for development and public law text; paid tier before real users |
| Free-tier rate limits | Automatic retry and backoff; keyword-only fallback; move to paid tier for the pilot |

## 14. Team

*[Add: project lead, engineering lead, **licensed Ethiopian lawyer as legal lead**,
native-speaker reviewers for each language, NGO partner contact.]*

## 15. Conclusion

Fitih AI is not a chatbot with legal keywords. It is a grounded system built on
the actual text of Ethiopian law, checked against that text before it answers,
designed for the documents Ethiopians actually receive, and delivered through the
channel they already use. A working prototype already exists. The next step is
the part that makes it trustworthy: a lawyer-verified corpus and measured accuracy.

**ፍትህ ለሁሉም። — Justice for everyone.**
