"""FastAPI surface — every read computed from live tables (queries.py); writes
manage models/agents, import folders, and start real runs. No mockup blobs."""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import FastAPI, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import catalog
from ..arbitration import dissent as dissent_ops
from ..contracts import SpecFingerprint
from ..db import seed
from ..db.tenancy import close, migrate, tenant_conn
from ..execution import fork as fork_mod
from ..execution import orchestrator
from ..execution import reverify as reverify_mod
from ..execution import runner as runner_mod
from ..execution import worktree as worktree_mod
from ..memory import drift as drift_mod
from ..security import egress as egress_mod
from ..security import vault
from ..transports import Budget, Prompt, build as build_transport
from ..planning import extract as extract_mod
from ..planning import match as match_mod
from ..planning import plan as plan_mod
from ..planning import research as research_mod
from ..planning import roster as roster_mod
from . import queries

RUN = seed.RUN_UUID  # last-resort fallback when no run exists yet


async def _current_run(c) -> UUID:
    """The run the console defaults to: the one flagged is_current, else the most
    recent, else the seed fallback (empty db)."""
    cur = await c.fetchval("SELECT id FROM runs WHERE is_current LIMIT 1")
    if cur:
        return cur
    cur = await c.fetchval("SELECT id FROM runs ORDER BY created_at DESC LIMIT 1")
    return cur or RUN


async def _resolve(c, run: str | None) -> UUID:
    """Which run a read/write targets: an explicit, existing ?run=<uuid>, else the
    current run. Unknown/garbage ids fall through to current, never 500."""
    if run:
        try:
            rid = UUID(run)
        except ValueError:
            rid = None
        if rid and await c.fetchval("SELECT 1 FROM runs WHERE id=$1", rid):
            return rid
    return await _current_run(c)


async def _make_current(c, run_id: UUID) -> None:
    await c.execute("UPDATE runs SET is_current=false WHERE is_current")
    await c.execute("UPDATE runs SET is_current=true WHERE id=$1", run_id)


async def _drift_loop():
    """Periodic template freshness sweep (§18.2): recompute every template's
    drift against the registries, then re-verify whatever went stale. Entirely
    off the critical path — a failure is swallowed and retried next tick, it
    never touches a user's run. Disable with DRIFT_SWEEP=0."""
    interval = int(os.getenv("DRIFT_INTERVAL_SECONDS", "86400"))
    await asyncio.sleep(int(os.getenv("DRIFT_INITIAL_DELAY_SECONDS", "120")))
    while True:
        try:
            summary = await drift_mod.sweep()
            if summary["stale_ids"]:
                await reverify_mod.reverify_all(summary["stale_ids"])
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — background job must survive its own errors
            pass
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # wait for db, then seed demo substrate only if explicitly asked
    # (LINEAGE_SEED=1). Default: empty, user-driven.
    for attempt in range(30):
        try:
            async with tenant_conn() as c:
                await c.fetchval("SELECT 1")
            break
        except Exception:
            if attempt == 29:
                raise
            await asyncio.sleep(1)
    await migrate()  # idempotent — brings a stale volume up to the current schema
    await _refresh_egress()  # load user-defined per-role egress globs into the gate
    if os.getenv("LINEAGE_SEED") == "1":
        await seed.seed()
    drift_task = asyncio.create_task(_drift_loop()) if os.getenv("DRIFT_SWEEP", "1") != "0" else None
    yield
    if drift_task:
        drift_task.cancel()
    await close()


app = FastAPI(title="Lineage", lifespan=lifespan)
# In production the web tier reverse-proxies /api on its own origin, so no CORS
# is needed at all. CORS_ORIGINS (comma-separated) opens it for direct browser
# access; defaults to "*" for local dev convenience.
_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health():
    return {"ok": True}


