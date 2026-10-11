"""Materialise a run's stored worktree to a scratch directory on disk.

The console imports a project into `worktree_files` (content in the DB). Both
the run gate (§7) and template re-verification (§18.2) need those files back on
a real filesystem to hand to `docker compose`. This is that shared step —
path-traversal-guarded so an imported path can never escape the scratch root.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import UUID

from ..db.tenancy import tenant_conn


async def materialise(run_id: UUID, prefix: str = "lineage-") -> Path | None:
    """Write a run's worktree to a fresh temp dir. Returns the root, or None if
    the run has no files. The caller owns cleanup of the returned directory."""
    async with tenant_conn() as c:
        files = await c.fetch(
            "SELECT folder, name, content FROM worktree_files WHERE run_id=$1 ORDER BY ordinal",
            run_id)
    if not files:
        return None
    root = Path(tempfile.mkdtemp(prefix=prefix))
    for f in files:
        rel = (f["folder"] + f["name"]).replace("\\", "/").lstrip("./")
        if ".." in rel.split("/"):
            continue  # never let an imported path escape the scratch root
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(f["content"] or "", encoding="utf-8")
    return root


async def read_files(run_id: UUID) -> dict[str, str]:
    """Run's worktree as {relative_path: text} without touching disk — for the
    manifest parser at promotion time."""
    async with tenant_conn() as c:
        files = await c.fetch(
            "SELECT folder, name, content FROM worktree_files WHERE run_id=$1", run_id)
    return {(f["folder"] + f["name"]).replace("\\", "/").lstrip("./"): (f["content"] or "")
            for f in files}
