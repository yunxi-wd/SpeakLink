"""Hybrid evidence retrieval with actual graph paths and no generated facts."""
from itertools import combinations
import networkx as nx
from ..schemas.domain import Snapshot
from ..schemas.api import SearchResult
from ..core.config import settings
from .vector_store import rank
from .graph_store import network

def search(snap: Snapshot, query: str, limit: int) -> SearchResult:
    """Rank cards by evidence similarity plus query-entity graph proximity."""
    scores = rank(snap, query)
    graph = network(snap)
    undirected = graph.to_undirected()
    matched = [e.id for e in snap.entities if e.id in graph and any(n.casefold() in query.casefold() for n in [e.name, *e.aliases])]
    adjacent = set(matched)
    for node in matched:
        adjacent.update(undirected.neighbors(node))
    for card in snap.cards:
        if adjacent.intersection(card.entity_ids):
            scores[card.id] = scores.get(card.id, 0) + 0.15
    cards = sorted([c for c in snap.cards if c.status != "deleted" and scores.get(c.id, 0) > 0.05], key=lambda c: (-scores[c.id], c.id))[:limit]
    nodes = matched[:12] or list(dict.fromkeys(eid for c in cards for eid in c.entity_ids if eid in graph))[:12]
    paths = []
    for a, b in combinations(nodes, 2):
        if nx.has_path(undirected, a, b):
            path = nx.shortest_path(undirected, a, b)
            if len(path) <= 5:
                paths.append(path)
        if len(paths) >= 12:
            break
    pairs = {frozenset((a, b)) for p in paths for a, b in zip(p, p[1:])}
    relations = [r for r in snap.relations if r.status == "active" and frozenset((r.head_entity_id, r.tail_entity_id)) in pairs]
    return SearchResult(cards=cards, scores=[round(scores[c.id], 4) for c in cards], paths=paths, relations=relations, embedding_provider=settings.embedding_provider)
