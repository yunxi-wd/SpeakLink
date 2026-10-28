"""Multi-agent handoff, failure isolation, concurrency, restart and legacy compatibility."""
from threading import Event
from uuid import uuid4
import time
import httpx
import pytest
from app.models.database import transaction, rows, put, load_snapshot, save_snapshot
from app.schemas.agents import ReviewIssue, ReviewReport, AgentRun, AgentEvent
from app.schemas.domain import now
from app.services import pipeline, reviewer
from app.core.config import settings

def source(client, text="张三参与语音项目。") -> str:
    """Create one unprocessed source recording through public contracts."""
    sid=client.post('/api/sessions',json={'title':'agents test'}).json()['id']
    assert client.put(f'/api/sessions/{sid}/transcript',json={'segments':[{'text':text}]}).status_code==200
    return sid

def wait_run(client, rid: str) -> dict:
    """Wait with a finite deadline for a background worker to reach a terminal state."""
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        result=client.get(f'/api/runs/{rid}').json()
        if result['run']['status'] not in {'queued','running'}:
            return result
        time.sleep(.01)
    raise AssertionError('job did not finish within 5 seconds')

def test_role_trace_and_cache(client):
    """Fresh requests invoke all roles; replays reuse facts without claiming new model calls."""
    sid=source(client)
    first=client.post(f'/api/sessions/{sid}/process')
    assert first.status_code==200,first.text
    run=client.get(f'/api/sessions/{sid}/runs').json()[0]
    trace=client.get(f'/api/runs/{run["id"]}').json()
    assert [e['role'] for e in trace['events']]==['summary','extractor','reviewer']
    assert trace['run']['mode']=='demo' and trace['run']['model_calls']==0
    assert all(e['status']=='completed' and e['input_digest'] for e in trace['events'])
    repeat=client.post(f'/api/sessions/{sid}/process').json()
    assert first.json()['entities']==repeat['entities']
    assert client.get(f'/api/sessions/{sid}/runs').json()[0]['cached'] is True

def test_feedback_loop_then_quarantine(client):
    """Demo handles review feedback; negative statements cannot become accepted assertions."""
    sid=source(client,'张三不参与语音项目。')
    response=client.post(f'/api/sessions/{sid}/process')
    assert response.status_code==200,response.text
    snap=response.json()
    assert all(r['status']=='pending' for r in snap['relations'])
    assert snap['cards'][0]['card_type']=='uncertain'
    run=client.get(f'/api/sessions/{sid}/runs').json()[0]
    events=client.get(f'/api/runs/{run["id"]}').json()['events']
    assert [e['role'] for e in events]==['summary','extractor','reviewer','extractor','reviewer']
    assert events[2]['output']['issues'][0]['verdict']=='revise'
    assert events[4]['output']['issues'][0]['verdict']=='uncertain'

def test_bounded_adversarial_reviewer(client,monkeypatch):
    """A reviewer continuously asking for changes cannot create an infinite loop."""
    def reject(cards,segments,candidates):
        tid,item=next((k,v) for k,v in reviewer.targets(cards,candidates).items() if v['kind']=='relation')
        return ReviewReport(issues=[ReviewIssue(target_id=tid,target_type='relation',verdict='revise',reason='仍需核查',confidence=.9,evidence_segment_ids=item['evidence'],source_card_ids=item['cards'])])
    monkeypatch.setattr(pipeline,'review',reject)
    sid=source(client)
    result=client.post(f'/api/sessions/{sid}/process')
    assert result.status_code==200,result.text
    run=client.get(f'/api/sessions/{sid}/runs').json()[0]
    assert run['rounds']==settings.agents.max_revisions
    assert run['steps_completed']==3+2*settings.agents.max_revisions
    assert result.json()['relations'][0]['status']=='pending'

