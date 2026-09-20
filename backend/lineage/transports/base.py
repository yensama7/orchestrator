"""Transport ABC (§20.3). Three implementations, one interface. Cost is a union
because subscription agents spend quota, not dollars."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Prompt:
    system: str = ""
    user: str = ""
    # stable / warm / cold ordering is enforced by the caller (L1, §10); the
    # transport must not reorder these blocks.
    stable: str = ""


@dataclass
class Budget:
    usd: float = 1.0


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    usd: float = 0.0


@dataclass
class Completion:
    text: str
    usage: Usage = field(default_factory=Usage)
    raw: dict | None = None


@dataclass
class Capacity:
    limit: int
    used: int = 0
    resets_at: str | None = None
    unit: str = "requests"


class Transport(ABC):
    name: str

    @abstractmethod
    async def complete(self, prompt: Prompt, *, schema=None, budget: Budget | None = None) -> Completion:
        ...

    @abstractmethod
    def capacity(self) -> Capacity:
        """Concurrency limit + headroom; the scheduler sizes its semaphore from
        this so a 5-request subscription window can't be dispatched 40 nodes."""
