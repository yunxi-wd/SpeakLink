"""Semantic labels, bounded coreference, negative evidence and export consistency."""
from test_chinese_prose import create_processed


def triples(snap, status='active'):
    """Resolve persisted endpoint IDs for evidence-level assertions."""
    names = {e['id']:e['name'] for e in snap['entities']}
    return {(names[r['head_entity_id']],r['predicate'] or r['type'],names[r['tail_entity_id']]) for r in snap['relations'] if r['status']==status}


def test_contextual_symbolism_and_enumeration(client):
    """A unique named topic supports a later pronoun and both coordinated objects."""
    sid, snap = create_processed(client,['这就是白杨树。','它象征农民和哨兵。'])
    assert {('白杨树','象征','农民'),('白杨树','象征','哨兵')} <= triples(snap)
    relation = next(r for r in snap['relations'] if r['status']=='active' and r['predicate']=='象征')
    assert len(relation['source_segment_ids'])==2
    assert len(relation['evidence_card_ids'])==2
    assert '象征' in client.get(f'/api/sessions/{sid}/export?format=markdown').text


def test_semantic_labels_and_direction(client):
    """Containment keeps subject-to-part direction; labels carry concrete meaning."""
    _, snap = create_processed(client,['星河平台包括检索模块。','研发团队使用知识图谱。','总部位于北京。'])
    facts = triples(snap)
    assert ('星河平台','包括','检索模块') in facts
    assert ('研发团队','使用','知识图谱') in facts
    assert ('总部','位于','北京') in facts


def test_ambiguous_pronoun_does_not_create_fact(client):
    """Two explicitly introduced subjects must not collapse onto the nearest one."""
    _, snap = create_processed(client,['白杨树是一种乔木。','柳树是一种乔木。','它象征农民。'])
    assert not any(t[1]=='象征' for t in triples(snap))
    assert any(t[1]=='象征' for t in triples(snap,'pending'))


def test_negative_semantics_are_not_accepted(client):
    """Negative assertions cannot be promoted into positive semantic edges."""
    _, snap = create_processed(client,['白杨树并未象征农民。'])
    assert not any(t[1]=='象征' for t in triples(snap))


def test_topic_transition_clears_coreference(client):
    """An explicit switch prevents stale topic links."""
    _, snap = create_processed(client,['这就是白杨树。','换个话题，它象征希望。'])
    assert not any(t[1]=='象征' for t in triples(snap))


def test_possessive_subject_is_not_its_owner(client):
    """The leaf, rather than its owner, is the grammatical subject."""
    _, snap = create_processed(client,['这就是白杨树。','它的叶子象征希望。'])
    assert ('叶子','象征','希望') in triples(snap)
    assert ('白杨树','象征','希望') not in triples(snap)


def test_negative_antecedent_does_not_veto_positive_predicate(client):
    """Negation scope stays in its clause while cross-card evidence is retained."""
    _, snap = create_processed(client,['这就是白杨树，绝不是平凡的树。','它象征农民。'])
    assert ('白杨树','象征','农民') in triples(snap)
