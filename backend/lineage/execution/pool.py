"""Warm sandbox pool (§14). Cold-starting a container per node dominates wall
clock, so sandboxes are pre-created and handed out on demand. Each sandbox is an
isolated working dir; with SANDBOX_DOCKER set, commands run inside a locked-down
container (read-only rootfs, no network, gVisor if the runtime is present)."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

_DOCKER = os.getenv("SANDBOX_DOCKER") == "1"
_RUNTIME = os.getenv("SANDBOX_RUNTIME", "runsc")  # gVisor; falls back to runc if absent


@dataclass
class Sandbox:
    id: str
    workdir: str

    def reset(self) -> None:
        """Clear the workdir so a warm sandbox never leaks files between the
        proposals it verifies in sequence."""
        for child in Path(self.workdir).iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)

    def write_files(self, files: dict[str, str]) -> int:
        """Stage a proposal's produced files into the workdir, clearing any prior
        contents first. Path-traversal guarded — a `..` segment can never escape
        the sandbox root (same guard as worktree.materialise). Returns the count
        written."""
        self.reset()
        n = 0
        for rel, content in (files or {}).items():
            rel = str(rel).replace("\\", "/").lstrip("./")
            if not rel or ".." in rel.split("/"):
                continue
            dest = Path(self.workdir) / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content if isinstance(content, str) else str(content),
                            encoding="utf-8")
            n += 1
        return n

    async def exec(self, argv: list[str], *, network: bool = False, timeout: float = 60) -> tuple[int, str]:
        if _DOCKER:
            cmd = ["docker", "run", "--rm", "--read-only",
                   "--tmpfs", "/tmp", "-v", f"{self.workdir}:/work", "-w", "/work"]
            if _has_runtime():
                cmd += ["--runtime", _RUNTIME]          # syscall isolation (§11)
            if not network:
                cmd += ["--network", "none"]            # egress default-deny (§11)
            cmd += ["python:3.12-slim", *argv]
        else:
            cmd = argv
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=self.workdir, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT)
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return 124, "timeout"
        return proc.returncode, out.decode(errors="replace")


class SandboxPool:
    def __init__(self, size: int = 4):
        self._free: asyncio.Queue[Sandbox] = asyncio.Queue()
        self._size = size
        self._all: list[Sandbox] = []

    async def start(self) -> None:
        for i in range(self._size):
            sb = Sandbox(id=f"sb-{i}", workdir=tempfile.mkdtemp(prefix="lineage-sb-"))
            self._all.append(sb)
            await self._free.put(sb)

    async def acquire(self) -> Sandbox:
        return await self._free.get()

    async def release(self, sb: Sandbox) -> None:
        await self._free.put(sb)

    async def shutdown(self) -> None:
        for sb in self._all:
            shutil.rmtree(sb.workdir, ignore_errors=True)

    @property
    def in_use(self) -> int:
        return self._size - self._free.qsize()


def _has_runtime() -> bool:
    return shutil.which(_RUNTIME) is not None


@contextlib.asynccontextmanager
async def scratch_sandbox():
    """A throwaway sandbox for behavioral verification outside a run's pool (the
    manual resurrect path, arbitration/dissent.py). Cleaned up on exit."""
    sb = Sandbox(id="scratch", workdir=tempfile.mkdtemp(prefix="lineage-sb-"))
    try:
        yield sb
    finally:
        shutil.rmtree(sb.workdir, ignore_errors=True)
