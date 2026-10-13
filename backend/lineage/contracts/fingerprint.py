from pydantic import BaseModel, Field


class Scale(BaseModel):
    model_config = {"extra": "allow"}  # scale shape varies by domain
    skus: int | None = None
    traffic: str | None = None


class SpecFingerprint(BaseModel):
    """The highest-leverage human input (§3 step 2). Editable, not hidden
    metadata. `extra=allow` so a free-thinking model can attach domain-specific
    fields (e.g. `realtime`, `offline_first`) without them being silently
    dropped — the shape is dynamic, only `domain` is normalised to a join key."""

    model_config = {"extra": "allow"}

    domain: str
    subdomain: str = ""
    scale: dict = Field(default_factory=dict)
    stack_hints: list[str] = Field(default_factory=list)
    payments: str | None = None
    auth: str = "none"
    multi_tenant: bool = False
    compliance: list[str] = Field(default_factory=list)
    region: str = ""