# ── live reads ───────────────────────────────────────────────────────────────
@app.get("/api/runs")
async def list_runs():
    async with tenant_conn() as c:
        rows = await c.fetch(
            "SELECT id, name, status, mode, spent_usd, is_current, created_at FROM runs "
            "ORDER BY created_at DESC, name")
        current = await _current_run(c)
    return {
        "current": str(current),
        "runs": [{"id": str(r["id"]), "name": r["name"], "status": r["status"],
                  "mode": r["mode"], "spent": round(float(r["spent_usd"]), 2),
                  "current": r["id"] == current} for r in rows],
    }


@app.get("/api/run")
async def run(run: str | None = None):
    async with tenant_conn() as c:
        return await queries.run_header(c, await _resolve(c, run))


@app.get("/api/lineage")
async def lineage(run: str | None = None):
    async with tenant_conn() as c:
        return await queries.lineage_graph(c, await _resolve(c, run))


@app.get("/api/memory")
async def memory(run: str | None = None):
    async with tenant_conn() as c:
        return await queries.memory_view(c, await _resolve(c, run))


@app.get("/api/charts")
async def charts(run: str | None = None):
    async with tenant_conn() as c:
        return await queries.charts(c, await _resolve(c, run))


@app.get("/api/workspace")
async def workspace(run: str | None = None):
    async with tenant_conn() as c:
        return await queries.workspace_view(c, await _resolve(c, run))


@app.get("/api/agents")
async def agents():
    async with tenant_conn() as c:
        rows = await c.fetch(
            "SELECT agent, role, model, transport, state, calls, tokens, cached_pct, "
            "cost_usd, passes, attempts, vind_pct FROM agents ORDER BY ordinal")
    return [_agent_display(r) for r in rows]


@app.get("/api/dissent")
async def dissent(run: str | None = None):
    async with tenant_conn() as c:
        rid = await _resolve(c, run)
        rows = await c.fetch(
            """SELECT id, node_id AS node, dissenter, winner, stage, reason, status
               FROM dissent WHERE run_id=$1 ORDER BY created_at DESC, id DESC LIMIT 60""", rid)
        # §P0: the leaderboard is a verified-skill ranking (its `promote` flag
        # feeds routing), so it counts only dissents from `live` runs. The per-run
        # ledger below is unfiltered — the resurrect/settle demo stays fully
        # visible there, scoped by the run's mode badge.
        board = await c.fetch(
            """SELECT d.dissenter AS agent,
                      count(*) AS overruled,
                      count(*) FILTER (WHERE d.status='resurrected') AS resurrected,
                      count(*) FILTER (WHERE d.status='vindicated') AS vindicated,
                      count(*) FILTER (WHERE d.status='refuted') AS refuted
               FROM dissent d JOIN runs r ON r.id = d.run_id
               WHERE r.mode='live'
               GROUP BY d.dissenter ORDER BY vindicated DESC""")
        models = {r["agent"]: r["model"] for r in await c.fetch("SELECT agent, model FROM agents")}
    leaderboard = [{
        "agent": b["agent"], "model": models.get(b["agent"], "—"),
        "rate": round(b["vindicated"] / b["overruled"] * 100) if b["overruled"] else 0,
        "overruled": b["overruled"], "resurrected": b["resurrected"],
        "vindicated": b["vindicated"], "refuted": b["refuted"],
        "promote": (b["overruled"] and b["vindicated"] / b["overruled"] > 0.5),
    } for b in board]
    return {"leaderboard": leaderboard,
            "ledger": [{**dict(r), "id": str(r["id"])} for r in rows]}


@app.post("/api/dissent/{dissent_id}/resurrect")
async def resurrect_dissent(dissent_id: str):
    """§8/§19.7: user-triggered instant rollback to a minority opinion. Re-verifies
    the dormant proposal, settles it, credits vindication, and — if it passes —
    installs it as the active decision for its node."""
    try:
        did = UUID(dissent_id)
    except ValueError:
        return {"ok": False, "reason": "bad_id"}
    return await dissent_ops.resurrect(did)


# ── replay / forking (§16.5) ─────────────────────────────────────────────────
class ForkIn(BaseModel):
    from_node: str
    override: dict | None = None  # {choice: ...} or {agent, body}; None = plain replay


