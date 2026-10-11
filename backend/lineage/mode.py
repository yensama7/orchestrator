"""Run mode — the Phase-0 truth-in-labeling invariant (phases.md §Phase 0).

A run is `live` only when it both *generated* with a real model (not the echo
stub) and *verified behaviorally* (a verifier that executes, not a structural
assert). Anything else is `simulated`. The point is a reviewer can tell at a
glance whether a number is real, and that a simulated run can never feed the
scoring/leaderboard surface used for routing — enforced here, not in a footnote.

Today behavioral verifiers don't exist (they land in Phase 1), so every run is
`simulated` by construction. When Phase 1 adds executing verifiers and a real
transport runs, `classify` flips the same run to `live` with no other change.
"""

from __future__ import annotations

SIMULATED = "simulated"
LIVE = "live"
MODES = (SIMULATED, LIVE)


def classify(used_echo: bool, used_behavioral: bool) -> str:
    """live iff real generation (no echo) AND at least one behavioral verifier."""
    return LIVE if (used_behavioral and not used_echo) else SIMULATED


def scoreable(mode: str) -> bool:
    """Whether a run's outcomes may write the routing-score surface / a benchmark
    may count it. Only live runs produce verified outcomes."""
    return mode == LIVE


def demo() -> None:
    assert classify(used_echo=False, used_behavioral=True) == LIVE
    assert classify(used_echo=True, used_behavioral=True) == SIMULATED   # echo poisons it
    assert classify(used_echo=False, used_behavioral=False) == SIMULATED  # structural only
    assert scoreable(LIVE) and not scoreable(SIMULATED)
    print("mode ok")


if __name__ == "__main__":
    demo()
