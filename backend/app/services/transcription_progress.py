"""Thread-safe ASR telemetry for the single-process local server.

Only observed audio coverage is numeric. Model loading is indeterminate. Records
are process-local: a restart returns idle rather than inventing continued work.
"""
from threading import RLock
from ..schemas.api import TranscriptionProgress

_lock = RLock()
_states: dict[str, TranscriptionProgress] = {}
ACTIVE = {'loading_model', 'reading_audio', 'recognizing', 'saving'}


def begin(sid: str) -> bool:
    """Acquire a per-recording transcription lease; reject overlapping ASR requests."""
    with _lock:
        if sid in _states and _states[sid].stage in ACTIVE:
            return False
        _states[sid] = TranscriptionProgress(stage='loading_model', message='正在加载本地语音模型，首次加载可能稍慢')
        return True


def update(sid: str, stage: str, processed_ms: int = 0, duration_ms: int = 0, segments_count: int = 0) -> None:
    """Publish segment coverage without implying an estimate of remaining time."""
    labels = {'loading_model': '正在加载本地语音模型', 'reading_audio': '正在读取音频并检测有效语音',
              'recognizing': '正在识别语音并整理简体中文', 'saving': '正在保存带时间戳的转写文本',
              'completed': '转写已完成'}
    with _lock:
        old = _states.get(sid, TranscriptionProgress())
        duration_ms = max(duration_ms, old.duration_ms)
        processed_ms = max(processed_ms, old.processed_ms)
        percent = None
        if stage == 'recognizing' and duration_ms > 0:
            percent = min(95, round(10 + 85 * min(processed_ms / duration_ms, 1)))
        elif stage == 'saving':
            percent = 98
        elif stage == 'completed':
            percent = 100
        _states[sid] = TranscriptionProgress(stage=stage, message=labels[stage], percent=percent,
            processed_ms=processed_ms, duration_ms=duration_ms,
            segments_count=max(segments_count, old.segments_count))


def fail(sid: str) -> None:
    """Release the lease on all failures; retain coverage for a useful retry display."""
    with _lock:
        old = _states.get(sid, TranscriptionProgress())
        _states[sid] = old.model_copy(update={'stage': 'failed', 'message': '转写未完成，音频仍保留，可重试'})


def read(sid: str) -> TranscriptionProgress:
    """Return a detached status value so readers cannot change server telemetry."""
    with _lock:
        return _states.get(sid, TranscriptionProgress()).model_copy(deep=True)
