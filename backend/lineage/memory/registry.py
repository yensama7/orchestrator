"""Package-registry lookups for the drift job (§18.2): latest published version
and known advisories for a dependency. npm + PyPI for versions, OSV for
advisories — all free, keyless, zero token cost.

Every call is pre-flight checked against the egress allowlist (role "drift",
§11) and is offline-safe: any network, timeout, or parse failure resolves to
"no information" (None / False) so the drift job degrades to the time-based
term rather than crashing. The system runs fully offline; this makes it
*sharper* when it has a network, never *dependent* on one.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

from ..security import egress

ROLE = "drift"
_TIMEOUT = httpx.Timeout(6.0)

# ecosystem → OSV ecosystem name
_OSV = {"npm": "npm", "pypi": "PyPI"}


async def latest(ecosystem: str, name: str) -> tuple[str | None, datetime | None]:
    """(latest version, its publish time) for a dep, or (None, None) offline /
    unknown ecosystem. Docker tags aren't version-resolvable here, so skipped."""
    try:
        if ecosystem == "npm":
            return await _npm(name)
        if ecosystem == "pypi":
            return await _pypi(name)
    except Exception:  # noqa: BLE001 — offline / rate-limited / malformed → unknown
        return None, None
    return None, None


async def has_advisory(ecosystem: str, name: str, version: str) -> bool:
    """True if OSV lists a vulnerability affecting this exact pinned version.
    Fails closed-to-safe (False) offline — a missed advisory is caught on the
    next online sweep; a false stale would thrash re-verification."""
    osv_eco = _OSV.get(ecosystem)
    if not osv_eco or not version:
        return False
    host = "api.osv.dev"
    try:
        egress.check(ROLE, host)
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"https://{host}/v1/query",
                json={"package": {"ecosystem": osv_eco, "name": name},
                      "version": _clean(version)},
            )
            r.raise_for_status()
            return bool(r.json().get("vulns"))
    except Exception:  # noqa: BLE001
        return False


async def _npm(name: str) -> tuple[str | None, datetime | None]:
    host = "registry.npmjs.org"
    egress.check(ROLE, host)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.get(f"https://{host}/{name}")
        r.raise_for_status()
        doc = r.json()
    ver = (doc.get("dist-tags") or {}).get("latest")
    when = (doc.get("time") or {}).get(ver) if ver else None
    return ver, _parse_time(when)


async def _pypi(name: str) -> tuple[str | None, datetime | None]:
    host = "pypi.org"
    egress.check(ROLE, host)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.get(f"https://{host}/pypi/{name}/json")
        r.raise_for_status()
        doc = r.json()
    ver = (doc.get("info") or {}).get("version")
    uploads = (doc.get("releases") or {}).get(ver) or []
    when = uploads[0].get("upload_time_iso_8601") if uploads else None
    return ver, _parse_time(when)


def _clean(version: str) -> str:
    return version.lstrip("^~>=<!v ").split(",")[0].strip()


def _parse_time(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def demo() -> None:
    # offline contract: unknown ecosystem and advisory lookups never raise and
    # resolve to "no information". (Live npm/PyPI hits are exercised by the
    # drift sweep against the running stack, not here — no network in tests.)
    assert asyncio.run(latest("docker", "postgres")) == (None, None)
    assert asyncio.run(latest("nonsense", "x")) == (None, None)
    assert asyncio.run(has_advisory("nonsense", "x", "1.0.0")) is False
    assert asyncio.run(has_advisory("npm", "x", "")) is False
    assert _clean("^1.2.3") == "1.2.3" and _clean(">=2.0.0,<3") == "2.0.0"
    assert _parse_time(None) is None and _parse_time("bad") is None
    assert _parse_time("2024-01-02T03:04:05Z").year == 2024
    print("registry.demo ok")


if __name__ == "__main__":
    demo()
