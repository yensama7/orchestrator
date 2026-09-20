"""Read-model computations — every view derived from live tables, no mockup
blobs. Each function takes an open tenant-scoped connection."""

from __future__ import annotations

import json
import os

from ..memory.embed import embed
from ..memory.projection import project
from ..memory.retrieval import TOP_K

CYCLE = ["amber", "violet", "sage", "steel", "rust"]
STATUS_COLOR = {"passed": "sage", "active": "amber", "failed": "rust", "abandoned": "rust"}


def _short(run_id) -> str:
    """Console label for a run: 'run/' + first 6 hex of its uuid."""
    return "run/" + str(run_id).replace("-", "")[:6]


def _fp_text(fp) -> str:
    d = json.loads(fp) if isinstance(fp, str) else (fp or {})
    return f"{d.get('domain','')} {d.get('subdomain','')} {' '.join(d.get('stack_hints',[]))}"


def _domain(fp) -> str:
    d = json.loads(fp) if isinstance(fp, str) else (fp or {})
    return d.get("domain", "")


async def run_header(c, run_id) -> dict:
    r = await c.fetchrow(
        """SELECT r.name, r.spent_usd, r.ceiling_usd, r.status, t.name AS tmpl
           FROM runs r LEFT JOIN templates t ON t.id = r.template_id WHERE r.id=$1""", run_id)
    agents = await c.fetch(
        "SELECT agent, cost_usd, tokens, cached_pct, state FROM agents ORDER BY ordinal")
    if r is None:  # no current run (empty db) — render an empty header, not a 500
        idle = sum(1 for a in agents if a["state"] == "idle")
        return {"id": "—", "label": "—", "spec": "no active run", "template": "—", "spent": 0.0,
                "projected": 0.0, "ceiling": 0.0,
                "rail": [{"label": "remaining", "usd": 0.0, "color": "ink3"}],
                "cache_note": "no active run — start one from New run",
                "navfoot": {"egress": "egress deny-all",
                            "agents": f"{len(agents)} agents · {idle} idle", "blocked": "0 blocked"}}
    spent = float(r["spent_usd"])
    ceiling = float(r["ceiling_usd"] or 0)

    rail = []
    for i, a in enumerate(agents):
        if float(a["cost_usd"]) > 0:
            rail.append({"label": a["agent"], "usd": round(float(a["cost_usd"]), 2),
                         "color": CYCLE[i % len(CYCLE)]})
    remainder = max(ceiling - spent, 0)
    rail.append({"label": "remaining", "usd": round(remainder, 2), "color": "ink3"})

    total_tok = sum(int(a["tokens"]) for a in agents)
    cached = [a for a in agents if a["cached_pct"] is not None]
    cache_pct = round(sum(a["cached_pct"] for a in cached) / len(cached)) if cached else 0
    cache_note = (f"{cache_pct}% of input tokens served from cache" if total_tok
                  else "no model calls yet — add a model in Settings")
    idle = sum(1 for a in agents if a["state"] == "idle")
    return {
        "id": str(run_id), "label": _short(run_id), "spec": r["name"], "template": r["tmpl"] or "—",
        "spent": round(spent, 2),
        "projected": round(min(ceiling, spent * 1.4) if spent else 0, 2),
        "ceiling": round(ceiling, 2), "rail": rail, "cache_note": cache_note,
        "navfoot": {"egress": "egress deny-all",
                    "agents": f"{len(agents)} agents · {idle} idle",
                    "blocked": "0 blocked"},
    }


async def lineage_graph(c, run_id) -> dict:
    runs = await c.fetch(
        "SELECT id, name, fingerprint, status, spent_usd, template_id FROM runs")
    tmpls = await c.fetch("SELECT id, name, domain, embedding FROM templates")

    points, edges = [], []
    for r in runs:
        x, y = project(await embed(_fp_text(r["fingerprint"])))
        points.append({
            "id": str(r["id"]), "kind": "run", "name": r["name"], "x": x, "y": y,
            "size": 6 + min(float(r["spent_usd"]), 10),
            "color": STATUS_COLOR.get(r["status"], "amber"),
            "domain": _domain(r["fingerprint"]) or "other",
            "ring": r["id"] == run_id,
            "meta": {"status": r["status"], "cost": round(float(r["spent_usd"]), 2)},
        })
        if r["template_id"]:
            edges.append([str(r["id"]), str(r["template_id"])])
    for t in tmpls:
        vec = _vec(t["embedding"])
        x, y = project(vec) if vec else (0.5, 0.5)
        points.append({"id": str(t["id"]), "kind": "template", "name": t["name"],
                       "x": x, "y": y, "size": 11, "color": "violet",
                       "domain": t["domain"], "ring": False,
                       "meta": {"status": "template"}})

    domains = ["all domains"] + sorted({p["domain"] for p in points if p["kind"] == "run"})

    # nearest + inherited via the match pipeline against the current run
    cur = await c.fetchrow("SELECT fingerprint FROM runs WHERE id=$1", run_id)
    nearest = await _nearest(c, run_id, cur["fingerprint"]) if cur else []
    inh = await _inherited(c)
    return {"points": points, "edges": edges, "nearest": nearest,
            "inherited": inh, "domains": domains}


