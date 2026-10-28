/** Read-only agent collaboration timeline; proposals never become browser-created facts. */
'use client';
import { useEffect, useState } from 'react';
import { api, type AgentRun, type RunDetail, type ReviewIssue, type Snapshot } from '@/api/client';
import { GraphProcessingProgress } from './ProcessingProgress';

export const stepLabels: Record<string, string> = { queued:'等待执行', summary:'整理要点', extractor:'抽取候选', reviewer:'核对原文', convergence:'规则收敛', restore:'恢复候选与人工校正', commit:'保存结果', completed:'已完成' };
const roleLabels: Record<string, string> = { summary:'摘要 Agent', extractor:'抽取 Agent', reviewer:'独立审核 Agent', coordinator:'协调器' };
const statuses: Record<string, string> = { queued:'排队中', running:'执行中', completed:'已完成', failed:'失败', conflicted:'遇到新修订', interrupted:'被重启中断' };

/** Show persisted role outputs, feedback rounds and exact source text for review issues. */
export default function AgentPanel({ snap, currentRunId }: { snap: Snapshot; currentRunId: string|null }) {
  const [runs,setRuns]=useState<AgentRun[]>([]), [selected,setSelected]=useState(''), [detail,setDetail]=useState<RunDetail|null>(null), [error,setError]=useState('');
  useEffect(()=> { let alive=true; api<AgentRun[]>(`/sessions/${snap.session.id}/runs`).then(items=>{ if(alive) {setRuns(items);setSelected(currentRunId || items[0]?.id || '');} }).catch(e=>alive&&setError(String(e))); return()=>{alive=false;}; },[snap.session.id,snap.revision,currentRunId]);
  useEffect(()=> { if(!selected)return; let alive=true; let timer:ReturnType<typeof setTimeout>|undefined;
    async function refresh(){ try {const value=await api<RunDetail>(`/runs/${selected}`); if(!alive)return;setDetail(value);setError('');if(['queued','running'].includes(value.run.status))timer=setTimeout(refresh,1200);}catch(e){if(alive)setError(String(e));} }
    setDetail(null);void refresh();return()=>{alive=false;clearTimeout(timer);};
  },[selected]);
  return <section className="agent-panel"><span className="eyebrow">EVIDENCE-DRIVEN COLLABORATION</span><h2>每一步，都能回看</h2><p className="muted">摘要提出要点，抽取提出候选，审核独立核对原文。审核意见可触发有限返工；无法确定的内容交给人工确认。</p>
    <label className="run-picker">执行记录<select aria-label="执行记录" value={selected} onChange={e=>setSelected(e.target.value)}><option value="">请选择执行记录</option>{runs.map(r=><option key={r.id} value={r.id}>{new Date(r.created_at).toLocaleString('zh-CN')} · {statuses[r.status]}{r.cached?' · 复用候选':''}</option>)}</select></label>
    {error&&<p role="alert" className="error">{error}</p>}{!runs.length&&!error&&<p className="empty">生成一次卡片与图谱后，这里会出现协作记录。</p>}
    {detail&&<>{detail.run.id !== currentRunId && <GraphProcessingProgress run={detail.run}/>}<div className="run-summary"><span className="pill">{statuses[detail.run.status]}</span><span>{detail.run.mode==='demo'?'规则演示：未调用大模型':detail.run.mode==='cached'?'复用已审核结果，不重新推理':'模型协作模式'}</span><span>返工 {detail.run.rounds} 轮</span><span>模型调用 {detail.run.model_calls} 次</span></div>
      {detail.run.error&&<p role="alert" className="error">{detail.run.error}</p>}{detail.run.cached&&<p className="muted">本次恢复已有候选并重放人工校正。查看更早的执行记录可看到原始审核过程；旧版记录可能没有逐角色历史。</p>}
      <ol className="agent-events">{detail.events.map(event=>{const issues=Array.isArray(event.output.issues)?event.output.issues as ReviewIssue[]:[];return <li key={event.id} data-testid="agent-event"><div className="event-title"><strong>{roleLabels[event.role]||event.role}</strong><span className="pill">第 {event.attempt+1} 轮 · {statuses[event.status]||event.status}</span></div><p className="muted">{event.provider==='demo'?'确定性规则':`${event.provider} / ${event.model}`} · {event.duration_ms} ms</p>
        {event.error&&<p className="error">{event.error}</p>}{event.role==='reviewer'&&event.status==='completed'&&!issues.length&&<p className="review-ok">本轮未发现需返工的问题；之后仍执行规则收敛和置信度过滤。</p>}
        {issues.map((issue,i)=><div className="review-issue" key={`${issue.target_id}-${i}`}><strong>{issue.verdict==='uncertain'?'待确认':issue.verdict==='reject'?'证据不支持':'需要返工'}</strong><p>{issue.reason}</p><details><summary>查看审核证据</summary>{snap.segments.filter(s=>issue.evidence_segment_ids.includes(s.id)).map(s=><blockquote key={s.id}><time>{(s.start_ms/1000).toFixed(1)}s — {(s.end_ms/1000).toFixed(1)}s</time>{s.raw_text||s.text}</blockquote>)}</details></div>)}
        <details className="raw-output"><summary>查看结构化结果</summary><pre>{JSON.stringify(event.output,null,2)}</pre></details></li>;})}</ol>
    </>}
  </section>;
}
