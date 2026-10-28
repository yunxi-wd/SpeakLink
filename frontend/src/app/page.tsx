/** Recording timeline and creation entrypoint. */
'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, type Session } from '@/api/client';
import Timeline from '@/components/Timeline';
/** Create a recording, then open its capture workspace. */
export default function Home() {
  const [sessions, setSessions] = useState<Session[]>([]), [title, setTitle] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false); const router = useRouter();
  useEffect(() => { api<Session[]>('/sessions').then(setSessions).catch(e => setError(String(e))); }, []);
  async function create() { setBusy(true); setError(''); try { const s = await api<Session>('/sessions', 'POST', { title: title.trim() || `灵感速记 ${new Date().toLocaleDateString('zh-CN')}` }); router.push(`/sessions/${s.id}`); } catch (e) { setError(String(e)); setBusy(false); } }
  return <main className="shell"><section className="hero"><div><span className="eyebrow">SPEAK. CAPTURE. CONNECT.</span><h1>一段声音，<br />一张<span>知识地图。</span></h1><p>留住转瞬即逝的灵感。<br />把口语整理成要点，让零散知识建立连接。</p><div className="create-form"><input aria-label="记录标题" placeholder="给这次速记起个名字…" value={title} onChange={e => setTitle(e.target.value)} onKeyDown={e => e.key === 'Enter' && !busy && void create()} /><button className="primary" disabled={busy} onClick={create}>{busy ? '创建中…' : '＋ 新建速记'}</button></div><div className="hero-tags"><span>◎ 本地存储</span><span>↗ 证据可回溯</span><span>◇ 人工可校正</span></div></div><div className="hero-art" aria-hidden="true"><div className="art-ring ring-one" /><div className="art-ring ring-two" /><div className="art-center">想法</div><div className="art-node n1">声音</div><div className="art-node n2">知识</div><div className="art-node n3">行动</div><div className="art-node n4">连接</div><div className="art-caption">EVERY THOUGHT HAS A PLACE.</div></div></section>{error && <p role="alert" className="error">{error}</p>}<section className="history-section"><div className="section-title"><div><span className="eyebrow">YOUR KNOWLEDGE JOURNEY</span><h2>最近的思考</h2></div><span className="pill">{sessions.length} 条记录</span></div><Timeline sessions={sessions} /></section></main>;
}
