"""schema.py – Pydantic models for the Dependency Exit Capsule."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class DependencyDetails(BaseModel):
    name: str
    pinned_version: Optional[str] = None
    latest_version: Optional[str] = None
    source_file: str  # e.g. "requirements.txt"


class RiskIndicator(BaseModel):
    type: str       # e.g. "no_recent_release", "deprecated", "low_downloads"
    evidence: str   # human-readable description
    source: str     # e.g. "PyPI", "GitHub"


class UsageLocation(BaseModel):
    file: str
    line: int
    snippet: str


class AIGenerated(BaseModel):
    """Content produced by Gemma 4 – never mixed with observed evidence."""
    proposed_replacement: Optional[str] = None
    rationale: Optional[str] = None
    migration_steps: List[str] = Field(default_factory=list)
    suggested_tests: List[str] = Field(default_factory=list)
    confidence: Optional[float] = None   # 0.0 – 1.0
    model: str = "gemma-4-26b-a4b-it"
    model_version: str = "gemma-4-26b-a4b-it"


class Observed(BaseModel):
    """Evidence gathered by actually running tests – never mixed with AI output."""
    baseline_test_result: Optional[str] = None    # "pass" | "fail" | "error"
    replacement_test_result: Optional[str] = None
    diff_summary: Optional[str] = None
    commands_run: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Top-level models
# ---------------------------------------------------------------------------

class DependencyEntry(BaseModel):
    details: DependencyDetails
    risk_indicators: List[RiskIndicator] = Field(default_factory=list)
    usage_locations: List[UsageLocation] = Field(default_factory=list)
    ai_generated: AIGenerated = Field(default_factory=AIGenerated)
    observed: Observed = Field(default_factory=Observed)
    compatibility_gaps: List[str] = Field(default_factory=list)
    open_concerns: List[str] = Field(default_factory=list)
    executed: bool = False


class Capsule(BaseModel):
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    target_repo: str
    dependencies: List[DependencyEntry] = Field(default_factory=list)
    global_limitations: List[str] = Field(default_factory=list)
