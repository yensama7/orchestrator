"""Metered API transport (§4). Standard key, cost in USD per token. Anthropic
Messages shape by default; the OpenAI-compatible path covers gpt/deepseek/kimi.
"""

from __future__ import annotations

import os

from .base import Budget, Capacity, Completion, Prompt, Transport, Usage

# $/1M tokens (in, out) — override via PRICES env for exact billing.
PRICES = {
    "claude-sonnet-4.6": (3.0, 15.0),
    "claude-opus-4.6": (15.0, 75.0),
    "gpt-5.1": (2.5, 10.0),
    "deepseek-v3.2": (0.28, 0.42),
    "kimi-k2": (0.15, 0.30),
    "gemini-3-pro": (2.5, 10.0),
}

# OpenAI-compatible base URL per provider. Every one of these speaks the
# /chat/completions shape, but each lives on its own host — posting a DeepSeek
# key to api.openai.com just 401s. Anthropic has its own path (handled below).
_BASES = {
    "OpenAI": "https://api.openai.com/v1",
    "DeepSeek": "https://api.deepseek.com/v1",
    "Moonshot": "https://api.moonshot.ai/v1",
    "xAI": "https://api.x.ai/v1",
    "Meta": "https://api.together.xyz/v1",
    "Mistral": "https://api.mistral.ai/v1",
    "Alibaba": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "Google": "https://generativelanguage.googleapis.com/v1beta/openai",
}


def _base_url(model: str) -> str:
    """Route to the provider's own OpenAI-compatible host. OPENAI_BASE_URL still
    overrides (self-hosted / proxy), else fall back to OpenAI."""
    from .. import catalog

    env = os.getenv("OPENAI_BASE_URL")
    if env:
        return env
    info = catalog.model_info(model)
    return _BASES.get(info["provider"] if info else "", "https://api.openai.com/v1")


class ApiTransport(Transport):
    def __init__(self, model: str, concurrency: int = 8, api_key: str | None = None):
        self.name = "api"
        self.model = model
        self._concurrency = concurrency
        self._key = api_key

    async def complete(self, prompt: Prompt, *, schema=None, budget: Budget | None = None) -> Completion:
        import httpx

        from .. import catalog

        anthropic = self.model.startswith("claude")
        info = catalog.model_info(self.model)
        env_var = (info and info.get("key_env")) or ("ANTHROPIC_API_KEY" if anthropic else "OPENAI_API_KEY")
        key = self._key or os.getenv(env_var)
        if not key:
            raise RuntimeError(f"{self.model}: no API key set ({env_var}) — this agent is API-only (§4)")

        async with httpx.AsyncClient(timeout=120) as c:
            if anthropic:
                r = await c.post("https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                    json={"model": self.model, "max_tokens": 1024,
                          "system": f"{prompt.stable}\n{prompt.system}".strip(),
                          "messages": [{"role": "user", "content": prompt.user}]})
                r.raise_for_status()
                d = r.json()
                text = "".join(b.get("text", "") for b in d.get("content", []))
                u = d.get("usage", {})
                inp, out = u.get("input_tokens", 0), u.get("output_tokens", 0)
            else:
                base = _base_url(self.model)
                r = await c.post(f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": self.model, "messages": [
                        {"role": "system", "content": f"{prompt.stable}\n{prompt.system}".strip()},
                        {"role": "user", "content": prompt.user}]})
                r.raise_for_status()
                d = r.json()
                text = d["choices"][0]["message"]["content"]
                u = d.get("usage", {})
                inp, out = u.get("prompt_tokens", 0), u.get("completion_tokens", 0)

        pin, pout = PRICES.get(self.model, (1.0, 3.0))
        usd = inp / 1e6 * pin + out / 1e6 * pout
        return Completion(text, Usage(input_tokens=inp, output_tokens=out, usd=usd), raw=d)

    def capacity(self) -> Capacity:
        return Capacity(limit=self._concurrency, unit="requests")


def demo() -> None:
    old = os.environ.pop("OPENAI_BASE_URL", None)
    try:
        assert _base_url("deepseek-v3.2") == "https://api.deepseek.com/v1"
        assert _base_url("gpt-5.1") == "https://api.openai.com/v1"
        assert "x.ai" in _base_url("grok-4")
        assert _base_url("unknown-model") == "https://api.openai.com/v1"  # safe fallback
        os.environ["OPENAI_BASE_URL"] = "http://proxy:1234/v1"
        assert _base_url("deepseek-v3.2") == "http://proxy:1234/v1"  # override wins
    finally:
        os.environ.pop("OPENAI_BASE_URL", None)
        if old:
            os.environ["OPENAI_BASE_URL"] = old
    print("api.demo ok")


if __name__ == "__main__":
    demo()
