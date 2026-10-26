"""evaluation_records.candidate

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evaluation_records", sa.Column("candidate", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("evaluation_records", "candidate")
