"""Retrieve a few versioned, annotated development examples for model prompting."""
import json
from functools import lru_cache
from ..core.config import ROOT

@lru_cache(maxsize=1)
def development_examples() -> list[dict]:
    """Load development split only; evaluation examples never enter model prompts."""
    path=ROOT/'configs/relation_examples.jsonl'
    return [item for line in path.read_text(encoding='utf-8').splitlines() if line.strip() and (item:=json.loads(line))['split']=='development' and item.get('use_for_prompt',False)] if path.exists() else []

def select_examples(text: str, limit: int=4) -> list[dict]:
    """Deterministic lexical retrieval; this is few-shot prompting, not weight training."""
    def grams(value: str) -> set[str]:
        """Use character bigrams without an external embedding dependency."""
        return {value[i:i+2] for i in range(max(0,len(value)-1))}
    query=grams(text)
    def score(item: dict) -> float:
        """Compare lexical overlap with an annotated original transcript."""
        tokens=grams(' '.join(item['segments']))
        return len(query&tokens)/max(1,len(query|tokens))
    ordered=sorted(development_examples(),key=lambda item:(-score(item),item['id']))[:limit]
    return [{'segments':item['segments'],'triples':item['triples'],'forbidden':item.get('forbidden',[])} for item in ordered]
