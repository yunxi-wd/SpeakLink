"""Rules-first candidate extraction followed by optional structured LLM review.

Demo grammar handles explicit short Chinese SVO clauses. This is a transparent
fallback for repeatable demonstrations, not general-purpose Chinese NER.
"""
import re
from collections import Counter
from .lexical import nouns, prose_candidates
from .relation_rules import extract_relations, canonical_label, relation_supported, PLACEHOLDER
from .chinese import simplified
from ..core.config import settings
from ..schemas.domain import Card, TranscriptSegment, EntityCandidate, RelationCandidate, ExtractionCandidates
from .llm import structured, role_config

VERBS = {"属于": "属于", "导致": "导致", "引起": "导致", "造成": "导致", "参与": "参与", "参加": "参与", "先于": "先后", "依赖": "依赖", "定义为": "定义", "例如": "例证", "对比": "对比"}
PRONOUNS = {"他", "她", "它", "他们", "她们", "这个项目", "那个方案", "该方案", "该项目"}

def entity_type(name: str) -> str:
    """Infer a conservative demo type from common surface forms."""
    if name in {"他", "她", "他们", "她们"} or re.match(r"^[张李王赵陈刘][\u4e00-\u9fff]{1,2}$", name):
        return "PERSON"
    if any(x in name for x in ["公司", "组织", "团队", "大学", "研究院"]):
        return "ORG"
    if name in {"北京", "上海", "深圳", "杭州"}:
        return "LOCATION"
    if re.fullmatch(r"\d{4}年|今天|明天|昨天", name):
        return "TIME"
    return "CONCEPT"

def preliminary(cards: list[Card]) -> ExtractionCandidates:
    """Collect noun/alias mentions only; sentence structure belongs to typed grammar."""
    entities = []
    frequencies = Counter(name for card in cards for name, _ in nouns(card.content))
    for card in cards:
        evidence = dict(confidence=card.confidence, evidence_segment_ids=card.source_segment_ids, source_card_ids=[card.id])
        for full, alias in re.findall(r"([\w\u4e00-\u9fff]{2,30})(?:简称|又称|也叫)([\w\u4e00-\u9fff]{1,30})", card.content):
            entities.append(EntityCandidate(name=full, aliases=[alias], type=entity_type(full), **evidence))
        mentions, _ = prose_candidates(card, frequencies)
        entities.extend(mentions)
    return ExtractionCandidates(entities=entities, relations=[])

def extract(cards: list[Card], segments: list[TranscriptSegment], feedback: dict | None = None) -> ExtractionCandidates:
    """Review rules/NER proposals with a model, then enforce local evidence references."""
    initial = preliminary(cards)
    contextual = extract_relations(cards, segments)
    # Legacy whole-clause SVO guesses are replaced, never unioned with grammar output.
    initial.relations = []
    # Prefer explicit grammatical endpoint spans over overlapping tokenizer pieces.
    # This is mention-boundary cleanup, not global alias merging.
    required = {name for r in initial.relations for name in (r.head, r.tail)}
    initial.entities = [e for e in initial.entities if e.name in required or not any(
        e.name != full.name and e.name in full.name
        and set(e.evidence_segment_ids) <= set(full.evidence_segment_ids)
        for full in contextual.entities)]
    for entity in initial.entities:
        kinds = {e.type for e in contextual.entities if e.name == entity.name}
        if len(kinds) == 1:
            entity.type = next(iter(kinds))
    initial.entities.extend(contextual.entities)
    initial.relations.extend(contextual.relations)
    if role_config("extractor")["provider"] == "demo":
        output = initial
    else:
        from .relation_examples import select_examples
        output = structured("entity_relation", {"cards": [c.model_dump() for c in cards], "segments": [s.model_dump() for s in segments], "preliminary": initial.model_dump(), "examples":select_examples(' '.join(s.text for s in segments)), "review_feedback": feedback}, ExtractionCandidates)
        # A model supplements auditable explicit facts; it cannot silently erase
        # high-confidence grammar facts by omitting them from its response.
        output.entities.extend(contextual.entities)
        known={(r.head,canonical_label(r.predicate,r.type),r.tail,tuple(r.evidence_segment_ids)) for r in output.relations}
        output.relations.extend(r for r in contextual.relations if (r.head,r.predicate,r.tail,tuple(r.evidence_segment_ids)) not in known)
    if feedback and role_config("extractor")["provider"] == "demo":
        # Demo demonstrates real feedback handling without claiming model reasoning.
        for issue in feedback["issues"]:
            target = feedback["targets"].get(issue["target_id"])
            if target and target["kind"] in {"entity", "relation"}:
                pool = output.entities if target["kind"] == "entity" else output.relations
                original = target["value"]
                for candidate in pool:
                    if candidate.model_dump() == original:
                        candidate.confidence = min(candidate.confidence, 0.49, settings.confidence_threshold / 2)
    segment_ids = {s.id for s in segments}
    for entity in output.entities:
        entity.name = simplified(entity.name)
        entity.aliases = [simplified(alias) for alias in entity.aliases]
    for relation in output.relations:
        relation.head, relation.tail = simplified(relation.head), simplified(relation.tail)
        relation.predicate = canonical_label(relation.predicate,relation.type) or None
        if not relation_supported(relation,segments,contextual):
            relation.confidence = min(relation.confidence,.49)
    # UI placeholder names can never become real facts, even if a model proposes them.
    output.entities = [e for e in output.entities if not PLACEHOLDER.fullmatch(e.name.strip())]
    allowed = {e.name for e in output.entities}
    output.relations = [r for r in output.relations if r.head in allowed and r.tail in allowed and r.predicate]
    card_map = {c.id: c for c in cards}
    for candidate in [*output.entities, *output.relations]:
        if not candidate.source_card_ids or not set(candidate.source_card_ids) <= card_map.keys() or not set(candidate.evidence_segment_ids) <= segment_ids:
            raise ValueError("模型候选引用了不存在的卡片或原文")
        linked = {sid for cid in candidate.source_card_ids for sid in card_map[cid].source_segment_ids}
        if not set(candidate.evidence_segment_ids) <= linked:
            raise ValueError("候选证据与来源卡片不一致")
    return output

