"""Decision status transitions (§5). Superseding is a flip + a new active row
linked by `supersedes`, done in one transaction so the partial `active` index
never sees two live decisions for the same subject."""

from __future__ import annotations

from uuid import UUID

from ..db.tenancy import tenant_conn
from .embed import embed, to_pgvector


async def supersede(old_id: UUID, run_id: UUID, subject: str, choice: str,
                    *, rationale: str = "", decided_by: str = "arbiter") -> UUID:
    vec = to_pgvector(await embed(choice))
    async with tenant_conn() as c:
        await c.execute("UPDATE semantic_memory SET status='superseded' WHERE id=$1", old_id)
        return await c.fetchval(
            """INSERT INTO semantic_memory (tenant_id, run_id, subject, choice, rationale,
                   status, supersedes, decided_by, confidence, embedding)
               VALUES (current_setting('app.tenant_id')::uuid,$1,$2,$3,$4,'active',$5,$6,0.85,$7)
               RETURNING id""",
            run_id, subject, choice, rationale, old_id, decided_by, vec,
        )


async def revert(memory_id: UUID) -> None:
    async with tenant_conn() as c:
        await c.execute("UPDATE semantic_memory SET status='reverted' WHERE id=$1", memory_id)
