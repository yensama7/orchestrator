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
from ..memory.embed import embed
from ..memory.retrieval import retrieve
from ..planning.plan import build_dag
from ..transports import Prompt, build as build_transport
from ..transports.base import Completion
from . import leases, scheduler, verify

_running: set[str] = set()
# workspace chunks per run, embedded once at run start (files are static during a
# run). Per node we send only the chunks matching that node — not the whole tree —
# so token cost scales with relevance, not workspace size.
# ponytail: module dict instead of threading run_id through every signature.
_ws_ctx: dict[str, dict] = {}


async def start(run_id: UUID) -> bool:
    if str(run_id) in _running:
        return False
    _running.add(str(run_id))
    asyncio.create_task(_run(run_id))
    return True


async def _run(run_id: UUID) -> None:
    try:
        fp, ceiling = await _load(run_id)
        _ws_ctx[str(run_id)] = await _worktree_chunks(run_id)
        roster = await _roster()
        if not roster:
            await mem.append_episodic(run_id, "ticker",
                                      {"key": "blocked", "text": "no agents — add one in Settings"})
            return
        dag = await build_dag(fp, ceiling)
        arb = Arbiter(await _scores(fp.domain))
        await _reset_agents()
        await mem.append_episodic(run_id, "ticker", {"key": "planned", "text": f"{len(dag.nodes)} nodes"})

        halted = False
        for level in scheduler.levels(dag):
            if await _over_ceiling(run_id, ceiling):
                halted = True
                await mem.append_episodic(run_id, "ticker",
                    {"key": "blocked", "text": f"ceiling ${ceiling:.2f} reached — run halted"})
                break
            await asyncio.gather(*(_node(run_id, n, fp, arb, roster) for n in level))

        status = "abandoned" if halted else "passed"
        async with tenant_conn() as c:
            await c.execute("UPDATE runs SET status=$2 WHERE id=$1", run_id, status)
        if not halted:
            await mem.append_episodic(run_id, "ticker", {"key": "passed", "text": "run complete"})
    except Exception as e:
        await mem.append_episodic(run_id, "ticker", {"key": "failed", "text": str(e)[:90]})
    finally:
        _ws_ctx.pop(str(run_id), None)
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
        winner_agent, winner_body = winner.agent, winner.body

        # commit per-agent usage (tokens/cost/pass) — this is what fills the charts.
        # pass credit is tied to the arbiter's winner attempt, before resurrection.
        for a in agents:
            u = per_agent[a["agent"]]
            await _bump_agent(a["agent"], u["tokens"], u["cost"], u["cached"],
                              passed=(a["agent"] == winner.agent and status == "passed"))
        await _charge(run_id, sum(u["cost"] for u in per_agent.values()))

        # §8: the winner failed verification → resurrect the highest-ranked dormant
        # dissent for this node and re-verify it. A dissenter that now passes is
        # vindicated (and becomes the effective decision); one that fails is refuted.
        if status == "failed":
            revived = await _resurrect_and_settle(run_id, node)
            if revived:
                winner_agent, winner_body = revived
                status = "passed"

        # record every passed decision, not a hardcoded three — this is what
        # retrieve() feeds back into later prompts, so the memory has to be real.
        choice = winner_body.get("choice")
        if status == "passed" and choice:
            subject = node.id.split(".")[0]
            await mem.write_semantic(run_id, subject, f"{subject} = {choice}",
                                     rationale=node.intent, decided_by=winner_agent)
        await mem.append_episodic(run_id, "node", {
            "node": node.id, "winner": winner_agent, "status": status,
            "stage": decision.stage, "text": f"{node.id} · {winner_agent} · {status}"})
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
    for a in agents:
        await _set_state([a["agent"]], "running")
        comp = await _dispatch(a, node, fp, run_id)
        per_agent[a["agent"]] = {
            "tokens": comp.usage.input_tokens + comp.usage.output_tokens,
            "cost": comp.usage.usd,
            "cached": (comp.usage.cached_tokens / max(comp.usage.input_tokens, 1) * 100),
        }
        proposals.append(Proposal(
            id=f"{node.id}:{a['agent']}", agent=a["agent"], body=_body(comp, node),
            normalised_cost=min(comp.usage.usd, 1.0)))
    for p, ag in zip(proposals, await _agreements(proposals)):
        p.agreement = ag
    return proposals, per_agent


async def _agreements(proposals: list[Proposal]) -> list[float]:
    """Real semantic agreement (stage-3 input): each proposal's mean cosine to its
    peers' choice text. Embeddings are L2-normalised, so dot == cosine; a lone
    proposal trivially agrees with itself (1.0). Replaces the old dispatch-order
    synthetic that just biased toward whoever went first."""
    if len(proposals) < 2:
        return [1.0] * len(proposals)
    vecs = [await embed(str(p.body.get("choice", ""))) for p in proposals]
    out = []
    for i, vi in enumerate(vecs):
        peers = [sum(a * b for a, b in zip(vi, vj)) for j, vj in enumerate(vecs) if j != i]
        out.append(round(max(0.0, sum(peers) / len(peers)), 3))
    return out


async def _dispatch(a: dict, node: NodeSpec, fp: SpecFingerprint, run_id) -> Completion:
    profile = await _role_profile(node.role)
    must_not = f"MUST NOT: {', '.join(node.constraints)}" if node.constraints else ""
    query = f"{node.role} {node.intent}"
    qvec = await embed(query)
    prior = await _prior_decisions(query)
    chunks = _relevant_workspace(str(run_id), qvec)
    prompt = Prompt(
        # cacheable prefix: identical for every node/agent in the run (domain +
        # file tree), so the provider serves it from cache after the first call.
        stable=_ws_stable(str(run_id), fp.domain),
        # variable tail: role, constraints, retrieved memory, and the chunks that
        # match *this* node — the only part that changes call to call.
        system="\n".join(x for x in (f"role={node.role}", profile, must_not, prior, chunks) if x),
        user=f"node {node.id}: {node.intent} for {fp.subdomain or fp.domain}")
    try:
        return await build_transport(a["model"], a["transport"], a.get("key")).complete(prompt)
    except Exception:
        return await build_transport(a["model"], "local").complete(prompt)  # keyless fallback


