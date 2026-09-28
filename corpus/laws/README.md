# Legal corpus

Put one file per law here (`.md` or `.txt`, UTF-8), then run:

```bash
python -m fitihai.cli ingest          # loads everything in corpus/laws/
python -m fitihai.cli laws            # check what was loaded
python -m fitihai.cli search "severance pay"   # test retrieval (no AI call)
```

**This folder ships empty on purpose.** Fitih AI must only cite the real, official
text of Ethiopian law. Do not paste summaries, blog posts or AI-generated text here.
Use the Negarit Gazeta (federal) or the regional gazette, and have a licensed
lawyer check each file before it goes live.

## Collecting laws from the web (many at once)

Most Ethiopian laws are online as Negarit Gazette PDFs, usually scans. The downloader
collects them and imports each one as a **draft**:

```bash
# 1. List the PDF links on a website's proclamations page, as a sources spreadsheet
python -m fitihai.cli discover https://<law-site>/proclamations --out corpus/sources/new.csv

# 2. Complete the spreadsheet (id, title, proclamation, domain, language for each row)
#    or fill in the url column of the ready-made list: corpus/sources/federal-core.csv

# 3. Download and import as drafts (--ocr reads scanned PDFs with the AI service)
python -m fitihai.cli fetch corpus/sources/federal-core.csv --ocr
```

The downloader:
- obeys each site's robots.txt, waits `FITIH_FETCH_DELAY` seconds between requests to one site, and identifies itself;
- caches every download in `data/downloads/`, so nothing is fetched twice;
- records the link, the file's SHA-256 fingerprint and the date in each law file (`source`, `source_sha256`, `fetched_on`), plus `text_source: ocr` when the text came from a scan;
- prints a line per law: imported, already in the library, failed (with the reason) or no link yet. One failure never stops the run.

Downloaded text is **not** approved text. Websites often carry unofficial retyped
copies, and OCR misreads letters and numbers. Review every draft against the gazette,
especially amounts, time limits and article numbers, before approving it. Prefer the
official sources (House of Peoples' Representatives, the Negarit Gazette). Laws and
official texts are generally not protected by Ethiopian copyright (confirm with your
lawyer), but respect each website's terms of use.

## Adding a law in the browser (easiest)

Open **`/admin`** on the running app and sign in with `FITIH_ADMIN_TOKEN`. Then:
**Import** the gazette PDF, or paste a link to it (tick **OCR** for scanned PDFs) → **Review** (fix any extraction errors; numbering gaps are
listed) → **Approve** (the reviewing lawyer's name) → **Publish changes**. The web app and
the Telegram bot use the law within 15 seconds.

## Adding a law from the command line

```bash
# 1. Convert the official PDF (it needs a text layer; OCR scanned copies first).
#    Bilingual gazettes: run once per language.
python -m fitihai.cli import gazette-1156.pdf --id labour-1156-2019-en \
    --title "Labour Proclamation" --proclamation 1156/2019 --year 2019 \
    --domain labor --language en --source "Federal Negarit Gazette, <issue>, <pages>"

# 2. Review corpus/laws/labour-1156-2019-en.md line by line against the gazette.
#    The importer prints any missing or out-of-order article numbers; check those first.

# 3. Approve. This sets status: in_force and records reviewed_by / reviewed_on.
python -m fitihai.cli approve corpus/laws/labour-1156-2019-en.md --by "Reviewer name"

# 4. Load it.
python -m fitihai.cli ingest --embed
```

Imported files start as `status: draft`. **Draft laws are stored but never searched
or cited**, so unreviewed text cannot reach users.

## File format

```text
---
id: labour-1156-2019              # unique, stable; used in citations (id:article)
title: Labour Proclamation
proclamation: 1156/2019
year: 2019
jurisdiction: federal             # federal | dire_dawa | oromia | somali | amhara | tigray | ...
domain: labor                     # labor | land | commercial | family | criminal | tax |
                                  # civil_procedure | administrative | other
language: en                      # am | en | om | ti
source: https://...               # official gazette link or scan reference
status: in_force                  # draft | in_force | repealed  (only in_force is retrieved)
reviewed_by: <name>               # set by `fitihai.cli approve`
reviewed_on: 2026-09-26           # set by `fitihai.cli approve`
---
Article 1. Short Title
This Proclamation may be cited as ...

Article 2. Definitions
...
```

Recognised article headings: `Article 12`, `Art. 12`, `ARTICLE 12`, `## Article 12`,
`አንቀጽ 12`, `አንቀጽ ፲፪` (Ge'ez numerals are converted to 12). Everything up to the
next heading belongs to that article. A line such as "Article 35 of this Proclamation …"
(the text after the number starts with a lowercase letter) is treated as a
cross-reference inside the article, not as a new heading.

**Bilingual laws:** ingest the Amharic and English versions as two files (for example
`labour-1156-2019-am` and `labour-1156-2019-en`). Amharic is the authoritative
version of federal law.

**Amendments:** when an article is amended, update the file and re-run `ingest`.
Re-ingesting a law replaces all of its articles. If a law is repealed, set
`status: repealed`.
