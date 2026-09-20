"""Per-role egress allowlist (§11). Default deny. In production this compiles to
netns/nftables rules enforced by the kernel; this module is the policy source of
truth and the pre-flight check the broker consults before any outbound call."""

from __future__ import annotations

from fnmatch import fnmatch

# role → allowed host globs. Everything else is denied.
ALLOWLIST: dict[str, list[str]] = {
    "planner": ["api.anthropic.com"],
    "senior-dev": ["api.anthropic.com", "api.openai.com", "registry.npmjs.org", "pypi.org"],
    "frontend": ["registry.npmjs.org"],
    "security": ["api.anthropic.com"],
    "security-analyst": [],          # analysis only, no egress
    "reflection": [],
    "devops": ["registry-1.docker.io", "*.docker.io"],
}


def allowed(role: str, host: str) -> bool:
    return any(fnmatch(host, pat) for pat in ALLOWLIST.get(role, []))


def check(role: str, host: str) -> None:
    if not allowed(role, host):
        raise PermissionError(f"egress denied: {role} → {host} not allowlisted")


def demo() -> None:
    assert allowed("senior-dev", "pypi.org")
    assert not allowed("frontend", "api.openai.com")
    assert not allowed("security-analyst", "api.anthropic.com")  # empty = deny-all
    assert not allowed("unknown-role", "anything")               # default deny
    try:
        check("frontend", "evil.example")
        raise AssertionError("should have denied")
    except PermissionError:
        pass
    print("egress.demo ok")


if __name__ == "__main__":
    demo()
