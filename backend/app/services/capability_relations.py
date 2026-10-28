"""Explicit capabilities and definition-bound purpose references across ASR segments.

Represents 能够完成 as ability, never as an already completed event. Only an
unambiguous research/development definition can bind 使它们 to a named system.
"""
import re
from ..schemas.domain import Card,TranscriptSegment,ExtractionCandidates,EntityCandidate,RelationCandidate

def capability_bridges(cards:list[Card],segments:list[TranscriptSegment],candidates:ExtractionCandidates)->ExtractionCandidates:
    """Connect a system/domain to its stated tasks, with antecedent and task evidence."""
    from .relation_rules import noun_phrase,noun_kind,split_items,NEGATIVE,UNCERTAIN,TRANSITION
    result=ExtractionCandidates(entities=[],relations=[])
    positions={s.id:i for i,s in enumerate(segments)}
    for index,segment in enumerate(segments):
        for clause in re.split(r'[，,。；;！？!?\n]',segment.text):
            match=re.search(r'(能够|可以|(?<![功智])能)完成(.+)',clause)
            if not match:continue
            prefix=clause[:match.start()].strip();objects=match.group(2)
            # Uncertainty/negation has scope over the ability clause, not a task's
            # relative clause such as 通常需要人类智能才能完成的任务.
            scope=prefix+match.group(1)+'完成'
            uncertain=bool(NEGATIVE.search(scope) or UNCERTAIN.search(prefix) or clause.endswith(('吗','么')))
            window=[segment]
            if not TRANSITION.search(segment.text):
                for previous in reversed(segments[max(0,index-3):index]):
                    if previous.speaker!=segment.speaker or TRANSITION.search(previous.text):break
                    window.insert(0,previous)
            window_ids={s.id for s in window}
            bindings={}
            for relation in candidates.relations:
                if relation.predicate in {'研究','开发'} and relation.tail.endswith('系统') and relation.confidence>=.75 and set(relation.evidence_segment_ids)<=window_ids:
                    # Require a definition, not just an unrelated person developing software.
                    proof=[s for s in window if s.id in relation.evidence_segment_ids]
                    if any(re.search(re.escape(relation.head)+r'是(?:研究|开发|研发)',s.text) for s in proof):
                        key=(relation.head,relation.tail)
                        bindings.setdefault(key,set()).update(relation.evidence_segment_ids)
            # Recover definitions whose object span is interrupted by ASR segmentation.
            for s in window:
                for definition in re.finditer(r'([\w\u4e00-\u9fff]{2,24})是(?:研究和开发|研究与开发|研究开发|研发)([\w\u4e00-\u9fff]{1,24}?系统)',s.text):
                    if NEGATIVE.search(definition.group()) or UNCERTAIN.search(definition.group()):continue
                    domain=noun_phrase(re.sub(r'^(?:简单来说|所谓)','',definition.group(1)))
                    system=noun_phrase(definition.group(2))
                    if domain and system:bindings.setdefault((domain,system),set()).add(s.id)
            reference=bool(re.search(r'(?:使|是)?(?:它们|他们|它|这些系统)$',prefix))
            domain=None;source_ids={segment.id}
            if reference:
                # 他们/它们 are acoustically identical; accept a nonhuman reading
                # only inside this unique formal definition. Raw text is untouched.
                if len(bindings)!=1 or any(re.search(r'系统[、和与及].{0,24}系统',s.text) for s in window):continue
                (domain,actor),antecedents=next(iter(bindings.items()));source_ids.update(antecedents)
            else:
                actor=re.sub(r'^(?:使|让)','',prefix)
                actor=re.sub(r'(?:可能|也许|计划|将|并不|尚未|未|不)$','',actor)
                actor=noun_phrase(actor)
                if not actor or actor in {'它','他','她','它们','他们','她们','该系统','这个系统'} or len(actor)>24 or re.search(r'研究|开发|分析|作为|为了',actor):continue
            targets=['任务'] if '任务' in objects else split_items(objects)
            if not targets:continue
            # A following demonstrative list supplies the exact task referent.
            for following in segments[index+1:index+3]:
                if following.speaker!=segment.speaker or TRANSITION.search(following.text):break
                if targets==['任务'] and re.match(r'\s*(?:这些|上述|这些个)任务(?:包括|包含|有)',following.text):
                    source_ids.add(following.id);break
            selected=[]
            for card in cards:
                if not set(card.source_segment_ids)&source_ids:continue
                text=card.content
                relevant=(any(n in text for n in [actor,domain] if n) or (re.search(r'(能够|可以|能)完成',text) and text.strip('，。；; ') in clause) or re.match(r'(?:这些|上述)任务',text))
                if relevant:selected.append(card)
            if not selected or not source_ids<={sid for c in selected for sid in c.source_segment_ids}:continue
            confidence=min(.86 if reference else .9,*(c.confidence for c in selected),.49 if uncertain else 1.)
            evidence=dict(confidence=confidence,evidence_segment_ids=sorted(source_ids),source_card_ids=sorted(c.id for c in selected))
            triples=[(actor,'能够完成',target) for target in targets]
            if domain:triples.extend((domain,'支持完成',target) for target in targets)
            for head,label,tail in triples:
                if head==tail:continue
                result.entities.extend(EntityCandidate(name=n,type=noun_kind(n),**evidence) for n in [head,tail])
                result.relations.append(RelationCandidate(head=head,tail=tail,type='其他',predicate=label,**evidence))
    return result
