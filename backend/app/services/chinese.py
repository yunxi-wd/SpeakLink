"""Local orthographic conversion; preserve raw ASR text separately for auditing."""
from functools import lru_cache
from opencc import OpenCC

@lru_cache(maxsize=1)
def converter() -> OpenCC:
    """Load deterministic traditional-to-simplified dictionaries once."""
    return OpenCC('t2s')

def simplified(text: str) -> str:
    """Normalize Chinese script without paraphrasing or correcting factual content."""
    return converter().convert(text)
