"""Human-first replayable correction operations and strict projection validation."""
from typing import Any
from ..schemas.domain import Snapshot, Entity, Relation, Card, TopicCluster
from ..schemas.api import CardPatch
from .common import stable_id
from .convergence import reconcile

COLLECTIONS = {"entity": "entities", "relation": "relations", "card": "cards", "cluster": "clusters"}
EDITABLE = {"entity": {"name", "type", "status"}, "relation": {"type", "status"}, "card": {"title", "content", "card_type", "status", "cluster_id"}, "cluster": {"name", "color"}}

def apply(snap: Snapshot, target_type: str, target_id: str, action: str, payload: dict[str, Any]) -> None:
    """Apply a validated edit to an in-memory snapshot; caller commits atomically.

    Merge payload: into_id. Split: name, source_card_ids. Update: editable fields.
    Split partitions provenance and copies mixed-evidence edges for both senses.
    """
    collection = getattr(snap, COLLECTIONS[target_type])
    target = next((x for x in collection if x.id == target_id), None)
    if target is None or getattr(target, "status", None) == "deleted":
        raise ValueError("校正目标不存在或已删除")
    if action == "update":
        if not payload or set(payload) - EDITABLE[target_type]:
            raise ValueError("包含不可编辑字段或空修改")
        if target_type == 'card':
            editable_text = {k: v for k, v in payload.items() if k in {'title', 'content', 'card_type'}}
            if any(value is None for value in editable_text.values()):
                raise ValueError('卡片标题、正文和类型不能设为空值')
            checked = CardPatch(expected_revision=snap.revision, **editable_text)
            payload = payload | checked.model_dump(exclude_unset=True, exclude={'expected_revision'})
        changed = target.model_dump() | payload
        if target_type=='cluster':changed['reason']='manual: 用户调整主题'
        if target_type == 'relation' and 'type' in payload:
            changed['predicate'] = None
        if "manual_edited" in changed:
            changed["manual_edited"] = True
        validated = type(target).model_validate(changed)
        if target_type == "card" and validated.cluster_id and validated.cluster_id not in {c.id for c in snap.clusters}:
            raise ValueError("主题簇不存在")
        if target_type=='card' and 'cluster_id' in payload:
            for group in snap.clusters:
                if group.id==validated.cluster_id:group.reason='manual: 用户分配主题'
        collection[collection.index(target)] = validated
    elif action == "delete" and target_type in {"entity", "relation", "card"}:
        if payload:
            raise ValueError("删除不接受额外字段")
        target.status, target.manual_edited = "deleted", True
        if target_type == "entity":
            for relation in snap.relations:
                if target.id in [relation.head_entity_id, relation.tail_entity_id]:
                    relation.status, relation.manual_edited = "deleted", True
    elif action == "merge" and target_type in {"entity", "cluster"}:
        if set(payload) != {"into_id"}:
            raise ValueError("合并需要且仅接受 into_id")
        destination = next((x for x in collection if x.id == payload["into_id"] and x.id != target.id and getattr(x, "status", "active") != "deleted"), None)
        if destination is None:
            raise ValueError("合并目标无效")
        if target_type == "cluster":
            destination.reason='manual: 用户合并主题'
            for card in snap.cards:
                if card.cluster_id == target.id:
                    card.cluster_id, card.manual_edited = destination.id, True
            snap.clusters.remove(target)
        else:
            destination.aliases = sorted(set(destination.aliases + target.aliases + [target.name]))
            destination.source_card_ids = sorted(set(destination.source_card_ids + target.source_card_ids))
            destination.source_segment_ids = sorted(set(destination.source_segment_ids + target.source_segment_ids))
            destination.manual_edited = True
            target.canonical_id, target.status, target.manual_edited = destination.id, "deleted", True
            for relation in snap.relations:
                if target.id in [relation.head_entity_id, relation.tail_entity_id]:
                    if relation.head_entity_id == target.id:
                        relation.head_entity_id = destination.id
                    if relation.tail_entity_id == target.id:
                        relation.tail_entity_id = destination.id
                    relation.manual_edited = True
                    if relation.head_entity_id == relation.tail_entity_id:
                        relation.status = "pending"
            # Keep stable old IDs as tombstones so future correction replay is possible.
            seen = {}
            for relation in snap.relations:
                key = (relation.head_entity_id, relation.tail_entity_id, relation.type, relation.status)
                if relation.status != "deleted" and key in seen:
                    earlier = seen[key]
                    earlier.evidence_card_ids = sorted(set(earlier.evidence_card_ids + relation.evidence_card_ids))
                    earlier.source_segment_ids = sorted(set(earlier.source_segment_ids + relation.source_segment_ids))
                    relation.status = "deleted"
                else:
                    seen[key] = relation
    elif action == "split" and target_type == "entity":
        if set(payload) != {"name", "source_card_ids"} or not isinstance(payload["source_card_ids"], list) or not isinstance(payload["name"], str) or not payload["name"].strip():
            raise ValueError("拆分需要 name 和 source_card_ids")
        selected = set(payload["source_card_ids"])
        if not selected or not selected < set(target.source_card_ids):
            raise ValueError("请选择部分来源卡片，原节点必须保留至少一张")
        new_id = stable_id(target.id, "split", payload["name"], sorted(selected))
        moved_segments = {s for c in snap.cards if c.id in selected for s in c.source_segment_ids}
        target.source_card_ids = sorted(set(target.source_card_ids) - selected)
        retained_segments = {s for c in snap.cards if c.id in target.source_card_ids for s in c.source_segment_ids}
        new = target.model_copy(deep=True)
        new.id = new.canonical_id = new_id
        new.name, new.aliases = payload["name"].strip(), []
        new.source_card_ids, new.source_segment_ids = sorted(selected), sorted(moved_segments & set(target.source_segment_ids))
        target.source_segment_ids = sorted(retained_segments & set(target.source_segment_ids))
        new.manual_edited = target.manual_edited = True
        snap.entities.append(new)
        for relation in list(snap.relations):
            if relation.status == "deleted" or target.id not in [relation.head_entity_id, relation.tail_entity_id]:
                continue
            moved_cards = selected & set(relation.evidence_card_ids)
            if not moved_cards:
                continue
            moved = relation
            if set(relation.evidence_card_ids) - selected:
                moved = relation.model_copy(deep=True)
                moved.id = stable_id(relation.id, "split", new.id)
                snap.relations.append(moved)
                relation.evidence_card_ids = sorted(set(relation.evidence_card_ids) - selected)
                relation.source_segment_ids = sorted(set(relation.source_segment_ids) & retained_segments)
            moved.evidence_card_ids = sorted(moved_cards)
            moved.source_segment_ids = sorted(set(moved.source_segment_ids) & moved_segments)
            if moved.head_entity_id == target.id:
                moved.head_entity_id = new.id
            if moved.tail_entity_id == target.id:
                moved.tail_entity_id = new.id
            moved.manual_edited = True
    else:
        raise ValueError("不支持的目标与校正操作组合")
    reconcile(snap)
