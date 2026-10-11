"""Memory writes: episodic (append-only) and semantic (status-flipped). The
episodic log is the source of truth replay/forking reads (§16.5)."""

from __future__ import annotations

from uuid import UUID

from ..db.tenancy import tenant_conn
from ..security.redact import redact_obj
from .embed import embed, to_pgvector


async def append_episodic(run_id: UUID, kind: str, payload: dict) -> None:
    # §P4b defense-in-depth: scrub secrets *here*, the chokepoint the DB, the SSE
    # stream, the console, and any log tailing episodic all read from — so a key
    # can never reach a log line even if one slipped past the egress gate.
    async with tenant_conn() as c:
        await c.execute(
            """INSERT INTO episodic_events (tenant_id, run_id, kind, payload)
               VALUES (current_setting('app.tenant_id')::uuid, $1, $2, $3::jsonb)""",
            run_id, kind, _json(redact_obj(payload)),
        )


async def write_semantic(run_id: UUID, subject: str, choice: str, *, rationale: str = "",
                         decided_by: str = "arbiter", confidence: float = 0.8) -> UUID:
    vec = to_pgvector(await embed(choice))
    async with tenant_conn() as c:
        return await c.fetchval(
            """INSERT INTO semantic_memory (tenant_id, run_id, subject, choice, rationale,
                   status, decided_by, confidence, embedding)
               VALUES (current_setting('app.tenant_id')::uuid, $1,$2,$3,$4,'active',$5,$6,$7)
               RETURNING id""",
            run_id, subject, choice, rationale, decided_by, confidence, vec,
        )


def _json(obj) -> str:
    import json
    return json.dumps(obj, default=str)