@app.post("/api/runs/{run_id:path}/fork")
async def fork_run(run_id: str, body: ForkIn):
    """Fork a run at a node, re-running from there with the decision at that node
    overridden (or re-run unchanged when override is null — deterministic replay)."""
    async with tenant_conn() as c:
        rid = await _resolve(c, run_id)
    return await fork_mod.create(rid, body.from_node, body.override)


@app.post("/api/dissent/{dissent_id}/fork")
async def fork_dissent(dissent_id: str):
    """One-click fork from a dormant dissent, using its minority proposal (§19.7)."""
    try:
        did = UUID(dissent_id)
    except ValueError:
        return {"ok": False, "reason": "bad_id"}
    return await fork_mod.from_dissent(did)


# ── settings: catalog, credentials, agents ──────────────────────────────────
@app.get("/api/catalog")
async def get_catalog():
    # merge models actually installed on the local Ollama server so any local
    # model present in the system can be added — not just the hardcoded few.
    providers = [dict(p) for p in catalog.CATALOG]
    installed = await _discover_local_models()
    if installed:
        prov = next(p for p in providers if p["provider"].startswith("Local"))
        known = {m["id"] for m in prov["models"]}
        prov["models"] = prov["models"] + [
            {"id": m, "label": f"{m} (installed)", "transports": ["local"]}
            for m in installed if m not in known]
    # merge OpenRouter's live catalogue so any model it serves can be added with
    # the one OPENROUTER_API_KEY — not just the curated few (same shape as above).
    orouter = await _discover_openrouter_models()
    if orouter:
        prov = next(p for p in providers if p["provider"] == "OpenRouter")
        known = {m["id"] for m in prov["models"]}
        prov["models"] = prov["models"] + [
            {"id": m["id"], "label": m["label"], "transports": ["api"]}
            for m in orouter if m["id"] not in known]
    return {"providers": providers, "roles": catalog.ROLE_HINTS}


async def _discover_openrouter_models() -> list[dict]:
    """OpenRouter's public model list (no key needed). OPENROUTER_DISCOVER=0 to
    stay on the curated set. Unreachable → curated defaults only."""
    if os.getenv("OPENROUTER_DISCOVER", "1") == "0":
        return []
    try:
        import httpx
        async with httpx.AsyncClient(timeout=4) as c:
            r = await c.get("https://openrouter.ai/api/v1/models")
            r.raise_for_status()
            return [{"id": m["id"], "label": m.get("name", m["id"])} for m in r.json().get("data", [])]
    except Exception:
        return []


async def _discover_local_models() -> list[str]:
    from ..transports.local import _OLLAMA
    if not _OLLAMA:
        return []
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(f"{_OLLAMA}/api/tags")
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []  # server down/unreachable → just the catalog defaults


@app.get("/api/settings")
async def settings():
    async with tenant_conn() as c:
        creds = await c.fetch("SELECT model, transport, enabled, api_key FROM model_credentials ORDER BY added_at")
        ags = await c.fetch("SELECT agent, role, model, transport, enabled FROM agents ORDER BY ordinal")
    return {
        "credentials": [{"model": r["model"], "transport": r["transport"], "enabled": r["enabled"],
                         "has_key": bool(r["api_key"]), "key_hint": _mask(vault.open_(r["api_key"]))} for r in creds],
        "agents": [dict(r) for r in ags],
    }


class CredIn(BaseModel):
    model: str
    transport: str = "api"
    api_key: str | None = None
    enabled: bool = True


async def _probe(model: str, transport: str, api_key: str | None) -> dict:
    """One tiny live call to confirm a credential actually works. Never raises —
    a bad key/CLI is reported, not thrown, so the row still saves and the user
    can fix it in place."""
    try:
        t = build_transport(model, transport, api_key)
        comp = await asyncio.wait_for(
            t.complete(Prompt(system="Reply with the single word OK.", user="ping"),
                       budget=Budget(usd=0.002)),
            timeout=40)
        return {"working": True, "detail": (comp.text or "").strip()[:60] or "ok"}
    except Exception as e:
        return {"working": False, "detail": f"{type(e).__name__}: {e}"[:200]}


