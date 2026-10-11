"""Security as adversary, not as feature (phases.md §P4c).

A red-team fixture plants a secret and asserts it cannot reach any channel: the
model-output path that becomes a proposal/artifact, the episodic payload the DB /
SSE stream / console / logs all read, and the outbound egress gate. CI runs this
on every commit (.github/workflows/ci.yml) — a leak on any path fails the build,
so defense-in-depth is proven, not claimed.

DB-free on purpose (same discipline as test_core): it exercises the redactor and
the egress scanner directly, which are the exact functions the live chokepoints
call (store.append_episodic → redact_obj, orchestrator._body → redact,
scan.scan at egress). Run: python -m tests.test_security  or  pytest.
"""

import asyncio

from lineage.security import redact, scan

# canonical planted secrets — one per known shape.
PLANTED = {
    "aws": "AKIAIOSFODNN7EXAMPLE",
    "openai": "sk-abcdefghijklmnop0123456789",
    "github": "ghp_" + "a" * 36,
    "slack": "xoxb-0123456789-abcdefghij",
}


def _leaks(blob: str) -> list[str]:
    return [s for s in PLANTED.values() if s in blob]


def test_model_output_channel_scrubbed():
    # orchestrator._body redacts raw model text before it becomes a proposal, so
    # a secret never reaches choice / produced files / semantic memory.
    for s in PLANTED.values():
        out = redact.redact(f'{{"choice":"use key {s}","confidence":0.9}}')
        assert s not in out and "redacted" in out


def test_episodic_channel_scrubbed():
    # store.append_episodic deep-redacts the payload → nothing reaches the DB,
    # the SSE stream, the console, or a log tailing episodic_events.
    payload = {"node": "deploy", "text": f"env {PLANTED['aws']}",
               "nested": {"token": PLANTED['github'], "list": [PLANTED['slack']]},
               "spent": 1.25}
    scrubbed = redact.redact_obj(payload)
    assert not _leaks(str(scrubbed)), scrubbed
    assert scrubbed["spent"] == 1.25            # non-secret values survive


def test_egress_gate_fails_closed():
    # the outbound scanner detects every planted shape → egress denied. Shares
    # PATTERNS with the redactor, so it can't miss what redaction catches.
    for s in PLANTED.values():
        assert asyncio.run(scan.scan(f"outbound payload {s}")), s


def test_clean_traffic_passes():
    assert redact.redact("just a normal message") == "just a normal message"
    assert redact.redact_obj({"text": "nothing secret", "n": 3}) == {"text": "nothing secret", "n": 3}
    assert asyncio.run(scan.scan("nothing secret here")) == []


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_"):
            _fn()
    print("all security checks ok")
