"""Conservative discourse bridges for explicitly stated application examples."""
import re
from ..schemas.domain import Card, TranscriptSegment, ExtractionCandidates, EntityCandidate, RelationCandidate

def application_bridges(cards: list[Card],segments: list[TranscriptSegment],candidates: ExtractionCandidates) -> ExtractionCandidates:
    """Link 'A..., B..., 都是X的应用' to X→应用于→A/B with complete evidence.

    Uses only preceding explicit activity subjects within a short same-speaker
    window. Shared paragraphs alone and vague pronouns never create bridges.
    """
    from .relation_rules import NEGATIVE,UNCERTAIN,noun_phrase,noun_kind,TRANSITION
    output=ExtractionCandidates(entities=[],relations=[])
    positions={s.id:i for i,s in enumerate(segments)}
    activities={'听懂','转换','理解','识别','生成','提供','分析','预测'}
    for index,segment in enumerate(segments):
        for match in re.finditer(r'(?:都是|是)([^，,。；;！？!?]{1,30}?)的(?:典型)?应用',segment.text):
            clause=re.split(r'[，,。；;！？!?]',segment.text[:match.end()])[-1]
            if NEGATIVE.search(clause) or UNCERTAIN.search(clause):continue
            domain=noun_phrase(match.group(1))
            if not domain:continue
            window=segments[max(0,index-2):index+1]
            if any(s.speaker!=segment.speaker or TRANSITION.search(s.text) for s in window):continue
            context=' '.join(s.text for s in window)
            cues=list(re.finditer(r'例如|比如|举例',context))
            if not cues and not match.group().startswith('都是'):continue
            offsets={};offset=0
            for s in window:offsets[s.id]=offset;offset+=len(s.text)+1
            subjects={}
            for relation in candidates.relations:
                indices=[positions[s] for s in relation.evidence_segment_ids]
                if relation.confidence<.75 or relation.predicate not in activities or not all(max(0,index-2)<=p<=index for p in indices):continue
                if relation.head==domain:continue
                if noun_kind(relation.head)=='PERSON':continue
                if cues and not any(offsets[sid]+segments[positions[sid]].text.find(relation.head)>=cues[-1].end() for sid in relation.evidence_segment_ids if sid in offsets):continue
                if segment.text.find(relation.head)>match.start() and segment.id in relation.evidence_segment_ids:continue
                subjects.setdefault(relation.head,relation)
            if not cues:
                # Without an explicit example cue, bind 都 only to a single
                # nearby coordinated clause, not every activity in the paragraph.
                together={name:r for name,r in subjects.items() if segment.id in r.evidence_segment_ids}
                subjects=together if len(together)>=2 else {}
            if not 1<=len(subjects)<=6:continue
            if match.group().startswith('都是') and len(subjects)<2:continue
            domain_cards=[c for c in cards if segment.id in c.source_segment_ids and domain in c.content]
            if not domain_cards:continue
            for name,original in subjects.items():
                source_ids=sorted({segment.id,*original.evidence_segment_ids})
                card_ids=sorted({*(c.id for c in domain_cards),*original.source_card_ids})
                confidence=min(original.confidence,*(c.confidence for c in domain_cards),.88)
                evidence=dict(confidence=confidence,evidence_segment_ids=source_ids,source_card_ids=card_ids)
                output.entities.extend(EntityCandidate(name=n,type=noun_kind(n),**evidence) for n in [domain,name])
                output.relations.append(RelationCandidate(head=domain,tail=name,type='例证',predicate='应用于',**evidence))
    return output
