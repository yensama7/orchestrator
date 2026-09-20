from pydantic import BaseModel


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0


class Cost(BaseModel):
    """Metered (api) transport spend, in USD."""

    usd: float = 0.0


class Quota(BaseModel):
    """Subscription transport accounting — quota units, not dollars (§4)."""

    limit: int
    used: int
    resets_at: str  # ISO8601
    unit: str = "requests"


class Capacity(BaseModel):
    limit: int
    used: int = 0
    resets_at: str | None = None
    unit: str = "requests"
