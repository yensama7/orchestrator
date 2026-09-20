"""Connection scoping (§18.4). The tenant is set per checkout, transaction-local,
so a session-scoped setting can't leak to the next checkout from the pool.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

import asyncpg

# Operationally single-tenant in V1; structurally multi-tenant from migration 1.
DEFAULT_TENANT = UUID("00000000-0000-0000-0000-000000000001")

# The app connects as the NOBYPASSRLS `app` role, never the owner.
DATABASE_URL = os.getenv("APP_DATABASE_URL", "postgres://app:app@db:5432/lineage")
# Owner URL used only to apply the (idempotent) schema on boot. Defaults to the
# compose superuser; the app URL can't run DDL/CREATE ROLE by design.
MIGRATE_DATABASE_URL = os.getenv("MIGRATE_DATABASE_URL", "postgres://lineage:lineage@db:5432/lineage")
_SCHEMA = Path(__file__).with_name("schema.sql")

_pool: asyncpg.Pool | None = None


async def migrate() -> None:
    """Apply schema.sql as the owner. Idempotent, so it closes schema drift on a
    persisted volume (initdb only runs on first boot) without wiping data."""
    conn = await asyncpg.connect(MIGRATE_DATABASE_URL)
    try:
        await conn.execute(_SCHEMA.read_text())
    finally:
        await conn.close()


async def pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
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
