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
status: in_force                  # in_force | repealed  (repealed laws are never retrieved)
---
Article 1. Short Title
This Proclamation may be cited as ...

Article 2. Definitions
...
```

Recognised article headings: `Article 12`, `Art. 12`, `ARTICLE 12`, `## Article 12`,
`አንቀጽ 12`, `አንቀጽ ፲፪` (Ge'ez numerals are converted to 12). Everything up to the
next heading belongs to that article.

**Bilingual laws:** ingest the Amharic and English versions as two files (for example
`labour-1156-2019-am` and `labour-1156-2019-en`). Amharic is the authoritative
version of federal law.

**Amendments:** when an article is amended, update the file and re-run `ingest`.
Re-ingesting a law replaces all of its articles. If a law is repealed, set
`status: repealed`.
