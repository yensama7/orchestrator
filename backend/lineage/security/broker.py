"""Capability broker (§11). Agents never hold credentials — they request a
short-lived, scoped, single-purpose token; every issuance is audited."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field


@dataclass
class Token:
    value: str
    scope: str
    expires_at: float

    def valid(self, scope: str) -> bool:
        return self.scope == scope and time.time() < self.expires_at


@dataclass
class Broker:
    audit: list[dict] = field(default_factory=list)
    _live: dict[str, Token] = field(default_factory=dict)

    def issue(self, agent: str, scope: str, ttl: float = 60.0) -> Token:
        tok = Token(secrets.token_urlsafe(16), scope, time.time() + ttl)
        self._live[tok.value] = tok
        self.audit.append({"agent": agent, "scope": scope, "at": time.time(), "action": "issue"})
        return tok

    def check(self, token_value: str, scope: str) -> bool:
        tok = self._live.get(token_value)
        ok = bool(tok and tok.valid(scope))
        self.audit.append({"token": token_value[:6], "scope": scope, "ok": ok, "action": "check"})
        return ok

    def revoke(self, token_value: str) -> None:
        self._live.pop(token_value, None)


def demo() -> None:
    b = Broker()
    tok = b.issue("dev-a", "db:read", ttl=5)
    assert b.check(tok.value, "db:read")
    assert not b.check(tok.value, "db:write")     # wrong scope
    assert not b.check("forged", "db:read")       # unknown token
    b.revoke(tok.value)
    assert not b.check(tok.value, "db:read")
    assert any(e["action"] == "issue" for e in b.audit)
    print("broker.demo ok")


if __name__ == "__main__":
    demo()