@app.post("/api/settings/credentials")
async def add_cred(body: CredIn):
    # test the key/CLI before we save it. api needs a key to test; if the row
    # already exists and no new key was sent, fall back to the stored key.
    effective_key = body.api_key
    if body.transport == "api" and not effective_key:
        async with tenant_conn() as c:
            effective_key = vault.open_(await c.fetchval(
                "SELECT api_key FROM model_credentials WHERE model=$1", body.model))
    test: dict | None = None
    if body.transport != "api" or effective_key:
        test = await _probe(body.model, body.transport, effective_key)
    # §P5: seal the key before it touches the DB — a dump/backup/row-log never
    # carries a usable key. require=True for an api key fails closed rather than
    # silently storing plaintext when LINEAGE_SECRET_KEY is unset.
    try:
        sealed = vault.seal(body.api_key, require=body.transport == "api" and bool(body.api_key))
    except RuntimeError as e:
        return {"ok": False, "tested": False, "detail": str(e)}
    async with tenant_conn() as c:
        # COALESCE keeps the stored (sealed) key when the user edits a row
        # without re-entering it.
        await c.execute(
            """INSERT INTO model_credentials (tenant_id, model, transport, api_key, enabled)
               VALUES (current_setting('app.tenant_id')::uuid, $1,$2,$3,$4)
               ON CONFLICT (tenant_id, model) DO UPDATE
                 SET transport=EXCLUDED.transport,
                     api_key=COALESCE(EXCLUDED.api_key, model_credentials.api_key),
                     enabled=EXCLUDED.enabled""",
            body.model, body.transport, sealed, body.enabled)
    return {"ok": True, "tested": test is not None, **(test or {"detail": "no key to test"})}


@app.post("/api/settings/credentials/{model}/test")
async def test_cred(model: str):
    async with tenant_conn() as c:
        r = await c.fetchrow(
            "SELECT model, transport, api_key FROM model_credentials WHERE model=$1", model)
    if r is None:
        return {"tested": False, "working": False, "detail": "not configured"}
    return {"tested": True, **await _probe(r["model"], r["transport"], vault.open_(r["api_key"]))}


@app.delete("/api/settings/credentials/{model}")
async def del_cred(model: str):
    async with tenant_conn() as c:
        await c.execute("DELETE FROM model_credentials WHERE model=$1", model)
    return {"ok": True}


class AgentIn(BaseModel):
    agent: str
    role: str
    model: str
    transport: str = "api"


@app.post("/api/settings/agents")
async def add_agent(body: AgentIn):
    async with tenant_conn() as c:
        n = await c.fetchval("SELECT count(*) FROM agents")
        await c.execute(
            """INSERT INTO agents (tenant_id, agent, role, model, transport, ordinal)
               VALUES (current_setting('app.tenant_id')::uuid, $1,$2,$3,$4,$5)
               ON CONFLICT (tenant_id, agent) DO UPDATE
                 SET role=EXCLUDED.role, model=EXCLUDED.model, transport=EXCLUDED.transport""",
            body.agent, body.role, body.model, body.transport, n)
    return {"ok": True}


@app.delete("/api/settings/agents/{agent}")
async def del_agent(agent: str):
    async with tenant_conn() as c:
        await c.execute("DELETE FROM agents WHERE agent=$1", agent)
    return {"ok": True}


# ── roles: user-defined, central agent researches skills/resources ───────────
class RoleIn(BaseModel):
    name: str
    description: str = ""
    egress: list[str] | None = None  # user-editable per-role host allowlist (§11)


async def _refresh_egress() -> None:
    """Load every role's egress globs into the security gate. Called at startup
    and after any role mutation, so the allowlist the broker enforces tracks what
    the user has configured without a restart."""
    async with tenant_conn() as c:
        rows = await c.fetch("SELECT name, egress FROM roles")
    egress_mod.set_overrides({r["name"]: _jarr(r["egress"]) for r in rows})


