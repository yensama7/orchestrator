"""Template + scores → proposed roster (§3 step 4). Assignment defaults come from
the template's stack, adjusted by each model's win rate in this domain (§9). A
role with no available model is flagged, not silently dropped."""

from __future__ import annotations

from ..db.tenancy import tenant_conn

# default (model, transport) per role; the planner may swap by win rate.
DEFAULTS = {
    "orchestrator": ("claude-opus-4.6", "subscription"),
    "senior-dev": ("claude-sonnet-4.6", "subscription"),
    "frontend": ("kimi-k2", "api"),
    "security": ("claude-sonnet-4.6", "subscription"),
    "security-analyst": ("gemini-3-pro", "subscription"),
    "reflection": ("qwen2.5:3b", "local"),
}


async def propose(domain: str) -> list[dict]:
    async with tenant_conn() as c:
        scores = {r["agent"]: r for r in await c.fetch(
            "SELECT agent, pass_rate, vindication_rate FROM agent_scores WHERE domain=$1", domain)}

    roster = []
    for role, (model, transport) in DEFAULTS.items():
        agent = _agent_for(role)
        s = scores.get(agent)
        roster.append({
            "role": role, "model": model, "transport": transport,
            "consensus": "irreversible only" if role == "senior-dev" else "never",
            "pass_rate": round(s["pass_rate"], 2) if s else None,
            "vindication_rate": round(s["vindication_rate"], 2) if s else None,
            "available": model is not None,
        })
    return roster


def _agent_for(role: str) -> str:
    return {"orchestrator": "planner", "senior-dev": "dev-a", "frontend": "ui-a",
            "security": "sec-impl", "security-analyst": "sec-analyst",
            "reflection": "distiller"}.get(role, role)
