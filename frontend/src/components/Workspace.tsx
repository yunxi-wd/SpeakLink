/** One authoritative revision drives transcript, cards, graph, search and corrections. */
'use client';
import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { api, type Snapshot, type AgentRun, type RunDetail, type Session } from '@/api/client';
import { useStore } from '@/store/useStore';
import CardView from './CardView';
import Recorder from './Recorder';
import SearchPanel from './SearchPanel';
import CorrectionPanel from './CorrectionPanel';
import AgentPanel from './AgentPanel';
import { GraphProcessingProgress } from './ProcessingProgress';
const GraphView = dynamic(() => import('./GraphView'), { ssr: false });

/** Load and mutate one recording while clearing stale search selections after revisions. */
export default function Workspace({ id }: { id: string }) {
  const [snap, setSnap] = useState<Snapshot | null>(null), [tab, setTab] = useState('capture'), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [runId,setRunId]=useState<string|null>(null), [job,setJob]=useState<AgentRun|null>(null);
  const router=useRouter();
  const reset = useStore(s => s.reset);
  useEffect(() => { let active = true; reset(); setRunId(null);setJob(null);setBusy(false); api<Snapshot>(`/sessions/${id}`).then(s => { if (active) { setSnap(s); setTab(s.cards.length ? 'dual' : 'capture'); } }).catch(e => { if (active) setError(String(e)); }); api<AgentRun[]>(`/sessions/${id}/runs`).then(runs=>{const running=runs.find(r=>['queued','running'].includes(r.status));if(active&&running){setRunId(running.id);setJob(running);setBusy(true);}}).catch(e=>active&&setError(String(e))); return () => { active = false; }; }, [id, reset]);
  useEffect(()=>{if(!runId)return;let alive=true;let timer:ReturnType<typeof setTimeout>|undefined;async function poll(){try{const result=await api<RunDetail>(`/runs/${runId}`);if(!alive)return;setJob(result.run);if(['queued','running'].includes(result.run.status)){timer=setTimeout(poll,1200);return;}if(result.run.status==='completed'){const latest=await api<Snapshot>(`/sessions/${id}`);if(alive){reset();setSnap(latest);setTab('dual');}}else{setError(result.run.error||'任务未完成，请查看整理进度。');}if(alive)setBusy(false);}catch(e){if(alive){setError(`读取进度失败，后台任务可能仍在运行；刷新可恢复。${String(e)}`);setBusy(false);}}}void poll();return()=>{alive=false;clearTimeout(timer);};},[runId,id,reset]);
  function update(s: Snapshot) { reset(); setSnap(s); }
  async function process() { setBusy(true); setError(''); try { const started=await api<AgentRun>(`/sessions/${id}/jobs`,'POST');setJob(started);setRunId(started.id);setTab('agents'); } catch (e) { setError(String(e));setBusy(false); } }
  async function clone() { setBusy(true);setError('');try{const copied=await api<Session>(`/sessions/${id}/clone`,'POST');await api(`/sessions/${copied.id}/jobs`,'POST');router.push(`/sessions/${copied.id}`);}catch(e){setError(String(e));setBusy(false);} }
  if (!snap) return <main className="shell"><p role="alert">{error || '载入记录…'}</p></main>;
  const pending = [...snap.entities, ...snap.relations].filter(x => x.status === 'pending').length;
  return <main className="shell workspace"><div className="breadcrumb"><Link href="/">所有速记</Link><span>/</span><span>{snap.session.title}</span></div><div className="workspace-heading"><div><span className="eyebrow">A SPACE FOR YOUR THOUGHTS</span><h1>{snap.session.title}</h1><p className="muted">{new Date(snap.session.created_at).toLocaleString('zh-CN')} · 修订 {snap.revision} · {snap.session.metadata.provider === 'demo' ? '规则演示模式' : snap.session.metadata.provider ? `模型：${snap.session.metadata.provider}` : '等待整理'}</p></div><div className="export-actions">{['json','graphml','markdown'].map(f => <a key={f} href={`/api/sessions/${id}/export?format=${f}`} download>{f.toUpperCase()} ↗</a>)}</div></div>
    <nav className="tabs">{[['capture','录音 / 上传'],['transcript','转写原文'],['dual','图谱 & 卡片'],['search','知识检索'],['agents','整理进度'],['corrections',`人工校正${pending ? ` · ${pending} 待确认` : ''}`]].map(([key, label]) => <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}</button>)}<button className="primary process-button" disabled={busy || !snap.segments.length} onClick={process}>{busy ? '正在整理…' : snap.cards.length ? '重新处理' : '生成卡片与图谱'}</button></nav>
    {job&&<GraphProcessingProgress run={job}/>}{snap.cards.length>0&&<button className="clone-button" disabled={busy} onClick={clone}>重新分析原文（保留原记录）</button>}{tab==='agents'&&<AgentPanel snap={snap} currentRunId={runId}/>} {error && <p role="alert" className="error">{error}</p>}{tab === 'capture' && <Recorder snap={snap} onChange={s => { update(s); setTab('transcript'); }} />}{tab === 'transcript' && <section className="transcript"><h2>每个想法，都有出处</h2>{snap.segments.map(s => <article key={s.id}><time>{(s.start_ms / 1000).toFixed(1)}s — {(s.end_ms / 1000).toFixed(1)}s</time><div>{s.speaker && <strong>{s.speaker}</strong>}<p>{s.text}</p>{s.raw_text !== s.text && <small>原始：{s.raw_text}</small>}<small className="segment-id">{s.id}</small></div></article>)}{!snap.segments.length && <p className="muted">先录音、上传文件或载入文本。</p>}</section>}{tab === 'dual' && <div className="dual-view"><GraphView snap={snap} /><CardView snap={snap} /></div>}{tab === 'search' && <div className="dual-view"><GraphView snap={snap} /><SearchPanel key={snap.revision} snap={snap} /></div>}{tab === 'corrections' && <CorrectionPanel snap={snap} onChange={update} />}
  </main>;
}
