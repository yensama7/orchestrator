"""Seed only *real* entities, idempotently, through the RLS-scoped app conn.

No fake agents, scatter points, charts, or default workspace files — those are
now user-driven (Settings, folder import) or computed from live activity. What
seeds here is genuine substrate: past runs (so the lineage graph has real nodes
and inheritance edges), a template they descend from, real semantic decisions
(so retrieval works and Memory has real points), and pitfalls.
"""

from __future__ import annotations

import json
from uuid import UUID

from ..memory.embed import embed, to_pgvector
from .tenancy import DEFAULT_TENANT, tenant_conn

RUN_UUID = UUID("4f2a9c00-0000-0000-0000-0000004f2a9c")
TMPL_UUID = UUID("ec03e3c0-0000-0000-0000-00000ec03e3c")
T = DEFAULT_TENANT

# past runs: (name, domain, status, spent, nodes, template?) — real lineage nodes
_RUNS = [
    ("ecommerce-storefront", "commerce", "active", 0.0, 0, True),   # current
    ("storefront-nordic", "commerce", "passed", 6.20, 74, True),
    ("marketplace-v2", "commerce", "passed", 9.80, 88, True),
    ("subscription-box", "commerce", "active", 3.10, 41, True),
    ("pos-terminal", "commerce", "failed", 4.40, 52, True),
    ("saas-analytics", "saas", "passed", 7.10, 63, False),
    ("mobile-loyalty", "mobile", "passed", 2.90, 38, False),
    ("api-gateway", "api", "failed", 5.60, 57, False),
]

_SEMANTIC = [
    ("auth", "auth = JWT", "session cookies don't survive the mobile client", "active"),
    ("db", "db = postgres 16", "one service covers vectors, relations, queue", "active"),
    ("payments", "payments = stripe connect", "marketplace split settlement", "active"),
    ("auth", "auth = server session", "superseded by JWT after mobile requirement", "superseded"),
    ("cache", "cache = redis", "hot product reads", "active"),
    ("search", "search = postgres tsvector", "avoid a second datastore", "active"),
]

_PITFALLS = [
    ("pg-hnsw-oom", "vector index build OOM on 8GB", "raise maintenance_work_mem before CREATE INDEX", 14.0, 6),
    ("paystack-webhook-retry", "duplicate order on webhook retry", "idempotency key on charge.success", 9.0, 3),
    ("next-image-domains", "next/image blocks remote host", "allowlist the CDN domain in next.config", 2.0, 4),
    ("rls-forgot-force", "tenant leak: RLS enabled not forced", "FORCE ROW LEVEL SECURITY on every table", 40.0, 1),
]


async def already_seeded() -> bool:
    async with tenant_conn() as c:
        return bool(await c.fetchval("SELECT 1 FROM runs WHERE id = $1", RUN_UUID))


async def seed() -> None:
    if await already_seeded():
        return
    async with tenant_conn() as c:
        await c.execute(
            """INSERT INTO templates (id, tenant_id, name, domain, roles, node_count,
                   carried_decisions, manifest, status, embedding)
               VALUES ($1,$2,'ecommerce-v3','commerce',$3,31,12,'{}'::jsonb,'fresh',$4)""",
            TMPL_UUID, T, json.dumps(["orchestrator", "senior-dev", "frontend", "security", "reflection"]),
            to_pgvector(await embed("commerce storefront nextjs postgres paystack")))

        for i, (name, domain, status, spent, nodes, tmpl) in enumerate(_RUNS):
            rid = RUN_UUID if i == 0 else None
            fp = json.dumps({"domain": domain, "subdomain": "storefront" if domain == "commerce" else "",
                             "region": "NG" if domain == "commerce" else "US",
                             "stack_hints": ["nextjs", "postgres"] if domain == "commerce" else ["fastapi"]})
            await c.execute(
                """INSERT INTO runs (id, tenant_id, name, fingerprint, template_id, status,
                       spent_usd, ceiling_usd)
                   VALUES (COALESCE($1, gen_random_uuid()),$2,$3,$4::jsonb,$5,$6,$7,$8)""",
                rid, T, name, fp, TMPL_UUID if tmpl else None, status, spent,
                15.0 if i == 0 else spent * 1.4)

        prev = None
        for subj, choice, rationale, status in _SEMANTIC:
            vec = to_pgvector(await embed(f"{subj} {choice} {rationale}"))
            row = await c.fetchrow(
                """INSERT INTO semantic_memory (tenant_id, run_id, subject, choice, rationale,
                       status, supersedes, decided_by, confidence, embedding)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,'arbiter',0.9,$8) RETURNING id""",
                T, RUN_UUID, subj, choice, rationale, status,
                prev if status == "superseded" else None, vec)
            if subj == "auth" and status == "active":
                prev = row["id"]

        for fp, symptom, resolution, cost, occ in _PITFALLS:
            await c.execute(
                """INSERT INTO pitfalls (tenant_id, fingerprint, domain, trigger, symptom,
                       resolution, cost_usd, occurrences, first_run_id, last_seen_at, embedding)
                   VALUES ($1,$2,'commerce','{}'::jsonb,$3,$4,$5,$6,$7,now(),$8)
                   ON CONFLICT DO NOTHING""",
                T, fp, symptom, resolution, cost, occ, RUN_UUID,
                to_pgvector(await embed(symptom)))
