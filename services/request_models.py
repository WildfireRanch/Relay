# services/request_models.py
# Purpose: Unified request/response models for /ask. Accepts both `question` and `query`
#          and exposes a derived `normalized_question`. Adds a stable response shape.

from typing import List, Optional
from uuid import uuid4

try:
    # Prefer Pydantic v1 import if available (most FastAPI installs)
    from pydantic import BaseModel, Field, root_validator
except Exception:  # Pydantic v2 fallback via compatibility shim
    from pydantic.v1 import BaseModel, Field, root_validator  # type: ignore


class GroundingRef(BaseModel):
    source: str = Field(..., description="Human-friendly source label or doc title")
    path: Optional[str] = Field(None, description="Repo/file path or URL")
    score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Normalized relevance score (0..1)")


class AskRequest(BaseModel):
    # Accept both; we normalize them.
    question: Optional[str] = Field(None, description="Preferred field for the user's question")
    query: Optional[str] = Field(None, description="Legacy/alternate field accepted for compatibility")

    # Optional knobs you may already support
    topics: List[str] = Field(default_factory=list)
    files: List[str] = Field(default_factory=list)
    reflect: bool = False

    # Derived; do not set directly
    normalized_question: str = Field("", description="Derived from question/query")

    @root_validator(pre=True)
    def _normalize(cls, values):
        q = (values.get("question") or values.get("query") or "").strip()
        if not q:
            raise ValueError("Either 'question' or 'query' is required and must be a non-empty string.")
        values["normalized_question"] = q

        # Normalize optional lists/bools if missing
        if values.get("topics") is None:
            values["topics"] = []
        if values.get("files") is None:
            values["files"] = []
        if values.get("reflect") is None:
            values["reflect"] = False

        return values


class AskResponse(BaseModel):
    # When grounded: `answer` is a synthesized string, `grounding` has attributions, `reason` is None.
    # When not grounded: `answer` is None, `grounding` is empty, `reason` explains why.
    answer: Optional[str] = None
    grounding: List[GroundingRef] = Field(default_factory=list)
    reason: Optional[str] = None
    corr_id: str = Field(..., description="Per-request correlation ID for logs/traces")

    @classmethod
    def new_corr_id(cls) -> str:
        return str(uuid4())


def make_no_answer(reason: str, corr_id: Optional[str] = None) -> AskResponse:
    return AskResponse(answer=None, grounding=[], reason=reason, corr_id=corr_id or AskResponse.new_corr_id())
