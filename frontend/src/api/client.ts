/** Typed server contracts and one shared HTTP error-handling boundary. */
export interface Session { id: string; title: string; created_at: string; status: string; audio_path?: string | null; metadata: Record<string, unknown> }
export interface Health { asr_installed: boolean; asr_model: string; asr_message: string }
export interface Segment { id: string; text: string; raw_text: string; start_ms: number; end_ms: number; speaker: string | null }
export interface Card { id: string; title: string; content: string; card_type: string; confidence: number; status: string; source_segment_ids: string[]; entity_ids: string[]; relation_ids: string[]; cluster_id: string | null; manual_edited?: boolean }
export interface Entity { id: string; name: string; type: string; status: string; confidence: number; source_card_ids: string[]; source_segment_ids: string[]; cluster_id: string | null }
export interface Relation { id: string; head_entity_id: string; tail_entity_id: string; predicate?: string | null; type: string; status: string; evidence_card_ids: string[]; confidence: number; source_segment_ids: string[] }
export interface Cluster { id: string; name: string; color: string; reason: string; card_ids: string[]; entity_ids: string[] }
export interface Snapshot { session: Session; segments: Segment[]; cards: Card[]; entities: Entity[]; relations: Relation[]; clusters: Cluster[]; revision: number }
export interface SearchResult { cards: Card[]; scores: number[]; paths: string[][]; relations: Relation[]; embedding_provider: string }
export interface Correction { id: string; action: string; target_type: string; active: boolean; created_at: string }
export interface AgentRun { id: string; session_id: string; status: 'queued'|'running'|'completed'|'failed'|'conflicted'|'interrupted'; base_revision: number; result_revision: number|null; mode: 'demo'|'model'|'cached'; current_step: string; steps_completed: number; rounds: number; model_calls: number; cached: boolean; pending_count: number; error: string|null; created_at: string; finished_at: string|null }
export interface ReviewIssue { target_id: string; target_type: string; verdict: string; reason: string; confidence: number; evidence_segment_ids: string[]; source_card_ids: string[] }
export interface AgentEvent { id: string; role: string; attempt: number; provider: string; model: string; status: string; output: Record<string, unknown>; error: string|null; duration_ms: number; sequence: number }
export interface RunDetail { run: AgentRun; events: AgentEvent[] }
export interface TranscriptionProgress { stage: 'idle'|'loading_model'|'reading_audio'|'recognizing'|'saving'|'completed'|'failed'; message: string; percent: number|null; processed_ms: number; duration_ms: number; segments_count: number }

/** Upload byte progress comes from the browser's network events, not a timer. */
export function uploadAudio(sessionId: string, file: File, onProgress: (percent: number | null) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest(), form = new FormData();
    form.append('file', file);
    xhr.open('POST', `/api/sessions/${sessionId}/audio`);
    xhr.upload.onprogress = event => onProgress(event.lengthComputable ? Math.round(event.loaded / event.total * 100) : null);
    xhr.onerror = () => reject(new Error('音频上传连接中断，请检查本地服务后重试。'));
    xhr.onabort = () => reject(new Error('音频上传已取消。'));
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) { onProgress(100); resolve(); return; }
      try { const error = JSON.parse(xhr.responseText); reject(new Error(typeof error.detail === 'string' ? error.detail : JSON.stringify(error.detail))); }
      catch { reject(new Error(`上传失败（${xhr.status}）`)); }
    };
    xhr.send(form);
  });
}

/** Fetch validated server state; never synthesize graph facts in the browser. */
export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const isForm = body instanceof FormData;
  const response = await fetch(`/api${path}`, { method, headers: body && !isForm ? { 'Content-Type': 'application/json' } : undefined, body: body ? isForm ? body : JSON.stringify(body) : undefined });
  if (!response.ok) { const error = await response.json().catch(() => ({ detail: response.statusText })); throw new Error(typeof error.detail === 'string' ? error.detail : JSON.stringify(error.detail)); }
  return response.json() as Promise<T>;
}
