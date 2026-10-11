"""Deterministic replay with forking (§16.5).

Scrub a run back to node N, change one decision, re-run from there. Because the
DAG walk is model-free (the planner wrote the graph, the scheduler only walks
it), everything up to N is reproducible, so a fork only has to:

  1. mint a child run that shares the parent's fingerprint, ceiling and worktree
  2. carry forward the parent's *active* decisions for every node before N
     (copied as-is, embeddings included — no re-embed, no re-dispatch)
  3. pin an override for node N (an edited choice, or — the Dissent view's
     one-click path — a resurrected minority proposal; §8)
  4. hand the child to the orchestrator, which skips the carried nodes, installs
     the override at N, and re-runs N onward normally

A plain replay-from-N is just a fork with no override. The child appears in the
Lineage graph linked to its parent, so a run's forks read as a tree.
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

from ..contracts import SpecFingerprint
from ..db.tenancy import tenant_conn
from ..planning.plan import build_dag
from . import orchestrator, scheduler


async def create(parent_run_id: UUID, from_node: str,
                 override: dict | None = None) -> dict:
    """Create and launch a fork. Returns {ok, run} or {ok: False, reason}."""
    async with tenant_conn() as c:
        parent = await c.fetchrow(
            "SELECT name, fingerprint, ceiling_usd FROM runs WHERE id=$1", parent_run_id)
    if parent is None:
        return {"ok": False, "reason": "parent_not_found"}

    fp = _fp(parent["fingerprint"])
    ceiling = float(parent["ceiling_usd"] or 10)
    dag = await build_dag(fp, ceiling)
    order = [n.id for n in dag.nodes]
    if from_node not in order:
        return {"ok": False, "reason": "unknown_node", "node": from_node}
    _, carried_subjects = scheduler.resume_plan(order, from_node)

    child = uuid4()
    name = f"fork of {parent['name']} @ {from_node}"
    async with tenant_conn() as c:
        async with c.transaction():
            await c.execute(
                """INSERT INTO runs (id, tenant_id, name, fingerprint, status,
                       spent_usd, ceiling_usd, forked_from, forked_at_node, fork_override)
                   VALUES ($1, current_setting('app.tenant_id')::uuid, $2, $3::jsonb,
                       'active', 0, $4, $5, $6, $7::jsonb)""",
                child, name, json.dumps(_fp_dict(parent["fingerprint"])), ceiling,
                parent_run_id, from_node, json.dumps(override) if override else None)
            # copy worktree so the fork builds/runs the same project
            await c.execute(
                """INSERT INTO worktree_files (tenant_id, run_id, folder, name, ext,
                       content, blame, ordinal, is_open)
                   SELECT tenant_id, $1, folder, name, ext, content, blame, ordinal, is_open
                   FROM worktree_files WHERE run_id=$2""", child, parent_run_id)
            # carry forward the decisions made before the divergence point
            if carried_subjects:
                await c.execute(
                    """INSERT INTO semantic_memory (tenant_id, run_id, subject, choice,
                           rationale, status, decided_by, confidence, embedding)
                       SELECT tenant_id, $1, subject, choice, rationale, 'active',
                           decided_by, confidence, embedding
                       FROM semantic_memory
                       WHERE run_id=$2 AND status='active' AND subject = ANY($3::text[])""",
                    child, parent_run_id, carried_subjects)
            await c.execute("UPDATE runs SET is_current=false WHERE is_current")
            await c.execute("UPDATE runs SET is_current=true WHERE id=$1", child)

    await orchestrator.start(child)
    return {"ok": True, "run": str(child), "from_node": from_node,
            "carried": len(carried_subjects)}


async def from_dissent(dissent_id: UUID) -> dict:
    """Fork a run at a dormant dissent's node, using that minority proposal as
    the override — the Dissent view's one-click 'fork from here' (§8/§19.7). A
    resurrected minority proposal *is* a fork."""
    async with tenant_conn() as c:
        d = await c.fetchrow(
            "SELECT run_id, node_id, dissenter, proposal FROM dissent WHERE id=$1", dissent_id)
    if d is None:
        return {"ok": False, "reason": "dissent_not_found"}
    body = json.loads(d["proposal"]) if isinstance(d["proposal"], str) else (d["proposal"] or {})
    return await create(d["run_id"], d["node_id"],
                        override={"agent": d["dissenter"], "body": body})


def _fp(raw) -> SpecFingerprint:
    return SpecFingerprint(**{**{"domain": "other"}, **_fp_dict(raw)})


def _fp_dict(raw) -> dict:
    return json.loads(raw) if isinstance(raw, str) else (dict(raw) if raw else {})
