"""Deterministic identifiers and conservative lexical normalization."""
import hashlib
import json
import re
import unicodedata
from .chinese import simplified

def stable_id(*parts: object) -> str:
    """Map an ordered input tuple to a stable 24-character ID."""
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]

def normalize(text: str) -> str:
    """Fold Unicode, case, whitespace and punctuation; avoid unsafe stemming."""
    text = unicodedata.normalize("NFKC", simplified(text)).casefold()
    text = re.sub(r"[\W_]+", "", text)
    return text[:-1] if text.endswith("们") and text[:-1] in {"项目", "方案"} else text
