"""One-command onboarding (phases.md §Phase 5). Produces a genuinely *verified*
build with no API key, so a new user sees the core value in one step instead of
after wiring ten providers:

    docker compose up -d db
    docker compose run --rm backend python -m lineage.onboarding

It applies migrations, binds a single agent to the fixture transport (recorded
real artifacts, verified live — transports/fixture.py), runs a small `tool` brief
end to end through the real orchestrator, and prints the headline the Simple UI
shows: run mode, verified-node count, spend, and cost-per-verified-result.

The verification is real (the behavioral verifiers execute the produced code in
the sandbox); only the generation is recorded. That's why it lands as `live` and
the metric is honest — it cost nothing locally.
"""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from .db.tenancy import close, migrate, tenant_conn
from .execution import orchestrator

_FP = {"domain": "tool", "subdomain": "cli", "stack_hints": ["python"]}


async def run_onboarding() -> dict:
    await migrate()
    async with tenant_conn() as c:
        await c.execute(
            """INSERT INTO model_credentials (tenant_id, model, transport, api_key, enabled)
               VALUES (current_setting('app.tenant_id')::uuid, 'lineage-fixture', 'fixture', NULL, true)
               ON CONFLICT (tenant_id, model) DO UPDATE SET transport='fixture', enabled=true""")
        await c.execute(
            """INSERT INTO agents (tenant_id, agent, role, model, transport, ordinal, enabled)
               VALUES (current_setting('app.tenant_id')::uuid, 'onboarding', 'senior-dev',
                       'lineage-fixture', 'fixture', 0, true)
               ON CONFLICT (tenant_id, agent) DO UPDATE
                 SET model='lineage-fixture', transport='fixture', enabled=true""")
        rid = uuid4()
        await c.execute(
            """INSERT INTO runs (id, tenant_id, name, fingerprint, status, spent_usd, ceiling_usd)
               VALUES ($1, current_setting('app.tenant_id')::uuid, 'onboarding-example',
                       $2::jsonb, 'active', 0, 15)""",
            rid, json.dumps(_FP))
        await c.execute("UPDATE runs SET is_current=false WHERE is_current")
        await c.execute("UPDATE runs SET is_current=true WHERE id=$1", rid)

    # run synchronously to completion (not the fire-and-forget start()).
    await orchestrator._run(rid)

    async with tenant_conn() as c:
        r = await c.fetchrow(
            "SELECT mode, status, spent_usd, verified_count FROM runs WHERE id=$1", rid)
    spent, verified = float(r["spent_usd"]), int(r["verified_count"])
    return {"run": str(rid), "mode": r["mode"], "status": r["status"], "spent": spent,
            "verified": verified, "cost_per_verified": (spent / verified) if verified else None}


def main() -> None:
    out = asyncio.run(_main())
    print("\n── onboarding example ──────────────────────────────")
    print(f"  mode                   {out['mode']}")
    print(f"  status                 {out['status']}")
    print(f"  verified nodes         {out['verified']}")
    print(f"  spent                  ${out['spent']:.2f}")
    cpv = out["cost_per_verified"]
    print(f"  cost / verified result {'$%.2f' % cpv if cpv is not None else '—'}")
    print("────────────────────────────────────────────────────")
    if out["mode"] != "live" or out["verified"] == 0:
        raise SystemExit("onboarding did not reach a verified live result")
    print("A verified build with no API key. Open the console to explore it.")


async def _main() -> dict:
    try:
        return await run_onboarding()
    finally:
        await close()


if __name__ == "__main__":
    main()
