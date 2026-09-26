"""Command line: ingest the corpus, list laws, test retrieval, ask a question.

    python -m fitihai.cli ingest [DIR]
    python -m fitihai.cli laws
    python -m fitihai.cli search "severance pay after dismissal"
    python -m fitihai.cli ask "..." --lang am
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import settings
from .corpus.store import CorpusStore
from .retrieval import BM25Index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fitihai")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_ingest = sub.add_parser("ingest", help="load law files into the database")
    p_ingest.add_argument("directory", nargs="?", default=str(settings.corpus_dir))
    sub.add_parser("laws", help="list ingested laws")
    p_search = sub.add_parser("search", help="test retrieval without calling the AI")
    p_search.add_argument("query")
    p_search.add_argument("-k", type=int, default=5)
    p_ask = sub.add_parser("ask", help="ask a question (calls Claude)")
    p_ask.add_argument("question")
    p_ask.add_argument("--lang", default="en")
    args = parser.parse_args(argv)

    store = CorpusStore(settings.db_path)
    if args.cmd == "ingest":
        results = store.ingest_dir(Path(args.directory))
        for law_id, n in results.items():
            print(f"  {law_id}: {n} articles")
        print(f"Ingested {len(results)} laws into {settings.db_path}")
    elif args.cmd == "laws":
        for law in store.list_laws():
            print(f"{law['id']:<32} {law['domain']:<16} {law['article_count']:>5} arts  {law['title']}")
    elif args.cmd == "search":
        for hit in BM25Index(store.all_articles()).search([args.query], top_k=args.k):
            print(f"{hit.score:6.2f}  {hit.article.citation}  — {hit.article.heading}")
    elif args.cmd == "ask":
        from .llm import ClaudeLegalModel
        from .pipeline import Advisor

        res = Advisor(settings, store, ClaudeLegalModel(settings)).ask(args.question, language=args.lang)
        print(res.answer)
        for c in res.citations:
            print(f"  • {c.citation}")
        print(f"\n{res.disclaimer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
