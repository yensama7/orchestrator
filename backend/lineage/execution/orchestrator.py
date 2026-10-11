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
from ..arbitration import confidence
from ..arbitration.scores import AgentScore, Proposal
from .. import mode as runmode
from ..contracts import NodeSpec, SpecFingerprint
from ..db.tenancy import tenant_conn
from ..memory import manifest
from ..memory import store as mem
from ..memory.distil import distil
from ..memory.embed import embed
from . import worktree
from ..memory.retrieval import retrieve
from ..planning.plan import build_dag
from ..security.redact import redact
from ..transports import Prompt, build as build_transport
from ..transports.base import Completion
from . import leases, routing, scheduler, verify
from .pool import SandboxPool

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
    pool: SandboxPool | None = None
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
        # §P2 routing inputs, snapshotted once so a run routes deterministically
        # (replay/fork depend on it): per-agent cost-per-verified-result for this
        # domain, and how often this fingerprint has burned us before.
        cpv = await _cost_per_verified(fp.domain)
        prior_failures = await _pitfall_count(fp.domain)
        await _reset_agents()
        await mem.append_episodic(run_id, "ticker", {"key": "planned", "text": f"{len(dag.nodes)} nodes"})

        # fork / replay (§16.5): resume from the divergence node, skip nodes whose
        # decisions were carried from the parent, install the override at it.
        fork_node, override = await _fork_spec(run_id)
        node_ids = [n.id for n in dag.nodes]
        order = {nid: i for i, nid in enumerate(node_ids)}
        resume_idx, _ = scheduler.resume_plan(node_ids, fork_node)
        if fork_node:
            await mem.append_episodic(run_id, "ticker",
                {"key": "planned", "text": f"fork — resuming at {fork_node}"})

        # run-level mode evidence (phases.md §P0): echo poisons `live`, a behavioral
        # verifier is required for it. Nodes mutate this as they run.
        flags = {"echo": False, "behavioral": False}
        halted = False
        # warm sandbox pool for behavioral verification (§P1b, §14). One sandbox is
        # handed to each node to execute its proposals' produced files; sized to the
        # widest level so a parallel level never serialises on sandbox contention.
        plan_levels = scheduler.levels(dag)
        pool = SandboxPool(size=max(4, max((len(lv) for lv in plan_levels), default=1)))
        await pool.start()
        for level in plan_levels:
            if await _over_ceiling(run_id, ceiling):
                halted = True
                await mem.append_episodic(run_id, "ticker",
                    {"key": "blocked", "text": f"ceiling ${ceiling:.2f} reached — run halted"})
                break
            tasks = []
            for n in level:
                if order[n.id] < resume_idx:
                    continue  # carried forward from the parent run
                if fork_node and n.id == fork_node and override:
                    tasks.append(_apply_override(run_id, n, override, pool))
                else:
                    tasks.append(_node(run_id, n, fp, arb, roster, flags, pool, cpv, prior_failures))
            if tasks:
                await asyncio.gather(*tasks)

        status = "abandoned" if halted else "passed"
        mode_val = runmode.classify(flags["echo"], flags["behavioral"])
        async with tenant_conn() as c:
            name = await c.fetchval("SELECT name FROM runs WHERE id=$1", run_id)
            await c.execute("UPDATE runs SET status=$2, mode=$3 WHERE id=$1", run_id, status, mode_val)
        await mem.append_episodic(run_id, "ticker",
            {"key": "planned", "text": f"mode: {mode_val}"})
        # §P0: vind% counts only live-run settlements; the mid-run recompute saw
        # this run's mode still defaulting to 'simulated', so refresh it now that
        # the final mode is committed. A no-op refresh after a simulated run.
        if mode_val == runmode.LIVE:
            await _fold_scores(fp.domain)  # §P2: this run's spend/verified → routing surface
            for agent in {a["agent"] for lst in roster.values() for a in lst}:
                await _bump_vind(agent)
        if not halted:
            await mem.append_episodic(run_id, "ticker", {"key": "passed", "text": "run complete"})
            # §5/§17 M5: promote the completed run into a reusable template so the
            # next run's `match` can inherit from it. Gated + idempotent in distil;
            # off the critical path, so a failure here never fails the run.
            try:
                man = manifest.parse(await worktree.read_files(run_id))
                if await distil(run_id, name or "untitled run", man):
                    await mem.append_episodic(run_id, "ticker",
                        {"key": "planned", "text": "distilled → template"})
            except Exception as e:  # noqa: BLE001
                await mem.append_episodic(run_id, "ticker",
                    {"key": "held", "text": f"distil skipped: {str(e)[:60]}"})
    except Exception as e:
        await mem.append_episodic(run_id, "ticker", {"key": "failed", "text": str(e)[:90]})
    finally:
        if pool is not None:
            await pool.shutdown()
        _ws_ctx.pop(str(run_id), None)
        _running.discard(str(run_id))


