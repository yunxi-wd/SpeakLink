/** Recording history reads durable session metadata from the API. */
import Link from 'next/link';
import type { Session } from '@/api/client';
/** Render recent recordings with links that restore their full graph snapshots. */
export default function Timeline({ sessions }: { sessions: Session[] }) { return <div className="timeline">{sessions.map(s => <Link className="history-row" href={`/sessions/${s.id}`} key={s.id}><div className="history-icon">◷</div><div><h3>{s.title}</h3><p>{new Date(s.created_at).toLocaleString('zh-CN')}</p></div><span className="pill">{s.status === 'ready' ? '已整理' : s.status === 'created' ? '新记录' : '处理中'}</span><span>↗</span></Link>)}{sessions.length === 0 && <div className="empty">第一条灵感，从一句话开始。</div>}</div>; }
