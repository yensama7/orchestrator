"""Types + weights for the deterministic arbiter (§18.3, §20.5)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentScore:
    """Per agent×domain, derived from verified outcomes (§9)."""

    pass_rate: float = 0.0
    escalation_rate: float = 0.0
    vindication_rate: float = 0.0
    overruled: int = 0
    vindicated: int = 0


@dataclass
class Proposal:
    id: str
    agent: str
    body: dict
    agreement: float = 0.0          # semantic agreement with peers, 0..1
    normalised_cost: float = 0.0    # 0..1
    valid: bool = True              # passes envelope schema + role policy (stage 1)
    violates_pitfall: str | None = None
    verifier_passes: bool | None = None  # None = not run


@dataclass
class Elimination:
    proposal_id: str
    agent: str
    stage: int
    reason: str


@dataclass
class Decision:
    winner: str | None
    stage: int
    trace: list[Elimination] = field(default_factory=list)
    held: bool = False   # stage-4 tie → human


@dataclass
class Weights:
    agree: float = 0.30
    pass_: float = 0.30
    vindicate: float = 0.25
    escalate: float = 0.20
    cost: float = 0.10


@dataclass
class ArbiterConfig:
    """Mirrors config/arbiter.yaml — tunable without a deploy."""

    epsilon: float = 0.05
    weights: Weights = field(default_factory=Weights)
