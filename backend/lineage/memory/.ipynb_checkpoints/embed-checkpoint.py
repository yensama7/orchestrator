"""Embeddings. Local, deterministic, dependency-free by default so the whole
memory pipeline runs offline; point EMBED_URL at a text-embeddings-inference
server (BGE-M3, §15) to swap in real semantics without touching callers.

The local embedder is a hashed bag-of-tokens projected to 1024 dims and
L2-normalised. It is not semantically strong — it exists so RRF/HNSW/rerank
have real vectors to move, and upgrades to TEI by setting one env var.
"""

from __future__ import annotations

import hashlib
import math
import os
import re

DIM = 1024
_EMBED_URL = os.getenv("EMBED_URL")  # e.g. http://tei:80/embed
_TOKEN = re.compile(r"[a-z0-9]+")


def _local(text: str) -> list[float]:
    vec = [0.0] * DIM
    toks = _TOKEN.findall(text.lower()) or ["∅"]
    for tok in toks:
        h = hashlib.blake2b(tok.encode(), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "big") % DIM
        sign = 1.0 if h[4] & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


async def embed(text: str) -> list[float]:
    if not _EMBED_URL:
        return _local(text)
    import httpx

    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(_EMBED_URL, json={"inputs": text})
        r.raise_for_status()
        data = r.json()
        return data[0] if isinstance(data[0], list) else data


def to_pgvector(vec: list[float]) -> str:
    """pgvector text form: '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def demo() -> None:
    a = _local("use postgres for storage")
    b = _local("use postgres for storage")
    c = _local("do not use postgres")
    assert a == b and len(a) == DIM
    dot = lambda x, y: sum(i * j for i, j in zip(x, y))
    assert dot(a, b) > dot(a, c)  # identical text closer than contradictory text
    assert to_pgvector([1.0, 2.0]).startswith("[1.0")
    print("embed.demo ok")


if __name__ == "__main__":
    demo()
