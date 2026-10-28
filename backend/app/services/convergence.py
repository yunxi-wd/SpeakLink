"""Deterministic candidate convergence, conservative coreference and provenance.

Ambiguous pronouns, aliases without literal evidence and weak assertions remain
pending. Accepted facts alone contribute to the visible graph.
"""
from ..core.config import settings
from ..schemas.domain import Snapshot, ExtractionCandidates, Entity, Relation, TopicCluster
from .common import normalize, stable_id
from .extractor import PRONOUNS, VERBS

def converge(snap: Snapshot, candidates: ExtractionCandidates) -> Snapshot:
    """Produce canonical entities/relations from candidates, retaining uncertain facts."""
    sid = snap.session.id
    segment_index = {s.id: i for i, s in enumerate(snap.segments)}
    segments = {s.id: s for s in snap.segments}
    card_map = {c.id: c for c in snap.cards}
    by_key: dict[tuple[str, str], Entity] = {}
    lookup: dict[tuple[str, str], set[str]] = {}
    raw_candidates = sorted(candidates.entities, key=lambda c: (min(segment_index[x] for x in c.evidence_segment_ids), c.name in PRONOUNS, not bool(c.aliases), c.name))
    for c in raw_candidates:
        position = min(segment_index[x] for x in c.evidence_segment_ids)
        name, status = c.name, "active"
        evidence_text = " ".join(segments[x].text for x in c.evidence_segment_ids)
        aliases = [a for a in c.aliases if normalize(a) in normalize(evidence_text)]
        if c.confidence < settings.confidence_threshold or any(card_map[x].status != "active" for x in c.source_card_ids):
            status = "pending"
        if name in PRONOUNS:
            desired = "PERSON" if name in {"他", "她", "他们", "她们"} else "CONCEPT"
            previous = [e for e in by_key.values() if e.type == desired and e.status == "active" and any(0 < position - segment_index[s] <= 2 for s in e.source_segment_ids)]
            if name in {"这个项目", "该项目"}:
                previous = [e for e in previous if "项目" in e.name]
            if name in {"那个方案", "该方案"}:
                previous = [e for e in previous if "方案" in e.name]
            previous = list({e.id: e for e in previous}.values())
            if len(previous) == 1 and name not in {"他们", "她们"}:
                name = previous[0].name
                # Pronouns must not become global aliases shared by later speakers.
            else:
                status = "pending"
        elif normalize(name) not in normalize(evidence_text):
            status = "pending"
        # Type and status are part of the key: a weak mention cannot contaminate a strong fact.
        key = (normalize(name), c.type + ":" + status)
        possible = [e for e in by_key.values() if e.type == c.type and e.status == status and (normalize(name) in {normalize(e.name), *map(normalize, e.aliases)} or normalize(e.name) in set(map(normalize, aliases)))]
        entity = possible[0] if len(possible) == 1 else by_key.get(key)
        if entity is None:
            eid = stable_id(sid, "entity", *key)
            entity = Entity(id=eid, canonical_id=eid, session_id=sid, name=name, aliases=aliases, type=c.type, confidence=c.confidence, status=status, source_card_ids=[], source_segment_ids=[])
            by_key[key] = entity
        entity.source_card_ids = sorted(set(entity.source_card_ids + c.source_card_ids))
        entity.source_segment_ids = sorted(set(entity.source_segment_ids + c.evidence_segment_ids))
        entity.aliases = sorted(set(entity.aliases + aliases + ([c.name] if c.name != name and c.name not in PRONOUNS else [])))
        entity.confidence = max(entity.confidence, c.confidence)
        for segment in c.evidence_segment_ids:
            lookup.setdefault((normalize(c.name), segment),set()).add(entity.id)
    snap.entities = sorted({e.id: e for e in by_key.values()}.values(), key=lambda e: e.id)
    entity_map = {e.id: e for e in snap.entities}
    relation_map: dict[str, Relation] = {}
    for c in candidates.relations:
        heads = set().union(*(lookup.get((normalize(c.head),s),set()) for s in c.evidence_segment_ids))
        tails = set().union(*(lookup.get((normalize(c.tail),s),set()) for s in c.evidence_segment_ids))
        # A weak occurrence must never replace an already established entity in
        # the same evidence segment (e.g. positive fact followed by a negation).
        heads = {eid for eid in heads if entity_map[eid].status=='active'} or heads
        tails = {eid for eid in tails if entity_map[eid].status=='active'} or tails
        if len(heads) != 1 or len(tails) != 1:
            raise ValueError("关系端点必须在相同证据段落中有唯一实体候选")
        head, tail = next(iter(heads)), next(iter(tails))
        rel_type = VERBS.get(c.type, c.type)
        if rel_type not in {"属于", "导致", "参与", "先后", "定义", "例证", "对比", "依赖", "其他"}:
            rel_type = "其他"
        status = "active" if c.confidence >= settings.confidence_threshold and all(entity_map[x].status == "active" for x in [head, tail]) and all(card_map[x].status == "active" for x in c.source_card_ids) and head != tail else "pending"
        rid = stable_id(sid, "relation", head, tail, rel_type, status, *([c.predicate] if c.predicate else []))
        if rid in relation_map:
            r = relation_map[rid]
            r.evidence_card_ids = sorted(set(r.evidence_card_ids + c.source_card_ids))
            r.source_segment_ids = sorted(set(r.source_segment_ids + c.evidence_segment_ids))
            r.confidence = max(r.confidence, c.confidence)
        else:
            relation_map[rid] = Relation(id=rid, session_id=sid, head_entity_id=head, tail_entity_id=tail, type=rel_type, predicate=c.predicate, confidence=c.confidence, evidence_card_ids=c.source_card_ids, source_segment_ids=c.evidence_segment_ids, status=status)
    snap.relations = sorted(relation_map.values(), key=lambda r: r.id)
    return snap

