"""Pitfalls as an evidence pipeline, not a permanent ban (phases.md §P3c).

The old model was `Failure → MUST NOT`: one observed failure injected a hard
constraint into every future plan for the domain, forever. That lets a single
fluke poison the DAG and can never be unlearned.

This replaces it with `Observation → Hypothesis → Verification → Confidence →
Knowledge`:

    first failure            → a *hypothesis* (low confidence, does NOT gate plans)
    repeated verified failure → confidence climbs; at the floor it becomes
                                *knowledge* and only then gates plans as MUST NOT
    a vindicated dissent      → a *disproof*: confidence drops, and enough
                                disproofs demote knowledge back to a hypothesis

Confidence is the same Beta-Binomial posterior as agent scoring
(`arbitration/confidence`): failures are "successes" (evidence the pitfall is
real), disproofs are the other side. So `plan.build_dag` injects only
`status='knowledge'` pitfalls as MUST NOT; a hypothesis is tracked and visible
but blocks nothing — which is what stops a stale pitfall from permanently
poisoning every future plan. Every promotion/demotion is an episodic event
(audit trail).
"""

from __future__ import annotations

from uuid import UUID

from ..arbitration.confidence import posterior_mean

PRIOR = 0.2          # innocent until proven: an unseen situation is probably fine
STRENGTH = 2         # low pseudo-count: a few *repeated* failures should convince
FLOOR = 3            # failures before a hypothesis can even be considered knowledge
THRESHOLD = 0.6      # …and its confidence must clear this to gate plans


def confidence(failures: int, disproofs: int) -> float:
    """Evidence that the pitfall is real. Failures raise it; disproofs lower it.
    Same shrinkage as agent scoring, so a lone failure stays a weak hypothesis."""
    return posterior_mean(failures, failures + disproofs,
                          prior=PRIOR, strength=STRENGTH)


def is_knowledge(failures: int, disproofs: int) -> bool:
    """Earns MUST-NOT status only on repeated verified failure *and* confidence."""
    return failures >= FLOOR and confidence(failures, disproofs) >= THRESHOLD


def _status(failures: int, disproofs: int) -> str:
    return "knowledge" if is_knowledge(failures, disproofs) else "hypothesis"


async def record_disproof(fingerprint: str, run_id: UUID | None = None) -> str | None:
    """A verified alternative beat this MUST NOT (a vindicated dissent on a node
    that carried the constraint). Count it against the pitfall and recompute —
    enough disproofs demote knowledge back to a hypothesis, so it stops gating."""
    from ..db.tenancy import tenant_conn  # deferred: keeps the pure math DB-free
    from . import store as mem
    async with tenant_conn() as c:
        row = await c.fetchrow(
            """UPDATE pitfalls SET disproofs = disproofs + 1
               WHERE fingerprint=$1 RETURNING occurrences, disproofs, status""",
            fingerprint)
        if row is None:
            return None
        new_status = _status(row["occurrences"], row["disproofs"])
        conf = confidence(row["occurrences"], row["disproofs"])
        await c.execute("UPDATE pitfalls SET status=$2, confidence=$3 WHERE fingerprint=$1",
                        fingerprint, new_status, conf)
    if new_status != row["status"] and run_id is not None:
        await mem.append_episodic(run_id, "memory", {
            "text": f"pitfall {fingerprint}: {row['status']} → {new_status} (disproved)"})
    return new_status


async def recompute(fingerprint: str) -> None:
    """Re-derive status+confidence from current counts (call after an upsert that
    bumped `occurrences`). Keeps the promotion threshold in one place: here."""
    from ..db.tenancy import tenant_conn  # deferred: keeps the pure math DB-free
    async with tenant_conn() as c:
        row = await c.fetchrow(
            "SELECT occurrences, disproofs FROM pitfalls WHERE fingerprint=$1", fingerprint)
        if row is None:
            return
        await c.execute(
            "UPDATE pitfalls SET status=$2, confidence=$3 WHERE fingerprint=$1",
            fingerprint, _status(row["occurrences"], row["disproofs"]),
            confidence(row["occurrences"], row["disproofs"]))


def demo() -> None:
    # a single failure is a hypothesis, not a ban — it must not gate a plan.
    assert not is_knowledge(failures=1, disproofs=0)
    assert _status(1, 0) == "hypothesis"

    # repeated verified failure earns knowledge (MUST NOT).
    assert is_knowledge(failures=6, disproofs=0)
    assert _status(6, 0) == "knowledge"

    # confidence is monotone: more failures never lowers it, disproofs do.
    assert confidence(6, 0) > confidence(3, 0) > confidence(1, 0)
    assert confidence(6, 3) < confidence(6, 0)

    # demotion: enough disproofs pull a known pitfall back below the bar, so it
    # stops gating future plans (no permanent poisoning).
    assert is_knowledge(6, 0) and not is_knowledge(6, 12)
    assert _status(6, 12) == "hypothesis"
    print("pitfalls.demo ok")


if __name__ == "__main__":
    demo()
