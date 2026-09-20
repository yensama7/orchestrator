"""Role → researched profile (§3). The central agent researches a role at
creation time (on a lightweight local model, or any configured model — see
_pick) so its skills + resources can be injected into every node prompt that
uses the role. Works for new and existing roles — re-running just refreshes the
profile. Falls back to an empty profile when no model is reachable, so role
creation never blocks on it."""

from __future__ import annotations

import json

from ..transports import Prompt
from ._pick import light_transport

_SYS = (
    "You are the orchestrator researching an agent role for a software build "
    "system. Given a role name and description, return ONLY JSON with keys: "
    "skills (array of short capability strings the role must have) and resources "
    "(array of concrete tools, libraries, docs, or APIs it should use). Be "
    "specific and concise: 4-8 skills, 3-6 resources."
)


async def research_role(name: str, description: str = "") -> dict:
    try:
        comp = await (await light_transport()).complete(
            Prompt(system=_SYS, user=f"role: {name}\ndescription: {description}"))
        data = json.loads(_json_slice(comp.text))
        return {"skills": [str(s) for s in data.get("skills", [])][:8],
                "resources": [str(r) for r in data.get("resources", [])][:6]}
    except Exception:
        return {"skills": [], "resources": []}  # CLI missing → re-run research later


def _json_slice(text: str) -> str:
    i, j = text.find("{"), text.rfind("}")
    return text[i:j + 1] if i != -1 and j > i else text


def demo() -> None:
    assert _json_slice('noise {"skills":[]} tail') == '{"skills":[]}'
    print("research.demo ok")


if __name__ == "__main__":
    demo()
