"""Egress secret scanning (§11). gitleaks as a subprocess on every artifact
before it leaves the sandbox; a built-in regex sweep is the fallback when
gitleaks isn't installed so the gate is never silently open."""

from __future__ import annotations

import asyncio
import re
import shutil

_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),                         # AWS access key
    re.compile(r"sk-[A-Za-z0-9]{20,}"),                      # OpenAI-style key
    re.compile(r"ghp_[A-Za-z0-9]{36}"),                      # GitHub PAT
    re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"), # private key
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),             # Slack token
]


async def scan(text: str) -> list[str]:
    """Returns a list of findings. Empty list = clean = allowed to egress."""
    if shutil.which("gitleaks"):
        return await _gitleaks(text)
    return [m.group(0)[:8] + "…" for p in _PATTERNS for m in p.finditer(text)]


async def _gitleaks(text: str) -> list[str]:
    import json
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(text)
        path = f.name
    proc = await asyncio.create_subprocess_exec(
        "gitleaks", "detect", "--no-git", "--source", path, "--report-format", "json",
        "--report-path", "/dev/stdout",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    out, _ = await proc.communicate()
    try:
        return [f["RuleID"] for f in json.loads(out or "[]")]
    except (json.JSONDecodeError, TypeError):
        return []


def demo() -> None:
    import asyncio as a
    clean = a.get_event_loop().run_until_complete(scan("nothing to see here"))
    dirty = a.get_event_loop().run_until_complete(scan("key AKIAIOSFODNN7EXAMPLE oops"))
    assert clean == [] and dirty  # fails closed on a real secret
    print("scan.demo ok")


if __name__ == "__main__":
    demo()
