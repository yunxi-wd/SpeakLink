"""Strict domain schemas shared by API validation, persistence and model outputs."""
from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

def now() -> str:
    """Return an ISO UTC timestamp suitable for sorting and persistence."""
    return datetime.now(timezone.utc).isoformat()

EntityType = Literal["PERSON", "ORG", "CONCEPT", "EVENT", "TIME", "LOCATION", "OTHER"]
RelationType = Literal["属于", "导致", "参与", "先后", "定义", "例证", "对比", "依赖", "其他"]
Status = Literal["active", "pending", "deleted"]

class Schema(BaseModel):
    """Reject unknown fields to catch contract drift immediately."""
    model_config = ConfigDict(extra="forbid")

class Session(Schema):
    """One recording and its durable processing state."""
    id: str
    title: str
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)
    audio_path: str | None = None
    duration_ms: int = 0
    status: str = "created"
    language: str = "zh"
    metadata: dict[str, Any] = Field(default_factory=dict)

class TranscriptSegment(Schema):
    """Finalized timestamped text retaining the unmodified ASR source."""
    id: str
    session_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=10000)
    raw_text: str = ""
    speaker: str | None = None
    confidence: float = Field(default=1, ge=0, le=1)
    is_final: bool = True

    @model_validator(mode="after")
    def valid_time(self) -> "TranscriptSegment":
        """Reject timestamps ending before their start."""
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms must be >= start_ms")
        return self

class Card(Schema):
    """Evidence-backed card; graph links are always derived server-side."""
    id: str
    session_id: str
    card_type: Literal["topic", "conclusion", "todo", "uncertain"]
    title: str
    content: str
    source_segment_ids: list[str]
    entity_ids: list[str] = Field(default_factory=list)
    relation_ids: list[str] = Field(default_factory=list)
    cluster_id: str | None = None
    vector_id: str | None = None
    confidence: float = Field(ge=0, le=1)
    status: Status = "active"
    manual_edited: bool = False
    created_at: str = Field(default_factory=now)

class Entity(Schema):
    """Canonical entity or pending candidate, with provenance links."""
    id: str
    session_id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    type: EntityType = "CONCEPT"
    canonical_id: str
    embedding_id: str | None = None
    cluster_id: str | None = None
    confidence: float = Field(ge=0, le=1)
    status: Status = "active"
    manual_edited: bool = False
    source_card_ids: list[str]
    source_segment_ids: list[str]

class Relation(Schema):
    """Directed evidence-backed relation between entity IDs."""
    id: str
    session_id: str
    head_entity_id: str
    predicate: str | None = None
    tail_entity_id: str
    type: RelationType
    evidence_card_ids: list[str]
    source_segment_ids: list[str]
    confidence: float = Field(ge=0, le=1)
    direction: Literal["directed", "undirected"] = "directed"
    status: Status = "active"
    manual_edited: bool = False

class TopicCluster(Schema):
    """Explainable topic grouping with user-editable label."""
    id: str
    session_id: str
    name: str
    card_ids: list[str]
    entity_ids: list[str]
    color: str
    confidence: float
    reason: str = ""

class Correction(Schema):
    """Replayable operation storing before/after snapshots and rollback state."""
    id: str
    session_id: str
    target_type: Literal["entity", "relation", "card", "cluster"]
    target_id: str
    action: Literal["merge", "split", "delete", "update"]
    before: dict[str, Any]
    after: dict[str, Any]
    operator: str = "local-user"
    created_at: str = Field(default_factory=now)
    active: bool = True

class QueryLog(Schema):
    """Auditable query and returned graph paths."""
    id: str
    session_id: str
    query: str
    retrieved_card_ids: list[str]
    graph_path: list[list[str]]
    created_at: str = Field(default_factory=now)

class Export(Schema):
    """Export artifact audit row."""
    id: str
    session_id: str
    format: Literal["json", "graphml", "markdown"]
    path: str
    created_at: str = Field(default_factory=now)

class Snapshot(Schema):
    """Atomic read model: cards and graph share one revision."""
    session: Session
    segments: list[TranscriptSegment] = Field(default_factory=list)
    cards: list[Card] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    clusters: list[TopicCluster] = Field(default_factory=list)
    revision: int = 0

class Evidence(Schema):
    """Every model candidate carries explicit confidence and evidence."""
    confidence: float = Field(ge=0, le=1)
    evidence_segment_ids: list[str] = Field(min_length=1)
    source_card_ids: list[str]

class CardCandidate(Evidence):
    """Untrusted structured summary candidate; card IDs are assigned by server."""
    type: Literal["topic", "conclusion", "todo", "uncertain"]
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=10000)

class SummaryCandidates(Schema):
    """Typed model response for stage one."""
    cards: list[CardCandidate] = Field(min_length=1, max_length=500)

class EntityCandidate(Evidence):
    """Raw name plus explicitly supported aliases, before convergence."""
    name: str = Field(min_length=1, max_length=120)
    aliases: list[str] = Field(default_factory=list)
    type: EntityType

class RelationCandidate(Evidence):
    """Raw endpoint names, normalized only after evidence checks."""
    head: str
    predicate: str | None = None
    tail: str
    type: str

class ExtractionCandidates(Schema):
    """Typed stage-two model response."""
    entities: list[EntityCandidate] = Field(max_length=2000)
    relations: list[RelationCandidate] = Field(max_length=4000)
