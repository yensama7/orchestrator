"""Async re-verification of a stale template (§18.2).

A template that drifted to `stale` is re-checked off the critical path: its
source run's worktree is materialised to scratch and smoke-built with
`docker compose build` — the cheapest thing that proves the recorded setup
still stands up.

    build passes → repin the manifest, bump version, set `fresh`
    build fails  → `quarantined` (excluded from retrieval) and the failure is
                   written to `pitfalls`, so the next plan in that domain
                   inherits the knowledge

Inconclusive outcomes (no source worktree, not containerised, Docker absent)
never quarantine — absence of a build is not a failing build. They stamp
`reverified_at` and leave status untouched for the next sweep.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from uuid import UUID

from ..db.tenancy import tenant_conn
from ..memory import manifest as manifest_mod
from . import runner, worktree

_BUILD_TIMEOUT = 600  # seconds; a smoke build, not a full run


async def reverify(template_id: UUID) -> str:
    """Re-verify one template. Returns the outcome string (also the new status
    for the decisive cases)."""
    async with tenant_conn() as c:
        row = await c.fetchrow(
            "SELECT source_run_id, domain, version FROM templates WHERE id=$1", template_id)
    if row is None:
        return "unknown"
    source_run_id = row["source_run_id"]
    if source_run_id is None:
        await _stamp(template_id)
        return "unverifiable"  # seed/global template, nothing to rebuild

    wt = await worktree.materialise(source_run_id, prefix="lineage-reverify-")
    if wt is None:
        await _stamp(template_id)
        return "unverifiable"
    try:
        g = runner.gate(wt)
        if not g.ready:
            await _stamp(template_id)
            return "unverifiable"
        try:
            rc, log = await _compose_build(wt, g.file)
        except FileNotFoundError:
            await _stamp(template_id)
            return "docker_missing"
        if rc == 0:
            await _repin(template_id, wt, row["version"])
            return "fresh"
        await _quarantine(template_id, row["domain"], log)
        return "quarantined"
    finally:
        shutil.rmtree(wt, ignore_errors=True)


async def reverify_all(template_ids: list[str]) -> dict[str, str]:
    """Re-verify a batch sequentially (compose builds are heavy — no parallelism)."""
    out: dict[str, str] = {}
    for tid in template_ids:
        try:
            out[tid] = await reverify(UUID(tid))
        except Exception as e:  # noqa: BLE001 — one bad template can't stop the batch
            out[tid] = f"error:{str(e)[:60]}"
    return out


async def _compose_build(worktree_path, compose_file: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "docker", "compose", "-f", compose_file, "build",
        cwd=str(worktree_path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=_BUILD_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        return 124, "build timed out"
    return proc.returncode or 0, (out or b"").decode("utf-8", "replace")[-2000:]


async def _stamp(template_id: UUID) -> None:
    async with tenant_conn() as c:
        await c.execute("UPDATE templates SET reverified_at=now() WHERE id=$1", template_id)


async def _repin(template_id: UUID, wt, version: int) -> None:
    files = {str(p.relative_to(wt)): p.read_text(encoding="utf-8", errors="replace")
             for p in wt.rglob("*") if p.is_file()}
    pinned = manifest_mod.parse(files)
    async with tenant_conn() as c:
        await c.execute(
            """UPDATE templates SET status='fresh', drift_score=0, version=$2,
                   manifest=$3::jsonb, reverified_at=now(), freshness_checked_at=now()
               WHERE id=$1""",
            template_id, version + 1, json.dumps(pinned))


async def _quarantine(template_id: UUID, domain: str, log: str) -> None:
    signature = f"template-reverify-fail:{template_id}"
    async with tenant_conn() as c:
        await c.execute(
            "UPDATE templates SET status='quarantined', reverified_at=now() WHERE id=$1",
            template_id)
        # record the failure as a first-class pitfall so the next plan in this
        # domain inherits it (§6). Deduped on (tenant_id, fingerprint).
        await c.execute(
            """INSERT INTO pitfalls (tenant_id, fingerprint, domain, trigger, symptom,
                   occurrences, last_seen_at)
               VALUES (current_setting('app.tenant_id')::uuid, $1, $2,
                   jsonb_build_object('kind','template_reverify'), $3, 1, now())
               ON CONFLICT (tenant_id, fingerprint)
               DO UPDATE SET occurrences = pitfalls.occurrences + 1,
                   symptom = excluded.symptom, last_seen_at = now()""",
            signature, domain, f"re-verification build failed: {log.strip()[-240:]}")
    # §P3c: re-derive hypothesis/knowledge from the new failure count — repeated
    # verified failure is what earns a pitfall its MUST NOT status.
    from ..memory import pitfalls as pitfalls_mod
    await pitfalls_mod.recompute(signature)
