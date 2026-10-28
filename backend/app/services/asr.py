"""CPU/GPU faster-whisper transcription with VAD and source-preserving cleanup."""
from functools import lru_cache
from typing import Any
import math
import re
from ..core.config import settings
from ..schemas.domain import TranscriptSegment
from .common import stable_id
from .chinese import simplified

def clean_text(text: str) -> str:
    """Remove filler/repeated punctuation only; never guess factual corrections."""
    text = simplified(text)
    return re.sub(r"([，。！？])\1+", r"\1", re.sub(r"^(嗯[，,]?|呃[，,]?)", "", text.strip())).strip() or text.strip()

@lru_cache(maxsize=1)
def model() -> Any:
    """Lazy-load ASR weights once; missing dependency raises a clear actionable error."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("未安装 faster-whisper；请安装 requirements-models.txt") from exc
    try:
        return WhisperModel(settings.asr_model, device=settings.asr_device, compute_type="int8" if settings.asr_device == "cpu" else "float16",
                            download_root=str(settings.data_dir / "models"))
    except Exception as exc:
        raise RuntimeError("语音模型加载失败。请先运行语音环境安装脚本下载模型，再重试转写；已上传音频仍保留。") from exc

def transcribe(path: str, sid: str, language: str) -> list[TranscriptSegment]:
    """Convert an uploaded recording into final timestamped segments using local VAD."""
    engine = model()
    try:
        results, _ = engine.transcribe(path, language=language, vad_filter=True, word_timestamps=True, beam_size=5,
                                      initial_prompt="以下是普通话录音，请使用简体中文。" if language == "zh" else None,
                                      condition_on_previous_text=False)
        return [TranscriptSegment(id=stable_id(sid, "segment", i), session_id=sid, start_ms=round(s.start * 1000), end_ms=round(s.end * 1000), raw_text=s.text.strip(), text=clean_text(s.text), confidence=min(1, math.exp(s.avg_logprob))) for i, s in enumerate(results) if s.text.strip()]
    except (ValueError, EOFError) as exc:
        raise ValueError("无法读取音频内容，请上传完整且可播放的 WAV、MP3 或 WebM 文件。") from exc