async def _node(run_id, node: NodeSpec, fp, arb, roster, flags: dict, pool: SandboxPool,
                cpv: dict, prior_failures: int) -> None:
    agents = await _assign(run_id, roster, node, cpv, prior_failures)
    if not agents:
        return
    held = await leases.acquire_all(run_id, node.id, agents[0]["agent"], node.writes, ttl_seconds=90)
    if held is None:
        await mem.append_episodic(run_id, "lease", {"node": node.id, "text": "deferred"})
        return
    # one warm sandbox for the whole node: behavioral verifiers (verify.py) execute
    # each proposal's produced files in it, and the resurrect loop re-verifies in it.
    sb = await pool.acquire()
    try:
        proposals, per_agent = await _propose(run_id, node, fp, agents)
        # §18.3 stage 2: verify every proposal *before* arbitration so a passing
        # test can beat a vote. Behavioral verifiers execute the produced files;
        # the winner's result is reused as its status.
        vres = {p.id: await verify.run(node.acceptance, p.body, sb) for p in proposals}
        for p in proposals:
            p.verifier_passes = vres[p.id].passed
        decision = arb.decide(fp.domain, proposals)
        if decision.held:
            await mem.append_episodic(run_id, "ticker", {"key": "held", "text": f"{node.id} — arbiter tie"})
        await _record_dissent(run_id, node.id, proposals, decision)

        winner = next((p for p in proposals if p.id == decision.winner), proposals[0])
        status = "passed" if vres[winner.id].passed else "failed"
        winner_agent, winner_body = winner.agent, winner.body

        # §P0: pass credit is a *verified-skill* number — it only counts when this
        # node was behaviorally verified with a real model. A structural pass on an
        # echo proposal records activity (tokens/cost) but no skill, so a simulated
        # run can't inflate the Agents/leaderboard surface used for routing.
        node_behavioral = verify.any_behavioral(node.acceptance)
        flags["behavioral"] = flags["behavioral"] or node_behavioral
        flags["echo"] = flags["echo"] or any(u["sim"] for u in per_agent.values())

        # commit per-agent usage (tokens/cost/pass) — this is what fills the charts.
        # pass credit is tied to the arbiter's winner attempt, before resurrection.
        for a in agents:
            u = per_agent[a["agent"]]
            verified = (a["agent"] == winner.agent and status == "passed"
                        and node_behavioral and not u["sim"])
            await _bump_agent(a["agent"], u["tokens"], u["cost"], u["cached"], passed=verified)
        await _charge(run_id, sum(u["cost"] for u in per_agent.values()))

        # §8: the winner failed verification → resurrect the highest-ranked dormant
        # dissent for this node and re-verify it. A dissenter that now passes is
        # vindicated (and becomes the effective decision); one that fails is refuted.
        if status == "failed":
            revived = await _resurrect_and_settle(run_id, node, sb)
            if revived:
                winner_agent, winner_body = revived
                status = "passed"

        # §P2: a verified result = a node that reached a behaviorally-verified pass.
        # Echo can't clear a behavioral gate (verify.py fails it closed), so this
        # counter is 0 on a pure-echo run without any mode check. Denominator of
        # the run's cost-per-verified-result.
        if status == "passed" and node_behavioral:
            await _bump_run_verified(run_id)

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
        await pool.release(sb)
        await leases.release(held)
        await _set_state([a["agent"] for a in agents], "idle")