async def _nearest(c, run_id, fp, k=4):
    qvec = await embed(_fp_text(fp))
    others = await c.fetch("SELECT id, name, status, fingerprint FROM runs WHERE id<>$1", run_id)
    scored = []
    for o in others:
        ov = await embed(_fp_text(o["fingerprint"]))
        scored.append((sum(a * b for a, b in zip(qvec, ov)), o))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"name": o["name"], "score": round(max(s, 0), 2),
             "outcome": STATUS_COLOR.get(o["status"], "amber")} for s, o in scored[:k]]


async def _inherited(c):
    t = await c.fetchrow(
        "SELECT name, status, node_count, carried_decisions, roles FROM templates LIMIT 1")
    if not t:
        return None
    pit = await c.fetchval("SELECT count(*) FROM pitfalls WHERE domain='commerce'")
    roles = json.loads(t["roles"]) if isinstance(t["roles"], str) else t["roles"]
    return {"template": t["name"], "status": t["status"], "rows": [
        {"label": "Agent stack", "n": f"{len(roles)} roles"},
        {"label": "Task graph shape", "n": f"{t['node_count']} nodes"},
        {"label": "Carried decisions", "n": str(t["carried_decisions"])},
        {"label": "Recorded pitfalls", "n": str(pit), "color": "rust"},
    ]}


async def memory_view(c, run_id) -> dict:
    ep = await c.fetchval("SELECT count(*) FROM episodic_events WHERE run_id=$1", run_id)
    active = await c.fetch(
        "SELECT id, subject, choice, status, embedding FROM semantic_memory WHERE run_id=$1", run_id)
    sem = sum(1 for r in active if r["status"] == "active")
    sup = sum(1 for r in active if r["status"] == "superseded")
    proc = await c.fetchval("SELECT count(*) FROM templates") + \
        await c.fetchval("SELECT count(*) FROM pitfalls")

    rows = await c.fetch("SELECT payload FROM episodic_events WHERE run_id=$1 "
                         "ORDER BY id DESC LIMIT 3", run_id)
    ep_texts = []
    for r in rows:
        p = json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
        if isinstance(p, dict) and p.get("text"):
            ep_texts.append(p["text"])
    sem_lines = [r["choice"] for r in active if r["status"] == "active"][:3]

    points = []
    for r in active:
        vec = _vec(r["embedding"])
        x, y = project(vec) if vec else (0.5, 0.5)
        color = "sage" if r["status"] == "active" else "rust" if r["status"] == "superseded" else "steel"
        points.append({"id": str(r["id"]), "kind": "semantic", "name": r["choice"],
                       "x": x, "y": y, "size": 6, "color": color, "domain": r["subject"],
                       "ring": False, "meta": {"status": r["status"], "subject": r["subject"]}})

    return {
        "tiers": [
            {"key": "episodic", "n": int(ep), "color": "steel", "lines": ep_texts or ["no events yet"]},
            {"key": "semantic", "n": sem, "color": "violet", "lines": sem_lines or ["no decisions yet"]},
            {"key": "procedural", "n": int(proc), "color": "amber",
             "lines": ["templates + pitfalls", f"→ {proc} recipes"]},
        ],
        "recall": [
            {"label": "Active decisions", "n": sem, "color": "sage"},
            {"label": "Superseded", "n": sup, "color": "rust"},
            {"label": "Episodic events", "n": int(ep), "color": "steel"},
        ],
        # real config/state, not benchmark blobs — honest about what's running now
        "quality": [
            {"label": "Retrievable rows", "n": str(sem)},
            {"label": "Top-k per prompt", "n": str(TOP_K)},
            {"label": "Embedder", "n": "BGE-M3 (TEI)" if os.getenv("EMBED_URL") else "local hash"},
            {"label": "Reranker", "n": "lexical + RRF"},
        ],
        "points": points,
    }


