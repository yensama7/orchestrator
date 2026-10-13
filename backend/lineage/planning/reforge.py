"""Move 1 — a contestable, revisable decomposition.

The planner's DAG is one deterministic act (plan.py); until now nothing could
contest it. The node-level machinery (consensus, dissent, resurrection) only ever
adjudicated the *answer* to a node, never the *shape* of the plan that produced
it.

When a node fails *hard* — the arbiter's winner fails its behavioral verifier AND
every resurrected dissent is refuted — the evidence points at the decomposition,
not the answer: no proposed way of doing this node *as specified* passes. That is
a plan bug, and it deserves the same treatment a wrong answer gets — it becomes a
recorded dissent, and the plan is reforged into a different shape of the same work
and re-run once.

`split` is the reforge: a deterministic vertical decomposition (scaffold → impl).
A bundled node that no single proposal could satisfy often just needed a smaller
first target — compile a skeleton of the module, then implement behaviour over a
scaffold that already builds. Deterministic so a replay/fork (§16.5) reforges
identically; the caller bounds it to one reforge per node per run.
"""

from __future__ import annotations

from ..contracts import NodeSpec


def reforgeable(node: NodeSpec) -> bool:
    """Only a code node (writes + already carries an executing verifier) can be
    reforged — the reforge is only *vindicated* by its sub-nodes building, so a
    framing/structural node has no behavioral ground truth to settle against."""
    from ..execution import verify  # deferred: keeps this module import-cheap
    return bool(node.writes) and verify.any_behavioral(node.acceptance)


def split(node: NodeSpec) -> list[NodeSpec]:
    """Reforge one failed node into [scaffold, impl]. The scaffold must only
    *compile* (build.succeeds) — a smaller target than the whole node; impl
    inherits the parent's full acceptance and constraints and builds over the
    scaffold. Same role, reads, and writes as the parent; budget split in two."""
    half = round(node.budget_usd / 2, 2)
    scaffold = NodeSpec(
        id=f"{node.id}.scaffold", role=node.role,
        intent=f"scaffold {node.intent}: types, signatures, and module layout only — no behaviour",
        reads=list(node.reads), writes=list(node.writes),
        acceptance=["confidence.min", "build.succeeds"],
        budget_usd=half, depends_on=list(node.depends_on))
    impl = NodeSpec(
        id=f"{node.id}.impl", role=node.role,
        intent=f"implement {node.intent} over the scaffold",
        irreversible=node.irreversible,
        reads=list(node.reads), writes=list(node.writes),
        acceptance=list(node.acceptance), constraints=list(node.constraints),
        budget_usd=half, depends_on=[scaffold.id])
    return [scaffold, impl]


def demo() -> None:
    from ..contracts import NodeSpec as NS

    code = NS(id="api.orders", role="senior-dev", intent="build the orders API",
              irreversible=True, reads=["db/**"], writes=["api/**"],
              acceptance=["confidence.min", "build.succeeds"], constraints=["p-0042"],
              budget_usd=4.0, depends_on=["schema.design"])
    framing = NS(id="plan", role="planner", intent="scope", acceptance=[])
    structural = NS(id="note", role="x", intent="y", writes=["x/**"],
                    acceptance=["confidence.min"])  # writes but no behavioral check

    assert reforgeable(code)
    assert not reforgeable(framing)        # no writes
    assert not reforgeable(structural)     # no executing verifier → nothing to vindicate against

    scaffold, impl = split(code)
    assert scaffold.id == "api.orders.scaffold" and impl.id == "api.orders.impl"
    # scaffold only has to compile; impl inherits the parent's real acceptance.
    assert scaffold.acceptance == ["confidence.min", "build.succeeds"]
    assert impl.acceptance == code.acceptance and impl.constraints == ["p-0042"]
    # impl waits on the scaffold; the scaffold keeps the parent's upstream deps.
    assert impl.depends_on == ["api.orders.scaffold"]
    assert scaffold.depends_on == ["schema.design"]
    # same writes (the reforge is a re-shape, not a re-scope) and budget halved.
    assert scaffold.writes == code.writes == impl.writes
    assert scaffold.budget_usd == 2.0 and impl.budget_usd == 2.0
    # deterministic — replay/fork reforge identically.
    assert [n.id for n in split(code)] == [n.id for n in split(code)]
    print("reforge.demo ok")


if __name__ == "__main__":
    demo()
