"""Evidence-preserving summarization with an explicit deterministic demo provider."""
from ..core.config import settings
from ..schemas.domain import TranscriptSegment, SummaryCandidates, CardCandidate, Card
from .common import stable_id
from .llm import structured, role_config
from .chinese import simplified
import re

def summarize(segments: list[TranscriptSegment], sid: str, created_at: str, feedback: dict | None = None) -> list[Card]:
    """Return validated cards; reject unknown evidence and empty source coverage."""
    if role_config("summary")["provider"] == "demo":
        pieces=[(s,part.strip()) for s in segments for part in re.split(r'[，,。；;！!？?\n]+',s.text) if part.strip()]
        candidates = SummaryCandidates(cards=[CardCandidate(type="uncertain" if any(w in text for w in ["可能", "不确定", "待确认"]) else "todo" if any(w in text for w in ["需要", "待办", "计划", "明天"]) else "conclusion" if any(w in text for w in ["因此", "结论", "导致", "造成"]) else "topic", title=text[:28], content=text, evidence_segment_ids=[s.id], source_card_ids=[], confidence=0.9) for s,text in pieces])
    else:
        candidates = structured("summary", {"segments": [s.model_dump() for s in segments], "review_feedback": feedback}, SummaryCandidates)
    valid = {s.id for s in segments}
    cards = []
    for c in candidates.cards:
        c.title, c.content = simplified(c.title), simplified(c.content)
        if not set(c.evidence_segment_ids) <= valid or c.source_card_ids:
            raise ValueError("摘要引用了不存在的段落或提前编造卡片 ID")
        pending = c.confidence < settings.confidence_threshold or c.type == "uncertain"
        cards.append(Card(id=stable_id(sid, "card", c.type, c.content, sorted(c.evidence_segment_ids)), session_id=sid, card_type="uncertain" if pending else c.type, title=c.title, content=c.content, source_segment_ids=c.evidence_segment_ids, confidence=c.confidence, status="pending" if pending else "active", created_at=created_at))
    return list({c.id: c for c in cards}.values())
