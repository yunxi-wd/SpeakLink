"""Model/ASR adapter contract tests use fakes, not claims about model quality."""
from types import SimpleNamespace
import pytest
from app.services import asr
from app.services.extractor import extract
from app.services.convergence import converge
from app.schemas.domain import ExtractionCandidates, EntityCandidate, RelationCandidate, Snapshot, Session, TranscriptSegment, Card

def test_asr_vad_timestamps_and_raw(monkeypatch):
    """Verify VAD request, seconds-to-ms conversion and raw-text preservation."""
    def fake(path, **options):
        assert options['vad_filter'] is True and options['word_timestamps'] is True
        return iter([SimpleNamespace(start=1.2,end=2.8,text='嗯，测试。',avg_logprob=-0.2)]), None
    monkeypatch.setattr(asr, 'model', lambda: SimpleNamespace(transcribe=fake))
    segment = asr.transcribe('not-real.wav','session','zh')[0]
    assert (segment.start_ms,segment.end_ms) == (1200,2800)
    assert segment.raw_text == '嗯，测试。' and segment.text == '测试。'

def test_explicit_alias_and_relation_normalization():
    """Supported alias mentions merge; synonym relation type converges deterministically."""
    segment = TranscriptSegment(id='s',session_id='x',start_ms=0,end_ms=1,text='人工智能（AI）导致效率提升。AI 引起效率提升。')
    card = Card(id='c',session_id='x',card_type='topic',title='主题',content=segment.text,source_segment_ids=['s'],confidence=.9)
    evidence = dict(confidence=.9,evidence_segment_ids=['s'],source_card_ids=['c'])
    candidates = ExtractionCandidates(entities=[EntityCandidate(name='人工智能',aliases=['AI'],type='CONCEPT',**evidence),EntityCandidate(name='AI',type='CONCEPT',**evidence),EntityCandidate(name='效率提升',type='CONCEPT',**evidence)], relations=[RelationCandidate(head='AI',tail='效率提升',type='引起',**evidence)])
    snap = converge(Snapshot(session=Session(id='x',title='x'),segments=[segment],cards=[card]),candidates)
    assert len(snap.entities) == 2 and snap.relations[0].type == '导致'

def test_large_graph(client):
    """Process 126 accepted nodes with valid edges and bounded source counts."""
    sid = client.post('/api/sessions',json={'title':'large'}).json()['id']
    client.put(f'/api/sessions/{sid}/transcript',json={'segments':[{'text':f'概念{i}依赖概念{i+1}。'} for i in range(125)]})
    response = client.post(f'/api/sessions/{sid}/process')
    assert response.status_code == 200, response.text
    graph = client.get(f'/api/sessions/{sid}/graph').json()
    assert len(graph['nodes']) == 126 and len(graph['edges']) == 125

def test_strict_compatible_model_schema():
    """Default-valued alias fields are still required for strict model providers."""
    from app.services.llm import strict_schema
    schema = strict_schema(ExtractionCandidates.model_json_schema())
    entity = schema['$defs']['EntityCandidate']
    assert entity['additionalProperties'] is False
    assert 'aliases' in entity['required']

def test_model_json_and_evidence_rejection(monkeypatch):
    """Structured models cannot inject cross-record evidence into accepted candidates."""
    from app.services import extractor
    from app.core.config import settings
    segment = TranscriptSegment(id='s',session_id='x',start_ms=0,end_ms=1,text='张三参与项目。')
    card = Card(id='c',session_id='x',card_type='topic',title='主题',content=segment.text,source_segment_ids=['s'],confidence=.9)
    candidate = ExtractionCandidates(entities=[EntityCandidate(name='张三',type='PERSON',confidence=.9,evidence_segment_ids=['foreign-segment'],source_card_ids=['c'])],relations=[])
    monkeypatch.setattr(settings,'llm_provider','ollama')
    monkeypatch.setattr(extractor,'structured',lambda *args: candidate)
    with pytest.raises(ValueError,match='不存在'):
        extract([card],[segment])
