"""Pessimistic per-file leases (§18.1, §20.4). Ordered, all-or-nothing
acquisition in one transaction is the entire deadlock story — do not optimise
it into per-file acquisition. Failure defers, never errors.
"""

from __future__ import annotations

from uuid import UUID

from ..db.tenancy import tenant_conn


class LeaseContention(Exception):
    pass


async def acquire_all(run_id: UUID, node_id: str, agent: str, write_globs: list[str],
                      ttl_seconds: float) -> list[UUID] | None:
    globs = sorted(write_globs)  # ORDERED — prevents deadlock
    if not globs:
        return []
    async with tenant_conn() as conn:
        try:
            ids: list[UUID] = []
            for g in globs:
                row = await conn.fetchrow(
                    """INSERT INTO file_leases
                         (tenant_id, run_id, node_id, agent_id, path_glob, mode, expires_at)
                       VALUES (current_setting('app.tenant_id')::uuid, $1,$2,$3,$4,'write',
                               now() + make_interval(secs => $5))
                       ON CONFLICT DO NOTHING
                       RETURNING id""",
                    run_id, node_id, agent, g, ttl_seconds,
                )
                if row is None:
                    raise LeaseContention(g)  # rolls the whole txn back
                ids.append(row["id"])
            return ids
        except LeaseContention:
            return None  # caller defers the node to the next scheduler level


async def release(lease_ids: list[UUID]) -> None:
    if not lease_ids:
        return
    async with tenant_conn() as conn:
        await conn.execute("DELETE FROM file_leases WHERE id = ANY($1::uuid[])", lease_ids)


async def reap_expired() -> int:
    """Sweep expired rows so a crashed sandbox can't wedge a path forever."""
    async with tenant_conn() as conn:
        return int((await conn.execute(
            "DELETE FROM file_leases WHERE expires_at < now()")).split()[-1])
