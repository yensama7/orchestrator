"""Pick a cheap transport for planner-side jobs (fingerprint extraction, role
research). Preference: a real local model (Ollama up), then any model whose API
key was added, then a configured subscription CLI, then the local echo. The echo
can't do real extraction — it only emits routing-shaped stand-in JSON — so it is
LAST, never first: preferring it silently starved every configured model and
made extraction fall back to the keyword heuristic (the "always commerce" bug).
These jobs still degrade instead of erroring: the echo path always returns."""

from __future__ import annotations

from ..transports import Transport, build as build_transport
from ..transports.local import _OLLAMA


def _select(creds: list[dict], ollama: str | None) -> tuple[str, str, str | None]:
    """Pure pick (model, transport, api_key) so the ordering is unit-testable."""
    if ollama:                                        # 1) real local server = free + capable
        for r in creds:
            if r["transport"] == "local":
                return r["model"], "local", None
    for r in creds:                                   # 2) any model with an API key
        if r["transport"] == "api" and r["api_key"]:
            return r["model"], "api", r["api_key"]
    for r in creds:                                   # 3) a configured subscription CLI
        if r["transport"] == "subscription":
            return r["model"], "subscription", None
    for r in creds:                                   # 4) local echo (no ollama) — last resort
        if r["transport"] == "local":
            return r["model"], "local", None
    return "qwen3-4b", "local", None                  # nothing configured → free echo


async def light_transport() -> Transport:
    from ..db.tenancy import tenant_conn  # deferred: keeps this importable driver-free

    async with tenant_conn() as c:
        creds = await c.fetch(
            "SELECT model, transport, api_key FROM model_credentials WHERE enabled ORDER BY added_at")
    model, transport, key = _select([dict(r) for r in creds], _OLLAMA)
    return build_transport(model, transport, key)


def demo() -> None:
    api = {"model": "gpt-5.1", "transport": "api", "api_key": "sk-x"}
    echo = {"model": "qwen3-4b", "transport": "local", "api_key": None}
    sub = {"model": "claude-opus-4.6", "transport": "subscription", "api_key": None}
    # echo present but so is a real key → the key wins (the extraction fix)
    assert _select([echo, api], ollama=None) == ("gpt-5.1", "api", "sk-x")
    # only echo configured → echo, but never ahead of a key
    assert _select([echo], ollama=None) == ("qwen3-4b", "local", None)
    # ollama up → local is real and preferred
    assert _select([echo, api], ollama="http://x")[1] == "local"
    # no key, no ollama, but a subscription CLI → subscription over echo
    assert _select([echo, sub], ollama=None) == ("claude-opus-4.6", "subscription", None)
    print("_pick.demo ok")


if __name__ == "__main__":
    demo()