async def _save_role(name, description, skills, resources, egress) -> None:
    async with tenant_conn() as c:
        await c.execute(
            """INSERT INTO roles (tenant_id, name, description, skills, resources, egress, researched_at)
               VALUES (current_setting('app.tenant_id')::uuid, $1,$2,$3::jsonb,$4::jsonb,$5::jsonb, now())
               ON CONFLICT (tenant_id, name) DO UPDATE
                 SET description=EXCLUDED.description, skills=EXCLUDED.skills,
                     resources=EXCLUDED.resources, egress=EXCLUDED.egress, researched_at=now()""",
            name, description, json.dumps(skills), json.dumps(resources), json.dumps(egress))
    await _refresh_egress()


@app.get("/api/roles")
async def list_roles():
    async with tenant_conn() as c:
        rows = await c.fetch(
            "SELECT name, description, skills, resources, egress, researched_at FROM roles ORDER BY name")
    return [{"name": r["name"], "description": r["description"],
             "skills": _jarr(r["skills"]), "resources": _jarr(r["resources"]),
             "egress": _jarr(r["egress"]),
             "researched_at": r["researched_at"].isoformat() if r["researched_at"] else None}
            for r in rows]


@app.get("/api/roles/presets")
async def list_role_presets():
    """ECC-derived starter roles the user can add with one click (no research call)."""
    return catalog.ROLE_PRESETS


@app.post("/api/roles/presets/{name}")
async def add_role_preset(name: str):
    preset = next((p for p in catalog.ROLE_PRESETS if p["name"] == name), None)
    if not preset:
        return {"ok": False, "error": f"no preset named {name}"}
    await _save_role(preset["name"], preset["description"], preset["skills"],
                     preset["resources"], preset.get("egress", []))
    return {"ok": True, **{k: preset[k] for k in ("skills", "resources") if k in preset}}


@app.post("/api/roles")
async def add_role(body: RoleIn):
    # central agent researches the role (new or existing — this refreshes it)
    profile = await research_mod.research_role(body.name, body.description)
    await _save_role(body.name, body.description, profile["skills"],
                     profile["resources"], body.egress or [])
    return {"ok": True, **profile}


@app.delete("/api/roles/{name}")
async def del_role(name: str):
    async with tenant_conn() as c:
        await c.execute("DELETE FROM roles WHERE name=$1", name)
    await _refresh_egress()
    return {"ok": True}


# ── workspace import ────────────────────────────────────────────────────────
@app.post("/api/workspace/import")
async def import_folder(files: list[UploadFile], paths: str = Form("[]"), run: str | None = None):
    rel = json.loads(paths)
    async with tenant_conn() as c:
        RUN = await _resolve(c, run)
        if not await c.fetchval("SELECT 1 FROM runs WHERE id=$1", RUN):
            # import-first flow (no run yet): attach files to a fresh draft run
            RUN = uuid4()
            await c.execute(
                """INSERT INTO runs (id, tenant_id, name, fingerprint, status, ceiling_usd)
                   VALUES ($1, current_setting('app.tenant_id')::uuid, 'imported worktree', '{}'::jsonb, 'active', 15)""",
                RUN)
            await _make_current(c, RUN)
        n = await c.fetchval("SELECT count(*) FROM worktree_files WHERE run_id=$1", RUN)
        first_open_set = await c.fetchval(
            "SELECT count(*) FROM worktree_files WHERE run_id=$1 AND is_open", RUN)
        imported = 0
        for i, up in enumerate(files):
            path = rel[i] if i < len(rel) else up.filename
            data = await up.read()
            if len(data) > 250_000:
                continue
            try:
                content = data.decode("utf-8")
            except UnicodeDecodeError:
                continue  # skip binaries
            parts = path.replace("\\", "/").split("/")
            name = parts[-1]
            folder = ("/".join(parts[:-1]) + "/") if len(parts) > 1 else "./"
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            is_open = not first_open_set and ext in ("py", "ts", "tsx", "js", "sql", "rs", "go", "md")
            await c.execute(
                """INSERT INTO worktree_files (tenant_id, run_id, folder, name, ext, content, blame, ordinal, is_open)
                   VALUES (current_setting('app.tenant_id')::uuid,$1,$2,$3,$4,$5,'[]'::jsonb,$6,$7)
                   ON CONFLICT (tenant_id, run_id, folder, name) DO UPDATE SET content=EXCLUDED.content""",
                RUN, folder, name, ext, content, n + i, is_open)
            if is_open:
                first_open_set = 1
            imported += 1
    return {"imported": imported}


