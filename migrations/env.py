from __future__ import annotations

from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from media_manager.app.persistence.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_url() -> str:
    env_url = os.getenv("DATABASE_URL")
    ini_url = config.get_main_option("sqlalchemy.url")
    url = env_url or ini_url
    if not url:
        raise RuntimeError("DATABASE_URL (or alembic sqlalchemy.url) must be set.")
    if "postgresql" not in url:
        raise RuntimeError("Alembic migrations must target PostgreSQL.")
    return url


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
