"""Confidence-aware scoring (phases.md §P3a).

Raw rates lie on small samples: a 5/5 agent reads as 1.00 and outranks a
950/1000 veteran. Every rate here is a Beta-Binomial posterior mean instead —
`(successes + prior·strength) / (trials + strength)`. The prior·strength term is
a pseudo-count that *is* the minimum-sample floor: below ~`strength` trials the
estimate sits near the prior, not on a lucky streak, and climbs toward the raw
rate only as real evidence accrues. That single formula gives the two
properties Phase 3 demands (proven in `demo`):

  1. more evidence never pulls a passing agent below the prior, and
  2. one failure can't zero a strong track record.

Deterministic and DB-free — same counts in, same score out, so replay/fork
(§16.5) rank identically. The DB wiring that feeds it counts lives in the
orchestrator.
"""

from __future__ import annotations

PRIOR = 0.5          # pass-rate prior: an unproven agent is a coin-flip, not a star
STRENGTH = 20        # pseudo-count = the sample floor; ≈20 trials to trust a rate
VIND_PRIOR = 0.2     # dissent is usually wrong; don't reward an unproven dissenter
VIND_STRENGTH = 10

# cohort cuts (trials): below → new, at/above → experienced; specialist needs
# depth in *this* domain, not just lifetime volume.
EXPERIENCED_MIN = STRENGTH
SPECIALIST_MIN = 30


def posterior_mean(successes: int, trials: int,
                   prior: float = PRIOR, strength: float = STRENGTH) -> float:
    """Beta-Binomial posterior mean. `trials` is attempts, `successes` ⊆ trials.
    Shrinks toward `prior` when evidence is thin; → raw rate as trials grow."""
    successes = max(0, min(successes, trials))  # clamp: successes can't exceed trials
    return round((successes + prior * strength) / (trials + strength), 4)


def cohort(trials: int, domain_trials: int = 0) -> str:
    """new | experienced | specialist. Separation is what stops a rookie's lucky
    streak from being read as veteran skill (the ranking itself is protected by
    the shrinkage above; the label makes the distinction auditable)."""
    if trials < EXPERIENCED_MIN:
        return "new"
    return "specialist" if domain_trials >= SPECIALIST_MIN else "experienced"


def demo() -> None:
    # 1 — the headline: a 5/5 rookie must NOT outrank a 950/1000 veteran.
    rookie = posterior_mean(5, 5)
    veteran = posterior_mean(950, 1000)
    assert rookie < veteran, (rookie, veteran)
    assert rookie < 0.75 and veteran > 0.9          # rookie shrunk, veteran trusted

    # 2 — more evidence never pulls a perfect agent below the prior, and the
    #     estimate only rises as successes accrue (monotone in evidence).
    perfect = [posterior_mean(k, k) for k in range(0, 50)]
    assert all(p >= PRIOR for p in perfect)
    assert perfect == sorted(perfect)               # non-decreasing

    # 3 — one failure can't zero a strong track record.
    strong = posterior_mean(950, 1000)
    after_a_miss = posterior_mean(950, 1001)
    assert after_a_miss > 0.9 and after_a_miss < strong

    # 4 — the floor: an unproven agent scores at the prior, not its tiny sample.
    assert abs(posterior_mean(0, 0) - PRIOR) < 1e-9
    assert posterior_mean(2, 2) < posterior_mean(200, 200)

    # cohorts: thin history is "new"; depth in a domain earns "specialist".
    assert cohort(3) == "new"
    assert cohort(50) == "experienced"
    assert cohort(50, domain_trials=40) == "specialist"
    print("confidence.demo ok")


if __name__ == "__main__":
    demo()
