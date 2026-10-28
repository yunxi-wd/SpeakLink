/** Microphone capture with permission feedback, upload progress and recoverable transcription. */
'use client';
import { useEffect, useRef, useState } from 'react';
import { api, type Snapshot, type Health } from '@/api/client';
export const DEMO = ['张三参与语音项目。', '他属于星河公司。', '语音项目依赖离线方案。', '那个方案导致成本下降。', '另外说，知识图谱属于人工智能。', '图谱检索依赖知识图谱。', '明天李四参与图谱检索。', '语音项目可能依赖云端服务，仍待确认。'];
/** Translate browser failures into actions the recorder can take. */
export function audioError(error: unknown): string {
  if (error instanceof DOMException) {
    if (error.name === 'NotAllowedError') return '麦克风权限被拒绝。请在浏览器地址栏允许此网站使用麦克风，或改用上传音频。';
    if (error.name === 'NotFoundError') return '没有检测到麦克风，请连接麦克风或上传音频。';
    if (error.name === 'NotReadableError') return '麦克风无法打开，可能被其他应用占用，请关闭占用后重试。';
  }
  return error instanceof Error ? error.message : String(error);
}
/** Capture actual audio; keep uploaded recordings available when ASR needs retrying. */
export default function Recorder({ snap, onChange }: { snap: Snapshot; onChange: (s: Snapshot) => void }) {
  const recorder = useRef<MediaRecorder | null>(null), stream = useRef<MediaStream | null>(null), mounted = useRef(true);
  const [recording, setRecording] = useState(false), [busy, setBusy] = useState(false), [requesting, setRequesting] = useState(false);
  const [error, setError] = useState(''), [progress, setProgress] = useState(''), [seconds, setSeconds] = useState(0);
  const [health, setHealth] = useState<Health | null>(null), [uploaded, setUploaded] = useState(!!snap.session.audio_path);
  const [text, setText] = useState(DEMO.join('\n'));
  useEffect(() => {
    mounted.current = true;
    api<Health>('/health').then(h => mounted.current && setHealth(h)).catch(e => mounted.current && setError(audioError(e)));
    return () => { mounted.current = false; if (recorder.current?.state === 'recording') { recorder.current.onstop = null; recorder.current.stop(); } stream.current?.getTracks().forEach(t => t.stop()); };
  }, []);
  useEffect(() => { if (!recording) return; const timer = setInterval(() => setSeconds(s => s + 1), 1000); return () => clearInterval(timer); }, [recording]);
  /** Retry server-held audio without requiring a second upload. */
  async function transcribe() {
    setBusy(true); setError(''); setProgress('正在识别语音并生成时间戳，请稍候。较长音频需要更多时间…');
    try { const result = await api<Snapshot>(`/sessions/${snap.session.id}/transcribe`, 'POST'); if (mounted.current) onChange(result); }
    catch (e) { if (mounted.current) { setError(audioError(e)); setProgress('音频已保存，可点击“重试转写”。'); } }
    finally { if (mounted.current) setBusy(false); }
  }
  /** Validate and upload a file before invoking ASR; preserve the retry affordance. */
  async function upload(file: File) {
    setError('');
    if (!file.size) { setError('音频为空，请录制一段声音后再试。'); return; }
    if (file.size > 100 * 1024 * 1024) { setError('文件超过 100 MB，请截取较短音频。'); return; }
    setBusy(true); setProgress(`正在上传 ${file.name}…`);
    try { const form = new FormData(); form.append('file', file); await api(`/sessions/${snap.session.id}/audio`, 'POST', form); if (!mounted.current) return; setUploaded(true); await transcribe(); }
    catch (e) { if (mounted.current) { setError(audioError(e)); setProgress(''); } }
    finally { if (mounted.current) setBusy(false); }
  }
  /** Request microphone access, capture supported media, then upload on stop. */
  async function record() {
    setError(''); setRequesting(true); setProgress('请在浏览器弹窗中允许使用麦克风…');
    try {
      if (!navigator.mediaDevices || !window.MediaRecorder) throw new Error('此浏览器不支持录音；请用 Chrome/Edge 打开 localhost 地址，或上传音频。');
      const acquired = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!mounted.current) { acquired.getTracks().forEach(t => t.stop()); return; }
      stream.current = acquired;
      const mime = ['audio/webm', 'audio/mp4', 'audio/ogg'].find(t => MediaRecorder.isTypeSupported(t));
      const active = new MediaRecorder(acquired, mime ? { mimeType: mime } : undefined);
      recorder.current = active;
      const chunks: BlobPart[] = [];
      active.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
      active.onerror = () => { active.onstop = null; acquired.getTracks().forEach(t => t.stop()); if (mounted.current) { setRecording(false); setError('录音中断，请检查麦克风后重新录制。'); setProgress(''); } };
      active.onstop = () => { acquired.getTracks().forEach(t => t.stop()); if (!mounted.current) return; setRecording(false); const actual = active.mimeType || 'audio/webm'; const extension = actual.includes('mp4') ? 'm4a' : actual.includes('ogg') ? 'ogg' : 'webm'; void upload(new File(chunks, `recording.${extension}`, { type: actual })); };
      active.start(1000); setSeconds(0); setRecording(true); setProgress('录音中，请说话；结束后点击“停止录音并转写”。');
    } catch (e) { stream.current?.getTracks().forEach(t => t.stop()); if (mounted.current) { setError(audioError(e)); setProgress(''); } }
    finally { if (mounted.current) setRequesting(false); }
  }
  /** Import explicitly labelled text demo segments; never substitute them for failed ASR. */
  async function importText() { setBusy(true); setError(''); setProgress('正在载入文本…'); try { const segments = text.split('\n').filter(t => t.trim()).map((t, i) => ({ text: t, start_ms: i * 5000, end_ms: (i + 1) * 5000 })); const result = await api<Snapshot>(`/sessions/${snap.session.id}/transcript`, 'PUT', { segments }); if (mounted.current) onChange(result); } catch (e) { if (mounted.current) setError(audioError(e)); } finally { if (mounted.current) { setBusy(false); setProgress(''); } } }
  const locked = busy || requesting || !!snap.cards.length;
  return <section className="record-panel"><div className="record-orb">◉</div><h2>想到什么，就说什么。</h2>
    <p className="muted">录音停下后，本地模型会转写为带时间戳的文字。</p>
    {!!snap.cards.length && <p role="status">这条记录已生成卡片，原始音频已锁定。要录制或上传另一段音频，请<a href="/">返回首页新建速记</a>；当前内容仍可在“转写原文”查看。</p>}
    {health && <p role="status" className={health.asr_installed ? 'muted' : 'error'}>{health.asr_installed ? `本地语音引擎已安装 · ${health.asr_model}` : health.asr_message}</p>}
    <div className="record-actions"><button className="primary" disabled={locked} onClick={() => recording ? recorder.current?.stop() : void record()}>{requesting ? '等待麦克风授权…' : recording ? `停止录音并转写 · ${seconds}s` : '开始录音'}</button>
      <label className="upload-button">上传音频<input aria-label="上传音频" type="file" accept="audio/*,.mp4" disabled={locked || recording} onChange={e => { const f = e.target.files?.[0]; e.target.value = ''; if (f) void upload(f); }} /></label></div>
    <p className="muted">WAV / MP3 / M4A / WebM / OGG / FLAC · 最大 100 MB</p>
    {progress && <p role="status" aria-live="polite">{progress}</p>}{error && <p className="error" role="alert">{error}</p>}
    {uploaded && !recording && !snap.cards.length && <button disabled={locked} onClick={() => void transcribe()}>重试转写</button>}
    <details className="text-import" open={!snap.segments.length}><summary>文本演示 / 导入转写</summary><p className="muted">每行一段。此入口使用每段 5 秒的演示时间戳，不代表真实 ASR 时间；音频上传保留实际时间戳。</p><textarea aria-label="转写文本" value={text} onChange={e => setText(e.target.value)} rows={7} /><button disabled={locked || recording || !text.trim()} onClick={importText}>载入文本</button></details>
  </section>;
}
