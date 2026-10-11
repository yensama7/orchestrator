"""Brief + template + pitfalls → task DAG (§3 step 6, phases.md §P1a).

The planner derives nodes from the fingerprint, not a fixed storefront script.
A template is picked by domain; conditional nodes (auth, payments) are included
only when the fingerprint asks for them, and `depends_on` expresses *real* data
dependencies — schema before API, API before UI — so independent work (auth and
payments both hang off the schema) lands in the same scheduler level and runs in
parallel. Pitfalls are injected as MUST NOT constraints on irreversible nodes
before a single node is written (§6).

The walk is deterministic given (fingerprint, template, pitfalls): no model
appears here, which is what makes a run replayable (§20.4). `plan_dag` is the
pure, DB-free core (golden-tested in `demo`); `build_dag` is the thin wrapper
that fetches pitfalls and keeps the existing call signature.
"""

from __future__ import annotations

from typing import Callable, NamedTuple

from ..contracts import Dag, NodeSpec, SpecFingerprint
from ..execution import verify


class N(NamedTuple):
    """A template body node. `deps` reference other body ids; `_frame` rewires a
    rootless body node onto `plan` and appends the shared review/verify gates."""
    id: str
    role: str
    intent: str
    irreversible: bool = False
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    acceptance: tuple[str, ...] = ()
    deps: tuple[str, ...] = ()


# Acceptance for a code-writing node (§18.3 stage 2): a cheap structural check
# first (short-circuits a malformed proposal before a sandbox spins up), then a
# behavioral check that *executes* the produced files (verify.py). The planner
# refuses to emit a code node without a behavioral check (see plan_dag).
BUILD = ("confidence.min", "build.succeeds")    # code that must compile/run
TESTS = ("confidence.min", "tests.pass")        # a node whose job is a test suite
SCHEMA = ("confidence.min", "schema.migrates")  # DDL that must apply

FRAMING = {"plan", "security.review", "verify"}  # not code nodes — no behavioral check


# ── domain templates: the interesting middle, framed by _frame ──────────────
def _commerce(fp: SpecFingerprint) -> list[N]:
    body = [N("schema.design", "senior-dev", "design the data model and migrations",
              True, (), ("db/**",), SCHEMA)]
    api_reads = ["db/**"]
    if fp.auth == "required":
        body.append(N("auth.session", "senior-dev", "implement session auth and route guards",
                      True, ("db/**",), ("auth/**",), BUILD, ("schema.design",)))
        api_reads.append("auth/**")
    if fp.payments:
        body.append(N("payments.webhook", "senior-dev",
                      f"implement the {fp.payments} webhook and signature verification",
                      True, ("db/**",), ("payments/**",), BUILD, ("schema.design",)))
    body.append(N("api.orders", "senior-dev", "build the orders API over the schema",
                  False, tuple(api_reads), ("api/**",), BUILD, ("schema.design",)))
    body.append(N("ui.build", "frontend", "build the storefront UI over the API",
                  False, ("api/**",), ("web/**",), BUILD, ("api.orders",)))
    return body


def _api(fp: SpecFingerprint) -> list[N]:
    body = [N("schema.design", "senior-dev", "design the data model and migrations",
              True, (), ("db/**",), SCHEMA)]
    api_reads = ["db/**"]
    deps = ["schema.design"]
    if fp.auth == "required":
        body.append(N("auth.session", "senior-dev", "implement token auth and guards",
                      True, ("db/**",), ("auth/**",), BUILD, ("schema.design",)))
        api_reads.append("auth/**")
        deps.append("auth.session")
    body.append(N("api.resource", "senior-dev", "build the CRUD resource endpoints",
                  False, tuple(api_reads), ("api/**",), BUILD, tuple(deps)))
    body.append(N("api.tests", "senior-dev", "write endpoint tests against the API",
                  False, ("api/**",), ("tests/**",), TESTS, ("api.resource",)))
    return body


def _saas(fp: SpecFingerprint) -> list[N]:
    body = [
        N("schema.design", "senior-dev", "design the multi-tenant data model",
          True, (), ("db/**",), SCHEMA),
        N("auth.session", "senior-dev", "implement session auth and tenant isolation",
          True, ("db/**",), ("auth/**",), BUILD, ("schema.design",)),
        N("api.resource", "senior-dev", "build the tenant-scoped API",
          False, ("db/**", "auth/**"), ("api/**",), BUILD, ("schema.design", "auth.session")),
        N("ui.build", "frontend", "build the admin dashboard over the API",
          False, ("api/**",), ("web/**",), BUILD, ("api.resource",)),
    ]
    return body


