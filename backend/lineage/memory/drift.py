"""Template staleness / drift detection (§18.2).

Retrieval never blocks on freshness — it reads a precomputed `status`. This
module computes that status off the critical path:

    drift = mean_over_deps( w(bump) · staleness(dep) )  +  λ · days_since_promotion

    w(major)=1.0  w(minor)=0.3  w(patch)=0.05
      drift < 0.25            → fresh
      0.25 ≤ drift < 0.6      → drifting   (retrieval down-weights, still offers)
      drift ≥ 0.6, or any dep → stale       (re-verification enqueued by caller)
        with a published advisory

The scoring core (`score`, `classify`, `staleness`) is pure and unit-tested.
`evaluate` / `sweep` add the registry lookups and the status write. `sweep`
returns the ids that went stale so the execution layer can enqueue
re-verification — memory never imports execution.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from . import manifest, registry

# tenant_conn is imported lazily inside evaluate/sweep so the pure scoring core
# (and its tests) load without the asyncpg driver present.

# bump weights (§18.2)
_W = {"major": 1.0, "minor": 0.3, "patch": 0.05, None: 0.0}
# a year of pure age adds this much drift on its own — nudges a long-promoted
# but otherwise-current template toward re-check without ever forcing stale.
_LAMBDA_PER_DAY = 0.2 / 365.0
_FRESH, _DRIFTING = 0.25, 0.6
# bound concurrent registry calls per sweep so we never hammer npm/PyPI.
_MAX_CONCURRENCY = 8


@dataclass(frozen=True)
class Dep:
    bump: str | None       # major|minor|patch|None(current)
    staleness: float       # [0,1]: how long the newer version has been available


def score(deps: list[Dep], days_since_promotion: float) -> float:
    """Pure drift score. Empty deps → time term only (can't assess, so lean on
    age). Mean (not sum) over deps so 'most deps current' reads as low drift
    regardless of project size."""
    dep_term = sum(_W[d.bump] * d.staleness for d in deps) / len(deps) if deps else 0.0
    return round(dep_term + _LAMBDA_PER_DAY * max(days_since_promotion, 0.0), 4)


def classify(drift: float, has_advisory: bool) -> str:
    if has_advisory or drift >= _DRIFTING:
        return "stale"
    if drift >= _FRESH:
        return "drifting"
    return "fresh"


def staleness(published: datetime | None, now: datetime | None = None) -> float:
    """How stale a newer release makes the pin: fraction of a year it has been
    available, capped at 1.0. Unknown publish date → 1.0 (assume fully stale so
    an unknown isn't silently ignored)."""
    if published is None:
        return 1.0
    now = now or datetime.now(timezone.utc)
    age_days = (now - published).total_seconds() / 86400.0
    return min(1.0, max(age_days, 0.0) / 365.0)


async def _assess_dep(eco: str, name: str, pinned: str) -> tuple[Dep | None, bool]:
    """Resolve one dependency against its registry → (Dep or None, advisory?).
    None when the registry has no answer (offline / docker / unknown) — such a
    dep is dropped from the mean entirely rather than diluting it."""
    latest, published = await registry.latest(eco, name)
    if latest is None:
        return None, False
    bump = manifest.classify_bump(pinned, latest)
    advisory = await registry.has_advisory(eco, name, pinned)
    return Dep(bump=bump, staleness=staleness(published) if bump else 0.0), advisory


async def evaluate(template_id: UUID, manifest_doc: dict, days_since_promotion: float
                   ) -> tuple[str, float]:
    """Resolve every dep, compute drift, classify, and persist status +
    drift_score + freshness_checked_at. Returns (status, drift_score)."""
    sem = asyncio.Semaphore(_MAX_CONCURRENCY)

    async def one(eco, name, pinned):
        async with sem:
            return await _assess_dep(eco, name, pinned)

    tasks = [one(eco, name, pinned)
             for eco, deps in (manifest_doc or {}).items()
             for name, pinned in deps.items()]
    results = await asyncio.gather(*tasks) if tasks else []
    deps = [d for d, _ in results if d is not None]
    advisory = any(adv for _, adv in results)

    drift = score(deps, days_since_promotion)
    status = classify(drift, advisory)
    from ..db.tenancy import tenant_conn
    async with tenant_conn() as c:
        await c.execute(
            """UPDATE templates SET drift_score=$2, status=$3::tmpl_status,
                   freshness_checked_at=now()
               WHERE id=$1 AND status <> 'quarantined'""",
            template_id, drift, status)
    return status, drift


async def sweep() -> dict:
    """Evaluate every tenant-owned, non-quarantined template. Returns a summary
    including `stale_ids` — the caller enqueues re-verification for those so this
    module stays free of any execution-layer import."""
    from ..db.tenancy import tenant_conn
    async with tenant_conn() as c:
        rows = await c.fetch(
            """SELECT id, manifest, extract(epoch FROM now()-created_at)/86400 AS age_days
               FROM templates
               WHERE status <> 'quarantined'
                 AND tenant_id = current_setting('app.tenant_id')::uuid""")
    summary = {"checked": 0, "fresh": 0, "drifting": 0, "stale": 0, "stale_ids": []}
    for r in rows:
        md = r["manifest"]
        md = json.loads(md) if isinstance(md, str) else (dict(md) if md else {})
        status, _ = await evaluate(r["id"], md, float(r["age_days"] or 0))
        summary["checked"] += 1
        summary[status] += 1
        if status == "stale":
            summary["stale_ids"].append(str(r["id"]))
    return summary


def demo() -> None:
    # scoring core — pure, no DB, no network
    assert score([], 0) == 0.0
    assert score([Dep("patch", 1.0)], 0) == 0.05
    assert score([Dep("major", 1.0)], 0) == 1.0
    assert score([Dep("major", 1.0), Dep(None, 0.0)], 0) == 0.5   # mean dilutes
    # time term alone: ~one year of age lands in the drifting band
    assert 0.19 < score([], 365) < 0.21

    assert classify(0.1, False) == "fresh"
    assert classify(0.3, False) == "drifting"
    assert classify(0.7, False) == "stale"
    assert classify(0.1, True) == "stale"                         # advisory forces stale

    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert staleness(None) == 1.0                                 # unknown date → fully stale
    assert staleness(now, now) == 0.0                             # published just now
    assert abs(staleness(datetime(2023, 1, 1, tzinfo=timezone.utc), now) - 1.0) < 0.01
    assert abs(staleness(datetime(2023, 7, 5, tzinfo=timezone.utc), now) - 0.5) < 0.02
    print("drift.demo ok")


if __name__ == "__main__":
    demo()
