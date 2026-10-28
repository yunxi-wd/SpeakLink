/** Typed server contracts and one shared HTTP error-handling boundary. */
export interface Session { id: string; title: string; created_at: string; status: string; audio_path?: string | null; metadata: Record<string, unknown> }
export interface Health { asr_installed: boolean; asr_model: string; asr_message: string }
export interface Segment { id: string; text: string; raw_text: string; start_ms: number; end_ms: number; speaker: string | null }
export interface Card { id: string; title: string; content: string; card_type: string; confidence: number; status: string; source_segment_ids: string[]; entity_ids: string[]; relation_ids: string[]; cluster_id: string | null }
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

/** Fetch validated server state; never synthesize graph facts in the browser. */
export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const isForm = body instanceof FormData;
  const response = await fetch(`/api${path}`, { method, headers: body && !isForm ? { 'Content-Type': 'application/json' } : undefined, body: body ? isForm ? body : JSON.stringify(body) : undefined });
  if (!response.ok) { const error = await response.json().catch(() => ({ detail: response.statusText })); throw new Error(typeof error.detail === 'string' ? error.detail : JSON.stringify(error.detail)); }
  return response.json() as Promise<T>;
}
