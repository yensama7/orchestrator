"""Metered API transport (§4). Standard key, cost in USD per token. Anthropic
Messages shape by default; the OpenAI-compatible path covers gpt/deepseek/kimi.
"""

from __future__ import annotations

import asyncio
import os

from .base import Budget, Capacity, Completion, Prompt, Transport, Usage

# Cached-input discount for the OpenAI-compatible path. OpenAI bills prompt-cache
# hits at 0.5× input; DeepSeek/most others are at or below that, so 0.5 is a
# conservative model (never under-bills) and keeps the Phase-2 cost-per-verified
# metric honest instead of charging every cached token at full rate (§P2).
CACHE_DISCOUNT = float(os.getenv("CACHE_DISCOUNT", "0.5"))

# 1024 truncates any node that must emit full runnable files (the files-map
# contract in orchestrator._dispatch) — the JSON gets cut mid-file, fails to
# parse, and the node reads as a model failure when it was really a ceiling.
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "4096"))

# Transient provider errors (rate limit / overload / dropped socket) retried
# with exponential backoff before complete() lets the exception propagate to
# orchestrator._dispatch, which falls back to the echo stub — and a single echo
# demotes the whole run to `simulated` (§P0). A hiccup shouldn't cost a run its
# `live` status. ponytail: fixed small cap, not claude-code's 10×+jitter layer —
# raise RETRY_ATTEMPTS if a provider's 429s outlast this.
RETRY_ATTEMPTS = int(os.getenv("API_RETRY_ATTEMPTS", "4"))
_RETRY_STATUS = {429, 500, 502, 503, 529}


async def _post_retry(client, url, **kw):
    """POST with bounded exponential backoff on transient status/transport errors."""
    import httpx

    last: Exception | None = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            r = await client.post(url, **kw)
            if r.status_code in _RETRY_STATUS and attempt < RETRY_ATTEMPTS - 1:
                last = httpx.HTTPStatusError(f"{r.status_code}", request=r.request, response=r)
            else:
                r.raise_for_status()
                return r
        except (httpx.TransportError, httpx.HTTPStatusError) as e:
            last = e
        await asyncio.sleep(0.5 * 2 ** attempt)  # 0.5s, 1s, 2s, …
    assert last is not None
    raise last


def openai_usd(pin: float, pout: float, inp: int, out: int, cached: int) -> float:
    """Input billed as fresh + cached×discount; output at full rate. $/1M rates."""
    fresh = max(inp - cached, 0)
    return (fresh * pin + cached * pin * CACHE_DISCOUNT + out * pout) / 1e6


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
    "OpenRouter": "https://openrouter.ai/api/v1",
}


def _base_url(model: str) -> str:
    """Route to the provider's own OpenAI-compatible host. OPENAI_BASE_URL still
    overrides (self-hosted / proxy), else fall back to OpenAI."""
    from .. import catalog

    env = os.getenv("OPENAI_BASE_URL")
    if env:
        return env
    info = catalog.model_info(model)
    # ponytail: a "/" in an api-path model id ⇒ an OpenRouter vendor/model slug.
    # This covers models discovered live from OpenRouter that aren't in the static
    # catalog. Only api-transport ids reach here, and none of ours but OpenRouter's
    # carry a slash — widen this if another slashed provider is ever added.
    provider = info["provider"] if info else ("OpenRouter" if "/" in model else "")
    return _BASES.get(provider, "https://api.openai.com/v1")


