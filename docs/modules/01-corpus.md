# Module 01 — Corpus and Law Library

## 1. Purpose
Hold the official text of Ethiopian law, split into individual articles, so that
every answer can be based on (and cite) a specific article. The corpus is the
knowledge base behind all of Fitih AI's output. Its quality limits the quality of
the whole system.

## 2. Scope
**In scope**
- File format for law texts (front matter + article text).
- Parsing a law into articles, including Amharic/Tigrinya headings and Ge'ez numerals.
- Storing laws and articles in SQLite, replacing them on re-ingest, and marking laws repealed.
- Listing laws and article counts.
- Storage for the embedding cache and usage counters (the tables live here; the
  logic lives in modules 02 and 08).

**Out of scope**
- Obtaining or typing the law texts (an editorial process, see §10).
- Search and ranking (module 02).

## 3. Files
| File | Role |
|---|---|
| `fitihai/corpus/chunker.py` | Front-matter parser, article splitter, Ge'ez numeral conversion |
| `fitihai/corpus/store.py` | `CorpusStore`: SQLite schema, ingest, queries, embedding cache, usage counters |
| `fitihai/cli.py` | `ingest`, `embed`, `laws`, `search` commands |
| `corpus/laws/` | Where law files go (ships empty on purpose) |
| `corpus/laws/README.md` | Editor's guide to the file format |
| `tests/fixtures/*.md` | Two **fictional** laws used only by tests |

## 4. Interfaces

### Law file format
```text
---
id: labour-1156-2019          # required, unique, stable (used in citations)
title: Labour Proclamation    # required
proclamation: 1156/2019
year: 2019
jurisdiction: federal         # federal | dire_dawa | oromia | somali | amhara | tigray | ...
domain: labor                 # required: labor | land | commercial | family | criminal | tax |
                              #   civil_procedure | administrative | other
language: en                  # required: am | en | om | ti
source: https://...           # official gazette link or scan reference
status: in_force              # in_force (default) | repealed
---
Article 1. Short Title
This Proclamation may be cited as ...
```

Recognised article headings: `Article 12`, `ARTICLE 12`, `Art. 12`, `## Article 12`,
`አንቀጽ 12`, `አንቀፅ 12`, `ዓንቀጽ 12`, `አንቀጽ ፲፪`. They can be followed by `.`, `:`, `-`, `–`, `—` or `)`.
Text before the first heading (preamble) is ignored.

### Python API
| Function / class | Description |
|---|---|
| `parse_law(raw: str) -> LawDocument` | Parse one file; raises `ValueError` on bad format |
| `split_articles(body: str) -> list[Article]` | Split body text into articles |
| `geez_to_int("፻፳፫") -> 123` | Ge'ez numeral conversion |
| `CorpusStore(db_path)` | Opens or creates the database |
| `.upsert_law(law) -> int` | Replace a law and its articles; returns article count |
| `.ingest_dir(path) -> {law_id: count}` | Ingest every `.md`/`.txt` except `README.md` |
| `.all_articles() -> list[ArticleRecord]` | All articles of laws with `status = in_force` |
| `.list_laws() -> list[dict]` | Laws with article counts |
| `ArticleRecord.citation` | Human-readable citation, e.g. `Labour Proclamation (Proclamation No. 1156/2019), Art. 39` |

### CLI
```bash
python -m fitihai.cli ingest [DIR] [--embed]
python -m fitihai.cli laws
python -m fitihai.cli search "severance pay" -k 5
```

## 5. Design and flow
1. **Parse front matter.** The file must start with `---`. Required keys are checked.
2. **Split articles.** A regular expression finds article headings line by line.
   Everything up to the next heading belongs to the current article.
3. **Normalise numbers.** Ge'ez numerals are converted to Arabic digits so that
   `አንቀጽ ፲፪` and `Article 12` get the same ID.
4. **Make IDs unique.** The ID is `<law id>:<number>`. If a number repeats (for
   example across parts or schedules), later copies get `-2`, `-3`.
5. **Replace, don't merge.** Re-ingesting a law deletes its old articles first, so
   amended text never lives next to the old text.
6. **Only in-force law is searchable.** `all_articles()` filters on `status`.

**Database tables:** `laws`, `articles` (cascade delete), `embeddings`
(model + text hash → vector, see module 02) and `usage` (module 08).

**Design decisions**
- *Article-level granularity:* citations must point at one article. Longer chunks
  would make verification vague.
- *Plain-text source files in git:* lawyers can review changes as diffs, and the
  history of every edit is kept.
- *Bilingual laws are stored as two files* (for example `...-am` and `...-en`).
  Amharic is the authoritative version of federal law.

## 6. Configuration
| Variable | Default | Meaning |
|---|---|---|
| `FITIH_DB` | `data/fitihai.db` | SQLite file |
| `FITIH_CORPUS_DIR` | `corpus/laws` | Default folder for `ingest` |

## 7. Data, privacy and security
- The corpus contains **public law text only**. It holds no user data.
- Sending corpus text to the embedding API (including a free tier) raises no
  privacy issue.
- **Integrity matters more than confidentiality:** a wrong article is a safety
  problem. Only official gazette text may be added, and each law needs lawyer sign-off.

## 8. Error handling
| Situation | Behaviour |
|---|---|
| No `---` front matter, or a required key is missing | `ValueError` naming the problem. Ingest stops so the error is noticed |
| No article headings found | `ValueError` telling the editor to check the headings |
| Invalid Ge'ez numeral | `ValueError` |
| Duplicate article numbers | Kept, with suffixed IDs |

## 9. Testing
`tests/test_core.py`: `test_geez_numerals`, `test_split_articles_english_and_amharic`,
`test_parse_law_requires_front_matter`, `test_ingest`.
To check by hand: `python -m fitihai.cli ingest tests/fixtures && python -m fitihai.cli laws`.

## 10. Limitations and next steps
- **The corpus is empty.** Phase 1 work: type or OCR the Layer-1 federal laws from
  the Negarit Gazeta, then do a lawyer QA pass on each law.
- Sub-articles (e.g. Art. 39(1)(b)) are not split out. The whole article is cited.
- There is no automatic tracking of amendments. An editor must update files when
  the gazette publishes changes. Add an `amended_by` field and a change log.
- Schedules, tables and annexes are not handled specially.
- Consider adding a `version_date` per law so answers can say "text as of …".
