"""Evidence-only Chinese noun mentions and explicit predicates for offline prose."""
from collections import Counter
from functools import lru_cache
import logging
import re
import jieba
from jieba.posseg import POSTokenizer
from ..core.config import settings
from ..schemas.domain import Card, EntityCandidate, RelationCandidate

STOP = {'时候','地方','方面','东西','情况','问题','意思','结果','今天','明天','昨天','作品','一种','一点','大家','自己'}
PREDICATES = {'象征':'其他','代表':'其他','用于':'其他','位于':'其他','包含':'其他','包括':'其他','拥有':'其他','是一种':'属于','是一个':'属于','是一名':'属于','是':'定义'}

@lru_cache(maxsize=1)
def tokenizer() -> POSTokenizer:
    """Initialize the local dictionary with a project-owned cache directory."""
    directory = settings.data_dir / 'nlp-cache'
    directory.mkdir(parents=True, exist_ok=True)
    jieba.setLogLevel(logging.ERROR)
    engine = jieba.Tokenizer()
    engine.tmp_dir = str(directory)
    return POSTokenizer(engine)

def nouns(text: str) -> list[tuple[str, str]]:
    """Return literal noun mentions, not inferred concepts or co-occurrence relations."""
    result = []
    for word, flag in tokenizer().cut(text, HMM=False):
        if 2 <= len(word) <= 24 and word not in STOP and (flag.startswith('n') or flag == 'eng'):
            kind = 'PERSON' if flag == 'nr' else 'LOCATION' if flag == 'ns' else 'ORG' if flag == 'nt' else 'CONCEPT'
            result.append((word, kind))
    return list(dict.fromkeys(result))

def prose_candidates(card: Card, frequencies: Counter) -> tuple[list[EntityCandidate], list[RelationCandidate]]:
    """Add bounded noun mentions and only locally explicit subject-predicate-object edges."""
    evidence = dict(confidence=min(card.confidence, .82), evidence_segment_ids=card.source_segment_ids, source_card_ids=[card.id])
    mentions = sorted(nouns(card.content), key=lambda x: (-frequencies[x[0]], card.content.index(x[0])))[:8]
    entities = [EntityCandidate(name=name, type=kind, **evidence) for name, kind in mentions]
    relations = []
    pattern = '|'.join(sorted(PREDICATES, key=len, reverse=True))
    for clause in re.split(r'[，,。；;！!？?\n]', card.content):
        match = re.search(r'(.+?)(' + pattern + r')(?:了|着)?(.+)', clause)
        if not match:
            continue
        before, verb, after = match.groups()
        left, right = nouns(before), nouns(after)
        # A pronoun or omitted subject is never replaced by the nearest keyword.
        if not left or not right or re.match(r'^(它|他|她|这|那)', before.strip()):
            continue
        head, tail = left[-1], right[-1] if '的' in after else right[0]
        if head[0] == tail[0]:
            continue
        entities.extend(EntityCandidate(name=name, type=kind, **evidence) for name, kind in [head, tail])
        h, t = head[0], tail[0]
        relations.append(RelationCandidate(head=h, tail=t, type=PREDICATES[verb], predicate=verb, **evidence))
    return entities, relations
