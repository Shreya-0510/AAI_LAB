from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

class TestPlan(BaseModel):
    strategy: Literal["llm_only", "hybrid"]
    selected_tests: list[str] = Field(default_factory=list)
    rationale: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_files: list[str] = Field(default_factory=list)

class ToolTrace(BaseModel):
    trace_id: str
    tool_name: str
    started_at: str
    duration_seconds: float
    status: str
    detail: str = ""