def reconcile(snap: Snapshot) -> None:
    """Rebuild every inverse link and cluster membership; reject dangling references."""
    entity_map = {e.id: e for e in snap.entities}
    card_ids = {c.id for c in snap.cards}
    segment_ids = {s.id for s in snap.segments}
    for e in snap.entities:
        if not set(e.source_card_ids) <= card_ids or not set(e.source_segment_ids) <= segment_ids:
            raise ValueError("实体来源不存在")
        if e.status == "active" and not any(c.id in e.source_card_ids and c.status != "deleted" for c in snap.cards):
            e.status = "pending"
    for r in snap.relations:
        if r.head_entity_id not in entity_map or r.tail_entity_id not in entity_map:
            raise ValueError("悬空关系")
        if not set(r.evidence_card_ids) <= card_ids or not set(r.source_segment_ids) <= segment_ids:
            raise ValueError("关系来源不存在")
        if r.status == "active" and not any(c.id in r.evidence_card_ids and c.status != "deleted" for c in snap.cards):
            r.status = "pending"
        if r.status == "active" and any(entity_map[e].status != "active" for e in [r.head_entity_id, r.tail_entity_id]):
            r.status = "pending"
    for c in snap.cards:
        c.entity_ids = sorted(e.id for e in snap.entities if c.id in e.source_card_ids and e.status != "deleted")
        c.relation_ids = sorted(r.id for r in snap.relations if c.id in r.evidence_card_ids and r.status != "deleted")
        c.vector_id = c.id
    for cluster in snap.clusters:
        cluster.card_ids = [c.id for c in snap.cards if c.cluster_id == cluster.id]
        cluster.entity_ids = sorted({eid for c in snap.cards if c.cluster_id == cluster.id for eid in c.entity_ids})
    for e in snap.entities:
        groups = [c.cluster_id for c in snap.cards if c.id in e.source_card_ids and c.cluster_id]
        e.cluster_id = max(sorted(set(groups)), key=groups.count) if groups else None
        e.embedding_id = e.id
