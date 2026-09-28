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
| `fitihai/admin.py` | Admin console API: the same workflow in the browser (see module 09) |
| `web/admin.html`, `web/admin.js` | Admin console page (`/admin`) |
| `fitihai/corpus/importer.py` | Gazette PDF/text → draft corpus file (OCR fallback for scans); `approve` records the reviewer |
| `fitihai/corpus/fetcher.py` | Web downloader: `discover` PDF links on a page; `fetch_sources` downloads a sources list and imports drafts |
| `corpus/sources/federal-core.csv` | Ready-made sources list of the Layer-1 federal laws (links to be filled in) |
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
status: in_force              # draft | in_force (default) | repealed
reviewed_by: <name>           # written by `fitihai.cli approve`
reviewed_on: YYYY-MM-DD       # written by `fitihai.cli approve`
---
Article 1. Short Title
This Proclamation may be cited as ...
```

Recognised article headings: `Article 12`, `ARTICLE 12`, `Art. 12`, `## Article 12`,
`አንቀጽ 12`, `አንቀፅ 12`, `ዓንቀጽ 12`, `አንቀጽ ፲፪`. They can be followed by `.`, `:`, `-`, `–`, `—` or `)`.
Text before the first heading (preamble) is ignored. A heading whose text starts
with a lowercase letter ("Article 35 of this Proclamation …") is a cross-reference
and stays inside the current article.

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
| `import_law(src, out, meta) -> (count, issues)` | Gazette PDF/text → `status: draft` file; `issues` lists missing or out-of-order article numbers |
| `approve(path, reviewer)` | Sets `status: in_force`, `reviewed_by`, `reviewed_on`; refuses a file that does not parse |
| `numbering_issues(articles)` | Gaps, repeats and out-of-order numbers |
| `ArticleRecord.citation` | Human-readable citation, e.g. `Labour Proclamation (Proclamation No. 1156/2019), Art. 39` |

### CLI
```bash
python -m fitihai.cli import gazette.pdf --id labour-1156-2019-en --title "Labour Proclamation" \
    --proclamation 1156/2019 --year 2019 --domain labor --language en --source "..."
python -m fitihai.cli approve corpus/laws/labour-1156-2019-en.md --by "Reviewer name"
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

**Corpus version and auto-reload.** Every ingest stores a new *corpus version* in the
database (`meta` table). The web server and the Telegram bot each check it at most every
15 seconds and reload their search index when it changes, so a law published from the
admin console reaches both channels without a restart. SQLite runs in WAL mode so both
processes can share the file. A lock serialises access within a process.

**Prune.** Loading the main corpus folder (`ingest` with no directory, or **Publish
changes** in the admin console) mirrors the folder exactly: laws whose file was deleted
are removed from the index.

**Collecting from the web.** `fitihai.cli discover <page>` lists the PDF links on a
page as a sources spreadsheet (`id,title,proclamation,year,domain,language,jurisdiction,url,source`).
`fitihai.cli fetch <sources.csv> [--ocr]` then downloads each PDF and imports it as a
draft. The downloader:
- obeys robots.txt and waits `FITIH_FETCH_DELAY` seconds between requests to one host;
- sends a User-Agent with `FITIH_FETCH_CONTACT`, and retries on 429 or 5xx with backoff;
- limits files to 100 MB, and caches downloads (by URL hash) in `data/downloads/`;
- rejects links that don't return a PDF;
- records `source`, `source_sha256` and `fetched_on`;
- reports each row as imported, exists, no-url, invalid or failed, and one failure never stops the run.

**Scanned gazettes (OCR).** If a PDF has almost no text layer, the importer splits it
into 4-page PDFs (pypdf) and sends each to the AI provider's `transcribe`, which uses the
verbatim OCR prompt from module 03. The pieces are joined, cleaned and parsed like any
other text, and the file records `text_source: ocr`. The admin console flags such
drafts, and reviewers must check numbers and Ge'ez characters closely. Without OCR,
a scanned PDF is rejected with a message saying to use `--ocr`.

**Import and review workflow**
```
gazette PDF ─► import (strip page headers/footers and page numbers, keep one language,
               re-join hyphenated words, validate) ─► status: draft   (stored, never cited)
            ─► reviewer checks each article against the gazette, fixes errors
            ─► approve --by <name> ─► status: in_force + reviewed_by/on ─► ingest --embed
```
The admin console (`/admin`) runs the same workflow in the browser: **Import** →
**Review** (numbering checks, article list, editable text) → **Approve** (reviewer name
plus a confirmation that every article was compared with the gazette) → **Publish
changes**. The server enforces the rules, not the page. Any edit to a law's text resets
it to draft and clears the approval. Only drafts can be deleted, and approved laws are
repealed instead, so there is always a record.
Bilingual gazettes print Amharic and English side by side. Importing with
`--language en` drops lines that are mostly Ge'ez script, and `--language am`
drops lines that are mostly Latin script. Each language becomes its own file.

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
`tests/test_importer.py`: header/footer and language cleaning, draft laws are not
searchable, approval records the reviewer, import from a real (generated) PDF,
rejection of scanned PDFs, cross-references are not headings, numbering issues,
and the CLI `import`/`approve` commands. `tests/test_fetcher.py` runs a local web
server with a text PDF, a scanned 9-page PDF, an HTML page posing as a PDF, a missing
file and a robots.txt-blocked folder. It covers discovery, robots.txt, drafts not being
searchable, OCR in 4-page batches, one failure not stopping the run, caching (a
second run makes no requests), the shipped sources list, and the CLI.
To check by hand: `python -m fitihai.cli ingest tests/fixtures && python -m fitihai.cli laws`.

## 10. Limitations and next steps
- **The corpus is empty.** Phase 1 work: import the Layer-1 federal laws from the
  Negarit Gazeta with `fitihai.cli import`, then do a lawyer QA pass on each law and
  run `approve`.
- OCR quality on scanned Ge'ez gazettes is unmeasured: benchmark it on a few laws before
  bulk imports. The two-column layout may interleave sentences, which the reviewer must fix.
- The downloader is generic (PDF links and a sources list). Site-specific crawlers,
  for example to follow pagination, can be added once the target sites are chosen.
- Sub-articles (e.g. Art. 39(1)(b)) are not split out. The whole article is cited.
- There is no automatic tracking of amendments. An editor must update files when
  the gazette publishes changes. Add an `amended_by` field and a change log.
- Schedules, tables and annexes are not handled specially.
- Consider adding a `version_date` per law so answers can say "text as of …".
