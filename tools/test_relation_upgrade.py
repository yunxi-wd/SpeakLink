"""Self-contained regression/integration tests using the portable Python runtime."""
from pathlib import Path
import os,sys,tempfile,unittest,json
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
sys.path.insert(0,str(ROOT/'tools'))
os.environ['KNOWGPT_DATA_DIR']=tempfile.mkdtemp(prefix='knowgpt-relation-test-')
os.environ['KNOWGPT_LLM_PROVIDER']='demo'
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.domain import TranscriptSegment,ExtractionCandidates,EntityCandidate,RelationCandidate
from app.services.summarizer import summarize
from app.services.extractor import extract
from app.services.graph_store import graph_view,evidence_view
from app.services.relation_examples import development_examples,select_examples
from evaluate_relations import evaluate,predict

class RelationUpgradeTests(unittest.TestCase):
    """Check facts, pending candidates, audited persistence and legacy upgrades."""
    @classmethod
    def setUpClass(cls):
        """Use an isolated migrated database with the real FastAPI lifecycle."""
        cls.client=TestClient(app);cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        """Stop only the test app and its owned worker pool."""
        cls.client.__exit__(None,None,None)

    def process(self,lines):
        """Run public endpoints with deterministic text and return persisted facts."""
        sid=self.client.post('/api/sessions',json={'title':'relation test'}).json()['id']
        response=self.client.put(f'/api/sessions/{sid}/transcript',json={'segments':[{'text':t} for t in lines]})
        self.assertEqual(response.status_code,200,response.text)
        response=self.client.post(f'/api/sessions/{sid}/process')
        self.assertEqual(response.status_code,200,response.text)
        return sid,response.json()

    def test_fixed_corpus(self):
        """Measure exact triples, including false positive edges and stability."""
        result=evaluate(ROOT/'configs/relation_examples.jsonl','evaluation,challenge')
        self.assertGreaterEqual(result['precision'],.98)
        self.assertGreaterEqual(result['recall'],.95)
        self.assertTrue(result['repeat_stability'])

    def test_no_card_nodes_in_either_mode(self):
        """Source links remain on facts; no virtual card entities are generated."""
        sid,snap=self.process(['星河平台由检索模块和导出模块组成。'])
        for mode in ['knowledge','evidence']:
            graph=self.client.get(f'/api/sessions/{sid}/graph?mode={mode}').json()
            self.assertEqual(len(graph['edges']),2)
            self.assertTrue(all(n.get('type')!='CARD' and not n['name'].startswith('卡片') for n in graph['nodes']))
            self.assertTrue(all(e['evidence_card_ids'] and e['source_segment_ids'] for e in graph['edges']))
        self.assertTrue(snap['cards'])

    def test_mixed_positive_and_negative(self):
        """Weak mentions cannot replace strong canonical endpoints."""
        facts,_=predict(['平台包含数据库，但不支持在线检索。'])
        self.assertEqual(facts,{('平台','包含','数据库')})

    def test_mixed_positive_and_speculation(self):
        """An uncertain clause cannot quarantine independent factual clauses."""
        facts,_=predict(['平台包含数据库，但它可能依赖云服务。'])
        self.assertEqual(facts,{('平台','包含','数据库')})

    def test_definition_and_question(self):
        """Questions and abstract action fragments never become subject entities."""
        facts,_=predict(['什么是人工智能？人工智能是研究和开发计算机系统的一门技术领域。'])
        self.assertEqual(facts,{('人工智能','属于','技术领域'),('人工智能','研究','计算机系统'),('人工智能','开发','计算机系统')})

    def test_speaker_switch_does_not_resolve_person(self):
        """Cross-speaker pronouns remain candidates rather than asserted facts."""
        segments=[TranscriptSegment(id='s0',session_id='test',text='张三参与项目甲。',start_ms=0,end_ms=1000,speaker='A'),TranscriptSegment(id='s1',session_id='test',text='他负责项目乙。',start_ms=1000,end_ms=2000,speaker='B')]
        cards=summarize(segments,'test','2026-10-19')
        candidates=extract(cards,segments)
        self.assertFalse(any(r.head=='张三' and r.tail=='项目乙' and r.confidence>=.75 for r in candidates.relations))

    def test_model_unsupported_direction_is_pending(self):
        """A reversed model edge must not pass just because both nouns occur."""
        segments=[TranscriptSegment(id='s0',session_id='test',text='平台包含数据库。',start_ms=0,end_ms=1000)]
        cards=summarize(segments,'test','2026-10-19')
        proof=dict(confidence=.99,evidence_segment_ids=['s0'],source_card_ids=[cards[0].id])
        model=ExtractionCandidates(entities=[EntityCandidate(name=n,type='CONCEPT',**proof) for n in ['平台','数据库','卡片1']],relations=[RelationCandidate(head='数据库',tail='平台',type='其他',predicate='包含',**proof)])
        with patch('app.services.extractor.role_config',return_value={'provider':'ollama'}),patch('app.services.extractor.structured',return_value=model):
            result=extract(cards,segments)
        self.assertNotIn('卡片1',{e.name for e in result.entities})
        self.assertTrue(all(r.confidence<.75 for r in result.relations if r.head=='数据库'))
        self.assertTrue(any(r.head=='平台' and r.tail=='数据库' and r.confidence>=.75 for r in result.relations))

    def test_manual_correction_survives(self):
        """Human edits remain pinned and replayed when reprocessing a recording."""
        sid,snap=self.process(['张三参与项目甲。'])
        target=next(e for e in snap['entities'] if e['name']=='张三' and e['status']=='active')
        changed=self.client.patch(f"/api/entities/{target['id']}",json={'expected_revision':snap['revision'],'name':'张老师'})
        self.assertEqual(changed.status_code,200,changed.text)
        repeated=self.client.post(f'/api/sessions/{sid}/process')
        self.assertEqual(repeated.status_code,200,repeated.text)
        self.assertIn('张老师',{e['name'] for e in repeated.json()['entities']})

    def test_legacy_cache_recomputed_without_corrections(self):
        """Reprocess upgrades an untouched old cache instead of silently replaying it."""
        from app.models.database import transaction,rows,put,load_snapshot,save_snapshot
        sid,snap=self.process(['平台依赖数据库。'])
        with transaction(True) as conn:
            cached=rows(conn,'runs',sid)[0];cached['fingerprint']='old-version';put(conn,'runs',cached)
            current=load_snapshot(conn,sid);current.session.metadata['fingerprint']='old-version';save_snapshot(conn,current)
        response=self.client.post(f'/api/sessions/{sid}/process')
        self.assertEqual(response.status_code,200,response.text)
        self.assertFalse(response.json()['session']['metadata']['candidate_cache_hit'])

    def test_prompt_split_isolation(self):
        """Only curated development examples can enter a model prompt."""
        self.assertTrue(development_examples())
        self.assertTrue(all(e['split']=='development' and e['use_for_prompt'] for e in development_examples()))
        self.assertLessEqual(len(select_examples('平台包含数据库')),4)

    def test_no_transitive_inference(self):
        """A contains B and B is in C never becomes A is in C."""
        facts,_=predict(['平台包含数据库。','数据库位于北京。'])
        self.assertNotIn(('平台','位于','北京'),facts)

if __name__=='__main__':unittest.main(verbosity=2)
