"""Rebuildable FAISS index over cards, entities and relation evidence.

Hash mode is an explicitly labeled offline lexical demo. Production semantic
mode lazily loads BGE through sentence-transformers and requires FAISS.
"""
from functools import lru_cache
import hashlib
import re
import numpy as np
from ..core.config import settings
from ..schemas.domain import Snapshot

@lru_cache(maxsize=1)
def encoder():
    """Load the configured local embedding model once."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(settings.embedding_model)

def embed(texts: list[str]) -> np.ndarray:
    """Encode texts to normalized float32 matrix [N,D]."""
    if not texts:
        return np.zeros((0, 512), dtype=np.float32)
    if settings.embedding_provider == "sentence_transformer":
        return np.asarray(encoder().encode(texts, normalize_embeddings=True), dtype=np.float32)
    result = np.zeros((len(texts), 512), dtype=np.float32)
    for i, text in enumerate(texts):
        text = re.sub(r"\s+", "", text.casefold())
        for n in [1, 2, 3]:
            for j in range(max(0, len(text) - n + 1)):
                index = int.from_bytes(hashlib.sha256(text[j:j+n].encode()).digest()[:4], "little") % 512
                result[i, index] += 1
    norm = np.linalg.norm(result, axis=1, keepdims=True)
    return result / np.maximum(norm, 1e-8)

def documents(snap: Snapshot) -> list[dict]:
    """Build index records with provenance mapping back to cards."""
    docs = [{"id": c.id, "text": c.title + '\n' + c.content, "card_ids": [c.id]} for c in snap.cards if c.status != "deleted"]
    docs += [{"id": e.id, "text": " ".join([e.name, *e.aliases]), "card_ids": e.source_card_ids} for e in snap.entities if e.status == "active"]
    entities = {e.id: e for e in snap.entities}
    segments = {s.id: s.text for s in snap.segments}
    docs += [{"id": r.id, "text": " ".join([entities[r.head_entity_id].name, r.type, entities[r.tail_entity_id].name, *[segments[s] for s in r.source_segment_ids]]), "card_ids": r.evidence_card_ids} for r in snap.relations if r.status == "active"]
    return docs

def rank(snap: Snapshot, query: str) -> dict[str, float]:
    """Rebuild from current revision, persist FAISS in semantic mode and rank evidence."""
    docs = documents(snap)
    if not docs:
        return {}
    vectors = embed([d["text"] for d in docs])
    q = embed([query])
    if settings.embedding_provider == "sentence_transformer":
        import faiss
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        directory = settings.data_dir / "vectors"
        directory.mkdir(exist_ok=True)
        faiss.write_index(index, str(directory / f"{snap.session.id}-{snap.revision}.faiss"))
        scores, indices = index.search(q, len(docs))
        ordered = zip(indices[0].tolist(), scores[0].tolist())
    else:
        scores = (vectors @ q[0]).tolist()
        ordered = sorted(enumerate(scores), key=lambda p: -p[1])
    ranking: dict[str, float] = {}
    for idx, score in ordered:
        for cid in docs[idx]["card_ids"]:
            lexical = 0.12 if query.casefold() in docs[idx]["text"].casefold() else 0
            ranking[cid] = max(ranking.get(cid, 0), float(score) + lexical)
    return ranking
