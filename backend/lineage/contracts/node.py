from pydantic import BaseModel, Field


class NodeSpec(BaseModel):
    id: str
    role: str
    intent: str
    irreversible: bool = False
    reads: list[str] = Field(default_factory=list)   # globs — drives §18.1 co-scheduling
    writes: list[str] = Field(default_factory=list)
    acceptance: list[str] = Field(default_factory=list)  # verifier ids that must pass
    budget_usd: float = 0.0
    constraints: list[str] = Field(default_factory=list)  # injected pitfall ids
    depends_on: list[str] = Field(default_factory=list)
    # runtime assignment
    transport: str = "api"
    agent: str = ""


class Dag(BaseModel):
    nodes: list[NodeSpec] = Field(default_factory=list)

    def by_id(self, node_id: str) -> NodeSpec | None:
        return next((n for n in self.nodes if n.id == node_id), None)
