"""Independent evidence review plus deterministic checks that models cannot waive."""
import re
from ..core.config import settings
from ..schemas.agents import ReviewIssue, ReviewReport
from ..schemas.domain import Card, ExtractionCandidates, TranscriptSegment, RelationCandidate
from .relation_rules import extract_relations, relation_supported
from .common import normalize, stable_id
from .llm import structured, role_config
from .extractor import PRONOUNS

def targets(cards: list[Card], candidates: ExtractionCandidates) -> dict[str, dict]:
    """Give every candidate an unambiguous content-bound reference for review messages."""
    result = {c.id: {"kind": "card", "value": c.model_dump(), "evidence": c.source_segment_ids, "cards": [c.id]} for c in cards}
    for kind, items in [("entity", candidates.entities), ("relation", candidates.relations)]:
        for i, item in enumerate(items):
            tid = stable_id("review-target", kind, i, item.model_dump())
            result[tid] = {"kind": kind, "value": item.model_dump(), "evidence": item.evidence_segment_ids, "cards": item.source_card_ids}
    return result

def rule_review(cards: list[Card], segments: list[TranscriptSegment], candidates: ExtractionCandidates) -> ReviewReport:
    """Flag unsupported surfaces and local negation; pending facts are never auto-promoted."""
    source = {s.id: s.text for s in segments}
    source_rules = extract_relations(cards,segments)
    issues = []
    for tid, item in targets(cards, candidates).items():
        value, kind = item["value"], item["kind"]
        text = " ".join(source[s] for s in item["evidence"])
        if kind=='card' and normalize(value['content']) in normalize(text):
            text=value['content']
        reason = None
        if kind == "entity" and value["name"] not in PRONOUNS and normalize(value["name"]) not in normalize(text):
            reason = "实体名称未在其引用原文中出现，需要重新核对候选与证据。"
        if kind == 'relation' and not relation_supported(RelationCandidate.model_validate(value),segments,source_rules):
            reason = '关系缺少明确同句证据、存在否定/推测，或指代与方向尚不确定。'
        if kind == "card" and value["status"] == "active" and re.search(r"不是|并未|不确定", text) and not re.search(r"不是|并未|不确定", value["content"]):
            reason = "卡片遗漏了原文的否定或不确定限定。"
        if reason:
            issues.append(ReviewIssue(target_id=tid, target_type=kind, verdict="uncertain" if value["confidence"] < settings.confidence_threshold else "revise", reason=reason, confidence=0.9, evidence_segment_ids=item["evidence"], source_card_ids=item["cards"]))
    return ReviewReport(issues=issues)

def review(cards: list[Card], segments: list[TranscriptSegment], candidates: ExtractionCandidates) -> ReviewReport:
    """Independently review evidence, validate model references and keep deterministic vetoes."""
    known = targets(cards, candidates)
    rules = rule_review(cards, segments, candidates)
    if role_config("reviewer")["provider"] == "demo":
        return rules
    report = structured("review", {"segments": [s.model_dump() for s in segments], "targets": known}, ReviewReport)
    for issue in report.issues:
        target = known.get(issue.target_id)
        if target is None or issue.target_type != target["kind"]:
            raise ValueError("审核 Agent 引用了不存在或类型不匹配的目标")
        if not issue.source_card_ids or not set(issue.source_card_ids) <= set(target["cards"]) or not set(issue.evidence_segment_ids) <= set(target["evidence"]):
            raise ValueError("审核 Agent 引用了目标以外的证据")
    issues = {issue.target_id: issue for issue in report.issues}
    for issue in rules.issues:
        issues[issue.target_id] = issue
    return ReviewReport(issues=list(issues.values()))

def quarantine(cards: list[Card], candidates: ExtractionCandidates, report: ReviewReport) -> None:
    """Lower unresolved confidence without discarding evidence or the decision audit."""
    known = targets(cards, candidates)
    cutoff = min(0.49, settings.confidence_threshold / 2)
    affected_cards = set()
    for issue in report.issues:
        item = known[issue.target_id]
        if item["kind"] == "card":
            affected_cards.update(issue.source_card_ids)
            continue
        pool = candidates.entities if item["kind"] == "entity" else candidates.relations
        for candidate in pool:
            if candidate.model_dump() == item["value"]:
                candidate.confidence = min(candidate.confidence, cutoff)
    for card in cards:
        if card.id in affected_cards:
            card.card_type, card.status, card.confidence = "uncertain", "pending", min(card.confidence, cutoff)
