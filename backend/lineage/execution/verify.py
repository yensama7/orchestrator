"""Verifier registry (§18.3 stage 2, phases.md §P1b). A verifier is a named
callable returning pass/fail for a proposal at a node. Executable ground truth
beats any vote — this is where that runs.

Two kinds:

* **structural** — pure functions of the proposal body (envelope/json/confidence).
  Cheap stage-1 gating; they never touch disk.
* **behavioral** — they stage the proposal's produced `files` into a sandbox and
  *execute* a real toolchain (compile/test/migrate), gating on the exit code.
  A node that writes code carries at least one (the planner enforces it,
  plan.py), so a structural pass on an echo proposal can no longer masquerade as
  a verified build. A run is only `live` if a behavioral verifier gated it
  (mode.py, §P0); the echo stub emits no files, so it fails these closed and the
  run stays honestly `simulated`.

Ceiling (ponytail): behavioral verification is hermetic only for the toolchains
present in the sandbox image (python-slim today → Python first-class, Node
best-effort, others fail closed). Per-stack images + a real ephemeral Postgres
for schema.migrates land in Phase 4; the mechanism here is complete and the
command set widens behind it without touching callers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from .pool import Sandbox


@dataclass
class VerifyResult:
    passed: bool
    summary: str


# a verifier takes the proposal body and (for behavioral ones) a sandbox; it may
# be sync or async. Structural verifiers ignore the sandbox.
Verifier = Callable[[dict, "Sandbox | None"], "Awaitable[VerifyResult] | VerifyResult"]
_REGISTRY: dict[str, Verifier] = {}
# Verifiers that *execute* the proposal's artifacts vs ones that only assert
# structure. A run is only `live` if a behavioral verifier gated it.
_BEHAVIORAL: set[str] = set()


def register(name: str, *, behavioral: bool = False):
    def deco(fn: Verifier):
        _REGISTRY[name] = fn
        if behavioral:
            _BEHAVIORAL.add(name)
        return fn
    return deco


def any_behavioral(acceptance: list[str]) -> bool:
    """Did this node carry at least one executing (behavioral) verifier?"""
    return any(name in _BEHAVIORAL for name in acceptance)


def behavioral_count(acceptance: list[str]) -> int:
    """How many executing verifiers a node carries — acceptance strength, a
    complexity-routing input (routing.py, §P2)."""
    return sum(1 for name in acceptance if name in _BEHAVIORAL)


async def run(acceptance: list[str], proposal: dict, sandbox: "Sandbox | None" = None) -> VerifyResult:
    """All named verifiers must pass. Missing verifier id fails closed. Behavioral
    verifiers need a sandbox; without one they fail closed rather than pass blind."""
    for name in acceptance:
        v = _REGISTRY.get(name)
        if v is None:
            return VerifyResult(False, f"unknown verifier {name}")
        res = v(proposal, sandbox)
        if hasattr(res, "__await__"):
            res = await res
        if not res.passed:
            return res
    return VerifyResult(True, "ok")


# ── structural verifiers (cheap, body-only) ─────────────────────────────────
@register("envelope.valid")
def _envelope_valid(p: dict, _sb=None) -> VerifyResult:
    ok = isinstance(p.get("choice"), str) and p.get("choice") != ""
    return VerifyResult(ok, "choice present" if ok else "empty/invalid choice")


@register("json.parses")
def _json_parses(p: dict, _sb=None) -> VerifyResult:
    try:
        json.dumps(p)
        return VerifyResult(True, "serialises")
    except (TypeError, ValueError) as e:
        return VerifyResult(False, str(e))


@register("confidence.min")
def _confidence_min(p: dict, _sb=None) -> VerifyResult:
    ok = float(p.get("confidence", 0)) >= 0.5
    return VerifyResult(ok, f"confidence {p.get('confidence', 0)}")


# ── behavioral verifiers (execute the proposal's files in a sandbox) ─────────
async def _execute(name: str, proposal: dict, sandbox: "Sandbox | None",
                   recipe: Callable[[str], "tuple[list[str], str] | None"]) -> VerifyResult:
    """Shared body: stage files → pick a command for the staged stack → run it
    under a hard timeout → pass iff exit 0. No files or no runnable stack fails
    closed — that is the point (an echo proposal produces nothing to execute)."""
    if sandbox is None:
        return VerifyResult(False, f"{name}: no sandbox")
    files = proposal.get("files")
    if not isinstance(files, dict) or not files:
        return VerifyResult(False, f"{name}: proposal produced no files")
    sandbox.write_files(files)
    cmd = recipe(sandbox.workdir)
    if cmd is None:
        return VerifyResult(False, f"{name}: no runner for this stack")
    argv, label = cmd
    rc, out = await sandbox.exec(argv, network=False, timeout=90)  # hang → 124, a fail
    tail = out.strip()[-300:]
    return VerifyResult(rc == 0, f"{label} ok" if rc == 0 else f"{label} rc={rc}: {tail}")


def _exts(workdir: str) -> set[str]:
    return {p.suffix for p in Path(workdir).rglob("*") if p.is_file()}


def _names(workdir: str) -> set[str]:
    return {p.name for p in Path(workdir).rglob("*") if p.is_file()}


def _build_cmd(wd: str):
    exts = _exts(wd)
    if ".py" in exts:
        return (["python", "-m", "compileall", "-q", "."], "compileall")
    if ".js" in exts:
        return (["sh", "-c", 'set -e; for f in $(find . -name "*.js"); do node --check "$f"; done'],
                "node --check")
    return None


def _tests_cmd(wd: str):
    if "package.json" in _names(wd):
        return (["npm", "test", "--silent"], "npm test")
    if ".py" in _exts(wd):
        # ponytail: unittest discover (stdlib, hermetic); use pytest when the
        # project configures it (conftest.py / pytest.ini) in Phase 4.
        return (["python", "-m", "unittest", "discover", "-q"], "unittest")
    return None


def _typecheck_cmd(wd: str):
    if "package.json" in _names(wd):
        return (["sh", "-c", "npx --no-install tsc --noEmit"], "tsc")
    if ".py" in _exts(wd):
        return (["python", "-m", "mypy", "--ignore-missing-imports", "--no-error-summary", "."], "mypy")
    return None


def _lint_cmd(wd: str):
    if "package.json" in _names(wd):
        return (["sh", "-c", "npx --no-install eslint ."], "eslint")
    if ".py" in _exts(wd):
        return (["python", "-m", "pyflakes", "."], "pyflakes")
    return None


# ponytail: SQLite executescript smoke — real execution, catches gross DDL
# errors, but is not Postgres. Swap to an ephemeral Postgres (VERIFY_DATABASE_URL)
# in Phase 4 so dialect-specific DDL verifies for real.
_SQL_SMOKE = (
    "import sqlite3, glob, sys\n"
    "fs = glob.glob('**/*.sql', recursive=True)\n"
    "if not fs: sys.exit('no .sql files produced')\n"
    "for f in fs:\n"
    "    sqlite3.connect(':memory:').executescript(open(f, encoding='utf-8').read())\n"
    "print('migrated', len(fs), 'file(s)')\n"
)


def _schema_cmd(wd: str):
    return (["python", "-c", _SQL_SMOKE], "sqlite-smoke")


@register("build.succeeds", behavioral=True)
async def _build(p, sb=None):
    return await _execute("build.succeeds", p, sb, _build_cmd)


@register("tests.pass", behavioral=True)
async def _tests(p, sb=None):
    return await _execute("tests.pass", p, sb, _tests_cmd)


@register("typecheck.clean", behavioral=True)
async def _typecheck(p, sb=None):
    return await _execute("typecheck.clean", p, sb, _typecheck_cmd)


@register("lint.clean", behavioral=True)
async def _lint(p, sb=None):
    return await _execute("lint.clean", p, sb, _lint_cmd)


@register("schema.migrates", behavioral=True)
async def _schema(p, sb=None):
    return await _execute("schema.migrates", p, sb, _schema_cmd)


def demo() -> None:
    import asyncio

    from .pool import scratch_sandbox

    async def main():
        async with scratch_sandbox() as sb:
            # good Python compiles; a syntax error does not.
            ok = await run(["confidence.min", "build.succeeds"],
                           {"choice": "x", "confidence": 0.9,
                            "files": {"src/app.py": "def f():\n    return 1\n"}}, sb)
            assert ok.passed, ok
            bad = await run(["build.succeeds"],
                            {"files": {"src/app.py": "def f(:\n"}}, sb)
            assert not bad.passed, bad

            # an echo proposal (no files) fails the behavioral gate closed — this
            # is what keeps a simulated run from passing as verified.
            none = await run(["build.succeeds"], {"choice": "proceed", "confidence": 0.6}, sb)
            assert not none.passed and "no files" in none.summary, none

            # a behavioral verifier with no sandbox fails closed, never blind-passes.
            nosb = await run(["build.succeeds"], {"files": {"a.py": "x=1\n"}}, None)
            assert not nosb.passed, nosb

            # tests execute for real: a passing unittest passes, a failing one fails.
            passing = {"files": {"test_x.py":
                "import unittest\nclass T(unittest.TestCase):\n"
                "    def test_ok(self): self.assertEqual(1, 1)\n"}}
            assert (await run(["tests.pass"], passing, sb)).passed
            failing = {"files": {"test_x.py":
                "import unittest\nclass T(unittest.TestCase):\n"
                "    def test_bad(self): self.assertEqual(1, 2)\n"}}
            assert not (await run(["tests.pass"], failing, sb)).passed

            # schema.migrates runs the DDL: valid applies, broken does not.
            assert (await run(["schema.migrates"],
                              {"files": {"db/001.sql": "CREATE TABLE t(id INTEGER);"}}, sb)).passed
            assert not (await run(["schema.migrates"],
                                  {"files": {"db/001.sql": "CREATE TABL t(id);"}}, sb)).passed

            # structural verifiers still work and ignore the sandbox.
            assert (await run(["json.parses", "confidence.min"],
                              {"choice": "c", "confidence": 0.7}, sb)).passed

        assert any_behavioral(["confidence.min", "build.succeeds"])
        assert not any_behavioral(["confidence.min", "json.parses"])

    asyncio.run(main())
    print("verify.demo ok")


if __name__ == "__main__":
    demo()