async def _assign(run_id, roster: dict, node: NodeSpec, cpv: dict, prior_failures: int) -> list[dict]:
    """Which agent(s) take this node. Irreversible nodes with >1 role peer still
    go to full consensus (unchanged). Otherwise the §P2 router picks a single
    agent by complexity × historical cost-per-verified-result, and logs why —
    COMPLEXITY_ROUTING=0 falls back to the first candidate (pre-Phase-2 behaviour)."""
    same = roster.get(node.role, [])
    # consensus on any irreversible node where >1 agent shares the role — not just
    # the literal "senior-dev", so a user's own role names get consensus too.
    if node.irreversible and len(same) > 1:
        return same
    cands = same or [a for lst in roster.values() for a in lst]
    if not cands:
        return []
    if not routing.enabled():
        return [cands[0]]
    needed = routing.node_tier(node, behavioral=verify.behavioral_count(node.acceptance),
                               prior_failures=prior_failures)
    chosen = routing.choose(cands, needed, cpv)
    await mem.append_episodic(run_id, "router", {
        "node": node.id, "tier": needed, "agent": chosen["agent"], "model": chosen["model"],
        "text": f"{node.id} → {needed} → {chosen['agent']} ({chosen['model']})"})
    return [chosen]


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
            "sim": comp.simulated,  # echo stand-in → can't count as verified (§P0)
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
    # §P1b: a node that must be behaviorally verified has to *produce the artifacts*
    # that get built/tested — tell the model to emit them as a files map. Without
    # this the loop is inert (nothing to execute). The echo stub ignores it and so
    # stays honestly `simulated`.
    contract = (
        "OUTPUT: return ONLY JSON of the form "
        '{"choice": "<short decision label>", "confidence": <0..1>, '
        '"files": {"<relative/path>": "<complete file contents>"}}. '
        "`files` must contain the full, runnable artifacts implementing this node "
        "so they can be built and tested — no prose, no placeholders."
        if node.writes and verify.any_behavioral(node.acceptance) else ""
    )
    prompt = Prompt(
        # cacheable prefix: identical for every node/agent in the run (domain +
        # file tree), so the provider serves it from cache after the first call.
        stable=_ws_stable(str(run_id), fp.domain),
        # variable tail: role, constraints, retrieved memory, and the chunks that
        # match *this* node — the only part that changes call to call.
        system="\n".join(x for x in (f"role={node.role}", profile, must_not, prior, chunks, contract) if x),
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
    # §P4b: redact the raw model output before it becomes a proposal — this scrubs
    # a leaked secret out of `choice`, every produced file, and semantic memory in
    # one place, upstream of the DB. The placeholder carries no quotes, so JSON
    # redacted as text still parses.
    text = redact(comp.text)
    try:
        b = json.loads(text)
        if isinstance(b, dict):
            b.setdefault("choice", text[:40])
            return b
    except (json.JSONDecodeError, TypeError):
        pass
    return {"choice": text.strip()[:60] or node.intent, "confidence": 0.6}


async def _fork_spec(run_id):
    """(fork node, override body) for a forked run, else (None, None) (§16.5)."""
    async with tenant_conn() as c:
        r = await c.fetchrow(
            "SELECT forked_at_node, fork_override FROM runs WHERE id=$1", run_id)
    if not r or not r["forked_at_node"]:
        return None, None
    ov = r["fork_override"]
    ov = json.loads(ov) if isinstance(ov, str) else ov
    return r["forked_at_node"], ov


async def _apply_override(run_id, node: NodeSpec, override: dict, pool: SandboxPool) -> None:
    """Install a forked decision at the divergence node without re-proposing —
    the user (or a resurrected dissent) already chose it. Verified for status,
    installed regardless: a fork is 'try this path from here'."""
    body = override["body"] if isinstance(override.get("body"), dict) else override
    agent = override.get("agent") or "fork"
    sb = await pool.acquire()
    try:
        vres = await verify.run(node.acceptance, body, sb)
    finally:
        await pool.release(sb)
    status = "passed" if vres.passed else "failed"
    choice = body.get("choice")
    if choice:
        subject = node.id.split(".")[0]
        await mem.write_semantic(run_id, subject, f"{subject} = {choice}",
                                 rationale=f"fork override at {node.id}", decided_by=agent)
    await mem.append_episodic(run_id, "node", {
        "node": node.id, "winner": agent, "status": status, "stage": 0,
        "text": f"{node.id} · {agent} · {status} (fork override)"})


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


async def _resurrect_and_settle(run_id, node: NodeSpec, sandbox):
    """§8: the winner failed → walk the dormant dissents for this node, highest
    stage first, re-verifying each stored proposal (behaviorally, in the node's
    sandbox). First one that passes is vindicated and returned as the effective
    (agent, body); the rest that get tried and fail are refuted. This is the
    resurrect/settle loop (§8) over SQL."""
    async with tenant_conn() as c:
        rows = await c.fetch(
            """SELECT id, dissenter, proposal FROM dissent
               WHERE run_id=$1 AND node_id=$2 AND status='dormant'
               ORDER BY stage DESC, id ASC""", run_id, node.id)
    for r in rows:
        body = json.loads(r["proposal"]) if isinstance(r["proposal"], str) else (r["proposal"] or {})
        vres = await verify.run(node.acceptance, body, sandbox)
        outcome = "vindicated" if vres.passed else "refuted"
        async with tenant_conn() as c:
            await c.execute("UPDATE dissent SET status=$2 WHERE id=$1", r["id"], outcome)
        await _bump_vind(r["dissenter"])
        await mem.append_episodic(run_id, "dissent",
            {"node": node.id, "text": f"{r['dissenter']} resurrected → {outcome}"})
        if vres.passed:
            # §P3b/§P3c: disprove the MUST NOT this verified alternative beat, and
            # promote the decision to knowledge if it's now repeatedly vindicated.
            from ..arbitration.dissent import on_vindicated
            await on_vindicated(run_id, node.id, body, r["dissenter"], node.constraints)
            return r["dissenter"], body
    return None


async def _bump_vind(agent: str) -> None:
    """Recompute an agent's vindication rate — shared with the manual-resurrect
    path (arbitration/dissent.py) so both triggers compute it identically."""
    from ..arbitration.dissent import recompute_vindication
    await recompute_vindication(agent)


# ── live state mutation on the shared agents rows ───────────────────────────
async def _roster() -> dict:
    async with tenant_conn() as c:
        agents = await c.fetch("SELECT agent, role, model, transport FROM agents WHERE enabled ORDER BY ordinal")
        from ..security import vault  # §P5: keys are sealed at rest, opened here
        creds = {r["model"]: vault.open_(r["api_key"]) for r in
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
    """§P3a: the arbiter ranks on confidence-shrunk posteriors, not raw rates.
    pass_rate shrinks (verified, trials); vindication_rate shrinks each agent's
    (vindicated, settled) dissents in this domain (live runs only — §P0). Thin
    samples sit near the prior, so a lucky streak can't outrank a veteran."""
    async with tenant_conn() as c:
        rows = await c.fetch(
            "SELECT agent, escalation_rate, verified, trials FROM agent_scores WHERE domain=$1",
            domain)
        vrows = await c.fetch(
            """SELECT d.dissenter AS agent,
                      count(*) FILTER (WHERE d.status='vindicated') AS v,
                      count(*) FILTER (WHERE d.status IN ('vindicated','refuted')) AS t
               FROM dissent d JOIN runs r ON r.id = d.run_id
               WHERE r.mode='live' AND r.fingerprint->>'domain'=$1
               GROUP BY d.dissenter""", domain)
    vind = {r["agent"]: (r["v"], r["t"]) for r in vrows}
    out = {}
    for r in rows:
        v, t = vind.get(r["agent"], (0, 0))
        out[r["agent"]] = AgentScore(
            pass_rate=confidence.posterior_mean(r["verified"], r["trials"]),
            escalation_rate=r["escalation_rate"],
            vindication_rate=confidence.posterior_mean(
                v, t, prior=confidence.VIND_PRIOR, strength=confidence.VIND_STRENGTH),
            vindicated=v, overruled=t,
            cohort=confidence.cohort(r["trials"], domain_trials=r["trials"]))
    return out


# ── §P2: cost-per-verified-result (routing input + run headline) ─────────────
async def _cost_per_verified(domain) -> dict:
    """Per-agent spend ÷ verified wins for this domain, from live runs only
    (agent_scores is fed by `_fold_scores` on live runs). Absent agent = unproven."""
    async with tenant_conn() as c:
        rows = await c.fetch(
            "SELECT agent, spend_usd, verified FROM agent_scores WHERE domain=$1 AND verified>0", domain)
    return {r["agent"]: float(r["spend_usd"]) / r["verified"] for r in rows}


async def _pitfall_count(domain) -> int:
    """How often this domain's fingerprint has burned us — a complexity input."""
    async with tenant_conn() as c:
        return int(await c.fetchval(
            "SELECT COALESCE(sum(occurrences),0) FROM pitfalls WHERE domain=$1", domain) or 0)


async def _bump_run_verified(run_id) -> None:
    async with tenant_conn() as c:
        await c.execute("UPDATE runs SET verified_count=verified_count+1 WHERE id=$1", run_id)


async def _fold_scores(domain) -> None:
    """Roll this run's per-agent spend + verified passes (the live `agents` rows,
    reset per run) into the cross-run cost-per-verified surface. Live runs only
    (§P0): a simulated run must never shift routing."""
    async with tenant_conn() as c:
        await c.execute(
            """INSERT INTO agent_scores (tenant_id, agent, domain, spend_usd, verified, trials)
               SELECT tenant_id, agent, $1, cost_usd, passes, attempts FROM agents WHERE calls>0
               ON CONFLICT (tenant_id, agent, domain) DO UPDATE
                 SET spend_usd = agent_scores.spend_usd + EXCLUDED.spend_usd,
                     verified  = agent_scores.verified  + EXCLUDED.verified,
                     trials    = agent_scores.trials    + EXCLUDED.trials""",
            domain)
