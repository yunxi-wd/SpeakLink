/** Evidence-backed cards with bidirectional graph selection and source disclosure. */
'use client';
import type { Card, Snapshot } from '@/api/client';
import { useStore } from '@/store/useStore';
const labels: Record<string, string> = { topic: '主题', conclusion: '结论', todo: '待办', uncertain: '待确认' };
/** Show cards linked to the selected node or the explicit search result list. */
export default function CardView({ snap, cards = snap.cards }: { snap: Snapshot; cards?: Card[] }) {
  const { selectedEntity, selectedCard, selectCard, selectEntity } = useStore();
  const visible = cards.filter(c => c.status !== 'deleted' && (!selectedEntity || c.entity_ids.includes(selectedEntity)));
  return <section className="cards-panel"><div className="panel-heading"><div><span className="eyebrow">THOUGHT CARDS</span><h2>留下有用的部分</h2></div><span className="pill">{visible.length} 张卡片</span></div>{selectedEntity && <button onClick={() => selectEntity(null)}>清除节点筛选 ×</button>}
    <div className="card-list">{visible.length === 0 && <div className="empty">还没有卡片。录一段话，或载入文本演示。</div>}{visible.map(c => <article key={c.id} className={`thought-card ${selectedCard === c.id ? 'selected' : ''}`} data-testid="thought-card"><button className="card-select" onClick={() => selectCard(c.id)}><div className="card-meta"><span className={`badge ${c.card_type}`}>{labels[c.card_type]}</span><span>{Math.round(c.confidence * 100)}% · {c.status === 'pending' ? '待审核' : '已收敛'}</span></div><h3>{c.title}</h3><p>{c.content}</p></button><div className="entity-tags">{c.entity_ids.map(id => { const e = snap.entities.find(n => n.id === id); return e && <button key={id} onClick={() => selectEntity(id)}>{e.name}</button>; })}</div><details><summary>查看原文 · {c.source_segment_ids.length} 段</summary>{snap.segments.filter(s => c.source_segment_ids.includes(s.id)).map(s => <blockquote key={s.id}><time>{(s.start_ms / 1000).toFixed(1)}s–{(s.end_ms / 1000).toFixed(1)}s</time>{s.text}<small>{s.id}</small></blockquote>)}</details></article>)}</div>
  </section>;
}
