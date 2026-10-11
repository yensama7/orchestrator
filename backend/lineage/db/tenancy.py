"""Connection scoping (§18.4). The tenant is set per checkout, transaction-local,
so a session-scoped setting can't leak to the next checkout from the pool.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    import asyncpg

# Operationally single-tenant in V1; structurally multi-tenant from migration 1.
DEFAULT_TENANT = UUID("00000000-0000-0000-0000-000000000001")

# The app connects as the NOBYPASSRLS `app` role, never the owner.
DATABASE_URL = os.getenv("APP_DATABASE_URL", "postgres://app:app@db:5432/lineage")
# Owner URL used only to apply migrations on boot. Defaults to the compose
# superuser; the app URL can't run DDL/CREATE ROLE by design.
MIGRATE_DATABASE_URL = os.getenv("MIGRATE_DATABASE_URL", "postgres://lineage:lineage@db:5432/lineage")
_MIGRATIONS = Path(__file__).with_name("migrations")

_pool: "asyncpg.Pool | None" = None


def migration_files() -> list[Path]:
    """Every db/migrations/NNN_*.sql in applied order. Lexical sort on a zero-padded
    numeric prefix == numeric order, which is why the prefix is the contract."""
    return sorted(_MIGRATIONS.glob("[0-9]*.sql"))


async def migrate() -> None:
    """Forward-only migration runner. Applies each NNN_*.sql not yet recorded in
    schema_migrations, in order, as the owner. Each file is idempotent, so a boot
    against a persisted volume predating the ledger re-applies safely and backfills
    the ledger (initdb only runs on first boot). One txn per file: a half-applied
    migration never commits."""
    import asyncpg
    conn = await asyncpg.connect(MIGRATE_DATABASE_URL)
    try:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
        applied = {r["version"] for r in await conn.fetch("SELECT version FROM schema_migrations")}
        for path in migration_files():
            version = path.name
            if version in applied:
                continue
            async with conn.transaction():
                await conn.execute(path.read_text())
                await conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES ($1) "
                    "ON CONFLICT DO NOTHING", version)
    finally:
        await conn.close()


async def pool() -> "asyncpg.Pool":
    global _pool
    if _pool is None:
        import asyncpg
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    return _pool


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def tenant_conn(tenant_id: UUID = DEFAULT_TENANT):
    p = await pool()
    async with p.acquire() as conn, conn.transaction():
        # true = transaction-local; required so it doesn't leak on pool reuse.
        await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(tenant_id))
        yield conn
