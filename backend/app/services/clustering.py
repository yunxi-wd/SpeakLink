"""Sequential topic segmentation with explicit cue and embedding-boundary explanations."""
import numpy as np
from ..schemas.domain import Snapshot, TopicCluster
from .common import stable_id
from .vector_store import embed

def cluster(snap: Snapshot) -> None:
    """Assign contiguous topic groups; embeddings and explicit transitions explain boundaries."""
    palette = ["#16a085", "#637de9", "#cf8b42", "#af6bc5", "#de6575", "#3c9dbc"]
    vectors = embed([c.content for c in snap.cards])
    current = None
    for i, card in enumerate(snap.cards):
        cue = any(w in card.content for w in ["换个话题", "接下来讨论", "另外说", "另一个主题"])
        similarity = float(np.dot(vectors[i], vectors[i - 1])) if i else 1
        boundary = current is None or cue or (settings_semantic() and similarity < 0.30)
        if boundary:
            current = TopicCluster(id=stable_id(snap.session.id, "cluster", card.id), session_id=snap.session.id, name=card.title[:18], card_ids=[], entity_ids=[], color=palette[len(snap.clusters) % len(palette)], confidence=0.95 if cue else 0.7, reason="显式话题切换词" if cue else "首个话题" if i == 0 else f"相邻卡片语义相似度 {similarity:.3f} < 0.30")
            snap.clusters.append(current)
        card.cluster_id = current.id

def settings_semantic() -> bool:
    """Only semantic embeddings may decide implicit topic boundaries."""
    from ..core.config import settings
    return settings.embedding_provider == "sentence_transformer"
