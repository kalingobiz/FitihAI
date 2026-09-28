"""Command line: ingest the corpus, list laws, test retrieval, ask a question.

    python -m fitihai.cli ingest [DIR] [--embed]
    python -m fitihai.cli embed
    python -m fitihai.cli import gazette.pdf --id labour-1156-2019-en --title "Labour Proclamation" \
        --proclamation 1156/2019 --year 2019 --domain labor --language en --source "..."
    python -m fitihai.cli approve corpus/laws/labour-1156-2019-en.md --by "Reviewer name"
    python -m fitihai.cli discover https://example.org/proclamations --out corpus/sources/new.csv
    python -m fitihai.cli fetch corpus/sources/federal-core.csv [--ocr]
    python -m fitihai.cli laws
    python -m fitihai.cli search "severance pay after dismissal"
    python -m fitihai.cli ask "..." --lang am
    python -m fitihai.cli eval eval/datasets/qa.jsonl [--label gemini-flash]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import settings
from .corpus.store import CorpusStore
from .retrieval import BM25Index


def _embed(store: CorpusStore) -> None:
    from .embeddings import build_embedder, embed_corpus

    embedder = build_embedder(settings)
    if embedder is None:
        print("FITIH_EMBEDDINGS=none; skipping embeddings (keyword search only)")
        return
    try:
        n = embed_corpus(store, embedder, store.all_articles())
    except Exception as exc:  # keep start-up alive; keyword search still works
        print(f"WARNING: embedding failed ({exc}); semantic search disabled until `fitihai.cli embed` succeeds")
        return
    print(f"Embedded {n} new articles with {embedder.model}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fitihai")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_ingest = sub.add_parser("ingest", help="load law files into the database")
    p_ingest.add_argument("directory", nargs="?", default=str(settings.corpus_dir))
    p_ingest.add_argument("--embed", action="store_true", help="also compute embeddings for semantic search")
    sub.add_parser("embed", help="compute embeddings for articles that have none (Gemini)")
    p_import = sub.add_parser("import", help="convert a gazette PDF/text into a DRAFT corpus file")
    p_import.add_argument("path")
    p_import.add_argument("--id", required=True)
    p_import.add_argument("--title", required=True)
    p_import.add_argument("--domain", required=True)
    p_import.add_argument("--language", required=True, choices=["am", "en", "om", "ti"])
    p_import.add_argument("--proclamation", default="")
    p_import.add_argument("--year", default="")
    p_import.add_argument("--jurisdiction", default="federal")
    p_import.add_argument("--source", default="", help="gazette issue, page, or official URL")
    p_import.add_argument("--out", help="default: <corpus dir>/<id>.md")
    p_import.add_argument("--overwrite", action="store_true")
    p_approve = sub.add_parser("approve", help="mark a reviewed corpus file as in force")
    p_approve.add_argument("path")
    p_approve.add_argument("--by", required=True, help="name of the reviewing lawyer")
    p_disc = sub.add_parser("discover", help="list the PDF links on a web page (to build a sources list)")
    p_disc.add_argument("url")
    p_disc.add_argument("--match", help="regex on link URL or text instead of '.pdf' links")
    p_disc.add_argument("--out", help="write a sources CSV skeleton to this file")
    p_fetch = sub.add_parser("fetch", help="download the PDFs in a sources CSV and import them as DRAFTS")
    p_fetch.add_argument("sources", help="CSV: id,title,proclamation,year,domain,language,jurisdiction,url,source")
    p_fetch.add_argument("--ocr", action="store_true", help="OCR scanned PDFs with the AI provider")
    p_fetch.add_argument("--overwrite", action="store_true", help="replace laws already in the library")
    p_fetch.add_argument("--only", nargs="*", help="fetch only these ids")
    sub.add_parser("laws", help="list ingested laws")
    p_search = sub.add_parser("search", help="test retrieval without calling the AI")
    p_search.add_argument("query")
    p_search.add_argument("-k", type=int, default=5)
    p_ask = sub.add_parser("ask", help="ask a question (calls the configured AI provider)")
    p_ask.add_argument("question")
    p_ask.add_argument("--lang", default="en")
    p_eval = sub.add_parser("eval", help="run an evaluation dataset (calls the AI provider)")
    p_eval.add_argument("datasets", nargs="+", help="one or more .jsonl files")
    p_eval.add_argument("--out", default="eval/results")
    p_eval.add_argument("--label", default="", help="short name for this run, e.g. the model")
    args = parser.parse_args(argv)

    # These commands only touch files; everything else needs the database.
    store = CorpusStore(settings.db_path) if args.cmd not in ("import", "approve", "discover", "fetch") else None
    if args.cmd == "ingest":
        directory = Path(args.directory)
        # Loading the main corpus folder mirrors it exactly (laws whose file was deleted are removed).
        prune = directory.resolve() == settings.corpus_dir.resolve()
        results = store.ingest_dir(directory, prune=prune)
        for law_id, n in results.items():
            print(f"  {law_id}: {n} articles")
        print(f"Ingested {len(results)} laws into {settings.db_path}")
        if args.embed:
            _embed(store)
    elif args.cmd == "embed":
        _embed(store)
    elif args.cmd == "import":
        from .corpus.importer import import_law

        meta = {k: getattr(args, k) for k in
                ("id", "title", "proclamation", "year", "jurisdiction", "domain", "language", "source")}
        out = Path(args.out) if args.out else settings.corpus_dir / f"{args.id}.md"
        n, issues = import_law(Path(args.path), out, meta, overwrite=args.overwrite)
        print(f"Wrote {out} with {n} articles (status: draft).")
        if issues:
            print("Check these places first; the PDF text may have been extracted incorrectly:")
            for issue in issues:
                print(f"  - {issue}")
        print("Check every article against the gazette, fix any errors, then run:")
        print(f"  python -m fitihai.cli approve {out} --by \"<reviewer name>\"")
    elif args.cmd == "approve":
        from .corpus.importer import approve

        meta = approve(Path(args.path), args.by)
        print(f"Approved {meta['id']} (reviewed by {meta['reviewed_by']} on {meta['reviewed_on']}). "
              "Run `ingest --embed` to make it searchable.")
    elif args.cmd in ("discover", "fetch"):
        from .corpus.fetcher import Fetcher, discover, fetch_sources, read_sources, write_sources_skeleton

        fetcher = Fetcher(settings.fetch_delay_seconds, contact=settings.fetch_contact,
                          cache_dir=settings.download_cache_dir)
        if args.cmd == "discover":
            links = discover(fetcher, args.url, args.match)
            for url, text in links:
                print(f"{url}\t{text}")
            print(f"{len(links)} link(s) found.")
            if args.out:
                write_sources_skeleton(links, Path(args.out))
                print(f"Wrote {args.out}: fill in id, domain and language for each law you want, then run fetch.")
        else:
            rows = read_sources(Path(args.sources))
            if args.only:
                rows = [r for r in rows if r.get("id") in set(args.only)]
            ocr = None
            if args.ocr:
                from .llm import build_model

                ocr = build_model(settings).transcribe
            results = fetch_sources(rows, settings.corpus_dir, fetcher, ocr=ocr, overwrite=args.overwrite)
            for r in results:
                detail = f"{r.articles} articles ({r.text_source})" if r.status == "imported" else r.message
                print(f"  {r.status:<9} {r.id:<40} {detail}")
                for issue in r.issues[:5]:
                    print(f"            check: {issue}")
            imported = sum(r.status == "imported" for r in results)
            print(f"{imported} imported as draft, {sum(r.status == 'failed' for r in results)} failed, "
                  f"{sum(r.status in ('no-url', 'exists', 'invalid') for r in results)} skipped.")
            if imported:
                print("Next: review each draft in /admin (or corpus/laws/), approve, then publish.")
    elif args.cmd == "laws":
        for law in store.list_laws():
            print(f"{law['id']:<32} {law['domain']:<16} {law['status']:<9} {law['article_count']:>5} arts  "
                  f"{law['title']}")
    elif args.cmd == "search":
        for hit in BM25Index(store.all_articles()).search([args.query], top_k=args.k):
            print(f"{hit.score:6.2f}  {hit.article.citation}  — {hit.article.heading}")
    elif args.cmd == "ask":
        from .embeddings import build_embedder
        from .llm import build_model
        from .pipeline import Advisor

        advisor = Advisor(settings, store, build_model(settings), build_embedder(settings))
        res = advisor.ask(args.question, language=args.lang)
        print(res.answer)
        for c in res.citations:
            print(f"  • {c.citation}")
        print(f"\n{res.disclaimer}")
    elif args.cmd == "eval":
        from .embeddings import build_embedder
        from .evaluation import TARGETS, load_dataset, run, summarize, write_report
        from .llm import build_model
        from .pipeline import Advisor

        items = [item for path in args.datasets for item in load_dataset(Path(path))]
        advisor = Advisor(settings, store, build_model(settings), build_embedder(settings))
        print(f"Running {len(items)} items with {settings.llm_provider} …")
        results = run(advisor, items)
        summary = summarize(results)
        run_dir = write_report(results, summary, Path(args.out), args.label)
        for key, value in summary.items():
            target = TARGETS.get(key)
            mark = "" if target is None or value is None else ("  ok" if value >= target else f"  below target {target:.0%}")
            print(f"  {key:<32} {value if value is not None else 'n/a'}{mark}")
        print(f"Report: {run_dir / 'report.md'}   Lawyer grading sheet: {run_dir / 'grading.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
