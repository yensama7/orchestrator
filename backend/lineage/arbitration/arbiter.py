"""Deterministic five-stage arbiter (§18.3, §20.5).

Same inputs → same winner, which is what forking (§16.5) and replay require.
No model in this loop. Stages short-circuit as soon as one proposal remains;
every eliminated proposal is recorded to the dissent ledger.
"""

from __future__ import annotations

from typing import Callable

from .scores import AgentScore, ArbiterConfig, Decision, Elimination, Proposal


def _partition(items, pred):
    keep, drop = [], []
    for it in items:
        (keep if pred(it) else drop).append(it)
    return keep, drop


class Arbiter:
    def __init__(
        self,
        scores: dict[str, AgentScore],
        cfg: ArbiterConfig | None = None,
        record: Callable[[str, str, list[Elimination], int], None] | None = None,
    ):
        self.scores = scores
        self.cfg = cfg or ArbiterConfig()
        self._record = record or (lambda winner, domain, trace, stage: None)

    def decide(self, domain: str, proposals: list[Proposal]) -> Decision:
        trace: list[Elimination] = []
        alive = list(proposals)

        # 1 — hard gates: schema/policy invalid or MUST NOT pitfall violation.
        alive, out = _partition(alive, lambda p: p.valid and not p.violates_pitfall)
        trace += [
            Elimination(p.id, p.agent, 1, p.violates_pitfall or "invalid envelope/policy")
            for p in out
        ]
        if len(alive) == 1:
            return self._finish(alive[0], domain, trace, 1)
        if not alive:
            return Decision(winner=None, stage=1, trace=trace)

        # 2 — executable ground truth: a passing test beats any vote.
        if any(p.verifier_passes is not None for p in alive):
            alive, out = _partition(alive, lambda p: p.verifier_passes is not False)
            trace += [Elimination(p.id, p.agent, 2, "verifier fail") for p in out]
            if len(alive) == 1:
                return self._finish(alive[0], domain, trace, 2)
            if not alive:
                return Decision(winner=None, stage=2, trace=trace)

        # 3 — scored vote (deterministic: ties broken by proposal id).
        scored = sorted(
            ((self._score(p, domain), p) for p in alive),
            key=lambda sp: (sp[0], sp[1].id),
            reverse=True,
        )

        # 4 — tie goes to a human, never a coin flip.
        if len(scored) > 1 and scored[0][0] - scored[1][0] < self.cfg.epsilon:
            return Decision(winner=None, stage=4, trace=trace, held=True)

        winner = scored[0][1]
        top = scored[0][0]
        trace += [
            Elimination(p.id, p.agent, 3, f"score {s:.2f} vs {top:.2f}")
            for s, p in scored[1:]
        ]
        return self._finish(winner, domain, trace, 3)

    def _score(self, p: Proposal, domain: str) -> float:
        a = self.scores.get(p.agent, AgentScore())
        w = self.cfg.weights
        return (
            w.agree * p.agreement
            + w.pass_ * a.pass_rate
            + w.vindicate * a.vindication_rate
            - w.escalate * a.escalation_rate
            - w.cost * p.normalised_cost
        )

    def _finish(self, winner: Proposal, domain: str, trace, stage: int) -> Decision:
        self._record(winner.agent, domain, trace, stage)  # §8 — nothing discarded
        return Decision(winner=winner.id, stage=stage, trace=trace)


def demo() -> None:
    scores = {
        "dev-a": AgentScore(pass_rate=0.91, vindication_rate=0.20),
        "dev-b": AgentScore(pass_rate=0.88, vindication_rate=0.30),
        "dev-c": AgentScore(pass_rate=0.74, vindication_rate=0.64),
    }
    arb = Arbiter(scores)

    # stage 1: a pitfall violation is disqualified, not penalised.
    d = arb.decide(
        "commerce",
        [
            Proposal("p1", "dev-a", {}, agreement=0.5),
            Proposal("p2", "dev-b", {}, violates_pitfall="p-0042"),
        ],
    )
    assert d.winner == "p1" and d.stage == 1
    assert any(e.stage == 1 and e.reason == "p-0042" for e in d.trace)

    # stage 2: a passing verifier beats a higher-scoring failing one.
    d = arb.decide(
        "commerce",
        [
            Proposal("p1", "dev-a", {}, agreement=0.9, verifier_passes=False),
            Proposal("p2", "dev-c", {}, agreement=0.1, verifier_passes=True),
        ],
    )
    assert d.winner == "p2" and d.stage == 2

    # stage 3: scored vote picks the higher composite score.
    d = arb.decide(
        "commerce",
        [
            Proposal("p1", "dev-a", {}, agreement=0.4, normalised_cost=0.2),
            Proposal("p2", "dev-c", {}, agreement=0.9, normalised_cost=0.1),
        ],
    )
    assert d.winner in {"p1", "p2"} and d.stage == 3

    # stage 4: near-identical scores are held for a human, not coin-flipped.
    tie = {"x": AgentScore(pass_rate=0.5), "y": AgentScore(pass_rate=0.5)}
    d = Arbiter(tie).decide(
        "commerce",
        [Proposal("p1", "x", {}, agreement=0.5), Proposal("p2", "y", {}, agreement=0.5)],
    )
    assert d.held and d.winner is None and d.stage == 4
    print("arbiter.demo ok")


if __name__ == "__main__":
    demo()
