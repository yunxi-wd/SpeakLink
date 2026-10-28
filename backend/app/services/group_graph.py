"""Derived topic communities and witnessed group bridges, never new entity facts."""
from collections import defaultdict
import networkx as nx
from ..schemas.domain import Snapshot
from .common import stable_id
from .relation_rules import canonical_label

PALETTE=['#247c68','#536fb4','#bd7742','#9365ac','#b95d77','#829444','#388ca0','#a58a35']

def project_groups(snap: Snapshot, network: nx.MultiDiGraph) -> tuple[dict,list[dict],list[dict]]:
    """Partition graph into named communities and aggregate only actual crossing edges.

    Connected components cannot show group bridges: every connecting edge would
    merge their colors. Communities keep dense topics distinct while preserving
    all cross-topic facts. Human-edited topic memberships take precedence.
    """
    nodes={e.id:e for e in snap.entities if e.id in network}
    simple=nx.Graph();simple.add_nodes_from(sorted(nodes,key=lambda eid:(nodes[eid].name,eid)))
    simple.add_edges_from(sorted((a,b) for a,b in network.edges()))
    if not nodes:return {},[],[]
    partitions=list(nx.community.greedy_modularity_communities(simple)) if simple.number_of_edges() else [{n} for n in simple]
    manual=any(c.reason.startswith('manual') for c in snap.clusters)
    topics={c.id:c for c in snap.clusters}
    if manual:
        by_topic=defaultdict(set)
        for eid,e in nodes.items():by_topic[e.cluster_id or 'ungrouped'].add(eid)
        partitions=list(by_topic.values())
    def leader(ids: set) -> str:
        """Prefer a local hub; names break ties without random layout dependence."""
        return min(ids,key=lambda eid:(-simple.subgraph(ids).degree(eid),-network.out_degree(eid),nodes[eid].name,eid))
    partitions.sort(key=lambda ids:(nodes[leader(ids)].name,sorted(ids)))
    membership={};groups=[]
    for index,ids in enumerate(partitions):
        hub=leader(ids);gid=stable_id('relation-group',sorted(ids));topic=topics.get(nodes[hub].cluster_id)
        name=topic.name if manual and topic else nodes[hub].name
        color=topic.color if manual and topic else PALETTE[index%len(PALETTE)]
        members=sorted(ids)
        groups.append(dict(id=gid,name=name,color=color,entity_ids=members,reason='人工主题分组' if manual else '已确认关系的社区分组；组间连线保留具体实体证据'))
        for eid in ids:membership[eid]=dict(group_id=gid,group_name=name,group_color=color)
    bridges={}
    for relation in sorted(snap.relations,key=lambda r:r.id):
        head,tail=relation.head_entity_id,relation.tail_entity_id
        if relation.status!='active' or not network.has_edge(head,tail,relation.id):continue
        source,target=membership[head]['group_id'],membership[tail]['group_id']
        if source==target:continue
        label=canonical_label(relation.predicate,relation.type)
        key=(source,target,label)
        bridge=bridges.setdefault(key,dict(id=stable_id('group-bridge',*key),source=source,target=target,label=label,relation_ids=[],evidence_segment_ids=[],source_card_ids=[],confidence=0.0))
        bridge['relation_ids'].append(relation.id)
        bridge['evidence_segment_ids']=sorted(set(bridge['evidence_segment_ids']+relation.source_segment_ids))
        bridge['source_card_ids']=sorted(set(bridge['source_card_ids']+relation.evidence_card_ids))
        bridge['confidence']=max(bridge['confidence'],relation.confidence)
    return membership,groups,list(bridges.values())
