from enum import Enum

from pydantic import BaseModel, Field


class Intent(str, Enum):
    """Closed set. Structural defence against prompt injection: injected prose
    has no intent to become."""

    PROPOSE = "propose"
    CRITIQUE = "critique"
    ACCEPT = "accept"
    BLOCK = "block"
    ASK = "ask"


class Envelope(BaseModel):
    model_config = {"extra": "forbid"}  # unknown fields reject the message

    from_role: str
    to_role: str
    intent: Intent
    task_id: str
    artifact_refs: list[str] = Field(default_factory=list)  # sha256 CAS hashes
    claims: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    tainted: bool = False
    notes: str = ""  # advisory; nothing downstream may branch on this
