"""Evaluate candidate+convergence precision/recall with a fixed non-prompt split.

Run with bundled Python. No recordings, production database or model weights are
modified. This measures extraction on annotated text, not ASR or neural training.
"""
from pathlib import Path
import argparse,json,os,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,os.environ.get('KNOWGPT_EVAL_BACKEND',str(ROOT/'backend')))
os.environ['KNOWGPT_DATA_DIR']=tempfile.mkdtemp(prefix='knowgpt-relation-eval-')
os.environ['KNOWGPT_LLM_PROVIDER']='demo'
from app.schemas.domain import Session,Snapshot,TranscriptSegment
from app.services.summarizer import summarize
from app.services.extractor import extract
from app.services.convergence import converge,reconcile
from app.services.reviewer import review,quarantine

def predict(lines: list[str]) -> tuple[set[tuple[str,str,str]],Snapshot]:
    """Run the same summarizer, extractor, reviewer and convergence as the service."""
    snap=Snapshot(session=Session(id='eval',title='relation evaluation'),segments=[TranscriptSegment(id=f's{i}',session_id='eval',text=t,raw_text=t,start_ms=i*1000,end_ms=(i+1)*1000) for i,t in enumerate(lines)])
    snap.cards=summarize(snap.segments,'eval',snap.session.created_at)
    candidates=extract(snap.cards,snap.segments)
    quarantine(snap.cards,candidates,review(snap.cards,snap.segments,candidates))
    converge(snap,candidates);reconcile(snap)
    names={e.id:e.name for e in snap.entities}
    aliases={'包括':'包含','涵盖':'包含','是一种':'属于','是一个':'属于','是一名':'属于','造成':'导致','引起':'导致','参加':'参与','采用':'使用','提高':'提升','推动':'促进'}
    return {(names[r.head_entity_id],aliases.get(r.predicate or r.type,r.predicate or r.type),names[r.tail_entity_id]) for r in snap.relations if r.status=='active'},snap

def evaluate(corpus: Path, split: str) -> dict:
    """Micro exact-triple metrics include extra edges as false positives."""
    tp=fp=fn=0;cases=[];stable=True
    for line in corpus.read_text(encoding='utf-8').splitlines():
        sample=json.loads(line)
        if split!='all' and sample['split'] not in split.split(','):continue
        expected={tuple(t) for t in sample['triples']};actual,_=predict(sample['segments'])
        repeated,_=predict(sample['segments']);stable &= repeated==actual
        tp+=len(expected&actual);fp+=len(actual-expected);fn+=len(expected-actual)
        cases.append(dict(id=sample['id'],category=sample['category'],missing=sorted(expected-actual),extra=sorted(actual-expected)))
    precision=tp/(tp+fp) if tp+fp else 1.;recall=tp/(tp+fn) if tp+fn else 1.
    return dict(cases=len(cases),split=split,true_positive=tp,false_positive=fp,false_negative=fn,precision=precision,recall=recall,f1=2*precision*recall/(precision+recall) if precision+recall else 0,repeat_stability=stable,failures=[c for c in cases if c['missing'] or c['extra']],note='Synthetic grammar and curated challenge cases; not a real-world accuracy guarantee or model training result.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--corpus',type=Path,default=ROOT/'configs/relation_examples.jsonl');parser.add_argument('--split',default='evaluation,challenge');parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=evaluate(args.corpus,args.split)
    if args.output:args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
