"""Run gate (§7, §20.8). Compose only, no bare-command fallback.

Run is disabled unless a compose file is present. RunGate.blocked carries an
Offer so the UI never has to know *why* Run is disabled — the backend decides,
the EmptyState renders it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

COMPOSE = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")


@dataclass
class Offer:
    label: str
    task: str


@dataclass
class RunGate:
    ready: bool
    file: str | None = None
    reason: str | None = None
    offer: Offer | None = None

    @classmethod
    def ok(cls, name: str) -> "RunGate":
        return cls(ready=True, file=name)

    @classmethod
    def blocked(cls, reason: str, offer: Offer) -> "RunGate":
        return cls(ready=False, reason=reason, offer=offer)


def gate(worktree: Path) -> RunGate:
    for name in COMPOSE:
        if (worktree / name).exists():
            return RunGate.ok(name)
    if (worktree / "Dockerfile").exists():
        return RunGate.blocked(
            "no_compose",
            Offer("Generate compose file", "devops.compose_from_dockerfile"),
        )
    return RunGate.blocked(
        "not_containerised",
        Offer("Containerise this project", "devops.containerise"),
    )


async def start(worktree: Path, g: RunGate):
    assert g.ready, "Run is disabled otherwise, no bypass"
    # ponytail: bare `docker compose up`; add gVisor netns + egress allowlist
    # (§11) when sandboxing lands. Spawns in the current namespace for now.
    import asyncio

    return await asyncio.create_subprocess_exec(
        "docker", "compose", "-f", g.file, "up", "--build", cwd=str(worktree)
    )


def demo() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        wt = Path(d)
        assert gate(wt).reason == "not_containerised"
        (wt / "Dockerfile").write_text("FROM scratch\n")
        g = gate(wt)
        assert not g.ready and g.reason == "no_compose" and g.offer.task.endswith("dockerfile")
        (wt / "compose.yaml").write_text("services: {}\n")
        assert gate(wt).ready and gate(wt).file == "compose.yaml"
    print("runner.demo ok")


if __name__ == "__main__":
    demo()
