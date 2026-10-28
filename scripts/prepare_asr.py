"""Download and load the configured local ASR model before users record audio."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

def main() -> None:
    """Validate the speech runtime and cache weights; no synthetic transcript is returned."""
    from app.core.config import settings
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default=settings.asr_model)
    args = parser.parse_args()
    from faster_whisper import WhisperModel
    destination = settings.data_dir / 'models'
    destination.mkdir(parents=True, exist_ok=True)
    WhisperModel(args.model, device=settings.asr_device, compute_type='int8' if settings.asr_device == 'cpu' else 'float16', download_root=str(destination))
    print(f'ASR model loaded successfully: {args.model}; cache: {destination}')
    if args.model != settings.asr_model:
        print(f'Set KNOWGPT_ASR_MODEL={args.model} before starting the backend.')

if __name__ == '__main__':
    main()
