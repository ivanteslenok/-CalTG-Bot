from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import Config
from app.database import Base, _normalize_database_url
from app.models import *  # noqa: F401, F403


# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _build_sync_database_url() -> str:
    """
    Строит синхронный URL для Alembic на основе того же DATABASE_URL, что использует приложение.

    Приложение работает с async URL (postgresql+asyncpg://),
    а Alembic нужен sync-драйвер (postgresql+psycopg2://).
    """
    async_url = _normalize_database_url(Config.DATABASE_URL or "")
    if async_url.startswith("postgresql+asyncpg://"):
        return async_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if async_url.startswith("postgres://"):
        return async_url.replace("postgres://", "postgresql+psycopg2://", 1)
    return async_url


SYNC_DATABASE_URL = _build_sync_database_url()

# Set target metadata
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = SYNC_DATABASE_URL or config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_engine(SYNC_DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()