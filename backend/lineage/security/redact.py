"""Defense-in-depth secret redaction (phases.md §P4b).

A secret must be scrubbed *before* it can reach a log line — not only at the
egress boundary (the pre-P4 state: scan.py ran at egress alone, so a key could
sit in the DB, the SSE stream, and the UI long before anything checked). One
redactor, applied at every channel chokepoint:

* model output  → orchestrator._body (so a leaked key never enters a proposal,
  an artifact, or semantic memory),
* episodic log  → memory.store.append_episodic (one edit covering DB + the SSE
  stream it feeds + the console + any log that tails it),
* egress        → scan.py stays the outbound gate and shares these PATTERNS, so
  detection and redaction can never drift apart.
"""

from __future__ import annotations

import re

# (name, pattern) — the single source of truth for both redaction here and the
# egress scanner (scan.py imports PATTERNS). Add a secret shape in one place.
PATTERNS: list[tuple[str, "re.Pattern[str]"]] = [
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("openai-key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("github-pat", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----")),
    ("slack-token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
]


def redact(text: str) -> str:
    """Replace every known secret shape with a labelled placeholder. The marker
    carries no quotes/backslashes, so redacting raw JSON text stays valid JSON."""
    if not isinstance(text, str) or not text:
        return text
    for name, pat in PATTERNS:
        text = pat.sub(f"«redacted:{name}»", text)
    return text


def redact_obj(obj):
    """Deep-redact every string in a JSON-shaped value (an episodic payload).
    Non-strings (spend floats, counts) pass through untouched."""
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, dict):
        return {k: redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(v) for v in obj]
    return obj


def demo() -> None:
    s = "key AKIAIOSFODNN7EXAMPLE and sk-abcdefghij0123456789xyz done"
    r = redact(s)
    assert "AKIA" not in r and "sk-abcdefghij" not in r and "redacted" in r
    assert redact("nothing here") == "nothing here"          # clean text untouched
    o = redact_obj({"text": "tok ghp_" + "a" * 36, "n": 5, "l": ["xoxb-0123456789"]})
    assert "ghp_" not in o["text"] and o["n"] == 5 and "xoxb-" not in o["l"][0]
    print("redact.demo ok")


if __name__ == "__main__":
    demo()
