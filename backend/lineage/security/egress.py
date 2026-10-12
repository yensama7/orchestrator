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
    # the drift job (§18.2) reads public registries to compare pinned versions
    # against latest, and OSV for advisories. Read-only, keyless, no token cost.
    "drift": ["registry.npmjs.org", "pypi.org", "api.osv.dev"],
}

# User-defined per-role host globs from the roles table, loaded at API startup
# and refreshed on role add/delete (api/main._refresh_egress). Merged *over* the
# hardcoded ALLOWLIST — additive only: a user can widen a role's egress, never
# punch below the deny-by-default floor a hardcoded role already sets.
_OVERRIDES: dict[str, list[str]] = {}


def set_overrides(mapping: dict[str, list[str]]) -> None:
    global _OVERRIDES
    _OVERRIDES = {k: list(v) for k, v in mapping.items() if v}


def patterns(role: str) -> list[str]:
    return ALLOWLIST.get(role, []) + _OVERRIDES.get(role, [])


def allowed(role: str, host: str) -> bool:
    return any(fnmatch(host, pat) for pat in patterns(role))


def check(role: str, host: str) -> None:
    if not allowed(role, host):
        raise PermissionError(f"egress denied: {role} → {host} not allowlisted")


def demo() -> None:
    assert allowed("senior-dev", "pypi.org")
    assert not allowed("frontend", "api.openai.com")
    assert not allowed("security-analyst", "api.anthropic.com")  # empty = deny-all
    assert not allowed("unknown-role", "anything")               # default deny
    # user overlay widens a role, additive over the hardcoded floor
    set_overrides({"frontend": ["cdn.example.com"], "security": []})
    assert allowed("frontend", "cdn.example.com")                # added by user
    assert allowed("frontend", "registry.npmjs.org")             # hardcoded still holds
    assert not allowed("security", "cdn.example.com")            # empty override = no-op
    set_overrides({})                                            # reset for the rest
    try:
        check("frontend", "evil.example")
        raise AssertionError("should have denied")
    except PermissionError:
        pass
    print("egress.demo ok")


if __name__ == "__main__":
    demo()
