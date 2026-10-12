"""Local transport — Ollama/vLLM (§4). Zero marginal cost, so the §P2 router
sends cheap/trivial nodes here when a local model is configured — by complexity
× proven cost-per-verified-result, not a fixed quota. Falls back to a
deterministic echo so the orchestrator runs with no model server present
(routing/fingerprint/summary shaped output)."""

from __future__ import annotations

import json
import os

from .base import Budget, Capacity, Completion, Prompt, Transport, Usage

_OLLAMA = os.getenv("OLLAMA_URL")  # e.g. http://ollama:11434


class LocalTransport(Transport):
    def __init__(self, model: str = "qwen2.5:3b", concurrency: int = 4):
        self.name = "local"
        self.model = model
        self._concurrency = concurrency

    async def complete(self, prompt: Prompt, *, schema=None, budget: Budget | None = None) -> Completion:
        if _OLLAMA:
            import httpx

            try:
                async with httpx.AsyncClient(timeout=120) as c:
                    r = await c.post(f"{_OLLAMA}/api/generate", json={
                        "model": self.model,
                        "prompt": f"{prompt.stable}\n{prompt.system}\n{prompt.user}",
                        "stream": False,
                    })
                    r.raise_for_status()
                    data = r.json()
                    text = data.get("response", "")
                    return Completion(text, Usage(
                        input_tokens=data.get("prompt_eval_count", 0),
                        output_tokens=data.get("eval_count", 0), usd=0.0), raw=data)
            except httpx.HTTPError:
                # OLLAMA_URL set but unreachable (DNS/connect/timeout) or the model
                # isn't pulled — honor the documented contract ("unreachable → echo
                # stand-in, so nothing breaks") instead of failing the node with a
                # raw [Errno -2]. Falls through to the echo path below.
                pass
        # echo: deterministic structured stand-in, free — flagged simulated so the
        # orchestrator can never label a run that used it `live` (mode.py).
        text = json.dumps({"choice": _echo_choice(prompt.user), "confidence": 0.6})
        return Completion(text, Usage(input_tokens=len(prompt.user) // 4,
                                      output_tokens=len(text) // 4, usd=0.0),
                          simulated=True)

    def capacity(self) -> Capacity:
        return Capacity(limit=self._concurrency, unit="slots")


def _echo_choice(user: str) -> str:
    u = user.lower()
    if "auth" in u:
        return "JWT"
    if "db" in u or "database" in u:
        return "postgres 16"
    if "payment" in u:
        return "paystack"
    return "proceed"
