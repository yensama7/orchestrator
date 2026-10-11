"""Dissent ledger operations (§8, §20.6).

The *automatic* resurrect-on-verify-failure loop lives in the orchestrator — it
runs mid-walk and already holds the live NodeSpec. This module is the
*user-initiated* counterpart: the "instant rollback to the minority opinion"
behind the Dissent view's Resurrect button (§19.7). A human picks a dormant
dissent; we re-verify its stored proposal against the node's acceptance,
settle it (vindicated | refuted), credit vindication identically to the
automatic path, and — when it passes — install it as the active decision for
that node by superseding the majority's choice.

`recompute_vindication` is the single source of truth for the leaderboard
number; the orchestrator delegates to it so both trigger paths stay consistent.

Full run-forking from the resurrected node (§16.5) is the separate replay
feature; this delivers the rollback of the *decision*, which is the load-bearing
half the view promises.
"""

from __future__ import annotations

import json
from uuid import UUID

from ..contracts import SpecFingerprint
from ..db.tenancy import tenant_conn
from ..execution import verify
from ..execution.pool import scratch_sandbox
from ..memory import pitfalls as pitfalls_mod
from ..memory import store as mem
from ..memory import supersede as supersede_mod
from ..planning.plan import build_dag
from . import retention


async def recompute_vindication(agent: str) -> float | None:
    """Recompute an agent's vindication rate from its settled dissents and write
    it to the agents row (Agents-table 'Vind' column + dissent leaderboard).

    §P0: a settlement only counts as verified skill if its run ended `live` —
    a simulated run re-verifies with structural checks, so its vindications are
    no more real than a structural pass. Gated by each dissent's own run mode,
    not the current run, because this is an all-time cross-run number."""
    async with tenant_conn() as c:
        row = await c.fetchrow(
            """SELECT count(*) FILTER (WHERE d.status='vindicated') AS v,
                      count(*) FILTER (WHERE d.status IN ('vindicated','refuted')) AS t
               FROM dissent d JOIN runs r ON r.id = d.run_id
               WHERE d.dissenter=$1 AND r.mode='live'""", agent)
        pct = (row["v"] / row["t"] * 100) if row["t"] else None
        await c.execute("UPDATE agents SET vind_pct=$2 WHERE agent=$1", agent, pct)
    return pct


async def on_vindicated(run_id: UUID, node_id: str, body: dict, agent: str,
                        constraints: list[str]) -> bool:
    """Shared §P3b/§P3c bookkeeping for *either* settle path (auto in the
    orchestrator, manual here). A verified alternative beat the majority, so:

      §P3c — every MUST NOT the node carried was just overridden by a passing
              proposal → record a disproof against that pitfall; enough disproofs
              demote it from knowledge back to a hypothesis (stops gating).
      §P3b — if this exact decision has now been vindicated `PROMOTE_AT` times,
              promote it up the retention ladder to reusable knowledge: write it
              back as an active semantic decision that future runs retrieve.

    Returns whether a knowledge decision was promoted."""
    for fp in constraints or []:
        await pitfalls_mod.record_disproof(fp, run_id)

    subject = node_id.split(".")[0]
    choice = body.get("choice")
    if not choice:
        return False
    async with tenant_conn() as c:
        vind_count = await c.fetchval(
            """SELECT count(*) FROM dissent d JOIN runs r ON r.id = d.run_id
               WHERE r.mode='live' AND d.status='vindicated'
                 AND split_part(d.node_id,'.',1)=$1 AND d.proposal->>'choice'=$2""",
            subject, choice)
    # fire once, the moment it crosses the bar (not on every later vindication).
    if vind_count != retention.PROMOTE_AT:
        return False
    await mem.write_semantic(
        run_id, subject, f"{subject} = {choice}", decided_by=agent, confidence=0.85,
        rationale=f"promoted to knowledge: vindicated {vind_count}× across runs")
    await mem.append_episodic(run_id, "memory", {
        "node": node_id,
        "text": f"dissent promoted to knowledge: {subject}={choice} ({agent}, {vind_count}×)"})
    return True


async def resurrect(dissent_id: UUID) -> dict:
    """Manually resurrect a dormant dissent. Returns a result dict for the API."""
    async with tenant_conn() as c:
        d = await c.fetchrow(
            """SELECT dn.run_id, dn.node_id, dn.dissenter, dn.winner, dn.proposal,
                      dn.status, r.fingerprint, r.ceiling_usd
               FROM dissent dn JOIN runs r ON r.id = dn.run_id
               WHERE dn.id=$1""", dissent_id)
    if d is None:
        return {"ok": False, "reason": "not_found"}
    if d["status"] != "dormant":
        return {"ok": False, "reason": "not_dormant", "status": d["status"]}

    body = _loads(d["proposal"])
    node = _find_node(await build_dag(_fp(d["fingerprint"]), float(d["ceiling_usd"] or 10)),
                      d["node_id"])
    acceptance = node.acceptance if node else []

    async with scratch_sandbox() as sb:  # behavioral re-verify needs a workdir
        vres = await verify.run(acceptance, body, sb)
    outcome = "vindicated" if vres.passed else "refuted"
    async with tenant_conn() as c:
        await c.execute("UPDATE dissent SET status=$2 WHERE id=$1", dissent_id, outcome)
    pct = await recompute_vindication(d["dissenter"])

    installed = False
    if vres.passed:
        installed = await _install_decision(
            d["run_id"], d["node_id"], body, d["dissenter"])
        await on_vindicated(d["run_id"], d["node_id"], body, d["dissenter"],
                            node.constraints if node else [])
    await mem.append_episodic(d["run_id"], "dissent", {
        "node": d["node_id"],
        "text": f"{d['dissenter']} resurrected → {outcome} (manual)"})
    return {"ok": True, "outcome": outcome, "node": d["node_id"],
            "dissenter": d["dissenter"], "installed": installed,
            "vindication": round(pct, 1) if pct is not None else None,
            "summary": vres.summary}


async def _install_decision(run_id: UUID, node_id: str, body: dict, agent: str) -> bool:
    """Make the resurrected proposal the active decision for its subject,
    superseding the majority's in one transaction (so retrieval never sees two
    live decisions). Returns whether a decision row was written."""
    subject = node_id.split(".")[0]
    choice = f"{subject} = {body.get('choice') or subject}"
    rationale = f"resurrected minority proposal by {agent}"
    async with tenant_conn() as c:
        old_id = await c.fetchval(
            """SELECT id FROM semantic_memory
               WHERE run_id=$1 AND subject=$2 AND status='active'
               ORDER BY created_at DESC LIMIT 1""", run_id, subject)
    if old_id:
        await supersede_mod.supersede(old_id, run_id, subject, choice,
                                      rationale=rationale, decided_by=agent)
    else:
        await mem.write_semantic(run_id, subject, choice,
                                 rationale=rationale, decided_by=agent)
    return True


def _find_node(dag, node_id: str):
    return next((n for n in dag.nodes if n.id == node_id), None)


def _fp(raw) -> SpecFingerprint:
    fpd = json.loads(raw) if isinstance(raw, str) else (dict(raw) if raw else {})
    return SpecFingerprint(**{**{"domain": "other"}, **fpd})


def _loads(v) -> dict:
    return json.loads(v) if isinstance(v, str) else (v or {})
