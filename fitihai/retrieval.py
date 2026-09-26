"""Article retrieval over the legal corpus.

A dependency-free BM25 index with tokenisation tuned for Ethiopic script:
homophone letters (ሀ/ሐ/ኀ, ሰ/ሠ, አ/ዐ, ጸ/ፀ) are folded together, and Ethiopic
words also contribute character bigrams so inflected forms still match.

Cross-language matching (e.g. an Amharic question against an English law) is
handled two ways: the router writes search queries in both English and Amharic,
and (optionally) Gemini embeddings add semantic search. The two rankings are
merged with reciprocal rank fusion.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable, Sequence

from .corpus.store import ArticleRecord

# Ethiopic homophone families: (variant block start, canonical block start).
_HOMOPHONES = [(0x1210, 0x1200), (0x1280, 0x1200), (0x1220, 0x1230), (0x12D0, 0x12A0), (0x1340, 0x1338)]
_FOLD: dict[int, int] = {}
for _src, _dst in _HOMOPHONES:
    for _i in range(7):
        _FOLD[_src + _i] = _dst + _i

_TOKEN_RE = re.compile(r"[\wሀ-፿]+", re.UNICODE)
_ETHIOPIC_RE = re.compile(r"[ሀ-፿]")

EN_STOPWORDS = frozenset(
    "a an and are as at be by can do does for from has have how i if in is it its my "
    "of on or shall should than that the their them there this to under was what when "
    "where which who will with without would you your me any may not no".split()
)


def fold_ethiopic(text: str) -> str:
    return text.translate(_FOLD)


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(fold_ethiopic(text.lower())):
        if _ETHIOPIC_RE.search(raw):
            tokens.append(raw)
            if len(raw) >= 3:
                tokens.extend(raw[i : i + 2] for i in range(len(raw) - 1))
        else:
            if raw in EN_STOPWORDS or len(raw) < 2:
                continue
            tokens.append(raw)
            if len(raw) > 6:
                tokens.append(raw[:6] + "~")  # crude stem: employ~ matches employer/employment
    return tokens


@dataclass(frozen=True)
class Hit:
    article: ArticleRecord
    score: float


class BM25Index:
    def __init__(self, articles: Sequence[ArticleRecord], k1: float = 1.5, b: float = 0.75):
        self.articles = list(articles)
        self.k1, self.b = k1, b
        self.doc_tf: list[Counter[str]] = []
        self.doc_len: list[int] = []
        df: Counter[str] = Counter()
        for a in self.articles:
            # Heading and law title are weighted by repetition.
            tokens = tokenize(f"{a.heading} {a.heading} {a.law_title} {a.text}")
            tf = Counter(tokens)
            self.doc_tf.append(tf)
            self.doc_len.append(len(tokens))
            df.update(tf.keys())
        n = len(self.articles)
        self.avgdl = (sum(self.doc_len) / n) if n else 0.0
        self.idf = {term: math.log(1 + (n - f + 0.5) / (f + 0.5)) for term, f in df.items()}
        self.postings: dict[str, list[int]] = defaultdict(list)
        for i, tf in enumerate(self.doc_tf):
            for term in tf:
                self.postings[term].append(i)

    def __len__(self) -> int:
        return len(self.articles)

    def search(
        self,
        queries: Iterable[str],
        top_k: int = 8,
        domains: Iterable[str] | None = None,
        jurisdictions: Iterable[str] | None = None,
    ) -> list[Hit]:
        domain_set = {d.lower() for d in domains or [] if d}
        juris_set = {j.lower() for j in jurisdictions or [] if j}
        scores: dict[int, float] = defaultdict(float)
        for query in queries:
            for term in set(tokenize(query)):
                idf = self.idf.get(term)
                if idf is None:
                    continue
                for i in self.postings[term]:
                    tf = self.doc_tf[i][term]
                    denom = tf + self.k1 * (1 - self.b + self.b * self.doc_len[i] / (self.avgdl or 1))
                    scores[i] += idf * tf * (self.k1 + 1) / denom
        hits = []
        for i, score in scores.items():
            a = self.articles[i]
            if domain_set and a.domain not in domain_set:
                score *= 0.5  # soft filter: prefer the classified domain, don't exclude others
            if juris_set and a.jurisdiction.lower() not in juris_set and a.jurisdiction.lower() != "federal":
                continue
            hits.append(Hit(a, score))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]


def reciprocal_rank_fusion(rankings: Iterable[Sequence[str]], k: int = 60) -> list[tuple[str, float]]:
    """Merge ranked ID lists; items ranked high in several lists come first."""
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, item in enumerate(ranking):
            scores[item] += 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