def test_failure_does_not_commit_and_is_audited(client,monkeypatch):
    """Model failure is visible in durable history while source revision remains untouched."""
    def fail(*args):
        raise httpx.ConnectError('private provider failure')
    monkeypatch.setattr(pipeline,'review',fail)
    sid=source(client)
    before=client.get(f'/api/sessions/{sid}').json()
    result=client.post(f'/api/sessions/{sid}/process')
    assert result.status_code==503
    assert client.get(f'/api/sessions/{sid}').json()==before
    run=client.get(f'/api/sessions/{sid}/runs').json()[0]
    assert run['status']=='failed' and 'private' not in run['error']
    assert client.get(f'/api/runs/{run["id"]}').json()['events'][-1]['status']=='failed'

def test_background_no_write_lock_and_cas(client,monkeypatch):
    """Concurrent edits finish during inference and cannot be overwritten by stale completion."""
    entered,released=Event(),Event()
    original=pipeline.review
    def delayed(*args):
        entered.set()
        assert released.wait(5)
        return original(*args)
    monkeypatch.setattr(pipeline,'review',delayed)
    sid=source(client)
    response=client.post(f'/api/sessions/{sid}/jobs')
    assert response.status_code==202,response.text
    assert entered.wait(3)
    try:
        assert client.post(f'/api/sessions/{sid}/jobs').status_code==409
        # This write would block if inference still held BEGIN IMMEDIATE.
        with transaction(True) as conn:
            snap=load_snapshot(conn,sid)
            snap.session.title='newer user edit'
            save_snapshot(conn,snap)
    finally:
        released.set()
    outcome=wait_run(client,response.json()['id'])
    assert outcome['run']['status']=='conflicted'
    current=client.get(f'/api/sessions/{sid}').json()
    assert current['session']['title']=='newer user edit' and current['cards']==[]

def test_clone_uses_new_evidence_ids(client,recording):
    """Re-analysis preserves the original corrected recording and receives new provenance IDs."""
    copied=client.post(f'/api/sessions/{recording["session"]["id"]}/clone')
    assert copied.status_code==201
    snap=client.get(f'/api/sessions/{copied.json()["id"]}').json()
    assert not snap['cards'] and len(snap['segments'])==len(recording['segments'])
    assert {s['id'] for s in snap['segments']}.isdisjoint({s['id'] for s in recording['segments']})

def test_reviewer_rejects_forged_target(client,monkeypatch):
    """Independent LLM reviewer cannot reference an unrelated recording or candidate."""
    from app.services import summarizer,extractor
    from app.schemas.domain import TranscriptSegment
    s=TranscriptSegment(id='s',session_id='x',start_ms=0,end_ms=1,text='张三参与项目。')
    cards=summarizer.summarize([s],'x',now())
    candidates=extractor.extract(cards,[s])
    monkeypatch.setattr(settings.agents.reviewer,'provider','ollama')
    monkeypatch.setattr(reviewer,'structured',lambda *args: ReviewReport(issues=[ReviewIssue(target_id='foreign',target_type='entity',verdict='reject',reason='fake',confidence=.9,evidence_segment_ids=['s'],source_card_ids=[cards[0].id])]))
    with pytest.raises(ValueError,match='不存在'):
        reviewer.review(cards,[s],candidates)

def test_legacy_corrected_cache_replays_without_inference(client,recording,monkeypatch):
    """v1 caches without base_snapshot preserve old canonical IDs and human changes."""
    sid=recording['session']['id']
    entity=recording['entities'][0]
    changed=client.patch(f'/api/entities/{entity["id"]}',json={'expected_revision':recording['revision'],'name':'人工名称'})
    assert changed.status_code==200
    with transaction(True) as conn:
        cached=rows(conn,'runs',sid)[0]
        cached.pop('base_snapshot')
        put(conn,'runs',cached)
    monkeypatch.setattr(pipeline,'summarize',lambda *args: (_ for _ in ()).throw(AssertionError('must not infer')))
    again=client.post(f'/api/sessions/{sid}/process')
    assert again.status_code==200,again.text
    assert next(e for e in again.json()['entities'] if e['id']==entity['id'])['name']=='人工名称'

