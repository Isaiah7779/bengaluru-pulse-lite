"""Lexical retrieval over rag_chunks (docs/v3/RETRIEVAL_FTS.md §4–§6).

PostgreSQL: weighted tsvector + GIN, `ts_rank_cd(..., 32)`; a strict query
(websearch AND) is filled from a loose OR query. SQLite (unit tests only): an
in-Python BM25 over the same rows with the same query processing. Retrieval
quality is measured on PostgreSQL only.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Protocol, Sequence

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from assistant import synonyms
from assistant.text import STOPWORDS, content_tokens, fold, normalise
from db.models import RagChunk, RagDocument

MAX_QUESTION_CHARS = 500
PER_DOCUMENT_CAP = 2
CANDIDATE_POOL = 30


@dataclass(frozen=True)
class Hit:
    chunk_id: int
    source_ref: str
    heading_path: str
    score: float
    snippet: str
    measured_on: Optional[date]


@dataclass(frozen=True)
class Query:
    original: str
    rewritten: str
    terms: List[str]  # content tokens of the rewritten question
    expansions: List[str]


class Retriever(Protocol):
    name: str

    def search(self, question: str, k: int = 5, visible: Sequence[str] = ("user",)) -> List[Hit]:
        ...


def build_query(question: str) -> Query:
    original = normalise(question)[:MAX_QUESTION_CHARS]
    rewritten = synonyms.rewrite(fold(original))
    rewritten = re.sub(r"[^a-z0-9_\-\s\"]", " ", rewritten)
    terms = list(dict.fromkeys(content_tokens(rewritten)))
    return Query(original, rewritten.strip(), terms, synonyms.expand(terms))


def cap_per_document(hits: List[Hit], k: int, cap: int = PER_DOCUMENT_CAP) -> List[Hit]:
    out: List[Hit] = []
    per_doc: Counter = Counter()
    for h in hits:
        if per_doc[h.source_ref] >= cap:
            continue
        per_doc[h.source_ref] += 1
        out.append(h)
        if len(out) == k:
            break
    return out


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- PostgreSQL

_PG_SQL = text(
    """
    SELECT c.id, d.source_ref, c.heading_path, c.measured_on, length(c.body) AS body_len, c.ordinal,
           ts_rank_cd(c.tsv, q, 32) AS score,
           ts_headline('english', c.body, q, 'MaxWords=60, MinWords=20') AS snippet
    FROM rag_chunks c
    JOIN rag_documents d ON d.id = c.document_id,
         {query} AS q
    WHERE c.tsv @@ q
      AND d.visibility = ANY(:visible)
      AND (c.valid_until IS NULL OR c.valid_until > :now)
    ORDER BY score DESC, body_len ASC, c.ordinal ASC
    LIMIT :pool
    """
)


class PostgresFTSRetriever:
    name = "postgres_fts"

    def __init__(self, session: Session):
        self.session = session

    def _run(self, query_sql: str, params: Dict, visible: Sequence[str]) -> List[Hit]:
        # Bound every search so a slow database cannot hold a request (and a worker) open.
        self.session.execute(text("SET LOCAL statement_timeout = '3s'"))
        sql = text(_PG_SQL.text.replace("{query}", query_sql))
        rows = self.session.execute(sql, {**params, "visible": list(visible), "now": _now(), "pool": CANDIDATE_POOL})
        return [Hit(r.id, r.source_ref, r.heading_path, float(r.score), r.snippet, r.measured_on) for r in rows]

    def search(self, question: str, k: int = 5, visible: Sequence[str] = ("user",)) -> List[Hit]:
        q = build_query(question)
        if not q.terms:
            return []
        hits = self._run("websearch_to_tsquery('english', :q)", {"q": q.rewritten}, visible)
        seen = {h.chunk_id for h in hits}
        if len(cap_per_document(hits, k)) < k:
            loose_terms = [t for t in q.terms + q.expansions if re.fullmatch(r"[a-z0-9_]+", t)]
            loose = " | ".join(loose_terms)
            if loose:
                extra = self._run("to_tsquery('english', :q)", {"q": loose}, visible)
                hits += [h for h in extra if h.chunk_id not in seen]
        return cap_per_document(hits, k)


# --------------------------------------------------------------------------- SQLite BM25


def _stem(token: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def _bm25_tokens(text_: str) -> List[str]:
    return [_stem(t) for t in content_tokens(text_)]


class BM25Retriever:
    """Test-only stand-in with the same interface (k1 = 1.2, b = 0.75)."""

    name = "sqlite_bm25"
    k1 = 1.2
    b = 0.75

    def __init__(self, session: Session):
        self.session = session

    def search(self, question: str, k: int = 5, visible: Sequence[str] = ("user",)) -> List[Hit]:
        q = build_query(question)
        terms = [_stem(t) for t in q.terms] + [_stem(t) for t in q.expansions if t not in STOPWORDS]
        if not q.terms:
            return []
        now = _now()
        rows = self.session.execute(
            select(RagChunk, RagDocument.source_ref)
            .join(RagDocument, RagDocument.id == RagChunk.document_id)
            .where(RagDocument.visibility.in_(list(visible)))
            .where(or_(RagChunk.valid_until.is_(None), RagChunk.valid_until > now))
        ).all()
        docs = []
        for chunk, ref in rows:
            # Heading words count three times (PostgreSQL weights them highest).
            toks = _bm25_tokens(chunk.heading_path) * 3 + _bm25_tokens(chunk.body)
            docs.append((chunk, ref, Counter(toks), len(toks)))
        if not docs:
            return []
        avg_len = sum(d[3] for d in docs) / len(docs)
        df = Counter(t for d in docs for t in set(d[2]))
        n = len(docs)
        scored = []
        for chunk, ref, tf, length in docs:
            score = 0.0
            for t in set(terms):
                if tf[t]:
                    idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                    score += idf * tf[t] * (self.k1 + 1) / (tf[t] + self.k1 * (1 - self.b + self.b * length / avg_len))
            if score > 0:
                scored.append((score, len(chunk.body), chunk.ordinal, chunk, ref))
        scored.sort(key=lambda s: (-s[0], s[1], s[2]))
        hits = [Hit(c.id, ref, c.heading_path, s, c.body[:600], c.measured_on) for s, _, _, c, ref in scored[:CANDIDATE_POOL]]
        return cap_per_document(hits, k)


def get_retriever(session: Session) -> Retriever:
    dialect = session.get_bind().dialect.name
    return PostgresFTSRetriever(session) if dialect == "postgresql" else BM25Retriever(session)
