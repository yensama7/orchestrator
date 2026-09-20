"""Dissent ledger (§8, §20.6). The whole feature is a handful of methods over
one table — value extraction from spend that already evaporated.

In-memory here; the SQL shape is in db/schema.sql. resurrect() turns a
90-second replan into a branch switch because the alternative already exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count

_STAGE_RANK = {1: 1, 2: 2, 3: 3, 4: 4}


@dataclass
class DissentRow:
    id: int
    run_id: str
    node_id: str
    dissenter: str
    winner: str
    stage: int
    reason: str
    proposal: dict
    status: str = "dormant"  # dormant|resurrected|vindicated|refuted
    score: float | None = None


class DissentLedger:
    def __init__(self):
        self._rows: list[DissentRow] = []
        self._ids = count(1)

    def record(self, run_id, node_id, winner, eliminations) -> None:
        for e in eliminations:
            self._rows.append(
                DissentRow(
                    id=next(self._ids),
                    run_id=run_id,
                    node_id=node_id,
                    dissenter=e.agent,
                    winner=winner,
                    stage=e.stage,
                    reason=e.reason,
                    proposal=getattr(e, "proposal", {}) or {},
                )
            )

    def resurrect(self, run_id: str, node_id: str) -> DissentRow | None:
        """Called when the winning path fails verification. Highest-ranked
        dormant dissent for the node — later stage first, then score."""
        cands = [
            r for r in self._rows
            if r.run_id == run_id and r.node_id == node_id and r.status == "dormant"
        ]
        if not cands:
            return None
        cands.sort(key=lambda r: (_STAGE_RANK.get(r.stage, 0), r.score or 0), reverse=True)
        row = cands[0]
        row.status = "resurrected"
        return row

    def settle(self, row_id: int, passed: bool) -> None:
        for r in self._rows:
            if r.id == row_id:
                r.status = "vindicated" if passed else "refuted"
                return

    def rows(self) -> list[DissentRow]:
        return list(self._rows)


def demo() -> None:
    from types import SimpleNamespace as E

    led = DissentLedger()
    led.record("run1", "schema.design", "dev-a", [
        E(agent="dev-c", stage=3, reason="score 0.61 vs 0.74", proposal={"choice": "uuid pk"}),
        E(agent="dev-b", stage=1, reason="pitfall p-0042", proposal={}),
    ])
    r = led.resurrect("run1", "schema.design")
    assert r.dissenter == "dev-c" and r.status == "resurrected"  # higher stage wins
    led.settle(r.id, passed=True)
    assert [x for x in led.rows() if x.id == r.id][0].status == "vindicated"
    # dev-b's stage-1 row is still dormant → next resurrect falls to it
    r2 = led.resurrect("run1", "schema.design")
    assert r2.dissenter == "dev-b"
    led.settle(r2.id, passed=False)
    assert led.resurrect("run1", "schema.design") is None  # nothing dormant left
    print("dissent.demo ok")


if __name__ == "__main__":
    demo()
