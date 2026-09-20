"""Brief + template + pitfalls → task DAG (§3 step 6). Pitfalls are injected as
MUST NOT constraints before a single node is written (§6). The planner emits the
DAG; the scheduler walks it — no model appears in the walk, which is what makes
a run replayable (§20.4)."""

from __future__ import annotations

from ..contracts import Dag, NodeSpec, SpecFingerprint
from ..db.tenancy import tenant_conn

# canonical storefront shape; irreversible nodes get consensus.
_TEMPLATE_DAG = [
    ("plan", "planner", "propose", False, [], ["plan/**"], []),
    ("schema.design", "senior-dev", "propose", True, [], ["db/**"], ["json.parses", "confidence.min"]),
    ("auth.session", "senior-dev", "propose", True, ["db/**"], ["auth/**"], ["envelope.valid"]),
    ("payments.webhook", "senior-dev", "propose", True, ["db/**"], ["payments/**"], ["envelope.valid"]),
    ("api.orders", "senior-dev", "propose", False, ["db/**", "auth/**"], ["api/**"], ["envelope.valid"]),
    ("ui.build", "frontend", "propose", False, ["api/**"], ["web/**"], ["json.parses"]),
    ("security.review", "security", "critique", False, ["**"], [], ["envelope.valid"]),
    ("verify", "planner", "accept", False, ["**"], [], ["confidence.min"]),
]


async def build_dag(fp: SpecFingerprint, budget_usd: float) -> Dag:
    async with tenant_conn() as c:
        pitfalls = await c.fetch(
            "SELECT fingerprint, symptom FROM pitfalls WHERE domain=$1 ORDER BY occurrences DESC",
            fp.domain)
    constraints = [p["fingerprint"] for p in pitfalls]

    n = len(_TEMPLATE_DAG)
    per_node = round(budget_usd / n, 2)
    prev = None
    nodes: list[NodeSpec] = []
    for nid, role, intent, irreversible, reads, writes, acceptance in _TEMPLATE_DAG:
        nodes.append(NodeSpec(
            id=nid, role=role, intent=intent, irreversible=irreversible,
            reads=reads, writes=writes, acceptance=acceptance,
            budget_usd=per_node,
            constraints=constraints if irreversible else [],
            depends_on=[prev] if prev else [],
        ))
        prev = nid
    return Dag(nodes=nodes)
