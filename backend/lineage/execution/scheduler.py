"""Level-wise DAG walk (§20.4). Builds each concurrency set by checking declared
write/read glob overlap and never co-schedules conflicting nodes — most
contention is prevented here, before any lock exists (§18.1 primary)."""

from __future__ import annotations

from fnmatch import fnmatch

from ..contracts import Dag, NodeSpec


def _overlap(a: NodeSpec, b: NodeSpec) -> bool:
    aw, bw = set(a.writes), set(b.writes)
    # write/write or write/read intersection (glob-aware)
    pairs = [(aw, bw), (aw, set(b.reads)), (bw, set(a.reads))]
    return any(fnmatch(x, y) or fnmatch(y, x) for xs, ys in pairs for x in xs for y in ys)


def levels(dag: Dag) -> list[list[NodeSpec]]:
    """Topological levels respecting depends_on, split further so no level holds
    two IO-conflicting nodes."""
    done: set[str] = set()
    remaining = list(dag.nodes)
    out: list[list[NodeSpec]] = []
    while remaining:
        ready = [n for n in remaining if all(d in done for d in n.depends_on)]
        if not ready:  # cycle guard — should not happen with a valid DAG
            out.append(remaining)
            break
        level: list[NodeSpec] = []
        for n in ready:
            if not any(_overlap(n, m) for m in level):
                level.append(n)
        out.append(level)
        for n in level:
            done.add(n.id)
            remaining.remove(n)
    return out


def resume_plan(order: list[str], from_node: str | None) -> tuple[int, list[str]]:
    """Fork / replay (§16.5): given the DAG's node ids in walk order and a
    divergence node, return (resume_index, carried_subjects). Nodes before the
    divergence are carried from the parent run; a node's subject is its id's
    first dotted segment ('schema.design' → 'schema'). An unknown or absent
    divergence resumes at 0 and carries nothing — a full re-run."""
    if not from_node or from_node not in order:
        return 0, []
    idx = order.index(from_node)
    return idx, sorted({order[i].split(".")[0] for i in range(idx)})


def demo() -> None:
    from ..contracts import Dag, NodeSpec
    dag = Dag(nodes=[
        NodeSpec(id="a", role="r", intent="i", writes=["db/**"]),
        NodeSpec(id="b", role="r", intent="i", writes=["web/**"]),
        NodeSpec(id="c", role="r", intent="i", reads=["db/**"], depends_on=["a"]),
    ])
    lv = levels(dag)
    # a and b don't conflict → same level; c waits on a
    assert {n.id for n in lv[0]} == {"a", "b"}
    assert lv[1][0].id == "c"

    # resume_plan (§16.5)
    order = ["plan", "schema.design", "auth.session", "api.orders"]
    assert resume_plan(order, "auth.session") == (2, ["plan", "schema"])
    assert resume_plan(order, "plan") == (0, [])          # fork at first node
    assert resume_plan(order, None) == (0, [])            # plain run
    assert resume_plan(order, "ghost") == (0, [])         # unknown node → full re-run
    print("scheduler.demo ok")


if __name__ == "__main__":
    demo()
