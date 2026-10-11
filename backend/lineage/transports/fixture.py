"""Fixture transport (phases.md §Phase 5 — onboarding). A recorded, real
proposal replayed offline: it emits *actual runnable artifacts* (a clean typed
module, a passing unittest, a valid migration), not the echo stub's keyword
stand-in. The behavioral verifiers (verify.py) then execute those artifacts for
real in the sandbox and genuinely pass — so the onboarding run is a true
verified outcome (`simulated=False` → mode.py classifies it `live`) with no API
key and no GPU.

The generation is pre-recorded, not model-produced; the *verification* is live.
That's the honest shape of a golden example: a new user sees a genuinely verified
build in one command, and the headline cost-per-verified-result is real (it cost
nothing locally). Not for benchmarks — benchmarks need real generation — which is
why this is a distinct transport, never a silent default.
"""

from __future__ import annotations

import json

from .base import Budget, Capacity, Completion, Prompt, Transport, Usage

# Artifacts that satisfy every behavioral verifier at once: the .py compiles
# (build.succeeds), is clean under pyflakes/mypy (lint/typecheck), the test
# passes under `unittest discover` (tests.pass), and the .sql applies
# (schema.migrates). One proposal covers any node the planner emits.
_FILES = {
    "app.py": "def add(a: int, b: int) -> int:\n    return a + b\n",
    "test_app.py": (
        "import unittest\n\n"
        "from app import add\n\n\n"
        "class AddTest(unittest.TestCase):\n"
        "    def test_adds(self) -> None:\n"
        "        self.assertEqual(add(2, 3), 5)\n"
    ),
    "db/001_init.sql": "CREATE TABLE IF NOT EXISTS item (id INTEGER PRIMARY KEY, name TEXT);\n",
}

_RECORDED = json.dumps({"choice": "implement the requested change", "confidence": 0.95,
                        "files": _FILES})


class FixtureTransport(Transport):
    def __init__(self, model: str = "lineage-fixture"):
        self.name = "fixture"
        self.model = model

    async def complete(self, prompt: Prompt, *, schema=None, budget: Budget | None = None) -> Completion:
        # real artifacts, zero marginal cost, NOT simulated — a live verified run.
        return Completion(_RECORDED, Usage(input_tokens=len(prompt.user) // 4,
                                           output_tokens=len(_RECORDED) // 4, usd=0.0))

    def capacity(self) -> Capacity:
        return Capacity(limit=8, unit="slots")


def demo() -> None:
    import asyncio

    async def main():
        comp = await FixtureTransport().complete(Prompt(user="node core.logic"))
        assert not comp.simulated, "fixture must count as real generation (live-eligible)"
        body = json.loads(comp.text)
        assert body["files"] and body["confidence"] >= 0.5
        # the staged files actually pass the behavioral verifiers.
        from ..execution.pool import scratch_sandbox
        from ..execution import verify
        async with scratch_sandbox() as sb:
            assert (await verify.run(["build.succeeds", "tests.pass"], body, sb)).passed

    asyncio.run(main())
    print("fixture.demo ok")


if __name__ == "__main__":
    demo()
