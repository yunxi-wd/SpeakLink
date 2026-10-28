"""Capabilities, cross-segment referents and the user's exact audio regression."""
from pathlib import Path
import os,sys,tempfile,unittest,json
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'tools')]
os.environ['KNOWGPT_DATA_DIR']=tempfile.mkdtemp(prefix='knowgpt-capability-test-')
os.environ['KNOWGPT_LLM_PROVIDER']='demo'
from evaluate_relations import predict
from app.services.graph_store import graph_view
from app.schemas.domain import TranscriptSegment
from app.services.summarizer import summarize
from app.services.extractor import extract

DEFINITION='人工智能是研究和开发计算机系统。'
ABILITY='使它们能够完成通常需要人类智能才能完成的任务的一门技术领域。'
TASKS='这些任务包括理解语言、识别图像和做出决策。'

class CapabilityTests(unittest.TestCase):
    """Ability must never become an assertion of completed work or ambiguous actors."""
    def test_split_definition_connects_both_subjects(self):
        facts,_=predict([DEFINITION,ABILITY,TASKS])
        self.assertIn(('人工智能','支持完成','任务'),facts)
        self.assertIn(('计算机系统','能够完成','任务'),facts)
        self.assertNotIn(('人工智能','完成','任务'),facts)

    def test_asr_homophone_is_bound_only_in_definition(self):
        facts,snap=predict([DEFINITION,ABILITY.replace('使它们','是他们'),TASKS])
        self.assertIn(('人工智能','支持完成','任务'),facts)
        self.assertIn('是他们',snap.segments[1].raw_text)

    def test_no_formal_antecedent_no_nonhuman_guess(self):
        facts,_=predict(['研发团队开发计算机系统。','他们能够完成任务。'])
        self.assertNotIn(('计算机系统','能够完成','任务'),facts)

    def test_multiple_systems_remain_unresolved(self):
        facts,_=predict(['人工智能是研究和开发甲系统和乙系统。',ABILITY,TASKS])
        self.assertFalse(any(r[1]=='支持完成' for r in facts))

    def test_topic_transition_breaks_reference(self):
        facts,_=predict([DEFINITION,'换个话题。',ABILITY,TASKS])
        self.assertFalse(any(r[1]=='支持完成' for r in facts))

    def test_negation_and_speculation_not_promoted(self):
        for line in ['人工智能不能够完成任务。','人工智能可能能够完成任务。','人工智能能够完成任务吗？','人工智能未能完成任务。']:
            facts,_=predict([line]);self.assertFalse(any(r[1]=='能够完成' for r in facts),line)

    def test_relative_clause_needs_is_not_main_uncertainty(self):
        facts,_=predict(['人工智能能够完成通常需要人类智能的任务。'])
        self.assertIn(('人工智能','能够完成','任务'),facts)

    def test_explicit_object_enumeration(self):
        facts,_=predict(['计算机系统可以完成图像识别和语言理解。'])
        self.assertEqual(facts,{('计算机系统','能够完成','图像识别'),('计算机系统','能够完成','语言理解')})

    def test_speaker_change_not_bound(self):
        segments=[TranscriptSegment(id='s0',session_id='x',text=DEFINITION,start_ms=0,end_ms=1000,speaker='A'),TranscriptSegment(id='s1',session_id='x',text=ABILITY,start_ms=1000,end_ms=2000,speaker='B')]
        candidates=extract(summarize(segments,'x','2026-10-19'),segments)
        self.assertFalse(any(r.predicate=='支持完成' for r in candidates.relations))

    def test_full_audio_graph_has_witnessed_task_bridge(self):
        audio=ROOT/'audio-segments.json'
        if not audio.exists():self.skipTest('Audio fixture not present; run transcribe_capability_audio.py first')
        original=json.loads(audio.read_text(encoding='utf-8'))
        facts,snap=predict([s['text'] for s in original])
        self.assertIn(('人工智能','支持完成','任务'),facts)
        names={e.id:e.name for e in snap.entities}
        relation=next(r for r in snap.relations if r.status=='active' and r.predicate=='支持完成' and names[r.head_entity_id]=='人工智能')
        self.assertGreaterEqual(len(relation.source_segment_ids),2)
        graph=graph_view(snap)
        self.assertTrue(any(relation.id in b['relation_ids'] for b in graph.group_relations))
        self.assertFalse(any(e.status=='active' and '他们能够完成' in e.name for e in snap.entities))
        self.assertTrue({('任务','包含','理解语言'),('任务','包含','识别图像')}<=facts)

if __name__=='__main__':unittest.main(verbosity=2)