def _anthropic_system(prompt: Prompt):
    """System as content blocks with a cache breakpoint after the stable prefix,
    so the run-constant tree is billed once (cache write) then read at 0.1×. No
    stable block → plain string (nothing worth a breakpoint)."""
    if not prompt.stable.strip():
        return prompt.system.strip()
    blocks = [{"type": "text", "text": prompt.stable, "cache_control": {"type": "ephemeral"}}]
    if prompt.system.strip():
        blocks.append({"type": "text", "text": prompt.system})
    return blocks


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
            pin, pout = PRICES.get(self.model, (1.0, 3.0))
            if anthropic:
                r = await _post_retry(c, "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                    json={"model": self.model, "max_tokens": MAX_OUTPUT_TOKENS,
                          "system": _anthropic_system(prompt),
                          "messages": [{"role": "user", "content": prompt.user}]})
                d = r.json()
                text = "".join(b.get("text", "") for b in d.get("content", []))
                u = d.get("usage", {})
                # Anthropic splits input: uncached + cache write (1.25×) + cache read (0.1×)
                fresh, out = u.get("input_tokens", 0), u.get("output_tokens", 0)
                cw, cr = u.get("cache_creation_input_tokens", 0), u.get("cache_read_input_tokens", 0)
                inp = fresh + cw + cr
                usd = (fresh * pin + cw * pin * 1.25 + cr * pin * 0.1) / 1e6 + out / 1e6 * pout
                cached = cr
            else:
                base = _base_url(self.model)
                openrouter = "openrouter.ai" in base
                body = {"model": self.model, "messages": [
                    # stable first so the provider's automatic prefix cache hits
                    {"role": "system", "content": f"{prompt.stable}\n{prompt.system}".strip()},
                    {"role": "user", "content": prompt.user}]}
                # OpenRouter's models aren't in PRICES, so ask it to return the real
                # USD cost — the only honest number for the spend rail (§P2).
                if openrouter:
                    body["usage"] = {"include": True}
                r = await _post_retry(c, f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {key}"}, json=body)
                d = r.json()
                text = d["choices"][0]["message"]["content"]
                u = d.get("usage", {})
                inp, out = u.get("prompt_tokens", 0), u.get("completion_tokens", 0)
                cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
                # OpenRouter reports actual cost; otherwise cached input billed at
                # CACHE_DISCOUNT× (§P2) so cost-per-verified isn't full-rate inflated.
                usd = (u["cost"] if openrouter and u.get("cost") is not None
                       else openai_usd(pin, pout, inp, out, cached))

        return Completion(text, Usage(input_tokens=inp, output_tokens=out,
                                      cached_tokens=cached, usd=usd), raw=d)

    def capacity(self) -> Capacity:
        return Capacity(limit=self._concurrency, unit="requests")


def demo() -> None:
    old = os.environ.pop("OPENAI_BASE_URL", None)
    try:
        assert _base_url("deepseek-v3.2") == "https://api.deepseek.com/v1"
        assert _base_url("gpt-5.1") == "https://api.openai.com/v1"
        assert "x.ai" in _base_url("grok-4")
        assert "openrouter.ai" in _base_url("anthropic/claude-sonnet-4.5")  # catalog
        assert "openrouter.ai" in _base_url("qwen/qwen3-next")             # slug heuristic, not in catalog
        assert _base_url("unknown-model") == "https://api.openai.com/v1"  # safe fallback
        os.environ["OPENAI_BASE_URL"] = "http://proxy:1234/v1"
        assert _base_url("deepseek-v3.2") == "http://proxy:1234/v1"  # override wins
        # cache discount: a fully-cached call costs less than a fully-fresh one,
        # and zero cache reproduces the old full-rate number.
        assert openai_usd(3.0, 15.0, 1000, 0, 0) == 3.0 / 1e6 * 1000
        assert openai_usd(3.0, 15.0, 1000, 0, 1000) < openai_usd(3.0, 15.0, 1000, 0, 0)
        assert openai_usd(3.0, 15.0, 1000, 0, 1000) == 1000 * 3.0 * CACHE_DISCOUNT / 1e6
    finally:
        os.environ.pop("OPENAI_BASE_URL", None)
        if old:
            os.environ["OPENAI_BASE_URL"] = old
    asyncio.run(_retry_selfcheck())
    print("api.demo ok")


async def _retry_selfcheck() -> None:
    import httpx

    # 503 twice then 200 → retried through to success (backoff slept for real;
    # fine, two short sleeps). A fake client counts calls and scripts responses.
    calls = {"n": 0}
    req = httpx.Request("POST", "http://x")

    class Fake:
        async def post(self, url, **kw):
            calls["n"] += 1
            code = 503 if calls["n"] < 3 else 200
            return httpx.Response(code, request=req, json={"ok": True})

    global RETRY_ATTEMPTS
    saved = RETRY_ATTEMPTS
    try:
        r = await _post_retry(Fake(), "http://x")
        assert calls["n"] == 3 and r.json()["ok"]
        # exhausts attempts on persistent 500 → raises, doesn't hang
        calls["n"] = 0
        RETRY_ATTEMPTS = 2

        class Always500:
            async def post(self, url, **kw):
                calls["n"] += 1
                return httpx.Response(500, request=req)

        try:
            await _post_retry(Always500(), "http://x")
            assert False, "should have raised"
        except httpx.HTTPStatusError:
            assert calls["n"] == 2
    finally:
        RETRY_ATTEMPTS = saved


if __name__ == "__main__":
    demo()
