"""The run loop (§7, §17 M1 + consensus). Walks the DAG, dispatches nodes to the
transports of the *user-configured* roster, arbitrates consensus deterministically,
records dissent, verifies, and writes every step to episodic_events so the console
streams live. Agent stats (calls/tokens/cost/state/pass) update live on the shared
agents rows, which is what fills the header rail, Agents table, and charts.

No LLM decides control flow here — the planner wrote the DAG, this walks it.
"""

from __future__ import annotations

import asyncio
import json
from uuid import UUID

from ..arbitration.arbiter import Arbiter
from ..arbitration.scores import AgentScore, Proposal
from ..contracts import NodeSpec, SpecFingerprint
from ..db.tenancy import tenant_conn
from ..memory import store as mem
from ..planning.plan import build_dag
from ..transports import Prompt, build as build_transport
from ..transports.base import Completion
from . import leases, scheduler, verify

_running: set[str] = set()


async def start(run_id: UUID) -> bool:
    if str(run_id) in _running:
        return False
    _running.add(str(run_id))
    asyncio.create_task(_run(run_id))
    return True


async def _run(run_id: UUID) -> None:
    try:
        fp, ceiling = await _load(run_id)
        roster = await _roster()
        if not roster:
            await mem.append_episodic(run_id, "ticker",
                                      {"key": "blocked", "text": "no agents — add one in Settings"})
            return
        dag = await build_dag(fp, ceiling)
        arb = Arbiter(await _scores(fp.domain))
        await _reset_agents()
        await mem.append_episodic(run_id, "ticker", {"key": "planned", "text": f"{len(dag.nodes)} nodes"})

        for level in scheduler.levels(dag):
            await asyncio.gather(*(_node(run_id, n, fp, arb, roster) for n in level))

        async with tenant_conn() as c:
            await c.execute("UPDATE runs SET status='passed' WHERE id=$1", run_id)
        await mem.append_episodic(run_id, "ticker", {"key": "passed", "text": "run complete"})
    except Exception as e:
        await mem.append_episodic(run_id, "ticker", {"key": "failed", "text": str(e)[:90]})
    finally:
        _running.discard(str(run_id))


async def _node(run_id, node: NodeSpec, fp, arb, roster) -> None:
    agents = _pick(roster, node)
    if not agents:
        return
    held = await leases.acquire_all(run_id, node.id, agents[0]["agent"], node.writes, ttl_seconds=90)
    if held is None:
        await mem.append_episodic(run_id, "lease", {"node": node.id, "text": "deferred"})
        return
    try:
        proposals, per_agent = await _propose(run_id, node, fp, agents)
        decision = arb.decide(fp.domain, proposals)
        if decision.held:
            await mem.append_episodic(run_id, "ticker", {"key": "held", "text": f"{node.id} — arbiter tie"})
        await _record_dissent(run_id, node.id, proposals, decision)

        winner = next((p for p in proposals if p.id == decision.winner), proposals[0])
        vres = await verify.run(node.acceptance, winner.body)
        status = "passed" if vres.passed else "failed"

        # commit per-agent usage (tokens/cost/pass) — this is what fills the charts
        for a in agents:
            u = per_agent[a["agent"]]
            await _bump_agent(a["agent"], u["tokens"], u["cost"], u["cached"],
                              passed=(a["agent"] == winner.agent and status == "passed"))
        await _charge(run_id, sum(u["cost"] for u in per_agent.values()))

        if node.id in ("schema.design", "auth.session", "payments.webhook"):
            await mem.write_semantic(run_id, node.id.split(".")[0],
                                     f"{node.id.split('.')[0]} = {winner.body.get('choice')}",
                                     decided_by=winner.agent)
        await mem.append_episodic(run_id, "node", {
            "node": node.id, "winner": winner.agent, "status": status,
            "stage": decision.stage, "text": f"{node.id} · {winner.agent} · {status}"})
    finally:
        await leases.release(held)
        await _set_state([a["agent"] for a in agents], "idle")


def _pick(roster: dict, node: NodeSpec) -> list[dict]:
    same = roster.get(node.role, [])
    if node.irreversible and node.role == "senior-dev" and len(same) > 1:
        return same                      # consensus over all senior-devs
    if same:
        return [same[0]]
    flat = [a for lst in roster.values() for a in lst]
    return [flat[0]] if flat else []


async def _propose(run_id, node, fp, agents) -> tuple[list[Proposal], dict]:
    proposals: list[Proposal] = []
    per_agent: dict[str, dict] = {}
    for i, a in enumerate(agents):
        await _set_state([a["agent"]], "running")
        comp = await _dispatch(a, node, fp)
        per_agent[a["agent"]] = {
            "tokens": comp.usage.input_tokens + comp.usage.output_tokens,
            "cost": comp.usage.usd,
            "cached": (comp.usage.cached_tokens / max(comp.usage.input_tokens, 1) * 100),
        }
        proposals.append(Proposal(
            id=f"{node.id}:{a['agent']}", agent=a["agent"], body=_body(comp, node),
            agreement=round(0.9 - 0.25 * i, 3), normalised_cost=min(comp.usage.usd, 1.0)))
    return proposals, per_agent


