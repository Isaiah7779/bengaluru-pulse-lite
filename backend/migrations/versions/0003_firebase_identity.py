"""users.firebase_uid; password_hash nullable for Firebase-only accounts

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("firebase_uid", sa.String(length=128), nullable=True))
        batch.alter_column("password_hash", existing_type=sa.String(length=100), nullable=True)
        batch.create_index("ix_users_firebase_uid", ["firebase_uid"], unique=True)


def downgrade() -> None:
    # Refuses to run while Firebase-only accounts exist (they have no password hash).
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_firebase_uid")
        batch.alter_column("password_hash", existing_type=sa.String(length=100), nullable=False)
        batch.drop_column("firebase_uid")