async def _prior_decisions(query: str) -> str:
    """Feed the run's own memory back in: retrieved active decisions become a
    'do not contradict' block. This closes the write→retrieve loop (retrieve()
    was defined but never called), so memory is used, not just recorded."""
    try:
        hits = await retrieve(query, top_k=4)
    except Exception:
        return ""  # retrieval is advisory — never block a node on it
    lines = [h["choice"] for h in hits if h.get("choice")]
    return "PRIOR DECISIONS (do not contradict):\n" + "\n".join(f"- {x}" for x in lines) if lines else ""


_CHUNK = 1200  # chars per chunk — one embed unit


async def _worktree_chunks(run_id) -> dict:
    """Split imported files into embedded chunks once per run. Embedding is local
    and free by default (embed.py), so this costs nothing at the paid model — it's
    what lets each node pull only the chunks it needs."""
    async with tenant_conn() as c:
        files = await c.fetch(
            "SELECT folder, name, content FROM worktree_files WHERE run_id=$1 ORDER BY ordinal", run_id)
    if not files:
        return {}
    names = [f"{f['folder']}{f['name']}" for f in files]
    tree = "\n".join("  " + n for n in names[:60])
    if len(names) > 60:
        tree += f"\n  … +{len(names) - 60} more"
    chunks = []
    for f in files:
        body = f["content"] or ""
        label = f"{f['folder']}{f['name']}"
        for i in range(0, len(body), _CHUNK):
            piece = body[i:i + _CHUNK]
            if piece.strip():
                chunks.append({"label": label, "text": piece, "vec": await embed(f"{label}\n{piece}")})
    return {"header": f"WORKSPACE — {len(files)} files:\n{tree}", "chunks": chunks}


def _ws_stable(run_id: str, domain: str) -> str:
    """Run-constant cacheable prefix: domain + the file tree. Same bytes for every
    node/agent, so it lives in Prompt.stable and gets served from cache."""
    ctx = _ws_ctx.get(run_id) or {}
    return "\n".join(x for x in (f"domain={domain}", ctx.get("header")) if x)


def _relevant_workspace(run_id: str, qvec, k: int = 6, budget: int = 6000) -> str:
    """Rank chunks by cosine to the node query; send only the top few under a char
    budget. Tree lives in the stable prefix (_ws_stable), so this is chunks only."""
    ctx = _ws_ctx.get(run_id) or {}
    chunks = ctx.get("chunks") or []
    if not chunks:
        return ""
    scored = sorted(chunks, key=lambda ch: sum(a * b for a, b in zip(ch["vec"], qvec)), reverse=True)
    parts, used = [], 0
    for ch in scored[:k]:
        block = f"\n--- {ch['label']} ---\n{ch['text']}"
        if used + len(block) > budget:
            break
        parts.append(block)
        used += len(block)
    return "".join(parts)


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


async def _resurrect_and_settle(run_id, node: NodeSpec):
    """§8: the winner failed → walk the dormant dissents for this node, highest
    stage first, re-verifying each stored proposal. First one that passes is
    vindicated and returned as the effective (agent, body); the rest that get
    tried and fail are refuted. Mirrors DissentLedger.resurrect/settle over SQL."""
    async with tenant_conn() as c:
        rows = await c.fetch(
            """SELECT id, dissenter, proposal FROM dissent
               WHERE run_id=$1 AND node_id=$2 AND status='dormant'
               ORDER BY stage DESC, id ASC""", run_id, node.id)
    for r in rows:
        body = json.loads(r["proposal"]) if isinstance(r["proposal"], str) else (r["proposal"] or {})
        vres = await verify.run(node.acceptance, body)
        outcome = "vindicated" if vres.passed else "refuted"
        async with tenant_conn() as c:
            await c.execute("UPDATE dissent SET status=$2 WHERE id=$1", r["id"], outcome)
        await _bump_vind(r["dissenter"])
        await mem.append_episodic(run_id, "dissent",
            {"node": node.id, "text": f"{r['dissenter']} resurrected → {outcome}"})
        if vres.passed:
            return r["dissenter"], body
    return None


async def _bump_vind(agent: str) -> None:
    """Recompute an agent's vindication rate from its settled dissents — the
    Agents-table 'Vind' column and the dissent leaderboard both read this."""
    async with tenant_conn() as c:
        row = await c.fetchrow(
            """SELECT count(*) FILTER (WHERE status='vindicated') AS v,
                      count(*) FILTER (WHERE status IN ('vindicated','refuted')) AS t
               FROM dissent WHERE dissenter=$1""", agent)
        pct = (row["v"] / row["t"] * 100) if row["t"] else None
        await c.execute("UPDATE agents SET vind_pct=$2 WHERE agent=$1", agent, pct)


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


async def _over_ceiling(run_id, ceiling: float) -> bool:
    """Budget gate (§7): halt the walk once the run's spend crosses its ceiling.
    Checked per level, not mid-dispatch — a level in flight finishes, then we stop."""
    async with tenant_conn() as c:
        spent = await c.fetchval("SELECT spent_usd FROM runs WHERE id=$1", run_id)
    return float(spent or 0) >= ceiling


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
