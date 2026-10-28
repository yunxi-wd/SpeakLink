/** Edit the selected real graph entity through the existing audited patch API. */
'use client';
import { useRef, useState, type FormEvent } from 'react';
import { api, type Entity, type Snapshot } from '@/api/client';
const types: Record<string, string> = { PERSON:'人物', ORG:'组织', CONCEPT:'概念', EVENT:'事件', TIME:'时间', LOCATION:'地点', OTHER:'其他' };

/** Keep original revision until save to reject edits based on an outdated graph. */
export default function EntityEditor({ entity, snap, disabled, onSaved, onCancel }: {
  entity: Entity; snap: Snapshot; disabled?: boolean; onSaved: (s: Snapshot) => void; onCancel: () => void;
}) {
  const [name, setName] = useState(entity.name), [type, setType] = useState(entity.type), [saving, setSaving] = useState(false), [error, setError] = useState('');
  const revision = useRef(snap.revision).current;
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!name.trim() || saving || disabled) return;
    setSaving(true); setError('');
    try { onSaved(await api<Snapshot>(`/entities/${entity.id}`, 'PATCH', { expected_revision: revision, name: name.trim(), type })); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setSaving(false); }
  }
  return <form className="inline-editor graph-entity-editor" aria-label="编辑图谱实体" onSubmit={save}>
    <label>实体名称<input aria-label="实体名称" value={name} autoFocus required maxLength={200} disabled={saving || disabled} onChange={e => setName(e.target.value)} /></label>
    <label>实体类型<select aria-label="实体类型" value={type} disabled={saving || disabled} onChange={e => setType(e.target.value)}>{Object.entries(types).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select></label>
    <p className="editor-note">保存后更新图中实体框的文字和关联检索，已有关系与原文证据继续保留。</p>
    {error && <p className="error" role="alert">{error}。输入内容仍保留。</p>}
    <div className="editor-actions"><button className="primary" type="submit" disabled={saving || disabled || !name.trim() || name.trim() === entity.name && type === entity.type}>{saving ? '保存中…' : '保存实体修改'}</button><button type="button" disabled={saving} onClick={onCancel}>取消</button></div>
  </form>;
}