@app.delete("/api/workspace")
async def clear_workspace(run: str | None = None):
    async with tenant_conn() as c:
        await c.execute("DELETE FROM worktree_files WHERE run_id=$1", await _resolve(c, run))
    return {"ok": True}


# ── planning + run ──────────────────────────────────────────────────────────
class BriefIn(BaseModel):
    brief: str


class FpIn(BaseModel):
    fingerprint: dict
    budget: float = 15.0


@app.post("/api/extract")
async def extract(body: BriefIn):
    return (await extract_mod.extract(body.brief)).model_dump()


@app.post("/api/match")
async def match(body: FpIn):
    return await match_mod.match(SpecFingerprint(**body.fingerprint))


@app.post("/api/roster")
async def roster(body: FpIn):
    return await roster_mod.propose(SpecFingerprint(**body.fingerprint).domain)


@app.post("/api/plan")
async def plan(body: FpIn):
    dag = await plan_mod.build_dag(SpecFingerprint(**body.fingerprint), body.budget)
    return dag.model_dump()


class StartIn(BaseModel):
    fingerprint: dict | None = None
    ceiling: float = 15.0
    name: str | None = None


@app.post("/api/runs/{run_id:path}/start")
async def start(run_id: str, body: StartIn | None = None):
    """Start a run. `new` (what the wizard posts) mints a fresh run and makes it
    current, so every New Run is a distinct, addressable run in the history — not
    a reused UUID. Re-starting an existing run id re-runs that one."""
    fp = json.dumps((body.fingerprint if body else None) or {"domain": "other"})
    name = (body.name if body else None) or "untitled run"
    ceiling = body.ceiling if body else 15.0
    async with tenant_conn() as c:
        try:
            existing = UUID(run_id)
        except ValueError:
            existing = None
        rid = existing if existing and await c.fetchval(
            "SELECT 1 FROM runs WHERE id=$1", existing) else None
        if rid is None:  # `new` / unknown id → create a fresh run
            rid = uuid4()
            await c.execute(
                """INSERT INTO runs (id, tenant_id, name, fingerprint, status, spent_usd, ceiling_usd)
                   VALUES ($1, current_setting('app.tenant_id')::uuid, $2, $3::jsonb, 'active', 0, $4)""",
                rid, name, fp, ceiling)
        await _make_current(c, rid)
    ok = await orchestrator.start(rid)
    return {"started": ok, "run": str(rid)}


@app.post("/api/runs/{run_id:path}/run")
async def run_compose(run_id: str):
    """§7 Run gate: materialise the imported worktree (stored in the DB) to a temp
    dir, gate it (compose required), and `docker compose up` if ready. This is what
    wires runner.py into the live path — previously it had no caller."""
    async with tenant_conn() as c:
        rid = await _resolve(c, run_id)
    wt = await worktree_mod.materialise(rid, prefix="lineage-run-")
    if wt is None:
        return {"started": False, "reason": "empty_worktree"}
    g = runner_mod.gate(wt)
    if not g.ready:
        return {"started": False, "reason": g.reason,
                "offer": {"label": g.offer.label, "task": g.offer.task}}
    try:
        await runner_mod.start(wt, g)
    except FileNotFoundError:
        return {"started": False, "reason": "docker_missing", "worktree": str(wt)}
    except RuntimeError as e:
        return {"started": False, "reason": str(e), "worktree": str(wt)}
    return {"started": True, "file": g.file, "kind": g.kind, "worktree": str(wt)}


