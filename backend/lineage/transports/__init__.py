"""Transport factory — a (model, transport) pair becomes one adapter."""

from __future__ import annotations

from .api import ApiTransport
from .base import Budget, Capacity, Completion, Prompt, Transport, Usage
from .local import LocalTransport
from .subscription import CLIS, SubscriptionTransport


def build(model: str, transport: str, api_key: str | None = None) -> Transport:
    if transport == "local":
        return LocalTransport(model)
    if transport == "subscription":
        cli = CLIS.get("claude" if model.startswith("claude")
                       else "gemini" if model.startswith("gemini") else "codex")
        return SubscriptionTransport(cli)
    return ApiTransport(model, api_key=api_key)


__all__ = ["build", "Transport", "Prompt", "Budget", "Completion", "Usage",
           "Capacity", "ApiTransport", "LocalTransport", "SubscriptionTransport"]
