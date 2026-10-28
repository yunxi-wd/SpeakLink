"""Typed agent messages, bounded review decisions and durable execution records."""
from typing import Any, Literal
from pydantic import Field
from .domain import Schema, Evidence, now

AgentRole = Literal["summary", "extractor", "reviewer", "coordinator"]
RunStatus = Literal["queued", "running", "completed", "failed", "conflicted", "interrupted"]

class ReviewIssue(Evidence):
    """Auditable decision about a specific candidate; no free-form hidden reasoning."""
    target_id: str
    target_type: Literal["card", "entity", "relation"]
    verdict: Literal["revise", "uncertain", "reject"]
    reason: str = Field(min_length=1, max_length=1000)

class ReviewReport(Schema):
    """Independent reviewer output; coordinator derives the next action from issues."""
    issues: list[ReviewIssue] = Field(max_length=6500)

class AgentRun(Schema):
    """Durable lifecycle of one request against a particular database revision."""
    id: str
    session_id: str
    status: RunStatus = "queued"
    base_revision: int
    result_revision: int | None = None
    fingerprint: str
    mode: Literal["demo", "model", "cached"]
    current_step: str = "queued"
    steps_completed: int = 0
    rounds: int = 0
    model_calls: int = 0
    cached: bool = False
    pending_count: int = 0
    error: str | None = None
    created_at: str = Field(default_factory=now)
    finished_at: str | None = None

class AgentEvent(Schema):
    """One role invocation with replayable output, provenance and timing."""
    id: str
    session_id: str
    run_id: str
    sequence: int
    role: AgentRole
    attempt: int
    provider: str
    model: str
    status: Literal["running", "completed", "failed"] = "running"
    input_digest: str
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    started_at: str = Field(default_factory=now)
    finished_at: str | None = None
    duration_ms: int = 0

class RunDetail(Schema):
    """Public execution timeline without provider URLs or credentials."""
    run: AgentRun
    events: list[AgentEvent]