# ── templates: freshness / drift (§18.2) ─────────────────────────────────────
@app.get("/api/templates")
async def list_templates():
    async with tenant_conn() as c:
        rows = await c.fetch(
            """SELECT id, name, domain, version, status, drift_score, node_count,
                      carried_decisions, source_run_id, freshness_checked_at, reverified_at
               FROM templates ORDER BY created_at DESC""")
    return {"templates": [{
        "id": str(r["id"]), "name": r["name"], "domain": r["domain"],
        "version": r["version"], "status": r["status"],
        "drift": round(float(r["drift_score"] or 0), 3),
        "nodes": r["node_count"], "decisions": r["carried_decisions"],
        "source_run": str(r["source_run_id"]) if r["source_run_id"] else None,
        "checked_at": r["freshness_checked_at"].isoformat() if r["freshness_checked_at"] else None,
        "reverified_at": r["reverified_at"].isoformat() if r["reverified_at"] else None,
    } for r in rows]}


@app.post("/api/templates/drift")
async def run_drift_sweep():
    """Recompute freshness for every template now, then re-verify what went
    stale. Normally runs on a timer (§18.2); this is the manual trigger."""
    summary = await drift_mod.sweep()
    reverified = (await reverify_mod.reverify_all(summary["stale_ids"])
                  if summary["stale_ids"] else {})
    return {"summary": summary, "reverified": reverified}


@app.post("/api/templates/{template_id}/reverify")
async def reverify_template(template_id: str):
    try:
        tid = UUID(template_id)
    except ValueError:
        return {"ok": False, "reason": "bad_id"}
    return {"ok": True, "outcome": await reverify_mod.reverify(tid)}


@app.get("/api/runs/{run_id:path}/stream")
async def stream(run_id: str):
    async with tenant_conn() as c:
        rid = await _resolve(c, run_id)
    async def gen():
        last = max(0, await _max_event_id(rid) - 8)
        while True:
            async with tenant_conn() as c:
                rows = await c.fetch(
                    "SELECT id, kind, payload FROM episodic_events WHERE run_id=$1 AND id>$2 "
                    "ORDER BY id LIMIT 50", rid, last)
            for r in rows:
                last = r["id"]
                payload = json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
                if r["kind"] == "spend":
                    yield f"event: spend\ndata: {json.dumps(payload)}\n\n"
                else:
                    ev = {"key": payload.get("key", r["kind"]),
                          "text": payload.get("text", json.dumps(payload))}
                    yield f"event: ticker\ndata: {json.dumps(ev)}\n\n"
            await asyncio.sleep(1.5)

    return StreamingResponse(gen(), media_type="text/event-stream")


# ── helpers ─────────────────────────────────────────────────────────────────
async def _max_event_id(run_id) -> int:
    async with tenant_conn() as c:
        return int(await c.fetchval(
            "SELECT COALESCE(max(id),0) FROM episodic_events WHERE run_id=$1", run_id) or 0)


def _agent_display(r) -> dict:
    return {
        "agent": r["agent"], "role": r["role"], "model": r["model"],
        "state": r["state"], "calls": r["calls"], "tokens": _humanize(r["tokens"]),
        "cached": f"{round(r['cached_pct'])}%" if r["cached_pct"] is not None else "—",
        "cost": f"${float(r['cost_usd']):.2f}",
        "pass": f"{round(r['passes'] / r['attempts'] * 100)}%" if r["attempts"] else "—",
        "vind": f"{round(r['vind_pct'])}%" if r["vind_pct"] is not None else "—",
    }


def _humanize(n: int) -> str:
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def _jarr(v) -> list:
    return json.loads(v) if isinstance(v, str) else (v or [])


def _mask(key: str | None) -> str:
    if not key:
        return ""
    return key[:3] + "…" + key[-4:] if len(key) > 8 else "•••"
