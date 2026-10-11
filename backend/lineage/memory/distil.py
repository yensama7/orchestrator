"""Run → template (§5, §16.1, §17 M5 promotion gate). Batch job, local model
tier. Aggregates the run's active decisions and roster into a reusable
procedural template. Real distillation would summarise with the local model;
here we roll up the verified-decision set, which is the load-bearing part.

Promotion gate: only a run that actually walked a DAG becomes a template —
an empty run is noise, not knowledge. Idempotent per source run (repins on
re-run instead of spawning duplicates), so the orchestrator can call it on
every successful completion.
"""

from __future__ import annotations

from uuid import UUID

from ..db.tenancy import tenant_conn
from .embed import embed, to_pgvector


async def distil(run_id: UUID, name: str, manifest: dict | None = None) -> UUID | None:
    """Promote a completed run into a reusable template. `manifest` is the
    run's resolved dependency versions (parsed by the caller, §18.2) and is
    pinned here as the baseline the drift job measures against; promotion
    (re)sets the freshness clock to now."""
    async with tenant_conn() as c:
        node_count = await c.fetchval(
            "SELECT count(*) FROM episodic_events WHERE run_id=$1 AND kind='node'", run_id)
        if not node_count:
            return None  # promotion gate: nothing ran, nothing to promote
        decisions = await c.fetch(
            "SELECT subject, choice FROM semantic_memory WHERE run_id=$1 AND status='active'",
            run_id,
        )
        roles = await c.fetch("SELECT DISTINCT role FROM agents WHERE run_id=$1", run_id)
        fp = await c.fetchval("SELECT fingerprint->>'domain' FROM runs WHERE id=$1", run_id)
        summary = "; ".join(f"{d['subject']}={d['choice']}" for d in decisions)
        vec = to_pgvector(await embed(summary or name))
        return await c.fetchval(
            """INSERT INTO templates (tenant_id, name, domain, roles, node_count,
                   carried_decisions, manifest, status, embedding, source_run_id,
                   drift_score, freshness_checked_at)
               VALUES (current_setting('app.tenant_id')::uuid,$1,$2,$3,$4,$5,$8::jsonb,
                   'fresh',$6,$7,0,now())
               ON CONFLICT (source_run_id) WHERE source_run_id IS NOT NULL
               DO UPDATE SET name=excluded.name, domain=excluded.domain,
                   roles=excluded.roles, node_count=excluded.node_count,
                   carried_decisions=excluded.carried_decisions,
                   embedding=excluded.embedding, manifest=excluded.manifest,
                   version=templates.version+1, status='fresh', drift_score=0,
                   freshness_checked_at=now(), reverified_at=NULL, created_at=now()
               RETURNING id""",
            name, fp or "commerce", _json([r["role"] for r in roles]),
            int(node_count), len(decisions), vec, run_id, _json(manifest or {}),
        )


def _json(obj) -> str:
    import json
    return json.dumps(obj)
