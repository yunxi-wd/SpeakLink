"""Acceptance tests for noisy terminology, meaningful hierarchy and visual labels."""
from app.schemas.domain import TranscriptSegment
from app.services.transcript_cleanup import clean_segments,TextEdits,TextEdit
from app.services.presentation import relation_label
from test_chinese_prose import create_processed
from test_semantic import triples

def test_domain_correction_preserves_raw():
    segment=TranscriptSegment(id='s',session_id='a',start_ms=0,end_ms=1000,text='呃，中泰战略建设业务中泰。中泰公司位于北京。')
    result=clean_segments([segment])
    assert segment.text=='中台战略建设业务中台。中泰公司位于北京。'
    assert '中泰战略' in segment.raw_text
    assert result['edits'] and result['provider']=='demo'

def test_uncertain_and_negation_edits_not_applied(monkeypatch):
    import app.services.transcript_cleanup as module
    monkeypatch.setattr(module,'role_config',lambda role:{'provider':'ollama'})
    monkeypatch.setattr(module,'structured',lambda *args:TextEdits(edits=[TextEdit(segment_id='s',before='不促进',after='促进',reason='错误建议',confidence=.99,evidence_segment_ids=['s'],source_card_ids=[])]))
    segment=TranscriptSegment(id='s',session_id='a',start_ms=0,end_ms=1000,text='项目不促进增长。')
    audit=clean_segments([segment])
    assert segment.text=='项目不促进增长。' and audit['edits'][0]['status']=='pending'

def test_digital_strategy_semantic_graph(client):
    sid,snap=create_processed(client,['中泰战略包含业务中泰和技术中泰。','业务中台提升运营数据能力。','技术中台提升产品技术能力。','数据化运营打破部门墙和数据墙。'])
    assert ('中台战略','包含','业务中台') in triples(snap)
    assert ('业务中台','提升','运营数据能力') in triples(snap)
    assert ('数据化运营','打破','部门墙') in triples(snap)
    graph=client.get(f'/api/sessions/{sid}/graph').json()
    assert all(e['label'] and e['label']!='原文提及' for e in graph['edges'])
    assert all(n['group'] and n['size'] in {20,30,50} for n in graph['nodes'])
    assert 1<=sum(n['level']=='core' for n in graph['nodes'])<=3
    assert graph==client.get(f'/api/sessions/{sid}/graph').json()
    assert any('中泰' in s['raw_text'] and '中台' in s['text'] for s in snap['segments'])
    relation = graph['edges'][0]
    updated=client.patch(f"/api/relations/{relation['id']}",json={'expected_revision':snap['revision'],'predicate':'促进'} )
    assert updated.status_code==200,updated.text
    replay=client.post(f'/api/sessions/{sid}/process')
    assert replay.status_code==200
    assert next(e for e in client.get(f'/api/sessions/{sid}/graph').json()['edges'] if e['id']==relation['id'])['label']=='促进'

def test_label_normalization_and_no_fake_direction():
    assert relation_label('包括','其他')=='包含'
    assert relation_label('涵盖','其他')=='包含'
    assert relation_label(None,'属于')=='属于'
    assert relation_label(None,'其他')==''
