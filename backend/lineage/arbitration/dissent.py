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
from ..memory import store as mem
from ..memory import supersede as supersede_mod
from ..planning.plan import build_dag


async def recompute_vindication(agent: str) -> float | None:
    """Recompute an agent's vindication rate from its settled dissents and write
    it to the agents row (Agents-table 'Vind' column + dissent leaderboard)."""
    async with tenant_conn() as c:
        row = await c.fetchrow(
            """SELECT count(*) FILTER (WHERE status='vindicated') AS v,
                      count(*) FILTER (WHERE status IN ('vindicated','refuted')) AS t
               FROM dissent WHERE dissenter=$1""", agent)
        pct = (row["v"] / row["t"] * 100) if row["t"] else None
        await c.execute("UPDATE agents SET vind_pct=$2 WHERE agent=$1", agent, pct)
    return pct


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

    vres = await verify.run(acceptance, body)
    outcome = "vindicated" if vres.passed else "refuted"
    async with tenant_conn() as c:
        await c.execute("UPDATE dissent SET status=$2 WHERE id=$1", dissent_id, outcome)
    pct = await recompute_vindication(d["dissenter"])

    installed = False
    if vres.passed:
        installed = await _install_decision(
            d["run_id"], d["node_id"], body, d["dissenter"])
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
