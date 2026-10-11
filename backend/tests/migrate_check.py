"""DB-backed migration + seed check (phases.md §Phase 5 — migrations tested on a
seeded DB in CI). Not a `test_*` so the DB-free core suite never imports it.

Proves: migrations apply from scratch, re-applying is a no-op (forward-only,
idempotent), the RLS `app` role the schema creates can connect, and seeding real
substrate through it works end to end.

    MIGRATE_DATABASE_URL=postgres://postgres:postgres@localhost/lineage \\
    APP_DATABASE_URL=postgres://app:app@localhost/lineage \\
    python -m tests.migrate_check
"""

from __future__ import annotations

import asyncio

from lineage.db import seed
from lineage.db.tenancy import close, migrate, tenant_conn


async def main() -> None:
    await migrate()           # from scratch
    await migrate()           # again → idempotent, must not error or duplicate

    async with tenant_conn() as c:  # connects as the NOBYPASSRLS app role
        versions = await c.fetchval("SELECT count(*) FROM schema_migrations")
        assert versions >= 1, "schema_migrations not populated"

    await seed.seed()
    async with tenant_conn() as c:
        runs = await c.fetchval("SELECT count(*) FROM runs")
        sem = await c.fetchval("SELECT count(*) FROM semantic_memory")
    assert runs > 0 and sem > 0, f"seed produced no substrate (runs={runs}, sem={sem})"

    await close()
    print("migrate_check ok")


if __name__ == "__main__":
    asyncio.run(main())
