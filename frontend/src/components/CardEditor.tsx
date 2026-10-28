/** Revision-checked inline card editor. Drafts remain local until an audited save. */
'use client';
import { useRef, useState, type FormEvent } from 'react';
import { api, type Card, type Snapshot } from '@/api/client';

export const cardTypes = { topic: '主题', conclusion: '结论', todo: '待办', uncertain: '待确认' };

/** Update editable text/type only; evidence, IDs and graph links remain server-owned. */
export default function CardEditor({ card, revision, disabled, onSaved, onCancel }: {
  card: Card; revision: number; disabled?: boolean; onSaved: (snap: Snapshot) => void; onCancel: () => void;
}) {
  const [title, setTitle] = useState(card.title), [content, setContent] = useState(card.content), [type, setType] = useState(card.card_type);
  const [saving, setSaving] = useState(false), [error, setError] = useState('');
  const originalRevision = useRef(revision).current;
  const changed = title.trim() !== card.title || content.trim() !== card.content || type !== card.card_type;
  const valid = title.trim().length > 0 && title.length <= 200 && content.trim().length > 0 && content.length <= 10000;
  async function save(event: FormEvent) {
    event.preventDefault();
    if (saving || disabled || !changed || !valid) return;
    setSaving(true); setError('');
    try {
      const snapshot = await api<Snapshot>(`/cards/${card.id}`, 'PATCH', { expected_revision: originalRevision, title: title.trim(), content: content.trim(), card_type: type });
      onSaved(snapshot);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setSaving(false); }
  }
  return <form className="inline-editor" aria-label="编辑要点卡片" onSubmit={save}>
    <label>卡片标题<input aria-label="卡片标题" value={title} maxLength={200} autoFocus required disabled={saving || disabled} onChange={e => setTitle(e.target.value)} /></label>
    <label>卡片类型<select aria-label="卡片类型" value={type} disabled={saving || disabled} onChange={e => setType(e.target.value)}>{Object.entries(cardTypes).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select></label>
    <label>卡片正文<textarea aria-label="卡片正文" value={content} maxLength={10000} rows={5} required disabled={saving || disabled} onChange={e => setContent(e.target.value)} /></label>
    <p className="editor-note">修改会保存为人工校正，原文和来源引用会保留。实体名称可在图谱选中后单独编辑。</p>
    {error && <p className="error" role="alert">{error}。输入内容仍保留，请核对记录的最新版本后重试。</p>}
    <div className="editor-actions"><button type="submit" className="primary" disabled={saving || disabled || !changed || !valid}>{saving ? '保存中…' : '保存修改'}</button><button type="button" disabled={saving} onClick={onCancel}>取消</button></div>
  </form>;
}