def _content(fp: SpecFingerprint) -> list[N]:
    # a static/content site: no schema, no payments, no API — a deliberately
    # different shape from commerce, which is the point of killing the template.
    body = [N("content.model", "senior-dev", "model the content types and routing",
              False, (), ("content/**",), BUILD)]
    if fp.auth == "required":
        body.append(N("auth.session", "senior-dev", "implement author/editor auth",
                      True, (), ("auth/**",), BUILD, ("content.model",)))
    body.append(N("ui.build", "frontend", "build the site UI over the content model",
                  False, ("content/**",), ("web/**",), BUILD, ("content.model",)))
    return body


def _data(fp: SpecFingerprint) -> list[N]:
    body = [
        N("schema.design", "senior-dev", "design the warehouse schema",
          True, (), ("db/**",), SCHEMA),
        N("pipeline.ingest", "senior-dev", "build the ingest stage",
          False, (), ("pipeline/ingest/**",), BUILD, ("schema.design",)),
        N("pipeline.transform", "senior-dev", "build the transform stage",
          False, ("pipeline/ingest/**",), ("pipeline/transform/**",), BUILD, ("pipeline.ingest",)),
        N("pipeline.load", "senior-dev", "build the load stage into the warehouse",
          False, ("db/**", "pipeline/transform/**"), ("pipeline/load/**",), BUILD,
          ("schema.design", "pipeline.transform")),
    ]
    return body


def _tool(fp: SpecFingerprint) -> list[N]:
    body = [
        N("core.logic", "senior-dev", "implement the core library logic",
          False, (), ("src/**",), BUILD),
        N("cli.interface", "senior-dev", "build the CLI over the core logic",
          False, ("src/**",), ("cli/**",), BUILD, ("core.logic",)),
        N("cli.tests", "senior-dev", "write tests for the CLI and core",
          False, ("src/**", "cli/**"), ("tests/**",), TESTS, ("cli.interface",)),
    ]
    return body


def _mobile(fp: SpecFingerprint) -> list[N]:
    body = [
        N("schema.design", "senior-dev", "design the backend data model",
          True, (), ("db/**",), SCHEMA),
        N("api.resource", "senior-dev", "build the mobile backend API",
          False, ("db/**",), ("api/**",), BUILD, ("schema.design",)),
        N("mobile.ui", "frontend", "build the mobile app UI over the API",
          False, ("api/**",), ("app/**",), BUILD, ("api.resource",)),
    ]
    return body


def _generic(fp: SpecFingerprint) -> list[N]:
    return [N("implement", "senior-dev", "implement the requested change",
              False, (), ("src/**",), BUILD)]


TEMPLATES: dict[str, Callable[[SpecFingerprint], list[N]]] = {
    "commerce": _commerce,
    "api": _api,
    "saas": _saas,
    "content": _content,
    "data": _data,
    "tool": _tool,
    "mobile": _mobile,
}


def select_template(fp: SpecFingerprint) -> Callable[[SpecFingerprint], list[N]]:
    """Domain → template builder. Unknown domains fall back to a minimal generic
    plan rather than defaulting to the storefront (the old bug)."""
    return TEMPLATES.get(fp.domain, _generic)


def _frame(body: list[N]) -> list[N]:
    """Wrap a template body with the shared gates: a `plan` node first (rootless
    body nodes depend on it), then `security.review` over every artifact, then
    `verify` to accept the run. Returns the full node list in walk order."""
    plan = N("plan", "planner", "scope the build and name the modules",
             False, (), ("plan/**",), ())
    body_ids = tuple(n.id for n in body)
    framed = [plan]
    for n in body:
        deps = n.deps or ("plan",)  # a rootless body node waits on the plan node
        framed.append(n._replace(deps=deps))
    framed.append(N("security.review", "security",
                    "review every artifact for secrets and unsafe patterns",
                    False, ("**",), (), ("envelope.valid",), body_ids or ("plan",)))
    framed.append(N("verify", "planner", "accept the run if every node passed its checks",
                    False, ("**",), (), ("confidence.min",), ("security.review",)))
    return framed


def plan_dag(fp: SpecFingerprint, budget_usd: float, constraints: list[str] | None = None) -> Dag:
    """Pure, deterministic, DB-free (fingerprint, template, pitfalls) → DAG.
    Golden-tested in `demo`; `build_dag` is the DB-backed wrapper."""
    constraints = constraints or []
    nodes = _frame(select_template(fp)(fp))
    # §P1b: a node that writes code must carry a verifier that *executes* it. A
    # template that emits a writing node with only structural checks is a planner
    # bug (it would let an echo proposal pass as a verified build) — fail loud.
    for n in nodes:
        if n.writes and n.id not in FRAMING and not verify.any_behavioral(n.acceptance):
            raise ValueError(f"code node {n.id} has no behavioral verifier")
    per_node = round(budget_usd / max(len(nodes), 1), 2)
    return Dag(nodes=[
        NodeSpec(
            id=n.id, role=n.role, intent=n.intent, irreversible=n.irreversible,
            reads=list(n.reads), writes=list(n.writes), acceptance=list(n.acceptance),
            budget_usd=per_node,
            constraints=constraints if n.irreversible else [],
            depends_on=list(n.deps),
        )
        for n in nodes
    ])


