"""Brief → SpecFingerprint (§3 step 2). LLM job on a lightweight local model (or
any configured model — see _pick); falls back to heuristic extraction only when
no model is reachable. The result is user-editable in the wizard — this is the
highest-leverage human input, so it's a first-class object, not metadata."""

from __future__ import annotations

import json
import re

from ..contracts import SpecFingerprint
from ..transports import Prompt
from ._pick import light_transport

_DOMAINS = {
    "storefront": ("commerce", "storefront"), "shop": ("commerce", "storefront"),
    "marketplace": ("commerce", "marketplace"), "dashboard": ("saas", "admin"),
    "api": ("api", "service"), "mobile": ("mobile", "app"),
}
_PAY = ["paystack", "stripe", "flutterwave", "adyen"]
_STACK = ["nextjs", "react", "postgres", "django", "fastapi", "rails", "go", "rust"]
_REGION = {"nigeria": "NG", "nigerian": "NG", "us": "US", "europe": "EU", "eu": "EU"}

_SYS = (
    "Extract a build spec from the brief. Return ONLY JSON with keys: "
    "domain (one word: commerce|saas|api|mobile|content|tool|data|other), "
    "subdomain, scale (object), stack_hints (array), payments (string|null), "
    "auth (none|required), multi_tenant (bool), compliance (array), region "
    "(2-letter code or ''). Infer domain from what the app does; do not default "
    "to commerce. Empty/unknown fields: use the type's empty value."
)

# canonical domain set (join key for roster/agent_scores/lineage grouping) and the
# synonyms a free-thinking model tends to emit. The prompt is unconstrained — the
# model reasons however it likes; we only normalise the *label* so "e-commerce",
# "web shop", "Commerce" all collapse to one bucket. Unknown → "other".
_CANON = {"commerce", "saas", "api", "mobile", "content", "tool", "data", "other"}
_SYN = {
    "ecommerce": "commerce", "e-commerce": "commerce", "retail": "commerce",
    "shop": "commerce", "store": "commerce", "storefront": "commerce",
    "marketplace": "commerce", "fintech": "commerce", "payment": "commerce",
    "b2b": "saas", "dashboard": "saas", "admin": "saas", "platform": "saas",
    "service": "api", "backend": "api", "microservice": "api", "rest": "api",
    "app": "mobile", "ios": "mobile", "android": "mobile",
    "cms": "content", "blog": "content", "media": "content", "publishing": "content",
    "news": "content", "website": "content", "web": "content",
    "utility": "tool", "devtool": "tool", "productivity": "tool",
    "analytics": "data", "etl": "data", "ml": "data", "pipeline": "data",
    "warehouse": "data", "dataset": "data",
}


def canon_domain(d: str) -> str:
    d = (d or "").strip().lower()
    if d in _CANON:
        return d
    if d in _SYN:
        return _SYN[d]
    for kw, canon in _SYN.items():  # substring: "e-commerce storefront" → commerce
        if kw in d:
            return canon
    return "other"


async def extract(brief: str) -> SpecFingerprint:
    try:
        comp = await (await light_transport()).complete(
            Prompt(system=_SYS, user=brief))
        data = json.loads(_json_slice(comp.text))
        data["domain"] = canon_domain(data.get("domain", ""))  # free reasoning, fixed label
        return SpecFingerprint(**data)
    except Exception:
        return _heuristic(brief)  # CLI missing/unauthed or bad JSON → keyword fallback


def _json_slice(text: str) -> str:
    i, j = text.find("{"), text.rfind("}")
    return text[i:j + 1] if i != -1 and j > i else text


def _heuristic(brief: str) -> SpecFingerprint:
    b = brief.lower()
    domain, subdomain = "other", ""
    for kw, (d, s) in _DOMAINS.items():
        if kw in b:
            domain, subdomain = d, s
            break
    skus = None
    m = re.search(r"(\d[\d,\.]*)\s*k?\s*sku", b)
    if m:
        n = float(m.group(1).replace(",", ""))
        skus = int(n * 1000) if "k" in b[m.start():m.end()] else int(n)
    return SpecFingerprint(
        domain=domain, subdomain=subdomain,
        scale={"skus": skus, "traffic": "low"} if skus else {"traffic": "low"},
        stack_hints=[s for s in _STACK if s in b],
        payments=next((p for p in _PAY if p in b), None),
        auth="required" if any(w in b for w in ("auth", "login", "admin", "account")) else "none",
        multi_tenant="multi-tenant" in b or "saas" in b,
        region=next((v for k, v in _REGION.items() if k in b), ""),
    )


def demo() -> None:
    import asyncio

    fp = _heuristic("Create a webpage that displays time, timezone and ip of visitor")
    assert fp.domain == "other" and fp.payments is None, fp  # no keyword => not commerce
    fp2 = _heuristic("Nigerian storefront with 2k skus and paystack")
    assert fp2.domain == "commerce" and fp2.payments == "paystack" and fp2.region == "NG", fp2
    assert _json_slice("noise {\"a\":1} tail") == '{"a":1}'
    # a free-thinking model's varied labels collapse to the canonical join key
    assert canon_domain("E-Commerce") == "commerce"
    assert canon_domain("web shop") == "commerce"
    assert canon_domain("analytics") == "data"
    assert canon_domain("wildly novel thing") == "other"
    assert canon_domain("saas") == "saas"

    # a model that answers is honored — extraction must NOT override it with the
    # keyword heuristic (this is the "always commerce" regression guard).
    class _Fake:
        text = '{"domain":"data","subdomain":"etl","auth":"required"}'
    class _T:
        async def complete(self, *a, **k):
            return _Fake()
    g = globals()
    orig = g["light_transport"]
    g["light_transport"] = lambda: _wrap(_T())
    try:
        got = asyncio.run(extract("build an ip/timezone webpage"))  # a brief the heuristic calls 'other'
        assert got.domain == "data" and got.auth == "required", got
    finally:
        g["light_transport"] = orig
    print("extract.demo ok")


async def _wrap(t):  # light_transport is awaited: `await light_transport()`
    return t


if __name__ == "__main__":
    demo()
