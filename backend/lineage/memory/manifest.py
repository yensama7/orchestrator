"""Dependency manifest parsing + semver comparison (§18.2).

A template pins the *resolved versions* of its project's dependencies at
promotion time; the drift job later compares those pins against what the
registries currently publish. This module is the pure, offline half of that:
parse the dependency files a worktree contains into a normalised

    {ecosystem: {name: version_spec}}

map, and classify the jump between two versions as major / minor / patch.
Network lookups live in registry.py; drift math in drift.py. Keeping parsing
pure makes it fully unit-testable with no DB and no sockets.
"""

from __future__ import annotations

import json
import re
import tomllib
from typing import Literal

Bump = Literal["major", "minor", "patch"]

# files we know how to read, by ecosystem. Matched on basename.
_NPM = {"package.json"}
_PYPI_REQ = re.compile(r"requirements.*\.txt$|^requirements\.txt$")
_PYPROJECT = {"pyproject.toml"}
_DOCKERFILE = re.compile(r"(^|/)Dockerfile$|\.Dockerfile$")
_COMPOSE = {"compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml"}

_REQ_LINE = re.compile(r"^\s*([A-Za-z0-9._-]+)\s*(?:==|>=|~=)\s*([A-Za-z0-9._+-]+)")
_FROM_LINE = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?([^\s]+)", re.MULTILINE)
_IMAGE_LINE = re.compile(r"^\s*image:\s*[\"']?([^\s\"']+)", re.MULTILINE)
_SEMVER = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def parse(files: dict[str, str]) -> dict[str, dict[str, str]]:
    """Worktree {relative_path: text} → {ecosystem: {dep: version}}.

    Unknown files are ignored; malformed known files are skipped (never raise —
    a user's project is untrusted input and must not crash a background job)."""
    out: dict[str, dict[str, str]] = {"npm": {}, "pypi": {}, "docker": {}}
    for path, content in files.items():
        base = path.replace("\\", "/").rsplit("/", 1)[-1]
        try:
            if base in _NPM:
                _parse_package_json(content, out["npm"])
            elif _PYPI_REQ.search(base):
                _parse_requirements(content, out["pypi"])
            elif base in _PYPROJECT:
                _parse_pyproject(content, out["pypi"])
            elif _DOCKERFILE.search(path) or base == "Dockerfile":
                _parse_images(_FROM_LINE, content, out["docker"])
            elif base in _COMPOSE:
                _parse_images(_IMAGE_LINE, content, out["docker"])
        except Exception:  # noqa: BLE001 — untrusted input, skip malformed files
            continue
    return {eco: deps for eco, deps in out.items() if deps}


def _parse_package_json(content: str, acc: dict[str, str]) -> None:
    doc = json.loads(content)
    for key in ("dependencies", "devDependencies"):
        for name, spec in (doc.get(key) or {}).items():
            if isinstance(spec, str) and spec[:1] not in ("", "*", "w", "f", "l", "g"):
                acc[name] = spec  # skip "*", "workspace:", "file:", "link:", "github:"


def _parse_requirements(content: str, acc: dict[str, str]) -> None:
    for line in content.splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = _REQ_LINE.match(line)
        if m:
            acc[m.group(1).lower()] = m.group(2)


def _parse_pyproject(content: str, acc: dict[str, str]) -> None:
    doc = tomllib.loads(content)
    deps = (doc.get("project") or {}).get("dependencies") or []
    poetry = (((doc.get("tool") or {}).get("poetry") or {}).get("dependencies") or {})
    for raw in deps:
        m = _REQ_LINE.match(raw) or re.match(r"^\s*([A-Za-z0-9._-]+)", raw)
        if m and m.lastindex and m.lastindex >= 2:
            acc[m.group(1).lower()] = m.group(2)
    for name, spec in poetry.items():
        if name.lower() == "python":
            continue
        if isinstance(spec, str):
            acc[name.lower()] = spec.lstrip("^~>=<! ")


def _parse_images(pattern: re.Pattern, content: str, acc: dict[str, str]) -> None:
    for ref in pattern.findall(content):
        if ":" in ref and not ref.startswith("$"):
            image, tag = ref.rsplit(":", 1)
            if "/" not in tag:  # avoid splitting a registry:port host
                acc[image] = tag


def version_tuple(spec: str) -> tuple[int, int, int]:
    """Best-effort (major, minor, patch) from a version spec. Non-numeric or
    missing components coerce to 0, so 'v1.2' → (1, 2, 0) and '^18' → (18, 0, 0).
    Returns (0,0,0) for unparseable specs so they never dominate a comparison."""
    m = _SEMVER.search(spec or "")
    if not m:
        return (0, 0, 0)
    return tuple(int(g) if g else 0 for g in m.groups())  # type: ignore[return-value]


def classify_bump(pinned: str, latest: str) -> Bump | None:
    """The jump from a pinned spec to the latest published version. None when
    latest is not strictly newer (already current, or pin is ahead/unparseable)."""
    po, pn = version_tuple(pinned), version_tuple(latest)
    if pn <= po:
        return None
    if pn[0] > po[0]:
        return "major"
    if pn[1] > po[1]:
        return "minor"
    return "patch"


def demo() -> None:
    files = {
        "package.json": json.dumps({
            "dependencies": {"react": "^18.2.0", "left-pad": "1.0.0", "x": "workspace:*"},
            "devDependencies": {"vite": "~5.0.0"},
        }),
        "backend/requirements.txt": "fastapi==0.115.6\n# comment\nhttpx>=0.28.1\n",
        "pyproject.toml": '[project]\ndependencies = ["pydantic>=2.10.4", "uvicorn==0.34.0"]\n',
        "Dockerfile": "FROM python:3.12-slim\nRUN echo hi\n",
        "compose.yaml": "services:\n  db:\n    image: postgres:16\n",
    }
    m = parse(files)
    assert m["npm"] == {"react": "^18.2.0", "left-pad": "1.0.0", "vite": "~5.0.0"}, m["npm"]
    assert m["pypi"]["fastapi"] == "0.115.6" and m["pypi"]["httpx"] == "0.28.1"
    assert m["pypi"]["pydantic"] == "2.10.4" and m["pypi"]["uvicorn"] == "0.34.0"
    assert m["docker"] == {"python": "3.12-slim", "postgres": "16"}, m["docker"]

    assert version_tuple("^18.2.0") == (18, 2, 0)
    assert version_tuple("v1.2") == (1, 2, 0)
    assert version_tuple("garbage") == (0, 0, 0)
    assert classify_bump("1.2.3", "2.0.0") == "major"
    assert classify_bump("1.2.3", "1.3.0") == "minor"
    assert classify_bump("1.2.3", "1.2.4") == "patch"
    assert classify_bump("1.2.3", "1.2.3") is None
    assert classify_bump("2.0.0", "1.9.9") is None

    assert parse({"weird.txt": "junk"}) == {}            # unknown file → nothing
    assert parse({"package.json": "{not json"}) == {}    # malformed → skipped, no raise
    print("manifest.demo ok")


if __name__ == "__main__":
    demo()
