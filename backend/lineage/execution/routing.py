"""Complexity-routed model tiers (phases.md §P2).

A node is scored deterministically from its shape — fan-in, writes breadth,
acceptance strength, prior failure rate for the fingerprint, irreversibility —
into a tier. A trivial config-touch routes to a cheap/local model; a complex or
irreversible node routes to the strong one. Among the agents eligible for a
node's role, the router then prefers the one with the best *historical
cost-per-verified-result* for this domain (the Phase-2 metric feeding back into
the next run's spend), falling back to the cheapest model when there's no
history yet. This replaces the old "40% of calls should be local" quota: cheap
that triggers a repair→re-call→re-verify cycle is not cheap, so the choice is
complexity × proven economics, not a fixed percentage.

The decision is a pure function of (node, candidates, history) — logged per node
so a run explains why it spent what it spent, and so a forked/replayed run
(§16.5) routes identically given the same DB snapshot. Routing is on by default;
set COMPLEXITY_ROUTING=0 to fall back to "first eligible agent" (the pre-Phase-2
behaviour) for an A/B against always-strong.
"""

from __future__ import annotations

import os

from ..contracts import NodeSpec
from ..transports.api import PRICES

TIERS = ("cheap", "standard", "strong")
_RANK = {t: i for i, t in enumerate(TIERS)}


def enabled() -> bool:
    return os.getenv("COMPLEXITY_ROUTING", "1") != "0"


# ── node complexity → the tier it deserves ──────────────────────────────────
def score(*, fan_in: int, writes: int, behavioral: int,
          prior_failures: int, irreversible: bool) -> float:
    """0..1 node complexity. Irreversible work pins to the top — a wrong
    irreversible decision is the expensive kind, so it always gets the strong
    model regardless of the other factors (phases.md §P2)."""
    if irreversible:
        return 1.0
    return round(
        0.30 * min(fan_in, 3) / 3          # integration surface
        + 0.20 * min(writes, 3) / 3        # blast radius of what it writes
        + 0.30 * min(behavioral, 2) / 2    # how hard it is to satisfy
        + 0.20 * min(prior_failures, 3) / 3,  # how often this fingerprint has burned us
        3)


def tier(s: float) -> str:
    return "strong" if s >= 0.66 else "standard" if s >= 0.33 else "cheap"


def node_tier(node: NodeSpec, *, behavioral: int, prior_failures: int) -> str:
    return tier(score(fan_in=len(node.depends_on), writes=len(node.writes),
                      behavioral=behavioral, prior_failures=prior_failures,
                      irreversible=node.irreversible))


# ── model → tier (by marginal price; local/subscription spend no dollars) ────
def model_tier(model: str, transport: str) -> str:
    if transport != "api":
        return "cheap"                      # local/subscription = zero marginal $
    pin = PRICES.get(model, (1.0, 3.0))[0]  # $/1M input tokens
    return "strong" if pin >= 5 else "standard" if pin >= 1 else "cheap"


# ── the pick: cheapest-proven agent at or above the needed tier ──────────────
def choose(candidates: list[dict], needed: str, history: dict[str, float]) -> dict:
    """Deterministic. `history[agent]` is that agent's cost-per-verified-result
    for the domain (lower is better); absent = never proven. Among agents whose
    model meets the needed tier (or, if none do, the strongest available), pick
    the lowest proven cost, then the cheapest tier, then agent id for a stable
    tie-break."""
    ranked = [(c, _RANK[model_tier(c["model"], c["transport"])]) for c in candidates]
    need = _RANK[needed]
    eligible = [cr for cr in ranked if cr[1] >= need]
    if not eligible:                        # nobody meets the floor → strongest we have
        top = max(r for _, r in ranked)
        eligible = [cr for cr in ranked if cr[1] == top]

    def key(cr):
        c, r = cr
        cpv = history.get(c["agent"])
        proven = cpv is not None
        # known-good agents first (ascending cost); else cheapest tier; then id.
        return (0 if proven else 1, cpv if proven else r, r, c["agent"])

    return min(eligible, key=key)[0]


def demo() -> None:
    # irreversible pins to strong no matter how small the node looks.
    assert tier(score(fan_in=0, writes=0, behavioral=0, prior_failures=0,
                      irreversible=True)) == "strong"
    # a tiny reversible node with one check is cheap.
    assert tier(score(fan_in=0, writes=1, behavioral=1, prior_failures=0,
                      irreversible=False)) == "cheap"
    # fan-in + two behavioral checks + a history of failures climbs the ladder.
    assert tier(score(fan_in=3, writes=3, behavioral=2, prior_failures=3,
                      irreversible=False)) == "strong"

    assert model_tier("claude-opus-4.6", "api") == "strong"
    assert model_tier("deepseek-v3.2", "api") == "cheap"
    assert model_tier("whatever", "local") == "cheap"
    assert model_tier("whatever", "subscription") == "cheap"

    cheap = {"agent": "cheap-a", "model": "deepseek-v3.2", "transport": "api"}
    mid = {"agent": "mid-a", "model": "gpt-5.1", "transport": "api"}
    strong = {"agent": "strong-a", "model": "claude-opus-4.6", "transport": "api"}
    cands = [cheap, mid, strong]

    # strong node, no history → the cheapest agent that still meets the floor.
    assert choose(cands, "strong", {})["agent"] == "strong-a"
    # cheap node, no history → the cheapest eligible tier.
    assert choose(cands, "cheap", {})["agent"] == "cheap-a"
    # history wins within the eligible set: the strong agent is cheaper per
    # verified result than the mid one, so a standard node still picks it.
    hist = {"mid-a": 4.0, "strong-a": 1.0}
    assert choose(cands, "standard", hist)["agent"] == "strong-a"
    # no eligible tier (need strong, only cheap present) → strongest available.
    assert choose([cheap], "strong", {})["agent"] == "cheap-a"
    # deterministic: same inputs, same pick (replay/fork depend on it).
    assert choose(cands, "standard", hist) == choose(cands, "standard", hist)
    print("routing.demo ok")


if __name__ == "__main__":
    demo()
