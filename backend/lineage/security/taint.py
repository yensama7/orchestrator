"""Taint tracking (§11). Web content, dependency files and tool output are
untrusted; the tag propagates through derived artifacts. An agent consuming
tainted input runs with writes and network disabled for that call."""

from __future__ import annotations

from dataclasses import dataclass, field

# §11: dependency and lock files are untrusted — they are machine-written from
# public registries and are a real injection vector (a crafted package name or
# lockfile comment carrying "ignore previous instructions…"). Imported project
# source the user chose to bring is trusted; these are not.
_UNTRUSTED_FILES = {
    "package.json", "package-lock.json", "npm-shrinkwrap.json", "yarn.lock",
    "pnpm-lock.yaml", "requirements.txt", "poetry.lock", "pipfile.lock",
    "go.mod", "go.sum", "cargo.lock", "gemfile.lock", "composer.lock",
    "packages.lock.json", "podfile.lock",
}


def is_untrusted_source(label: str) -> bool:
    """True if a workspace file label (``folder/name``) is a dependency/lock file."""
    return label.strip().lower().rsplit("/", 1)[-1] in _UNTRUSTED_FILES


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
    # dependency/lock files are classified untrusted; ordinary source is not.
    assert is_untrusted_source("app/package-lock.json")
    assert is_untrusted_source("go.sum") and not is_untrusted_source("src/main.go")
    print("taint.demo ok")


if __name__ == "__main__":
    demo()
