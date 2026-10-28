/** Natural-language hybrid retrieval with evidence cards and real path highlights. */
'use client';
import { useState } from 'react';
import { api, type Snapshot, type SearchResult } from '@/api/client';
import { useStore } from '@/store/useStore';
import CardView from './CardView';
/** Submit a query and highlight actual returned entities and relations in the shared graph. */
export default function SearchPanel({ snap }: { snap: Snapshot }) {
  const [query, setQuery] = useState(''), [result, setResult] = useState<SearchResult | null>(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const { setPaths, selectEntity } = useStore();
  async function submit() { setBusy(true); setError(''); try { const r = await api<SearchResult>(`/sessions/${snap.session.id}/search`, 'POST', { query }); setResult(r); selectEntity(null); setPaths([...r.paths.flat(), ...r.relations.map(x => x.id)]); } catch (e) { setError(String(e)); } finally { setBusy(false); } }
  return <section><div className="search-form"><input aria-label="自然语言问题" placeholder="例如：张三与语音项目有什么联系？" value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => e.key === 'Enter' && query.trim() && !busy && void submit()} /><button className="primary" disabled={busy || !query.trim()} onClick={submit}>{busy ? '检索中…' : '检索知识'}</button></div>{error && <p role="alert">{error}</p>}{result && <><p className="muted">索引：{result.embedding_provider} · {result.cards.length} 张相关卡片 · 路径为无向连通路径，关系箭头仍表示原始方向。</p>{result.paths.map((p, i) => <button className="path" key={i} onClick={() => setPaths([...p, ...result.relations.filter(r => p.includes(r.head_entity_id) && p.includes(r.tail_entity_id)).map(r => r.id)])}>{p.map(id => snap.entities.find(e => e.id === id)?.name || id).join(' ↔ ')}</button>)}<CardView snap={snap} cards={result.cards} /></>}</section>;
}
