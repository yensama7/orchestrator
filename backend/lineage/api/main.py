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
from ..contracts import SpecFingerprint
from ..db import seed
from ..db.tenancy import close, migrate, tenant_conn
from ..execution import orchestrator
from ..execution import runner as runner_mod
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
    if os.getenv("LINEAGE_SEED") == "1":
        await seed.seed()
    yield
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
            "SELECT id, name, status, spent_usd, is_current, created_at FROM runs "
            "ORDER BY created_at DESC, name")
        current = await _current_run(c)
    return {
        "current": str(current),
        "runs": [{"id": str(r["id"]), "name": r["name"], "status": r["status"],
                  "spent": round(float(r["spent_usd"]), 2),
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
            """SELECT node_id AS node, dissenter, winner, stage, reason, status
               FROM dissent WHERE run_id=$1 ORDER BY created_at DESC, id DESC LIMIT 60""", rid)
        board = await c.fetch(
            """SELECT dissenter AS agent,
                      count(*) AS overruled,
                      count(*) FILTER (WHERE status='resurrected') AS resurrected,
                      count(*) FILTER (WHERE status='vindicated') AS vindicated,
                      count(*) FILTER (WHERE status='refuted') AS refuted
               FROM dissent GROUP BY dissenter ORDER BY vindicated DESC""")
        models = {r["agent"]: r["model"] for r in await c.fetch("SELECT agent, model FROM agents")}
    leaderboard = [{
        "agent": b["agent"], "model": models.get(b["agent"], "—"),
        "rate": round(b["vindicated"] / b["overruled"] * 100) if b["overruled"] else 0,
        "overruled": b["overruled"], "resurrected": b["resurrected"],
        "vindicated": b["vindicated"], "refuted": b["refuted"],
        "promote": (b["overruled"] and b["vindicated"] / b["overruled"] > 0.5),
    } for b in board]
    return {"leaderboard": leaderboard, "ledger": [dict(r) for r in rows]}


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
    return {"providers": providers, "roles": catalog.ROLE_HINTS}


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
                         "has_key": bool(r["api_key"]), "key_hint": _mask(r["api_key"])} for r in creds],
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
            effective_key = await c.fetchval(
                "SELECT api_key FROM model_credentials WHERE model=$1", body.model)
    test: dict | None = None
    if body.transport != "api" or effective_key:
        test = await _probe(body.model, body.transport, effective_key)
    async with tenant_conn() as c:
        await c.execute(
            """INSERT INTO model_credentials (tenant_id, model, transport, api_key, enabled)
               VALUES (current_setting('app.tenant_id')::uuid, $1,$2,$3,$4)
               ON CONFLICT (tenant_id, model) DO UPDATE
                 SET transport=EXCLUDED.transport,
                     api_key=COALESCE(EXCLUDED.api_key, model_credentials.api_key),
                     enabled=EXCLUDED.enabled""",
            body.model, body.transport, body.api_key, body.enabled)
    return {"ok": True, "tested": test is not None, **(test or {"detail": "no key to test"})}


@app.post("/api/settings/credentials/{model}/test")
async def test_cred(model: str):
    async with tenant_conn() as c:
        r = await c.fetchrow(
            "SELECT model, transport, api_key FROM model_credentials WHERE model=$1", model)
    if r is None:
        return {"tested": False, "working": False, "detail": "not configured"}
    return {"tested": True, **await _probe(r["model"], r["transport"], r["api_key"])}


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


@app.get("/api/roles")
async def list_roles():
    async with tenant_conn() as c:
        rows = await c.fetch(
            "SELECT name, description, skills, resources, researched_at FROM roles ORDER BY name")
    return [{"name": r["name"], "description": r["description"],
             "skills": _jarr(r["skills"]), "resources": _jarr(r["resources"]),
             "researched_at": r["researched_at"].isoformat() if r["researched_at"] else None}
            for r in rows]


@app.post("/api/roles")
async def add_role(body: RoleIn):
    # central agent researches the role (new or existing — this refreshes it)
    profile = await research_mod.research_role(body.name, body.description)
    async with tenant_conn() as c:
        await c.execute(
            """INSERT INTO roles (tenant_id, name, description, skills, resources, researched_at)
               VALUES (current_setting('app.tenant_id')::uuid, $1,$2,$3::jsonb,$4::jsonb, now())
               ON CONFLICT (tenant_id, name) DO UPDATE
                 SET description=EXCLUDED.description, skills=EXCLUDED.skills,
                     resources=EXCLUDED.resources, researched_at=now()""",
            body.name, body.description,
            json.dumps(profile["skills"]), json.dumps(profile["resources"]))
    return {"ok": True, **profile}


@app.delete("/api/roles/{name}")
async def del_role(name: str):
    async with tenant_conn() as c:
        await c.execute("DELETE FROM roles WHERE name=$1", name)
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
        files = await c.fetch(
            "SELECT folder, name, content FROM worktree_files WHERE run_id=$1 ORDER BY ordinal", rid)
    if not files:
        return {"started": False, "reason": "empty_worktree"}
    import tempfile
    from pathlib import Path
    wt = Path(tempfile.mkdtemp(prefix="lineage-run-"))
    for f in files:
        rel = (f["folder"] + f["name"]).replace("\\", "/").lstrip("./")
        if ".." in rel.split("/"):
            continue  # never let an imported path escape the temp worktree
        dest = wt / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(f["content"] or "", encoding="utf-8")
    g = runner_mod.gate(wt)
    if not g.ready:
        return {"started": False, "reason": g.reason,
                "offer": {"label": g.offer.label, "task": g.offer.task}}
    try:
        await runner_mod.start(wt, g)
    except FileNotFoundError:
        return {"started": False, "reason": "docker_missing", "worktree": str(wt)}
    return {"started": True, "file": g.file, "worktree": str(wt)}


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
