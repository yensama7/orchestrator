"""Verifier registry (§18.3 stage 2). A verifier is a named callable that
returns pass/fail for a proposal at a node. Executable ground truth beats any
vote — this is where that runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Awaitable, Callable


@dataclass
class VerifyResult:
    passed: bool
    summary: str


Verifier = Callable[[dict], "Awaitable[VerifyResult] | VerifyResult"]
_REGISTRY: dict[str, Verifier] = {}


def register(name: str):
    def deco(fn: Verifier):
        _REGISTRY[name] = fn
        return fn
    return deco


async def run(acceptance: list[str], proposal: dict) -> VerifyResult:
    """All named verifiers must pass. Missing verifier id fails closed."""
    for name in acceptance:
        v = _REGISTRY.get(name)
        if v is None:
            return VerifyResult(False, f"unknown verifier {name}")
        res = v(proposal)
        if hasattr(res, "__await__"):
            res = await res
        if not res.passed:
            return res
    return VerifyResult(True, "ok")


# ── built-in verifiers ──────────────────────────────────────────────────────
@register("envelope.valid")
def _envelope_valid(p: dict) -> VerifyResult:
    ok = isinstance(p.get("choice"), str) and p.get("choice") != ""
    return VerifyResult(ok, "choice present" if ok else "empty/invalid choice")


@register("json.parses")
def _json_parses(p: dict) -> VerifyResult:
    try:
        json.dumps(p)
        return VerifyResult(True, "serialises")
    except (TypeError, ValueError) as e:
        return VerifyResult(False, str(e))


@register("confidence.min")
def _confidence_min(p: dict) -> VerifyResult:
    ok = float(p.get("confidence", 0)) >= 0.5
    return VerifyResult(ok, f"confidence {p.get('confidence', 0)}")
