"""Simplified transcription, ordinary prose extraction, and provenance graph boundaries."""
from types import SimpleNamespace
from app.services import asr

def test_asr_simplifies_without_losing_raw(monkeypatch):
    """Orthographic normalization must keep untouched raw text and real timestamps."""
    class Engine:
        def transcribe(self, path, **kwargs):
            assert '简体中文' in kwargs['initial_prompt']
            return iter([SimpleNamespace(start=1, end=3, text='知識圖譜屬於人工智慧，臺灣團隊參與這個專案。', avg_logprob=-.1)]), None
    monkeypatch.setattr(asr, 'model', lambda: Engine())
    item = asr.transcribe('fixture.wav', 'sid', 'zh')[0]
    assert '知识图谱属于' in item.text and '台湾团队参与' in item.text
    assert '知識圖譜' in item.raw_text and item.start_ms == 1000

def create_processed(client, lines):
    """Exercise the actual source, coordinator and convergence APIs."""
    sid = client.post('/api/sessions',json={}).json()['id']
    client.put(f'/api/sessions/{sid}/transcript',json={'segments':[{'text':line} for line in lines]})
    response = client.post(f'/api/sessions/{sid}/process')
    assert response.status_code == 200, response.text
    return sid, response.json()

def test_prose_has_nodes_and_literal_relations(client):
    """Common predicate grammar works without the demo's original small verb list."""
    sid, snap = create_processed(client,['白杨树是一种乔木。','白杨树象征农民。','树叶在阳光下舒展，树干笔直。'])
    names = {e['name'] for e in snap['entities'] if e['status']=='active'}
    assert {'白杨树','乔木','农民'} <= names
    assert any(r['predicate']=='象征' and r['status']=='active' for r in snap['relations'])
    assert len(client.get(f'/api/sessions/{sid}/graph').json()['edges']) >= 2

def test_provenance_links_are_not_semantic_claims(client):
    """Descriptive nouns yield source links; mere co-occurrence creates no fact edges."""
    sid, snap = create_processed(client,['树叶在阳光下舒展，树干笔直。'])
    semantic = client.get(f'/api/sessions/{sid}/graph').json()
    evidence = client.get(f'/api/sessions/{sid}/graph?mode=evidence').json()
    assert semantic['nodes'] and semantic['edges']==[]
    assert evidence['edges'] and all(e['type']=='原文提及' for e in evidence['edges'])
    assert evidence['revision']==snap['revision']
    assert all(e['evidence_card_ids'][0] in {c['id'] for c in snap['cards']} for e in evidence['edges'])

def test_traditional_evidence_is_not_rejected_and_clone_is_fresh(client):
    """Traditional raw evidence validates simplified names, while source copies use fresh IDs."""
    sid, snap = create_processed(client,['知識圖譜屬於人工智能。'])
    assert any(e['name']=='知识图谱' and e['status']=='active' for e in snap['entities'])
    cloned = client.post(f'/api/sessions/{sid}/clone').json()['id']
    fresh = client.get(f'/api/sessions/{cloned}').json()
    assert fresh['segments'][0]['text']=='知识图谱属于人工智能。'
    assert fresh['segments'][0]['raw_text']=='知識圖譜屬於人工智能。'
    assert not fresh['cards'] and fresh['segments'][0]['id'] != snap['segments'][0]['id']


def test_evidence_view_preserves_semantic_edges(client):
    """Adding source links must not remove already accepted entity relationships."""
    sid, snap = create_processed(client,['白杨树象征农民。'])
    semantic = client.get(f'/api/sessions/{sid}/graph').json()
    combined = client.get(f'/api/sessions/{sid}/graph?mode=evidence').json()
    assert semantic['edges']
    by_id = {edge['id']: edge for edge in combined['edges']}
    for edge in semantic['edges']:
        assert by_id[edge['id']]['predicate'] == '象征'
        assert by_id[edge['id']]['edge_kind'] == 'semantic'
    assert any(edge.get('edge_kind') == 'provenance' for edge in combined['edges'])
    assert combined['revision'] == semantic['revision'] == snap['revision']