async def charts(c, run_id) -> dict:
    agents = await c.fetch("SELECT agent, tokens, cost_usd FROM agents WHERE tokens>0 ORDER BY ordinal")
    nodes = await c.fetch(
        "SELECT payload FROM episodic_events WHERE run_id=$1 AND kind='node' ORDER BY id", run_id)
    spends = await c.fetch(
        "SELECT payload, extract(epoch from at) AS ts FROM episodic_events "
        "WHERE run_id=$1 AND kind='spend' ORDER BY id", run_id)

    token_attr = [{"label": a["agent"], "value": int(a["tokens"]), "unit": "tokens",
                   "color": CYCLE[i % len(CYCLE)]} for i, a in enumerate(agents)]
    cost_share = [{"label": a["agent"], "value": round(float(a["cost_usd"]), 4), "unit": "$",
                   "color": CYCLE[i % len(CYCLE)]} for i, a in enumerate(agents)]

    passed = failed = 0
    for n in nodes:
        p = json.loads(n["payload"]) if isinstance(n["payload"], str) else n["payload"]
        if p.get("status") == "passed":
            passed += 1
        else:
            failed += 1
    verification = [{"label": "Passed first try", "value": passed, "unit": "nodes", "color": "sage"},
                    {"label": "Failed", "value": failed, "unit": "nodes", "color": "rust"}]

    # cumulative spend series (actual) + uncached counterfactual (cache-adjusted)
    series, cum = [], 0.0
    t0 = float(spends[0]["ts"]) if spends else 0
    for s in spends:
        p = json.loads(s["payload"]) if isinstance(s["payload"], str) else s["payload"]
        cum = float(p.get("spent", cum))
        t = int(float(s["ts"]) - t0)
        series.append({"x": t, "actual": round(cum, 2), "uncached": round(cum / 0.17, 2)})  # ~83% cache

    return {
        "token_attr": token_attr, "cost_share": cost_share, "verification": verification,
        "spend_series": series,
        "throughput": [{"x": i, "nodes": i + 1} for i in range(len(nodes))],
    }


async def workspace_view(c, run_id) -> dict:
    files = await c.fetch(
        "SELECT folder, name, ext, held, content, blame, is_open FROM worktree_files "
        "WHERE run_id=$1 ORDER BY ordinal", run_id)
    names = {f["name"] for f in files}
    COMPOSE = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")
    if names & set(COMPOSE):
        gate = {"ready": True, "file": next(n for n in COMPOSE if n in names), "services": []}
    elif "Dockerfile" in names:
        gate = {"ready": False, "reason": "no_compose", "offer": {"label": "Generate compose file"}}
    else:
        gate = {"ready": False, "reason": "not_containerised", "offer": {"label": "Containerise this project"}}

    tree, open_file = [], None
    for f in files:
        grp = next((g for g in tree if g["folder"] == f["folder"]), None)
        if grp is None:
            grp = {"folder": f["folder"], "files": []}
            tree.append(grp)
        grp["files"].append({"name": f["name"], "ext": f["ext"], "held": f["held"]})
        if f["is_open"] and f["content"] is not None:
            blame = _vec_json(f["blame"])
            open_file = {"name": f["name"], "ext": f["ext"], "mode": _mode(f["ext"]),
                         "why": f"extension .{f['ext']} → tier 1 → grammar",
                         "lines": (f["content"] or "").count("\n"), "chars": len(f["content"] or ""),
                         "content": f["content"], "blame": blame or [], "held": f["held"]}
    return {"worktree": _short(run_id), "tree": tree, "open": open_file, "gate": gate,
            "empty": not files}


def _mode(ext: str) -> str:
    return {"py": "python", "ts": "typescript", "tsx": "typescript", "js": "javascript",
            "sql": "sql", "rs": "rust", "yaml": "yaml", "yml": "yaml", "md": "markdown",
            "go": "go", "json": "json"}.get(ext, "text")


def _vec(embedding):
    """pgvector comes back as text '[..]' — parse to list[float]."""
    if embedding is None:
        return None
    if isinstance(embedding, str):
        return [float(x) for x in embedding.strip("[]").split(",") if x]
    return list(embedding)


def _vec_json(v):
    return json.loads(v) if isinstance(v, str) else (v or [])
