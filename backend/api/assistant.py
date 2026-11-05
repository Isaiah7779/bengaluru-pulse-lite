"""V3 assistant endpoints (docs/v3/ADR-0001-rag-mvp.md).

Signed-in users only (`current_user`, even when API_AUTH_REQUIRED=false). The assistant
quotes project documentation; it never computes routes, ETAs, traffic or forecasts.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.deps import current_user, require_admin, settings_dep
from assistant import answer, safety
from auth.security import LoginRateLimiter
from core.errors import AppError, NotFound
from core.settings import Settings, get_settings
from db.models import RagChunk, RagDocument, RagQuery, User
from db.session import get_db

logger = logging.getLogger("pulse.assistant")
router = APIRouter(tags=["assistant"])

limiter = LoginRateLimiter(get_settings().rag_rate_limit_per_10_min, 600)


class AskIn(BaseModel):
    question: str = Field(..., min_length=1, max_length=safety.MAX_QUESTION_CHARS)


class CitationOut(BaseModel):
    n: int
    chunk_id: int
    title: str
    source_ref: str
    heading: str
    measured_on: Optional[str] = None


class AskOut(BaseModel):
    answer: str
    refused: bool
    refusal_code: Optional[str] = None
    reason: Optional[str] = None
    scope: Optional[str] = None
    citations: List[CitationOut] = []
    retriever: Optional[str] = None
    composer: str
    disclaimer: str
    latency_ms: float


@router.post("/v1/assistant/ask", response_model=AskOut)
def ask(body: AskIn, user: User = Depends(current_user), db: Session = Depends(get_db),
        settings: Settings = Depends(settings_dep)):
    key = f"user:{user.id}"
    if limiter.blocked(key):
        raise AppError("Too many assistant questions; try again in a few minutes", code="rate_limited", status_code=429)
    limiter.record_failure(key)  # counts every request

    result = answer.ask(db, body.question, k=settings.rag_top_k)
    try:
        db.add(RagQuery(
            endpoint="ask",
            question=safety.clean_question(body.question) if settings.rag_query_retention_days > 0 else None,
            chunk_ids=[c.chunk_id for c in result.citations],
            refusal_code=result.refusal_code if result.refused else None,
            guard_result=result.reason,
            composer=result.composer,
            latency_ms=result.latency_ms,
        ))
        db.commit()
    except Exception:  # logging must never break an answer
        db.rollback()
        logger.warning("could not record assistant query", exc_info=True)
    return AskOut(**{**asdict(result), "citations": [asdict(c) for c in result.citations]})


@router.get("/v1/assistant/sources/{chunk_id}")
def source(chunk_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.execute(
        select(RagChunk, RagDocument).join(RagDocument, RagDocument.id == RagChunk.document_id)
        .where(RagChunk.id == chunk_id, RagDocument.visibility == "user")
    ).first()
    if row is None:
        raise NotFound("Source not found")
    chunk, doc = row
    return {
        "chunk_id": chunk.id,
        "title": doc.title,
        "source_ref": doc.source_ref,
        "heading": chunk.heading_path.split(" › ", 1)[-1],
        "measured_on": chunk.measured_on.isoformat() if chunk.measured_on else None,
        "commit_sha": doc.commit_sha,
        "text": safety.sanitize_passage(chunk.body),
    }


@router.get("/v1/admin/rag/status")
def status(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return {
        "documents": db.scalar(select(func.count(RagDocument.id))),
        "chunks": db.scalar(select(func.count(RagChunk.id))),
        "commit_sha": db.scalar(select(RagDocument.commit_sha).limit(1)),
        "queries_logged": db.scalar(select(func.count(RagQuery.id))),
        "retriever": "postgres_fts" if db.get_bind().dialect.name == "postgresql" else "sqlite_bm25",
        "composer": "extractive",
    }
