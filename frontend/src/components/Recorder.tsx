/** Microphone capture with permission feedback, upload progress and recoverable transcription. */
'use client';
import { useEffect, useRef, useState } from 'react';
import { api, uploadAudio, type Snapshot, type Health, type TranscriptionProgress } from '@/api/client';
import ProcessingProgress from './ProcessingProgress';
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
  const [phase, setPhase] = useState<'idle'|'upload'|'asr'|'failed'>('idle');
  const [uploadPercent, setUploadPercent] = useState<number|null>(0);
  const [asrProgress, setAsrProgress] = useState<TranscriptionProgress|null>(null);
  const [pollWarning, setPollWarning] = useState('');
  const watchEpoch = useRef(0), changed = useRef(onChange);
  changed.current = onChange;
  /** Observe real backend telemetry; on remount resume an existing ASR request. */
  function watchTranscription(recover = false) {
    const epoch = ++watchEpoch.current;
    let observedActive = recover;
    async function poll() {
      if (!mounted.current || epoch !== watchEpoch.current) return;
      try {
        const value = await api<TranscriptionProgress>(`/sessions/${snap.session.id}/transcription-progress`);
        if (!mounted.current || epoch !== watchEpoch.current) return;
        setPollWarning('');
        if (['loading_model','reading_audio','recognizing','saving'].includes(value.stage)) {
          observedActive = true; setAsrProgress(value); setPhase('asr');
        } else if (observedActive) {
          setAsrProgress(value);
          if (value.stage === 'completed') {
            const result = await api<Snapshot>(`/sessions/${snap.session.id}`);
            if (mounted.current && epoch === watchEpoch.current) { setBusy(false); setPhase('idle'); changed.current(result); }
            return;
          }
          setBusy(false); setPhase('failed');
          setError(value.stage === 'idle' ? '本地服务已重启，转写进度已中断，音频仍保留，可重试。' : value.message);
          return;
        }
      } catch {
        if (mounted.current && epoch === watchEpoch.current) setPollWarning('暂时无法读取实时进度，正在重连…');
      }
      if (mounted.current && epoch === watchEpoch.current) setTimeout(() => void poll(), 800);
    }
    void poll();
  }
  useEffect(() => {
    mounted.current = true;
    api<Health>('/health').then(h => mounted.current && setHealth(h)).catch(e => mounted.current && setError(audioError(e)));
    api<TranscriptionProgress>(`/sessions/${snap.session.id}/transcription-progress`).then(value => {
      if (mounted.current && value.stage !== 'idle' && !['completed','failed'].includes(value.stage)) {
        setBusy(true); setUploaded(true); setPhase('asr'); setAsrProgress(value); watchTranscription(true);
      }
    }).catch(() => {});
    return () => { mounted.current = false; watchEpoch.current++; if (recorder.current?.state === 'recording') { recorder.current.onstop = null; recorder.current.stop(); } stream.current?.getTracks().forEach(t => t.stop()); };
  }, []);
  useEffect(() => { if (!recording) return; const timer = setInterval(() => setSeconds(s => s + 1), 1000); return () => clearInterval(timer); }, [recording]);
  /** Retry server-held audio without requiring a second upload. */
  async function transcribe() {
    let recovering = false;
    setBusy(true); setError(''); setProgress(''); setPhase('asr'); setAsrProgress(null); setPollWarning('');
    const request = api<Snapshot>(`/sessions/${snap.session.id}/transcribe`, 'POST');
    watchTranscription();
    try { const result = await request; if (mounted.current) { watchEpoch.current++; setPhase('idle'); onChange(result); } }
    catch (e) {
      if (mounted.current) {
        const live = await api<TranscriptionProgress>(`/sessions/${snap.session.id}/transcription-progress`).catch(() => null);
        if (mounted.current && live && ['loading_model','reading_audio','recognizing','saving'].includes(live.stage)) {
          recovering = true; setAsrProgress(live); watchTranscription(true);
        } else if (mounted.current) {
          watchEpoch.current++; setError(audioError(e)); setPhase('failed'); setProgress('音频已保存，可点击“重试转写”。');
        }
      }
    }
    finally { if (mounted.current && !recovering) setBusy(false); }
    return recovering;
  }
  /** Validate and upload a file before invoking ASR; preserve the retry affordance. */
  async function upload(file: File) {
    setError('');
    if (!file.size) { setError('音频为空，请录制一段声音后再试。'); return; }
    if (file.size > 100 * 1024 * 1024) { setError('文件超过 100 MB，请截取较短音频。'); return; }
    setBusy(true); setPhase('upload'); setUploadPercent(0); setAsrProgress(null); setProgress(`正在上传 ${file.name}…`);
    let recovering = false;
    try { await uploadAudio(snap.session.id, file, value => mounted.current && setUploadPercent(value)); if (!mounted.current) return; setUploaded(true); recovering = await transcribe(); }
    catch (e) { if (mounted.current) { setError(audioError(e)); setProgress(''); setPhase('failed'); } }
    finally { if (mounted.current && !recovering) setBusy(false); }
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
  const audioStages = ['上传音频', '加载模型', '识别语音', '保存转写'];
  const audioIndex = phase === 'upload' || phase === 'failed' && !uploaded ? 0 : asrProgress?.stage === 'saving' || asrProgress?.stage === 'completed' ? 3 : asrProgress?.stage === 'recognizing' ? 2 : 1;
  return <section className="record-panel"><div className="record-orb">◉</div><h2>想到什么，就说什么。</h2>
    <p className="muted">录音停下后，本地模型会转写为带时间戳的文字。</p>
    {!!snap.cards.length && <p role="status">这条记录已生成卡片，原始音频已锁定。要录制或上传另一段音频，请<a href="/">返回首页新建速记</a>；当前内容仍可在“转写原文”查看。</p>}
    {health && <p role="status" className={health.asr_installed ? 'muted' : 'error'}>{health.asr_installed ? `本地语音引擎已安装 · ${health.asr_model}` : health.asr_message}</p>}
    <div className="record-actions"><button className="primary" disabled={locked} onClick={() => recording ? recorder.current?.stop() : void record()}>{requesting ? '等待麦克风授权…' : recording ? `停止录音并转写 · ${seconds}s` : '开始录音'}</button>
      <label className="upload-button">上传音频<input aria-label="上传音频" type="file" accept="audio/*,.mp4" disabled={locked || recording} onChange={e => { const f = e.target.files?.[0]; e.target.value = ''; if (f) void upload(f); }} /></label></div>
    <p className="muted">WAV / MP3 / M4A / WebM / OGG / FLAC · 最大 100 MB</p>
    {['upload','asr','failed'].includes(phase) && <ProcessingProgress
      title={phase === 'failed' ? '音频处理未完成' : phase === 'upload' ? '正在上传音频' : asrProgress?.message || '正在准备语音转写'}
      percent={phase === 'upload' ? uploadPercent : asrProgress?.percent ?? null} stages={audioStages} activeIndex={audioIndex}
      running={busy} failed={phase === 'failed'} detail={phase === 'upload' ? `${progress}${uploadPercent === 100 ? ' 文件已发送，正在等待服务器保存。' : ''}` :
        phase === 'failed' ? uploaded ? '已上传的音频仍保留，可重试转写。' : '上传未完成，请重新选择音频重试。' : pollWarning || (asrProgress?.duration_ms ?
          `已处理 ${(asrProgress.processed_ms / 1000).toFixed(1)} / ${(asrProgress.duration_ms / 1000).toFixed(1)} 秒音频 · ${asrProgress.segments_count} 段转写。百分比为音频处理阶段进度。` :
          '正在加载模型、读取音频或检测有效语音；长音频和首次加载需要更多时间。')} />}
    {progress && phase !== 'upload' && <p role="status" aria-live="polite">{progress}</p>}{error && <p className="error" role="alert">{error}</p>}
    {uploaded && !recording && !snap.cards.length && <button disabled={locked} onClick={() => void transcribe()}>重试转写</button>}
    <details className="text-import" open={!snap.segments.length}><summary>文本演示 / 导入转写</summary><p className="muted">每行一段。此入口使用每段 5 秒的演示时间戳，不代表真实 ASR 时间；音频上传保留实际时间戳。</p><textarea aria-label="转写文本" value={text} onChange={e => setText(e.target.value)} rows={7} /><button disabled={locked || recording || !text.trim()} onClick={importText}>载入文本</button></details>
  </section>;
}
