"""Alembic environment: uses the application's DATABASE_URL and ORM metadata."""

from logging.config import fileConfig

from alembic import context

from db.models import Base
from db.session import get_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Compare only objects the ORM owns.

    Excludes PostGIS/TIGER extension tables and the PostGIS columns/indexes that
    the migration adds on PostgreSQL only (geog columns, GiST and trigram indexes).
    """

    if type_ == "table" and reflected and compare_to is None:
        return False
    if type_ == "column" and name == "geog":
        return False
    if type_ == "index" and name and (name.endswith("_geog") or name.endswith("_trgm")):
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=str(get_engine().url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection") or get_engine()
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
