"""Fingerprint → nearest past runs + proposed template (§3 step 3). Embeds the
fingerprint and ranks runs/templates by cosine, filtered to the tenant."""

from __future__ import annotations

import json

from ..contracts import SpecFingerprint
from ..db.tenancy import tenant_conn
from ..memory.embed import embed, to_pgvector

_OUTCOME = {"passed": "sage", "active": "amber", "failed": "rust", "abandoned": "rust"}


async def match(fp: SpecFingerprint, k: int = 4) -> dict:
    text = f"{fp.domain} {fp.subdomain} {' '.join(fp.stack_hints)} {fp.payments or ''} {fp.region}"
    vec = to_pgvector(await embed(text))
    async with tenant_conn() as c:
        # nearest runs by name embedding proxy — runs store a fingerprint, embed
        # it on the fly for ranking (cheap at this scale).
        runs = await c.fetch(
            "SELECT id, name, status, fingerprint FROM runs WHERE fingerprint <> '{}'::jsonb")
        tmpl = await c.fetchrow(
            """SELECT name, status, node_count, carried_decisions, roles,
                      (embedding <=> $1) AS dist
               FROM templates WHERE embedding IS NOT NULL
               ORDER BY embedding <=> $1 LIMIT 1""", vec)
        pitfalls = await c.fetchval(
            "SELECT count(*) FROM pitfalls WHERE domain = $1", fp.domain)

    qvec = await embed(text)
    scored = []
    for r in runs:
        rvec = await embed(json.dumps(r["fingerprint"], default=str))
        scored.append((_cos(qvec, rvec), r))
    scored.sort(key=lambda x: x[0], reverse=True)
    nearest = [{"name": r["name"], "score": round(max(s, 0), 2),
                "outcome": _OUTCOME.get(r["status"], "amber")} for s, r in scored[:k]]

    inherited = None
    if tmpl:
        inherited = {
            "template": tmpl["name"], "status": tmpl["status"],
            "rows": [
                {"label": "Agent stack", "n": f"{len(json.loads(tmpl['roles']))} roles"},
                {"label": "Task graph shape", "n": f"{tmpl['node_count']} nodes"},
                {"label": "Carried decisions", "n": str(tmpl["carried_decisions"])},
                {"label": "Recorded pitfalls", "n": str(pitfalls), "color": "rust"},
            ],
        }
    return {"nearest": nearest, "inherited": inherited}


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # both L2-normalised already