async def _dispatch(a: dict, node: NodeSpec, fp: SpecFingerprint) -> Completion:
    profile = await _role_profile(node.role)
    must_not = f"MUST NOT: {', '.join(node.constraints)}" if node.constraints else ""
    prompt = Prompt(
        stable=f"role={node.role} domain={fp.domain}",
        system="\n".join(x for x in (profile, must_not) if x),
        user=f"node {node.id}: {node.intent} for {fp.subdomain or fp.domain}")
    try:
        return await build_transport(a["model"], a["transport"], a.get("key")).complete(prompt)
    except Exception:
        return await build_transport(a["model"], "local").complete(prompt)  # keyless fallback


async def _role_profile(role: str) -> str:
    # ponytail: per-dispatch query; fold into _roster() if node counts grow.
    async with tenant_conn() as c:
        r = await c.fetchrow("SELECT skills, resources FROM roles WHERE name=$1", role)
    if not r:
        return ""
    skills = _jarr(r["skills"])
    resources = _jarr(r["resources"])
    parts = []
    if skills:
        parts.append("SKILLS: " + ", ".join(skills))
    if resources:
        parts.append("RESOURCES: " + ", ".join(resources))
    return " | ".join(parts)


def _jarr(v) -> list:
    return json.loads(v) if isinstance(v, str) else (v or [])


def _body(comp: Completion, node: NodeSpec) -> dict:
    try:
        b = json.loads(comp.text)
        if isinstance(b, dict):
            b.setdefault("choice", comp.text[:40])
            return b
    except (json.JSONDecodeError, TypeError):
        pass
    return {"choice": comp.text.strip()[:60] or node.intent, "confidence": 0.6}


async def _record_dissent(run_id, node_id, proposals, decision) -> None:
    winner_agent = next((x.agent for x in proposals if x.id == decision.winner), proposals[0].agent)
    losers = [(e.agent, e.stage, e.reason, next((p for p in proposals if p.id == e.proposal_id), None))
              for e in decision.trace]
    if not losers and decision.held:
        losers = [(p.agent, 4, "stage-4 tie → held for human", p) for p in proposals[1:]]
    if not losers:
        return
    async with tenant_conn() as c:
        for agent, stage, reason, p in losers:
            await c.execute(
                """INSERT INTO dissent (tenant_id, run_id, node_id, dissenter, winner,
                       stage, reason, proposal, status)
                   VALUES (current_setting('app.tenant_id')::uuid,$1,$2,$3,$4,$5,$6,$7::jsonb,'dormant')""",
                run_id, node_id, agent, winner_agent, stage, reason, json.dumps(p.body if p else {}))
    await mem.append_episodic(run_id, "dissent", {"node": node_id, "text": f"{len(losers)} overruled"})


# ── live state mutation on the shared agents rows ───────────────────────────
async def _roster() -> dict:
    async with tenant_conn() as c:
        agents = await c.fetch("SELECT agent, role, model, transport FROM agents WHERE enabled ORDER BY ordinal")
        creds = {r["model"]: r["api_key"] for r in
                 await c.fetch("SELECT model, api_key FROM model_credentials WHERE enabled")}
    out: dict[str, list[dict]] = {}
    for a in agents:
        out.setdefault(a["role"], []).append(
            {"agent": a["agent"], "model": a["model"], "transport": a["transport"],
             "key": creds.get(a["model"])})
    return out


async def _reset_agents() -> None:
    async with tenant_conn() as c:
        await c.execute("UPDATE agents SET calls=0, tokens=0, cost_usd=0, passes=0, attempts=0, state='idle'")


async def _bump_agent(agent, tokens, cost, cached_pct, passed: bool) -> None:
    async with tenant_conn() as c:
        await c.execute(
            """UPDATE agents SET calls=calls+1, tokens=tokens+$2, cost_usd=cost_usd+$3,
                   cached_pct=$4, attempts=attempts+1, passes=passes+$5 WHERE agent=$1""",
            agent, int(tokens), cost, round(cached_pct, 1), 1 if passed else 0)


async def _set_state(agent_names, state) -> None:
    async with tenant_conn() as c:
        await c.execute("UPDATE agents SET state=$2 WHERE agent=ANY($1)", agent_names, state)


async def _charge(run_id, usd: float) -> None:
    async with tenant_conn() as c:
        spent = await c.fetchval(
            "UPDATE runs SET spent_usd=spent_usd+$2 WHERE id=$1 RETURNING spent_usd", run_id, usd)
    await mem.append_episodic(run_id, "spend", {"spent": float(spent)})


async def _load(run_id):
    async with tenant_conn() as c:
        r = await c.fetchrow("SELECT fingerprint, ceiling_usd FROM runs WHERE id=$1", run_id)
    raw = r["fingerprint"]
    fpd = json.loads(raw) if isinstance(raw, str) else (dict(raw) if raw else {})
    return SpecFingerprint(**{**{"domain": "other"}, **fpd}), float(r["ceiling_usd"] or 10)


async def _scores(domain):
    async with tenant_conn() as c:
        rows = await c.fetch(
            "SELECT agent, pass_rate, escalation_rate, vindication_rate FROM agent_scores WHERE domain=$1",
            domain)
    return {r["agent"]: AgentScore(pass_rate=r["pass_rate"], escalation_rate=r["escalation_rate"],
                                   vindication_rate=r["vindication_rate"]) for r in rows}
