"""Embedding → 2D coords for the lineage/memory graphs (§15 precompute).

UMAP+HDBSCAN is the real batch projector; this is a cheap deterministic
stand-in: project the 1024-vec onto two fixed pseudo-random unit axes and squash
to 0..1. Same input → same point, so the graph is stable across reloads, and it
runs with no sklearn/umap dependency. Swap for UMAP when clusters must be tight.
"""

from __future__ import annotations

import hashlib
import math

DIM = 1024


def _axis(seed: int) -> list[float]:
    v = []
    for i in range(DIM):
        h = hashlib.blake2b(f"{seed}:{i}".encode(), digest_size=4).digest()
        v.append((int.from_bytes(h, "big") / 2**32) - 0.5)
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


_AX = _axis(1)
_AY = _axis(2)


def project(vec: list[float]) -> tuple[float, float]:
    dx = sum(a * b for a, b in zip(vec, _AX))
    dy = sum(a * b for a, b in zip(vec, _AY))
    # tanh squash into a padded 0..1 box
    x = 0.5 + 0.42 * math.tanh(dx * 6)
    y = 0.5 + 0.42 * math.tanh(dy * 6)
    return round(x, 4), round(y, 4)
