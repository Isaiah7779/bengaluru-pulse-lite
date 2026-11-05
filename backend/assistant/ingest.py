"""Ingest the allowlisted corpus into rag_documents / rag_chunks.

    python -m assistant.ingest            # from backend/, ingests HEAD
    python -m assistant.ingest --rev v3-rag

Idempotent: a document whose content hash is unchanged is skipped; a changed
document has its chunks replaced. Documents no longer in the allowlist are removed.
Runs outside the web process (locally, in CI or a scheduled job).
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Dict, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from assistant import corpus
from assistant.chunking import chunk_eval_report, chunk_markdown
from assistant.text import normalise, sha256
from db.models import RagChunk, RagDocument, utcnow

logger = logging.getLogger("pulse.assistant.ingest")


def ingest(session: Session, rev: str = "HEAD", repo: Path = corpus.REPO_ROOT, allowlist=corpus.ALLOWLIST) -> Dict[str, int]:
    started = time.perf_counter()
    commit = corpus.resolve_commit(rev, repo)
    sources = corpus.load_sources(commit, repo, allowlist)
    stats = {"documents_added": 0, "documents_updated": 0, "documents_unchanged": 0,
             "documents_removed": 0, "chunks_written": 0}

    existing = {(d.source_type, d.source_ref): d for d in session.scalars(select(RagDocument))}
    wanted = set()
    for src in sources:
        key = (src.source_type, src.path)
        wanted.add(key)
        doc_hash = sha256(src.text)
        doc = existing.get(key)
        if doc is not None and doc.content_hash == doc_hash:
            stats["documents_unchanged"] += 1
            continue

        fallback = Path(src.path).name
        title, chunks = (chunk_eval_report(src.text, src.path) if src.source_type == "eval_report"
                         else chunk_markdown(src.text, fallback))
        for c in chunks:
            hit = corpus.find_secret(c.body)
            if hit:
                raise corpus.CorpusError(f"chunk of {src.path} looks like it contains a credential ({hit})")

        if doc is None:
            doc = RagDocument(source_type=src.source_type, source_ref=src.path)
            session.add(doc)
            stats["documents_added"] += 1
        else:
            session.execute(delete(RagChunk).where(RagChunk.document_id == doc.id))
            stats["documents_updated"] += 1
        doc.title = title[:200]
        doc.commit_sha = commit
        doc.content_hash = doc_hash
        doc.visibility = "user"
        doc.ingested_at = utcnow()
        session.flush()
        for ordinal, c in enumerate(chunks):
            body = c.body.strip()
            session.add(RagChunk(
                document_id=doc.id, ordinal=ordinal, heading_path=normalise(c.heading_path)[:400], body=body,
                measured_on=c.measured_on, content_hash=sha256(body),
                meta={**c.meta, "source_ref": src.path, "commit_sha": commit},
            ))
        stats["chunks_written"] += len(chunks)

    for key, doc in existing.items():
        if key not in wanted:
            session.delete(doc)
            stats["documents_removed"] += 1
    session.flush()
    stats["commit_sha"] = commit
    stats["seconds"] = round(time.perf_counter() - started, 3)
    logger.info("RAG ingest: %s", stats)
    return stats


SNAPSHOT_PATH = Path(__file__).resolve().parent / "corpus_snapshot.json"


def export_snapshot(rev: str = "HEAD", path: Path = SNAPSHOT_PATH, repo: Path = corpus.REPO_ROOT) -> Dict:
    """Write the chunked corpus to JSON so a deployment without git or docs/ can load it.

    The snapshot is built by the same code as `ingest` (allowlist, secret guard, chunking)
    and records the commit it came from.
    """

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as _Session

    from db.models import Base

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[RagDocument.__table__, RagChunk.__table__])
    with _Session(engine) as s:
        stats = ingest(s, rev, repo)
        docs = []
        for d in s.scalars(select(RagDocument).order_by(RagDocument.id)):
            docs.append({
                "source_type": d.source_type, "source_ref": d.source_ref, "title": d.title,
                "commit_sha": d.commit_sha, "content_hash": d.content_hash, "visibility": d.visibility,
                "chunks": [{"ordinal": c.ordinal, "heading_path": c.heading_path, "body": c.body,
                            "measured_on": c.measured_on.isoformat() if c.measured_on else None,
                            "content_hash": c.content_hash, "meta": c.meta}
                           for c in sorted(d.chunks, key=lambda c: c.ordinal)],
            })
    payload = {"commit_sha": stats["commit_sha"], "documents": docs}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"commit_sha": stats["commit_sha"], "documents": len(docs), "chunks": stats["chunks_written"], "path": str(path)}


def load_snapshot(session: Session, path: Path = SNAPSHOT_PATH) -> Dict[str, int]:
    """Load the corpus snapshot into rag_* tables; documents with an unchanged hash are skipped."""

    from datetime import date as _date

    if not path.exists():
        return {"snapshot": 0}
    payload = json.loads(path.read_text(encoding="utf-8"))
    stats = {"documents_added": 0, "documents_updated": 0, "documents_unchanged": 0, "documents_removed": 0,
             "chunks_written": 0}
    existing = {(d.source_type, d.source_ref): d for d in session.scalars(select(RagDocument))}
    wanted = set()
    for item in payload["documents"]:
        key = (item["source_type"], item["source_ref"])
        wanted.add(key)
        for c in item["chunks"]:
            if corpus.find_secret(c["body"]):
                raise corpus.CorpusError(f"snapshot chunk of {item['source_ref']} looks like a credential")
        doc = existing.get(key)
        if doc is not None and doc.content_hash == item["content_hash"]:
            stats["documents_unchanged"] += 1
            continue
        if doc is None:
            doc = RagDocument(source_type=item["source_type"], source_ref=item["source_ref"])
            session.add(doc)
            stats["documents_added"] += 1
        else:
            session.execute(delete(RagChunk).where(RagChunk.document_id == doc.id))
            stats["documents_updated"] += 1
        doc.title, doc.commit_sha, doc.content_hash = item["title"], item["commit_sha"], item["content_hash"]
        doc.visibility, doc.ingested_at = item["visibility"], utcnow()
        session.flush()
        for c in item["chunks"]:
            session.add(RagChunk(
                document_id=doc.id, ordinal=c["ordinal"], heading_path=c["heading_path"], body=c["body"],
                measured_on=_date.fromisoformat(c["measured_on"]) if c["measured_on"] else None,
                content_hash=c["content_hash"], meta=c["meta"],
            ))
        stats["chunks_written"] += len(item["chunks"])
    for key, doc in existing.items():
        if key not in wanted:
            session.delete(doc)
            stats["documents_removed"] += 1
    session.flush()
    stats["commit_sha"] = payload["commit_sha"]
    return stats


def main(argv: Optional[list] = None) -> None:
    parser = argparse.ArgumentParser(description="Ingest the assistant corpus")
    parser.add_argument("--rev", default="HEAD", help="git revision to read the corpus from")
    parser.add_argument("--export", action="store_true", help="write corpus_snapshot.json instead of a database")
    parser.add_argument("--from-snapshot", action="store_true", help="load corpus_snapshot.json into the database")
    args = parser.parse_args(argv)
    if args.export:
        print(json.dumps(export_snapshot(args.rev), indent=2))
        return
    from db.session import session_scope

    with session_scope() as s:
        print(json.dumps(load_snapshot(s) if args.from_snapshot else ingest(s, args.rev), indent=2))


if __name__ == "__main__":
    main()
