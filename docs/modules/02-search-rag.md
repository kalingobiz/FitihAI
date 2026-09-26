# Module 02 — Search / RAG (Retrieval-Augmented Generation)

## 1. Purpose
For every question or document, find the handful of law articles that actually
apply, and give only those to the AI. This is what makes answers *grounded*: the
model explains law it has been shown, instead of recalling law from memory.

## 2. Scope
**In scope:** keyword search (BM25), semantic search (Gemini embeddings), merging
the two rankings, domain and jurisdiction preferences, the embedding cache, and the
fallback when semantic search fails.
**Out of scope:** choosing the search terms (done by the router, module 03/04) and
checking citations after the answer (module 04).

## 3. Files
| File | Role |
|---|---|
| `fitihai/retrieval.py` | Ethiopic tokeniser, `BM25Index`, `reciprocal_rank_fusion` |
| `fitihai/embeddings.py` | `GeminiEmbedder`, `VectorIndex`, `embed_corpus`, `load_vector_index` |
| `fitihai/pipeline.py` | `Advisor._retrieve()` combines everything |
| `fitihai/corpus/store.py` | `load_embeddings` / `save_embeddings` (cache table) |

## 4. Interfaces
| Function | Input → Output |
|---|---|
| `tokenize(text)` | text → tokens (folded Ethiopic words + syllable bigrams; English words + 6-letter stems) |
| `BM25Index(articles).search(queries, top_k, domains, jurisdictions)` | several queries → `list[Hit(article, score)]` |
| `GeminiEmbedder.embed_documents(texts)` / `.embed_query(text)` | text → 768-dim vectors |
| `VectorIndex(ids, vectors).search(qvec, top_k)` | vector → `[(article_id, cosine)]` |
| `reciprocal_rank_fusion(rankings, k=60)` | several ranked ID lists → one fused list |
| `embed_corpus(store, embedder, articles) -> int` | embeds only articles with no cached vector |
| `Advisor._retrieve(queries, domain, jurisdiction, semantic_text)` | → up to `top_k` `ArticleRecord`s |

CLI: `python -m fitihai.cli embed` (or `ingest --embed`); `python -m fitihai.cli search "…"` (keyword only).

## 5. Design and flow
```
queries = [original text] + router's English queries + router's Amharic queries
      │
      ├─► BM25 keyword search ─── top 30 (articles outside the classified domain get half score)
      │
      ├─► embed(original text) ─► cosine search ─── top 30          (skipped if no embeddings)
      │
      └─► reciprocal rank fusion ─► drop other regions' laws ─► first top_k (8) articles
```

**Ethiopic keyword handling**
- *Homophone folding:* Amharic spelling varies between letters that sound the
  same. ሐ/ኀ → ሀ, ሠ → ሰ, ዐ → አ and ፀ → ጸ are folded (all seven vowel orders), so
  `ሠራተኛ` matches `ሰራተኛ`.
- *Syllable bigrams:* Amharic words take prefixes and suffixes (የ-, -ን, -ዎች …).
  Two-syllable pieces let inflected forms match the statute's wording.
- *English:* stop-words are dropped, and a crude 6-letter stem (`employ~`) links
  employer/employment/employee.

**Semantic search (Gemini `gemini-embedding-001`)**
- Articles are embedded as `"<law title>, Article N. <heading>\n<text>"` with task
  type `RETRIEVAL_DOCUMENT`. Queries use `RETRIEVAL_QUERY`.
- Vectors are **cached by SHA-256 of that text**. Re-ingesting unchanged laws costs
  nothing, and a changed article is re-embedded automatically.
- Multilingual embeddings connect an Amharic or Oromo question to an English
  article, which keyword search cannot do on its own.

**Why hybrid?** Keyword search is precise for article numbers, proclamation
numbers and fixed legal terms. Embeddings capture meaning across languages. Rank
fusion needs no score calibration between the two, and an item that ranks well in
both lists rises to the top.

**Jurisdiction rule:** federal law is always eligible. Regional or city law is
kept only if it matches the jurisdiction the router detected (for example
`dire_dawa`). When the jurisdiction is unknown, nothing is excluded.

## 6. Configuration
| Variable | Default | Meaning |
|---|---|---|
| `FITIH_EMBEDDINGS` | `gemini` | `gemini` = hybrid, `none` = keyword only |
| `FITIH_EMBEDDING_MODEL` | `gemini-embedding-001` | Embedding model |
| `FITIH_EMBEDDING_DIM` | `768` | Output dimensionality |
| `FITIH_TOP_K` | `8` | Articles passed to the AI |
| `CANDIDATES` (constant) | `30` | Candidates per retriever before fusion |
| `BATCH_SIZE` (constant) | `100` | Texts per embedding request |

## 7. Data, privacy and security
- Corpus embeddings contain public law only.
- **Query embeddings send the user's question (or the first 2,000 characters of
  their document) to Google.** On the free tier this may be used to improve
  Google's products. Use the paid tier with real users (see module 08).
- The embedding cache stores vectors of law text only, never of user queries.

## 8. Error handling
| Situation | Behaviour |
|---|---|
| Embedding API error or rate limit during a request | Logged as a warning; **keyword-only results are returned** |
| Rate limit (429) or 5xx | The SDK retries 4 times with backoff (2–30 s) |
| Some articles have no vector | Warning at start-up asking you to run `fitihai.cli embed`; those articles remain keyword-searchable |
| Embedding fails during `ingest --embed` | Warning printed and exit code 0, so the server still starts |
| No matches at all | Empty list; the answer then says the law is not in the library (module 04) |

## 9. Testing
- `tests/test_core.py`: `test_ethiopic_homophones_fold`, `test_bm25_finds_relevant_article`.
- `tests/test_gemini_rag.py`: `test_rrf_prefers_items_ranked_by_both`, `test_vector_index_cosine`,
  `test_embeddings_are_cached_by_text`, `test_semantic_search_bridges_languages` (an
  Amharic query finds an English article only through embeddings),
  `test_semantic_failure_falls_back_to_keywords`.
- To check by hand: `python -m fitihai.cli search "…"` shows keyword ranking.

## 10. Limitations and next steps
- Measure retrieval with the evaluation set (module 12): *recall@8* = is the
  correct article among the 8 given to the AI?
- The vector search is brute-force in memory. That is fine up to roughly 50k
  articles. Beyond that, move to PostgreSQL + pgvector.
- Afaan Oromo keyword search has no stemming yet.
- Add an optional re-ranking step if evaluation shows the right article is often
  ranked 9th–30th.
- A domain-specific Amharic legal synonym list would help BM25.
