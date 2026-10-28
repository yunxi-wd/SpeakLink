"""Request and response schemas for all public JSON endpoints."""
from typing import Any, Literal
from pydantic import Field, field_validator
from .domain import Schema, Snapshot, Card, Relation, EntityType, RelationType

class TranscriptionProgress(Schema):
    """Observed ASR stage and audio coverage; percent is absent before duration is known."""
    stage: Literal['idle', 'loading_model', 'reading_audio', 'recognizing', 'saving', 'completed', 'failed'] = 'idle'
    message: str = '尚未开始转写'
    percent: int | None = Field(default=None, ge=0, le=100)
    processed_ms: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)
    segments_count: int = Field(default=0, ge=0)

class CreateSession(Schema):
    """Create an empty local recording."""
    title: str = Field(default="未命名速记", min_length=1, max_length=200)
    language: str = "zh"

class SegmentInput(Schema):
    """User-supplied timestamped transcript; IDs assigned by server."""
    text: str = Field(min_length=1, max_length=10000)
    start_ms: int = Field(default=0, ge=0)
    end_ms: int = Field(default=0, ge=0)
    speaker: str | None = None

class TranscriptInput(Schema):
    """Replace transcript only before processing to preserve correction references."""
    segments: list[SegmentInput] = Field(min_length=1, max_length=500)

class SearchRequest(Schema):
    """Natural-language retrieval bounded by a caller-selected result limit."""
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=8, ge=1, le=30)

class SearchResult(Schema):
    """Relevant cards and real graph paths (never generated answers)."""
    cards: list[Card]
    scores: list[float]
    paths: list[list[str]]
    relations: list[Relation]
    embedding_provider: str

class CorrectionInput(Schema):
    """Version-checked correction; operation payload validated by action handler."""
    session_id: str
    target_type: Literal["entity", "relation", "card", "cluster"]
    target_id: str
    action: Literal["merge", "split", "delete", "update"]
    payload: dict[str, Any] = Field(default_factory=dict)
    expected_revision: int
    operator: str = "local-user"

class EntityPatch(Schema):
    """Editable entity fields and concurrency revision."""
    expected_revision: int
    name: str | None = Field(default=None, min_length=1)
    type: EntityType | None = None
    status: Literal["active", "pending"] | None = None

class CardPatch(Schema):
    """Audited card text/type edits; source references and graph IDs are immutable."""
    expected_revision: int = Field(ge=0)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=10000)
    card_type: Literal['topic', 'conclusion', 'todo', 'uncertain'] | None = None

    @field_validator('title', 'content')
    @classmethod
    def nonblank(cls, value: str | None) -> str | None:
        """Reject whitespace-only edits while preserving paragraph formatting."""
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError('标题和正文不能只包含空白字符')
        return value

class RelationPatch(Schema):
    """Editable relation fields and concurrency revision."""
    expected_revision: int
    type: RelationType | None = None
    status: Literal["active", "pending"] | None = None

class Health(Schema):
    """Configuration readiness, not a promise that model weights are installed."""
    status: str
    llm_provider: str
    embedding_provider: str
    asr_installed: bool
    asr_model: str = ""
    asr_message: str = ""

class Graph(Schema):
    """Visible graph projection with pending candidates counted separately."""
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    pending_count: int
    revision: int
    groups: list[dict[str, Any]] = Field(default_factory=list)
    group_relations: list[dict[str, Any]] = Field(default_factory=list)
