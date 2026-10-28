"""Regression tests for factual group bridges and discourse evidence boundaries."""
from pathlib import Path
import sys,unittest,os,tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'tools')]
os.environ['KNOWGPT_DATA_DIR']=tempfile.mkdtemp(prefix='knowgpt-groups-')
os.environ['KNOWGPT_LLM_PROVIDER']='demo'
from evaluate_relations import predict
from app.services.graph_store import graph_view
from app.services.convergence import reconcile

LINES=['甲平台包含甲检索和甲导出。','甲检索依赖甲导出。','乙平台包含乙数据库和乙查询。','乙数据库支持乙查询。','甲平台使用乙平台。']

class GroupBridgeTests(unittest.TestCase):
    """All overview edges require nonempty references to original entity edges."""
    def test_connected_topics_keep_bridge(self):
        _,snap=predict(LINES);graph=graph_view(snap)
        self.assertEqual(len(graph.groups),2)
        self.assertEqual(len(graph.group_relations),1)
        bridge=graph.group_relations[0];self.assertEqual(bridge['label'],'使用')
        witnesses={r['id']:r for r in graph.edges}
        self.assertTrue(bridge['relation_ids'])
        self.assertTrue(all(witnesses[rid]['cross_group'] for rid in bridge['relation_ids']))
        self.assertTrue(bridge['evidence_segment_ids'] and bridge['source_card_ids'])
        self.assertEqual(graph.model_dump(),graph_view(snap).model_dump())

    def test_no_relation_no_group_edge(self):
        _,snap=predict(LINES[:-1]);self.assertFalse(graph_view(snap).group_relations)

    def test_delete_bridge_removes_aggregate(self):
        _,snap=predict(LINES);before=graph_view(snap)
        ids=set(before.group_relations[0]['relation_ids'])
        for relation in snap.relations:
            if relation.id in ids:relation.status='deleted'
        reconcile(snap);self.assertFalse(graph_view(snap).group_relations)

    def test_pending_is_not_bridge(self):
        _,snap=predict(LINES[:-1]+['甲平台可能使用乙平台。'])
        self.assertFalse(graph_view(snap).group_relations)

    def test_application_discourse(self):
        facts,snap=predict(['人工智能属于技术领域。','例如，语音助手听懂问题，翻译软件转换语言，都是人工智能的应用。'])
        self.assertIn(('人工智能','应用于','语音助手'),facts)
        self.assertIn(('人工智能','应用于','翻译软件'),facts)
        self.assertFalse(any(e['type']=='CARD' for e in graph_view(snap).nodes))

    def test_no_application_inferred_from_cooccurrence(self):
        facts,_=predict(['人工智能属于技术领域。','语音助手听懂问题，翻译软件转换语言。'])
        self.assertFalse(any(r[1]=='应用于' for r in facts))

    def test_negative_application_not_accepted(self):
        facts,_=predict(['例如，语音助手听懂问题，翻译软件转换语言，都不是人工智能的应用。'])
        self.assertFalse(any(r[1]=='应用于' for r in facts))

    def test_unrelated_earlier_activity_not_application(self):
        facts,_=predict(['某系统分析数据。','例如，语音助手听懂问题，翻译软件转换语言，都是人工智能的应用。'])
        self.assertNotIn(('人工智能','应用于','某系统'),facts)

if __name__=='__main__':unittest.main(verbosity=2)
