"""Execution adapters (§7, §20.8, phases.md §P4a).

Pre-P4 this was "no compose → don't run": a CLI, a static site, a library or a
Terraform module could never be run or verified. Now *every* execution method
declares a sandboxable execution specification, and there is one boundary with
several adapters behind it:

* **Compose**    — a compose file is present → `docker compose up --build`.
* **Dockerfile** — a Dockerfile but no compose → build the image, run it
  network-denied (the egress default-deny from §11).
* **Native**     — a detectable stack (Node / Python / Go / Rust / static) → run
  the project's entrypoint inside the locked-down sandbox (`pool.docker_argv`:
  read-only rootfs, gVisor when present, `--network none`). Phase-1 behavioral
  verification (verify.py) already runs in that same sandbox, so "the verifier
  sits behind the adapter" holds for non-compose projects too.

`gate()` is ready for any project it can place; it only blocks a genuinely empty
worktree. RunGate keeps its shape (ready/file/reason/offer) so the `/run`
endpoint and the EmptyState UI are unchanged — `kind` is additive.

Ceiling (ponytail): the Native/Dockerfile run commands are a best-effort launch
per stack, not a universal entrypoint resolver. The sandbox boundary is real and
default-deny; the *command* widens behind it (per-stack entrypoint config) when a
project needs more than its conventional start.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .pool import docker_argv

COMPOSE = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")

# marker file → (stack, image, run argv). First match wins; order is deliberate
# (a package.json beats a stray .py). `run` is the conventional launch for the
# stack — behind the sandbox boundary, so a wrong guess fails closed, not open.
_NATIVE = [
    ("package.json", "node", "node:20-slim",
     ["sh", "-c", "npm start --if-present || node ."]),
    ("go.mod", "go", "golang:1.23", ["go", "run", "."]),
    ("Cargo.toml", "rust", "rust:1-slim", ["cargo", "run"]),
    ("main.tf", "terraform", "hashicorp/terraform:latest", ["validate"]),
    ("index.html", "static", "python:3.12-slim",
     ["python", "-m", "http.server", "8000"]),
]


@dataclass
class Offer:
    label: str
    task: str


@dataclass
class RunGate:
    ready: bool
    file: str | None = None
    kind: str | None = None          # compose | dockerfile | native:<stack>
    reason: str | None = None
    offer: Offer | None = None

    @classmethod
    def ok(cls, name: str, kind: str) -> "RunGate":
        return cls(ready=True, file=name, kind=kind)

    @classmethod
    def blocked(cls, reason: str, offer: Offer) -> "RunGate":
        return cls(ready=False, reason=reason, offer=offer)


def _native(worktree: Path):
    """(marker, stack, image, argv) for the first stack this worktree matches,
    else None. A bare `.py` file with no manifest still counts as Python."""
    names = {p.name for p in worktree.iterdir() if p.is_file()}
    for marker, stack, image, argv in _NATIVE:
        if marker in names:
            return marker, stack, image, argv
    pys = sorted(p.name for p in worktree.glob("*.py"))
    if pys:
        entry = "main.py" if "main.py" in pys else "app.py" if "app.py" in pys else pys[0]
        return entry, "python", "python:3.12-slim", ["python", entry]
    return None


def gate(worktree: Path) -> RunGate:
    for name in COMPOSE:
        if (worktree / name).exists():
            return RunGate.ok(name, "compose")
    if (worktree / "Dockerfile").exists():
        return RunGate.ok("Dockerfile", "dockerfile")
    nat = _native(worktree)
    if nat:
        marker, stack, _img, _argv = nat
        return RunGate.ok(marker, f"native:{stack}")
    return RunGate.blocked(
        "empty_project",
        Offer("Add project files to run", "devops.scaffold"),
    )


async def start(worktree: Path, g: RunGate):
    """Launch the gated worktree through its adapter. Compose/Dockerfile/Native
    each return the spawned process; the caller owns its lifecycle."""
    assert g.ready, "Run is disabled otherwise, no bypass"
    import asyncio

    wd = str(worktree)
    if g.kind == "compose":
        # ponytail: compose manages its own network, so gVisor/egress-netns can't
        # wrap `up` the way docker_argv wraps a single container. Per-service
        # sandboxing lands with a compose-rewrite pass; the single-container
        # adapters below are already default-deny.
        return await asyncio.create_subprocess_exec(
            "docker", "compose", "-f", g.file, "up", "--build", cwd=wd)

    if g.kind == "dockerfile":
        tag = f"lineage-run-{worktree.name}".lower()
        build = await asyncio.create_subprocess_exec(
            "docker", "build", "-t", tag, ".", cwd=wd)
        if await build.wait() != 0:
            raise RuntimeError("docker build failed")
        # network-denied by default (§11 egress default-deny) — the built image
        # runs with no outbound reach unless a later policy opens it.
        return await asyncio.create_subprocess_exec(
            "docker", "run", "--rm", "--network", "none", tag, cwd=wd)

    # native:<stack> — run the stack's entrypoint behind the shared sandbox
    # boundary (read-only rootfs, gVisor if present, --network none).
    marker, stack, image, argv = _native(worktree)
    return await asyncio.create_subprocess_exec(
        *docker_argv(wd, image, argv, network=False), cwd=wd)


def demo() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        wt = Path(d)
        # empty worktree: nothing to place → blocked with an Offer.
        assert gate(wt).reason == "empty_project" and not gate(wt).ready

        # a bare Python script is now runnable (Native), not a dead end.
        (wt / "main.py").write_text("print('hi')\n")
        g = gate(wt)
        assert g.ready and g.kind == "native:python" and g.file == "main.py"

        # a Node manifest beats the stray .py — package.json wins.
        (wt / "package.json").write_text("{}\n")
        assert gate(wt).kind == "native:node"

        # a static site is Native too.
        with tempfile.TemporaryDirectory() as d2:
            st = Path(d2)
            (st / "index.html").write_text("<h1>hi</h1>\n")
            assert gate(st).kind == "native:static"

        # Dockerfile (no compose) is its own adapter, no longer "blocked".
        (wt / "Dockerfile").write_text("FROM scratch\n")
        assert gate(wt).ready and gate(wt).kind == "dockerfile"

        # compose still wins over everything and is the top adapter.
        (wt / "compose.yaml").write_text("services: {}\n")
        assert gate(wt).ready and gate(wt).kind == "compose" and gate(wt).file == "compose.yaml"
    print("runner.demo ok")


if __name__ == "__main__":
    demo()
