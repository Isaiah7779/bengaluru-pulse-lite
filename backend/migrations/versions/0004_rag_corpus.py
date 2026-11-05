"""V3 assistant tables: rag_documents, rag_chunks (+ tsvector on PostgreSQL), rag_queries, rag_eval_runs

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rag_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=256), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("commit_sha", sa.String(length=40), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_type", "source_ref", name="uq_rag_document_source"),
    )
    op.create_table(
        "rag_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("heading_path", sa.String(length=400), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("measured_on", sa.Date(), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["rag_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "ordinal", name="uq_rag_chunk_ordinal"),
    )
    op.create_index(op.f("ix_rag_chunks_valid_until"), "rag_chunks", ["valid_until"], unique=False)
    op.create_table(
        "rag_queries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("endpoint", sa.String(length=32), nullable=False),
        sa.Column("question", sa.String(length=500), nullable=True),
        sa.Column("chunk_ids", sa.JSON(), nullable=True),
        sa.Column("refusal_code", sa.String(length=32), nullable=True),
        sa.Column("guard_result", sa.String(length=32), nullable=True),
        sa.Column("composer", sa.String(length=32), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_rag_queries_created_at"), "rag_queries", ["created_at"], unique=False)
    op.create_table(
        "rag_eval_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("golden_set", sa.String(length=64), nullable=False),
        sa.Column("retriever", sa.String(length=32), nullable=False),
        sa.Column("commit_sha", sa.String(length=40), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    _fts_upgrade()


def _fts_upgrade() -> None:
    """PostgreSQL only: weighted tsvector (heading A, stemmed body B, unstemmed body D) + GIN."""

    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE rag_chunks ADD COLUMN tsv tsvector GENERATED ALWAYS AS ("
        "setweight(to_tsvector('english', coalesce(heading_path, '')), 'A') || "
        "setweight(to_tsvector('english', body), 'B') || "
        "setweight(to_tsvector('simple', body), 'D')) STORED"
    )
    op.execute("CREATE INDEX ix_rag_chunks_tsv ON rag_chunks USING GIN (tsv)")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_rag_chunks_tsv")
    op.drop_table("rag_eval_runs")
    op.drop_index(op.f("ix_rag_queries_created_at"), table_name="rag_queries")
    op.drop_table("rag_queries")
    op.drop_index(op.f("ix_rag_chunks_valid_until"), table_name="rag_chunks")
    op.drop_table("rag_chunks")
    op.drop_table("rag_documents")
