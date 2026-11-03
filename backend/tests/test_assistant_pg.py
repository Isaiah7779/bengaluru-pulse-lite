"""V3 Phase 1 on live PostGIS: migration 0004, generated tsvector, FTS retrieval, metrics.

Uses a throwaway database (created and dropped here). Skipped without PostGIS.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

PG_ADMIN_URL = os.getenv("LIVE_PG_URL", "postgresql://pulse:pulse_dev_only@127.0.0.1:5433/pulse")
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pg_available() -> bool:
    try:
        import psycopg

        with psycopg.connect(PG_ADMIN_URL, connect_timeout=2):
            return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def rag_db():
    if not pg_available():
        pytest.skip("live PostGIS not running")
    import psycopg

    name = f"pulse_ragtest_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(PG_ADMIN_URL, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    url = PG_ADMIN_URL.rsplit("/", 1)[0] + f"/{name}"
    env = {**os.environ, "DATABASE_URL": url}
    out = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env,
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr[-2000:]
    engine = create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        yield engine
    finally:
        engine.dispose()
        with psycopg.connect(PG_ADMIN_URL, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture(scope="module")
def ingested(rag_db):
    from assistant.ingest import ingest

    with Session(rag_db) as s:
        stats = ingest(s)
        s.commit()
    return stats


def test_migration_adds_generated_tsvector_and_gin_index(rag_db):
    with rag_db.connect() as conn:
        col = conn.execute(text(
            "select is_generated from information_schema.columns where table_name='rag_chunks' and column_name='tsv'"
        )).scalar()
        idx = conn.execute(text("select indexdef from pg_indexes where indexname='ix_rag_chunks_tsv'")).scalar()
    assert col == "ALWAYS"
    assert "USING gin" in idx


def test_fts_retrieves_the_expected_sections(rag_db, ingested):
    from assistant.retrieval import PostgresFTSRetriever, get_retriever

    with Session(rag_db) as s:
        retriever = get_retriever(s)
        assert isinstance(retriever, PostgresFTSRetriever)
        hits = retriever.search("What is a shortcut in Pulse?")
        assert any("Shortcut / longcut classification" in h.heading_path for h in hits[:3])
        assert all(0 <= h.score <= 1 for h in hits)
        stale = retriever.search("forecast insufficient data 14 days")
        assert any(h.measured_on is not None for h in stale)


def test_phase1_retrieval_metrics_meet_the_provisional_targets(rag_db, ingested):
    """P1-5 recall@5 >= 0.80, P1-6 MRR >= 0.60, P1-8 p95 <= 150 ms (provisional, ACCEPTANCE_CRITERIA.md)."""

    from assistant.evaluate import run

    with Session(rag_db) as s:
        metrics = run(s)
    assert metrics["retriever"] == "postgres_fts" and metrics["answerable_items"] == 53
    assert metrics["recall_at_5"] >= 0.80, metrics["misses"]
    assert metrics["mrr_at_10"] >= 0.60
    assert metrics["latency_ms_p95"] <= 150