def test_explicit_alias_and_missing_subject_retained(client):
    """Rule candidates keep explicit aliases and unresolved omitted subjects for human review."""
    sid=client.post('/api/sessions',json={}).json()['id']
    client.put(f'/api/sessions/{sid}/transcript',json={'segments':[{'text':'人工智能简称AI。'},{'text':'AI属于计算机科学。'},{'text':'依赖数据。'}]})
    snap=client.post(f'/api/sessions/{sid}/process').json()
    assert any(e['name']=='人工智能' and 'AI' in e['aliases'] for e in snap['entities'])
    assert any(e['name']=='省略主语' and e['status']=='pending' for e in snap['entities'])

def test_model_budget_and_independent_role_configuration(client,monkeypatch):
    """Simulated model calls consume the configured budget and unresolved criticism is retained."""
    original_config=pipeline.role_config
    monkeypatch.setattr(pipeline,'role_config',lambda role: original_config(role) if role=='correction' else dict(original_config(role),provider='ollama',model=f'{role}-model'))
    monkeypatch.setattr(settings.agents,'max_model_calls',3)
    def criticize(cards,segments,candidates):
        tid,item=next((k,v) for k,v in reviewer.targets(cards,candidates).items() if v['kind']=='relation')
        return ReviewReport(issues=[ReviewIssue(target_id=tid,target_type='relation',verdict='revise',reason='需要检查',confidence=.9,evidence_segment_ids=item['evidence'],source_card_ids=item['cards'])])
    monkeypatch.setattr(pipeline,'review',criticize)
    sid=source(client)
    response=client.post(f'/api/sessions/{sid}/process')
    assert response.status_code==200,response.text
    run=client.get(f'/api/sessions/{sid}/runs').json()[0]
    assert run['model_calls']==3 and run['steps_completed']==3
    assert response.json()['relations'][0]['status']=='pending'
    assert [e['model'] for e in client.get(f'/api/runs/{run["id"]}').json()['events']]==['summary-model','extractor-model','reviewer-model']

def test_restart_marks_jobs_interrupted(client):
    """Restart recovery retains an explicit terminal error rather than ghost-running jobs."""
    sid=source(client)
    work=pipeline.prepare(sid)
    with transaction(True) as conn:
        event=AgentEvent(id=str(uuid4()),session_id=sid,run_id=work.run.id,sequence=1,
                         role='summary',attempt=1,provider='demo',model='demo',input_digest='test')
        put(conn,'agent_events',event.model_dump())
    pipeline.shutdown()
    pipeline.startup()
    recovered=client.get(f'/api/runs/{work.run.id}').json()['run']
    assert recovered['status']=='interrupted' and recovered['finished_at']
    interrupted=client.get(f'/api/runs/{work.run.id}').json()['events'][0]
    assert interrupted['status']=='failed' and interrupted['finished_at'] and interrupted['error']
    assert client.get(f'/api/sessions/{sid}').json()['cards']==[]
    assert client.post(f'/api/sessions/{sid}/process').status_code==200

def test_successful_review_handoff(client,monkeypatch):
    """Feedback passed to extractor can resolve the review and retain accepted facts."""
    original_extract=pipeline.extract
    received=[]
    def extraction(cards,segments,feedback=None):
        received.append(feedback)
        return original_extract(cards,segments)
    calls=0
    def independent_review(cards,segments,candidates):
        nonlocal calls
        calls+=1
        if calls==2:
            return ReviewReport(issues=[])
        tid,item=next((k,v) for k,v in reviewer.targets(cards,candidates).items() if v['kind']=='relation')
        return ReviewReport(issues=[ReviewIssue(target_id=tid,target_type='relation',verdict='revise',reason='重新核对原文',confidence=.9,evidence_segment_ids=item['evidence'],source_card_ids=item['cards'])])
    monkeypatch.setattr(pipeline,'extract',extraction)
    monkeypatch.setattr(pipeline,'review',independent_review)
    sid=source(client)
    result=client.post(f'/api/sessions/{sid}/process').json()
    assert received[0] is None and received[1]['issues'][0]['reason']=='重新核对原文'
    assert result['relations'][0]['status']=='active'
