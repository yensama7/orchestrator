"""Run → template (§5, §16.1). Batch job, local model tier. Aggregates the
run's active decisions and roster into a reusable procedural template. Real
distillation would summarise with the local model; here we roll up the
verified-decision set, which is the load-bearing part."""

from __future__ import annotations

from uuid import UUID

from ..db.tenancy import tenant_conn
from .embed import embed, to_pgvector


async def distil(run_id: UUID, name: str) -> UUID:
    async with tenant_conn() as c:
        decisions = await c.fetch(
            "SELECT subject, choice FROM semantic_memory WHERE run_id=$1 AND status='active'",
            run_id,
        )
        roles = await c.fetch("SELECT DISTINCT role FROM agents WHERE run_id=$1", run_id)
        node_count = await c.fetchval(
            "SELECT count(*) FROM episodic_events WHERE run_id=$1 AND kind='node'", run_id)
        fp = await c.fetchval("SELECT fingerprint->>'domain' FROM runs WHERE id=$1", run_id)
        summary = "; ".join(f"{d['subject']}={d['choice']}" for d in decisions)
        vec = to_pgvector(await embed(summary or name))
        return await c.fetchval(
            """INSERT INTO templates (tenant_id, name, domain, roles, node_count,
                   carried_decisions, manifest, status, embedding)
               VALUES (current_setting('app.tenant_id')::uuid,$1,$2,$3,$4,$5,'{}'::jsonb,'fresh',$6)
               RETURNING id""",
            name, fp or "commerce", _json([r["role"] for r in roles]),
            int(node_count or 0), len(decisions), vec,
        )


def _json(obj) -> str:
    import json
    return json.dumps(obj)
