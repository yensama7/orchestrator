"""Hybrid retrieval: BM25 + vector fused with RRF in Postgres (retrieval.sql),
then a local rerank keeping the top 6 (§20.7). status='active' in both branches
is what stops an agent re-proposing a reversed decision.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..db.tenancy import tenant_conn
from .embed import embed, to_pgvector

_SQL = (Path(__file__).parent / "retrieval.sql").read_text()
_TOKEN = re.compile(r"[a-z0-9]+")
TOP_K = 6


async def retrieve(query: str, top_k: int = TOP_K) -> list[dict]:
    vec = to_pgvector(await embed(query))
    async with tenant_conn() as c:
        # RLS already scopes the tenant; retrieval.sql filters on it explicitly
        # too (defence in depth), so pass the current setting as $1.
        tenant = await c.fetchval("SELECT current_setting('app.tenant_id')::uuid")
        rows = await c.fetch(_SQL, tenant, vec, query)
    return _rerank(query, [dict(r) for r in rows])[:top_k]


def _rerank(query: str, rows: list[dict]) -> list[dict]:
    """Local rerank stand-in for bge-reranker-v2-m3: RRF fused with lexical
    overlap. Swap in the cross-encoder (§15) when recall@10 needs the last mile.
    """
    q = set(_TOKEN.findall(query.lower()))
    for r in rows:
        overlap = len(q & set(_TOKEN.findall((r.get("choice") or "").lower())))
        r["rerank"] = float(r.get("rrf", 0)) + 0.02 * overlap
    rows.sort(key=lambda r: r["rerank"], reverse=True)
    return rows
