"""Dissent retention ladder (phases.md §P3b).

Today a dissent settles to `vindicated` | `refuted` and stops there — a minority
opinion that keeps being right never becomes reusable. The ladder adds a reading
on top of the stored status:

    never-tested          → archive    (dormant: kept, not trusted)
    tested + failed        → low        (refuted)
    tested + succeeded     → high       (vindicated once)
    repeatedly vindicated  → knowledge  (promote to a reusable decision)

`tier` is a pure function of (status, how many times this same decision has been
vindicated), so the reading is deterministic and auditable. The actual promotion
to a semantic-memory decision (the "knowledge" rung) is the DB step in
arbitration/dissent.py — it writes the proposal back as an active decision once
`vind_count` crosses `PROMOTE_AT`, which is what `retrieve()` then feeds into
future runs.
"""

from __future__ import annotations

PROMOTE_AT = 2   # a decision vindicated this many times is no longer luck


def tier(status: str, vind_count: int = 0) -> str:
    """status is the dissent row's settled state; vind_count is how often this
    exact decision (subject+choice) has been vindicated across runs."""
    if status == "refuted":
        return "low"
    if status == "vindicated":
        return "knowledge" if vind_count >= PROMOTE_AT else "high"
    return "archive"  # dormant / resurrected-but-unsettled: kept, not trusted


def earned_promotion(vind_count: int) -> bool:
    return vind_count >= PROMOTE_AT


def demo() -> None:
    assert tier("dormant") == "archive"
    assert tier("resurrected") == "archive"
    assert tier("refuted") == "low"
    assert tier("vindicated", vind_count=1) == "high"
    assert tier("vindicated", vind_count=PROMOTE_AT) == "knowledge"
    # one vindication is "high", not yet knowledge — it has to repeat.
    assert tier("vindicated", 1) == "high" and not earned_promotion(1)
    assert earned_promotion(PROMOTE_AT)
    print("retention.demo ok")


if __name__ == "__main__":
    demo()
