"""Taint tracking (§11). Web content, dependency files and tool output are
untrusted; the tag propagates through derived artifacts. An agent consuming
tainted input runs with writes and network disabled for that call."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TaintSet:
    _tainted: set[str] = field(default_factory=set)

    def mark(self, artifact_id: str) -> None:
        self._tainted.add(artifact_id)

    def is_tainted(self, artifact_id: str) -> bool:
        return artifact_id in self._tainted

    def derive(self, new_id: str, from_ids: list[str]) -> None:
        """A derived artifact inherits taint if any input is tainted."""
        if any(self.is_tainted(i) for i in from_ids):
            self.mark(new_id)

    def call_policy(self, input_ids: list[str]) -> dict:
        """Capabilities for a call consuming these inputs."""
        tainted = any(self.is_tainted(i) for i in input_ids)
        return {"writes": not tainted, "network": not tainted, "tainted": tainted}


def demo() -> None:
    t = TaintSet()
    t.mark("web:page1")
    t.derive("summary", ["web:page1"])          # inherits taint
    t.derive("clean", ["local:notes"])          # stays clean
    assert t.is_tainted("summary") and not t.is_tainted("clean")
    assert t.call_policy(["summary"]) == {"writes": False, "network": False, "tainted": True}
    assert t.call_policy(["clean"])["writes"] is True
    print("taint.demo ok")


if __name__ == "__main__":
    demo()
