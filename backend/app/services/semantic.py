"""Evidence-backed Chinese predicates and bounded topic coreference for offline use.

This module emits candidates, never stored graph edges. Named topic introductions
provide context for singular pronouns; ambiguity and negation remain pending.
"""
import re
from ..schemas.domain import Card, TranscriptSegment, EntityCandidate, RelationCandidate, ExtractionCandidates
from .lexical import nouns

# Keep display predicates literal, so reviewers can locate the exact source words.
PREDICATES = {'象征':'其他', '代表':'其他', '位于':'其他', '用于':'其他',
              '具有':'其他', '拥有':'其他', '包括':'其他', '包含':'其他',
              '负责':'其他', '开发':'其他', '提出':'其他', '研究':'其他',
              '使用':'其他', '保护':'其他', '支持':'其他', '是一种':'属于',
              '是一个':'属于', '是一名':'属于', '有':'其他'}
PATTERN = '|'.join(sorted(PREDICATES, key=len, reverse=True))
NEGATIVE = re.compile(r'没有|并未|尚未|未曾|不(?:是|会|能|再|曾|具|拥|象征|代表|位于|用于|包括|包含|负责|开发|提出|研究|使用|保护|支持)|可能|也许|是否|假如|如果')
TRANSITION = re.compile(r'换个话题|另外说|接下来讨论|另一个话题')


def phrase(text: str) -> tuple[str, str] | None:
    """Choose a literal noun phrase, retaining compound names rather than fragments."""
    text = re.sub(r'^(?:至少|也|就|还|了|着|在|一名|一种|一个)+', '', text.strip())
    # Full names with these suffixes are safer than Jieba's incomplete '白洋'.
    match = re.fullmatch(r'[\w\u4e00-\u9fff]{1,20}(?:树|项目|方案|系统|平台|公司|团队|模块|图谱)', text)
    if match:
        return text, 'ORG' if text.endswith(('公司', '团队')) else 'CONCEPT'
    values = nouns(text)
    if values:
        return values[-1] if '的' in text else values[0]
    if text in {'树', '皮', '干', '枝', '叶', '根', '希望'}:
        return text, 'CONCEPT'
    return None


def contextual_candidates(cards: list[Card], segments: list[TranscriptSegment]) -> ExtractionCandidates:
    """Resolve a singular topic only with explicit introduction and shared evidence.

Only previous, same-speaker context is used. Named alternative topics make the
pronoun ambiguous. Topic transitions clear context; unresolved pronouns are kept
at low confidence for human review rather than replacing them with a keyword.
"""
    entities: list[EntityCandidate] = []
    relations: list[RelationCandidate] = []
    anchors: dict[str, tuple[tuple[str, str], Card]] = {}
    segment_map = {s.id: s for s in segments}
    previous_speaker = None
    positions = {c.id: i for i, c in enumerate(cards)}
    for card in cards:
        speaker = segment_map[card.source_segment_ids[0]].speaker
        if TRANSITION.search(card.content) or (previous_speaker is not None and speaker != previous_speaker):
            anchors.clear()
        previous_speaker = speaker
        # Explicit introductions anchor subsequent pronouns without guessing from frequency.
        for match in re.finditer(r'(?:这就是|这是)([^，,。；;！!？?]{1,24})|([^，,。；;！!？?]{1,24}?)(?:是一种|是一个|是一名)', card.content):
            raw = match.group(1) or match.group(2)
            topic = phrase(raw)
            if topic and raw.strip() == topic[0] and len(raw) <= 20 and not re.search(r'和|、|与|以及', raw):
                anchors[topic[0]] = (topic, card)
        for clause in re.split(r'[，,。；;！!？?\n]', card.content):
            match = re.search(r'(.*?)(' + PATTERN + r')(?:了|着)?(.+)', clause)
            if not match:
                continue
            before, verb, after = match.groups()
            # Generic '有' inside possessive/negative clauses is not a positive assertion.
            if verb == '有' and (before.endswith(('所', '没')) or not before.strip()):
                continue
            pronoun = re.search(r'它|他|她|该项目|这个项目|那个方案|该方案', before)
            omitted = not re.sub(r'至少|也|就|还|更|则', '', before).strip()
            context = None
            uncertain = bool(NEGATIVE.search(clause))
            possessive = re.fullmatch(r'(?:它|他|她)的(.+)', before.strip())
            if possessive and phrase(possessive.group(1)):
                head = phrase(possessive.group(1))
            elif pronoun or omitted:
                choices = [a for a in anchors.values() if 0 <= positions[card.id] - positions[a[1].id] <= 8]
                if pronoun and pronoun.group() in {'他', '她'}:
                    choices = [a for a in choices if a[0][1] == 'PERSON']
                if len(choices) == 1:
                    head, context = choices[0]
                else:
                    head = (pronoun.group() if pronoun else '省略主语', 'OTHER')
                    uncertain = True
            else:
                head = phrase(before)
            if not head:
                continue
            # Time/adverb subjects in noisy ASR cannot become a fabricated symbolic entity.
            if before.strip() in {'晚上', '今天', '明天', '后来', '然后'}:
                uncertain = True
            tails = [phrase(part) for part in re.split(r'、|以及|和', after)]
            for tail in tails:
                if not tail or head[0] == tail[0]:
                    continue
                sources = [card] + ([context] if context and context.id != card.id else [])
                evidence = dict(confidence=min(*(c.confidence for c in sources), .49 if uncertain else .82),
                                evidence_segment_ids=sorted({s for c in sources for s in c.source_segment_ids}),
                                source_card_ids=sorted({c.id for c in sources}))
                entities.extend(EntityCandidate(name=name, type=kind, **evidence) for name, kind in [head, tail])
                relations.append(RelationCandidate(head=head[0], tail=tail[0], type=PREDICATES[verb], predicate=verb, **evidence))
    return ExtractionCandidates(entities=entities, relations=relations)
