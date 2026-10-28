"""NetworkX projections built exclusively from accepted database facts."""
import networkx as nx
from ..schemas.domain import Snapshot
from ..schemas.api import Graph
from .relation_rules import PLACEHOLDER, canonical_label
from .group_graph import project_groups

def network(snap: Snapshot) -> nx.MultiDiGraph:
    """Return active canonical directed graph; preserve parallel relation types."""
    graph = nx.MultiDiGraph()
    for e in snap.entities:
        if e.status == "active" and not PLACEHOLDER.fullmatch(e.name.strip()):
            graph.add_node(e.id, name=e.name, type=e.type, cluster_id=e.cluster_id or "")
    for r in snap.relations:
        if r.status == "active" and canonical_label(r.predicate,r.type) and r.head_entity_id in graph and r.tail_entity_id in graph:
            graph.add_edge(r.head_entity_id, r.tail_entity_id, key=r.id, id=r.id, type=r.type, predicate=r.predicate or '', confidence=r.confidence)
    return graph

def graph_view(snap: Snapshot) -> Graph:
    """Expose accepted nodes/edges and an explicit pending counter."""
    graph = network(snap)
    membership,groups,bridges=project_groups(snap,graph)
    return Graph(nodes=[dict(e.model_dump(),**membership[e.id]) for e in snap.entities if e.id in graph], edges=[dict(r.model_dump(),predicate=canonical_label(r.predicate,r.type),cross_group=membership[r.head_entity_id]['group_id']!=membership[r.tail_entity_id]['group_id']) for r in snap.relations if r.status == "active" and graph.has_edge(r.head_entity_id, r.tail_entity_id, r.id)], pending_count=sum(x.status == "pending" for x in [*snap.entities, *snap.relations]), revision=snap.revision,groups=groups,group_relations=bridges)

def evidence_view(snap: Snapshot) -> Graph:
    """Evidence remains attached to semantic edges; never synthesize card nodes."""
    return graph_view(snap)
