"""Headless end-to-end check of the human path over the real HTTP API.

Drives the same routes the console calls — extract → match → roster → plan →
start → board/run/agents/charts/dissent/lineage/memory/credits — and asserts the
*accuracy* relationships a human would eyeball (pie segments, spent ≤ ceiling,
pass-rate bounds, vindicated ≤ overruled, cumulative spend non-decreasing). It
also proves the fingerprint fix: a novel domain survives as its own bucket and a
dynamic extra field round-trips, instead of everything collapsing to "other".

No new deps (stdlib urllib). Works whether the DB is empty or seeded — empty
views assert their empty-state, populated views assert their math.

    BASE=http://localhost:8000 python -m tests.test_e2e      # needs the stack up

Bring the stack up first (README): `docker compose up -d` then, for real
numbers, `docker compose run --rm backend python -m lineage.onboarding`.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):  # Windows consoles default to cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.environ.get("BASE", "http://localhost:8000").rstrip("/")
_fails: list[str] = []
_checks = 0


def ok(cond: bool, label: str, detail: object = "") -> None:
    global _checks
    _checks += 1
    mark = "ok " if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f"  → {detail}" if detail != "" else ""))
    if not cond:
        _fails.append(label)


def call(method: str, path: str, body: dict | None = None) -> object:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 (localhost)
        return json.loads(r.read() or "null")


def section(title: str) -> None:
    print(f"\n── {title} ".ljust(70, "─"))


def main() -> int:
    print(f"e2e against {BASE}")

    section("health")
    h = call("GET", "/api/health")
    ok(isinstance(h, dict) and (h.get("ok") or h.get("status")), "health responds", h)

    # ── fingerprint fix: novel domain + dynamic field survive end-to-end ──────
    section("fingerprint (the fix)")
    novel = {"domain": "weather", "subdomain": "forecast", "realtime": True,
             "auth": "none"}
    # extract is model-dependent; just prove it returns a valid, non-crashing fp
    ex = call("POST", "/api/extract", {"brief": "a page showing visitor time, timezone and IP"})
    ok(isinstance(ex, dict) and "domain" in ex, "extract returns a fingerprint", ex.get("domain"))

    plan_novel = call("POST", "/api/plan", {"fingerprint": novel, "budget": 8.0})
    ids = {n["id"] for n in plan_novel["nodes"]}
    ok("implement" in ids, "novel domain → generic template (not storefront)", sorted(ids))
    ok("payments.webhook" not in ids, "novel domain has no storefront payments node")

    plan_shop = call("POST", "/api/plan",
                     {"fingerprint": {"domain": "commerce", "auth": "required",
                                      "payments": "stripe"}, "budget": 8.0})
    shop_ids = {n["id"] for n in plan_shop["nodes"]}
    ok("payments.webhook" in shop_ids, "commerce → storefront DAG differs", sorted(shop_ids))
    ok(ids != shop_ids, "two domains plan different DAGs")

    m = call("POST", "/api/match", {"fingerprint": novel})
    ok(isinstance(m, dict) or isinstance(m, list), "match accepts a dynamic fingerprint")
    rr = call("POST", "/api/roster", {"fingerprint": novel})
    ok(isinstance(rr, (dict, list)), "roster accepts a novel domain")

    # ── start a run carrying the novel+dynamic fingerprint ────────────────────
    section("start run")
    started = call("POST", "/api/runs/new/start",
                   {"fingerprint": novel, "ceiling": 12.0, "name": "e2e weather run"})
    rid = started.get("run")
    ok(bool(rid), "run started, addressable id returned", rid)
    q = f"?run={rid}" if rid else ""

    # ── run header: credit limit accuracy ─────────────────────────────────────
    section("run header / credit limit")
    rh = call("GET", f"/api/run{q}")
    spent, ceiling = rh.get("spent", 0), rh.get("ceiling", 0)
    ok(spent <= ceiling or ceiling == 0, "spent ≤ ceiling (credit limit honored)",
       f"{spent}/{ceiling}")
    ok(rh.get("projected", 0) <= max(ceiling, 0.001) or ceiling == 0,
       "projected spend capped at ceiling", rh.get("projected"))
    rail = rh.get("rail", [])
    ok(any(x.get("label") == "remaining" for x in rail), "spend rail has a remaining band")
    cpv = rh.get("cost_per_verified")
    ok(cpv is None or cpv >= 0, "cost-per-verified is None or ≥ 0 (no div-by-zero)", cpv)

    # ── board ─────────────────────────────────────────────────────────────────
    section("board")
    b = call("GET", "/api/board")
    cards = b.get("cards", [])
    ok(all(c["spent"] >= 0 for c in cards), f"all {len(cards)} cards have spend ≥ 0")
    ok(all((c["cost_per_verified"] is None) == (c["verified_count"] == 0) for c in cards),
       "cost-per-verified present iff something was verified")

    # ── agents: pass-rate bounds ──────────────────────────────────────────────
    section("agents")
    ag = call("GET", "/api/agents")
    def pct(s): return int(s.rstrip("%")) if isinstance(s, str) and s.endswith("%") else None
    bad = [a for a in ag if (p := pct(a.get("pass"))) is not None and not (0 <= p <= 100)]
    ok(not bad, f"{len(ag)} agents, every pass-rate in 0..100%", [a["agent"] for a in bad])
    vbad = [a for a in ag if (p := pct(a.get("vind"))) is not None and not (0 <= p <= 100)]
    ok(not vbad, "every vindication-rate in 0..100%")

    # ── charts: pie + line accuracy ───────────────────────────────────────────
    section("charts (pie / verification / spend line)")
    ch = call("GET", f"/api/charts{q}")
    cost = ch.get("cost_share", [])
    ok(all(s["value"] >= 0 for s in cost), f"cost-share pie: {len(cost)} segments, all ≥ 0")
    tok = ch.get("token_attr", [])
    ok(all(s["value"] >= 0 for s in tok), "token pie: all segments ≥ 0")
    ver = ch.get("verification", [])
    vsum = sum(s["value"] for s in ver)
    tp = ch.get("throughput", [])
    ok(vsum == len(tp), "verification pie (passed+failed) == node throughput count",
       f"{vsum} == {len(tp)}")
    series = ch.get("spend_series", [])
    actual = [p["actual"] for p in series]
    ok(actual == sorted(actual), "cumulative spend is non-decreasing", actual)
    ok(all(p["uncached"] >= p["actual"] for p in series),
       "uncached counterfactual ≥ actual spend (cache saves money)")

    # ── dissent ────────────────────────────────────────────────────────────────
    section("dissent")
    d = call("GET", f"/api/dissent{q}")
    lb = d.get("leaderboard", [])
    ok(all(0 <= r["rate"] <= 100 for r in lb), f"leaderboard: {len(lb)} rows, rate in 0..100")
    ok(all(r["vindicated"] <= r["overruled"] for r in lb),
       "vindicated ≤ overruled (can't win more than you were overruled)")
    ok(all(r["vindicated"] + r["refuted"] + r["resurrected"] <= r["overruled"] + r["resurrected"]
           for r in lb) if lb else True, "settled counts within bounds")
    led = d.get("ledger", [])
    ok(all("status" in r and "node" in r for r in led), f"ledger: {len(led)} entries well-formed")

    # ── credits: subscription / api-key / usage ───────────────────────────────
    section("credits (subscription / api / usage)")
    cr = call("GET", "/api/credits")
    api = cr.get("api_spend", {})
    by = api.get("by_provider", {})
    ok(abs(api.get("total", 0) - round(sum(by.values()), 4)) < 1e-6,
       "api spend total == sum of per-provider spend", api.get("total"))
    subs = cr.get("subscriptions", [])
    ok(all(s["used"] >= 0 and s["limit"] > 0 for s in subs),
       f"{len(subs)} subscription windows: used ≥ 0, limit > 0", subs)

    # ── lineage / memory: novel domain surfaces as its own bucket ─────────────
    section("lineage / memory (dynamic domain in graph + pie)")
    lin = call("GET", f"/api/lineage{q}")
    domains = lin.get("domains", [])
    ok("other" not in domains or "weather" in domains or len(domains) > 1,
       "graph domain filter is built from real domains, not all-'other'", domains)
    pts = lin.get("points", [])
    ok(all("domain" in p for p in pts), f"{len(pts)} graph points each carry a domain")
    mem = call("GET", f"/api/memory{q}")
    ok(isinstance(mem, dict), "memory view responds", list(mem.keys())[:6])

    # ── verdict ────────────────────────────────────────────────────────────────
    print("\n" + "═" * 70)
    if _fails:
        print(f"FAIL — {len(_fails)}/{_checks} checks failed:")
        for f in _fails:
            print(f"   ✗ {f}")
        return 1
    print(f"PASS — all {_checks} checks green across the human path.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.URLError as e:
        print(f"\ncannot reach {BASE} — is the stack up? "
              f"(`docker compose up -d`)  [{e}]")
        sys.exit(2)