async def build_dag(fp: SpecFingerprint, budget_usd: float) -> Dag:
    from ..db.tenancy import tenant_conn  # deferred: keeps plan_dag DB/asyncpg-free

    async with tenant_conn() as c:
        # §P3c: only a pitfall that reached `knowledge` (repeated verified failure)
        # gates the plan as MUST NOT. A hypothesis — a one-off failure, or one a
        # vindicated dissent has since disproved — is tracked but injects nothing,
        # so a stale fluke can't permanently poison every future DAG.
        pitfalls = await c.fetch(
            "SELECT fingerprint, symptom FROM pitfalls "
            "WHERE domain=$1 AND status='knowledge' ORDER BY occurrences DESC",
            fp.domain)
    return plan_dag(fp, budget_usd, [p["fingerprint"] for p in pitfalls])


def demo() -> None:
    from ..execution import scheduler

    # the storefront is now ONE template, selected by domain — not the default.
    store = plan_dag(SpecFingerprint(domain="commerce", auth="required", payments="paystack"), 8.0)
    ids = {n.id for n in store.nodes}
    assert {"schema.design", "auth.session", "payments.webhook", "api.orders", "ui.build"} <= ids

    # a different brief builds a *visibly different* DAG — no payments, no schema.
    site = plan_dag(SpecFingerprint(domain="content"), 8.0)
    site_ids = {n.id for n in site.nodes}
    assert "payments.webhook" not in site_ids and "schema.design" not in site_ids
    assert "content.model" in site_ids
    assert ids != site_ids, "two briefs must not plan the same DAG"

    # conditional nodes: no auth flag → no auth node; no payments → no webhook.
    bare = plan_dag(SpecFingerprint(domain="commerce"), 8.0)
    bare_ids = {n.id for n in bare.nodes}
    assert "auth.session" not in bare_ids and "payments.webhook" not in bare_ids

    # real dependencies → real parallelism: auth and payments both hang off the
    # schema, so the scheduler co-schedules them in one level (≥2 nodes).
    lv = scheduler.levels(store)
    assert any(len(level) >= 2 for level in lv), "no level parallelises"
    assert {n.id for n in lv[0]} == {"plan"}  # plan gates everything

    # deterministic: same inputs → identical plan (replay/fork depend on this).
    again = plan_dag(SpecFingerprint(domain="commerce", auth="required", payments="paystack"), 8.0)
    assert [n.id for n in store.nodes] == [n.id for n in again.nodes]

    # unknown domain → generic, not storefront.
    other = {n.id for n in plan_dag(SpecFingerprint(domain="other"), 8.0).nodes}
    assert "implement" in other and "payments.webhook" not in other

    # budget is split across nodes and pitfalls land only on irreversible nodes.
    p = plan_dag(SpecFingerprint(domain="commerce", payments="stripe"), 8.0, ["p-0042"])
    webhook = p.by_id("payments.webhook")
    assert webhook.irreversible and webhook.constraints == ["p-0042"]
    assert p.by_id("ui.build").constraints == []  # reversible → no MUST NOT

    # §P1b: every code-writing node across every template carries a behavioral
    # verifier — there is no writing node a structural-only pass can slip through.
    for d in ("commerce", "api", "saas", "content", "data", "tool", "mobile", "other"):
        for n in plan_dag(SpecFingerprint(domain=d, auth="required", payments="stripe"), 8.0).nodes:
            if n.writes and n.id not in FRAMING:
                assert verify.any_behavioral(n.acceptance), f"{d}/{n.id} has no behavioral check"
    assert p.by_id("schema.design").acceptance[-1] == "schema.migrates"
    assert p.by_id("payments.webhook").acceptance[-1] == "build.succeeds"

    # the guard fires if a template ever regresses to structural-only on a writer.
    TEMPLATES["_bad"] = lambda fp: [N("oops", "senior-dev", "writes but no behavioral check",
                                      False, (), ("src/**",), ("confidence.min",))]
    try:
        plan_dag(SpecFingerprint(domain="_bad"), 8.0)
        raise AssertionError("guard must reject a structural-only writing node")
    except ValueError as e:
        assert "oops" in str(e)
    finally:
        del TEMPLATES["_bad"]
    print("plan.demo ok")


if __name__ == "__main__":
    demo()
