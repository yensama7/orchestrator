"""Subscription transport (§4, §20.3). Drives an official headless CLI
authenticated against the user's consumer subscription — never a browser
session, never reused cookies (that path violates provider terms and gets
accounts banned). Parses the CLI's structured output stream, not stdout text.

Accounting is in quota units, not dollars.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from .base import Budget, Capacity, Completion, Prompt, Transport, Usage


@dataclass
class CliSpec:
    """How to invoke and parse one CLI in non-interactive JSON-stream mode."""
    argv_template: list[str]      # e.g. ["claude", "-p", "{prompt}", "--output-format", "stream-json"]
    window_limit: int = 50        # requests per rate window

    def argv(self, prompt: str) -> list[str]:
        return [a.replace("{prompt}", prompt) for a in self.argv_template]


# Known CLIs (§4). Present + authed on the host to be usable; unavailable → the
# roster UI disables the subscription option with a reason.
CLIS = {
    "claude": CliSpec(["claude", "-p", "{prompt}", "--output-format", "stream-json"]),
    "codex": CliSpec(["codex", "exec", "--json", "{prompt}"]),
    "gemini": CliSpec(["gemini", "-p", "{prompt}", "--json"]),
}


class SubscriptionTransport(Transport):
    def __init__(self, cli: CliSpec, concurrency: int = 1):
        self.name = "subscription"
        self._cli = cli
        self._sem = asyncio.Semaphore(concurrency)  # hard rate limit, no burst
        self._used = 0

    async def complete(self, prompt: Prompt, *, schema=None, budget: Budget | None = None) -> Completion:
        async with self._sem:
            proc = await asyncio.create_subprocess_exec(
                *self._cli.argv(f"{prompt.stable}\n{prompt.system}\n{prompt.user}".strip()),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                env=_clean_env(),  # no inherited secrets
            )
            out, err = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"CLI exit {proc.returncode}: {err.decode()[:200]}")
            self._used += 1
            return _parse_stream(out.decode())

    def capacity(self) -> Capacity:
        return Capacity(limit=self._cli.window_limit, used=self._used, unit="requests")


def _parse_stream(raw: str) -> Completion:
    text_parts, usage = [], Usage()
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            block = json.loads(line)
        except json.JSONDecodeError:
            continue
        if block.get("type") in ("text", "assistant") and "text" in block:
            text_parts.append(block["text"])
        elif "delta" in block and "text" in block.get("delta", {}):
            text_parts.append(block["delta"]["text"])
        elif "result" in block:
            text_parts.append(str(block["result"]))
    return Completion("".join(text_parts), usage, raw={"lines": raw.count(chr(10))})


def _clean_env() -> dict:
    import os
    # keep PATH/HOME so the CLI finds its own OAuth token store; drop app secrets
    keep = ("PATH", "HOME", "USERPROFILE", "APPDATA", "XDG_CONFIG_HOME")
    return {k: v for k, v in os.environ.items() if k in keep}
