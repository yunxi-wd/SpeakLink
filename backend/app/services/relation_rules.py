"""Evidence-first Chinese relation grammar over original segments, not summary text.

Rules cover coordinated objects, explicit passive voice, composition, definitions,
bounded coreference and scoped uncertainty. They produce candidates only. No
co-occurrence edge, transitive fact or inverse membership is invented.
"""
from dataclasses import dataclass
import re
from ..schemas.domain import Card, TranscriptSegment, EntityCandidate, RelationCandidate, ExtractionCandidates
from .chinese import simplified

VERSION = 'relation-v8-capability-bridges-20261019'
SURFACES = {
    '属于':('属于','属于'), '隶属于':('属于','属于'),
    '是一种':('属于','属于'), '是一个':('属于','属于'), '是一名':('属于','属于'),
    '定义为':('定义','定义'), '指的是':('定义','定义'), '是指':('定义','定义'), '是':('定义','定义'),
    '包括':('包含','其他'), '包含':('包含','其他'), '涵盖':('包含','其他'),
    '导致':('导致','导致'), '造成':('导致','导致'), '引起':('导致','导致'),
    '参与':('参与','参与'), '参加':('参与','参与'), '依赖于':('依赖','依赖'), '依赖':('依赖','依赖'),
    '先于':('先于','先后'), '早于':('先于','先后'), '晚于':('晚于','先后'),
    '象征':('象征','其他'), '代表':('代表','其他'), '位于':('位于','其他'),
    '坐落于':('位于','其他'), '用于':('用于','其他'), '具有':('具有','其他'),
    '拥有':('拥有','其他'), '负责':('负责','其他'), '开发':('开发','其他'),
    '提出':('提出','其他'), '研究':('研究','其他'), '使用':('使用','其他'),
    '采用':('使用','其他'), '保护':('保护','其他'), '支持':('支持','其他'),
    '建设':('建设','其他'), '构建':('建设','其他'), '提升':('提升','其他'),
    '提高':('提升','其他'), '促进':('促进','其他'), '推动':('促进','其他'),
    '打破':('打破','其他'), '实现':('实现','其他'), '形成':('形成','其他'),
    '连接':('连接','其他'), '降低':('降低','其他'), '减少':('减少','其他'),
    '增强':('增强','其他'), '提供':('提供','其他'), '支撑':('支持','其他'),
    '生产':('生产','其他'), '创立':('创立','其他'), '创办':('创立','其他'),
    '创作':('创作','其他'), '撰写':('创作','其他'), '发明':('发明','其他'),
    '发现':('发现','其他'), '担任':('担任','其他'), '服务于':('服务','其他'),
    '服务':('服务','其他'), '维护':('维护','其他'), '听懂':('听懂','其他'),
    '转换':('转换','其他'), '理解':('理解','其他'), '识别':('识别','其他'),
    '分析':('分析','其他'), '生成':('生成','其他'), '预测':('预测','其他'),
    '歌唱':('歌唱','其他'), '望着':('望着','其他'),
    '射进':('射进','其他'), '照射':('照射','其他'), '飞向':('飞向','其他'),
    '有':('拥有','其他'),
    '应用于':('应用于','例证'),
}
VERB = '|'.join(sorted(SURFACES,key=len,reverse=True))
PLACEHOLDER = re.compile(r'^(?:卡片|card)\s*\d+$',re.I)
PRONOUNS = {'它','他','她','他们','她们','它们','该项目','这个项目','那个项目','该方案','那个方案','这个方案','该平台','该系统'}
TRANSITION = re.compile(r'换个话题|另外说|另一个话题|接下来讨论')
UNCERTAIN = re.compile(r'可能|也许|或许|不一定|是否|能否|如果|假如|计划|打算|预计|准备|应该|有望|将会|尚待|需要')
NEGATIVE = re.compile(r'不是|不等于|不再|不能|不会|并非|没有|并未|尚未|未曾|未能|不(?:'+VERB+r')')
FILLER = re.compile(r'^(?:嗯|呃|额|然后|所以|因此|另外|接着|其实|就是说|也就是说|首先|其次|最后|并且|而且|同时)[，,\s]*')

def canonical_label(value: str | None, kind: str = '其他') -> str:
    """Return a specific nonempty canonical predicate or an empty invalid label."""
    label = simplified(value or kind).strip()
    if label in {'其他','相关','原文提及','关联','提及'} or not label:return ''
    return SURFACES.get(label,(label,kind))[0]

def noun_kind(name: str) -> str:
    """Conservative surface typing; do not truncate a full literal noun phrase."""
    if re.fullmatch(r'[张李王赵陈刘周吴郑孙马][\u4e00-\u9fff]{1,2}',name) or name.endswith(('先生','女士','老师')):return 'PERSON'
    if name.endswith(('公司','团队','大学','研究院','集团','部门','委员会')):return 'ORG'
    if name in {'北京','上海','深圳','杭州','广州','中国','日本','法国'}:return 'LOCATION'
    if re.fullmatch(r'\d{4}年|今天|明天|昨天',name):return 'TIME'
    return 'CONCEPT'

def noun_phrase(raw: str) -> str:
    """Keep a complete literal span, stripping only grammatical boundary particles."""
    text=raw.strip().strip('“”"‘’《》：: ')
    text=re.sub(r'^(?:了|着|一个|一种|一名|一项|一只|这个|这项|这些|那些|许多|我们的|你的|我们所说的)','',text)
    text=re.sub(r'(?:呢|啊|呀|吧|的)$','',text).strip()
    if not text or len(text)>60 or PLACEHOLDER.fullmatch(text) or text in {'我们','大家','省略主语','这','那','所','没','都','也','什么','谁','如何','怎么'}:return ''
    return text

def split_items(raw: str) -> list[str]:
    """Split enumeration boundaries while preserving literal compound names."""
    raw=re.sub(r'(?:等内容|等部分|等模块|等等|等)$','',raw.strip())
    return [name for part in re.split(r'、|以及|还有|(?<=.)和(?!平|谐|睦|蔼)|与|及|或',raw) if (name:=noun_phrase(part))]

@dataclass
class Mention:
    """A topic subject with its original segment, speaker and sequence position."""
    name: str
    segment_id: str
    position: int
    speaker: str | None

def extract_relations(cards: list[Card], segments: list[TranscriptSegment]) -> ExtractionCandidates:
    """Parse original source clauses into stable evidence-backed candidates."""
    entities:list[EntityCandidate]=[]; relations:list[RelationCandidate]=[]
    card_map={s.id:[c for c in cards if s.id in c.source_segment_ids] for s in segments}
    anchors:dict[str,Mention]={}; last_subject: Mention | None=None; previous_speaker=None
    for position, segment in enumerate(segments):
        text=simplified(segment.text)
        if TRANSITION.search(text) or (position and previous_speaker!=segment.speaker):
            anchors.clear();last_subject=None
        previous_speaker=segment.speaker
        # Introductions bind a following pronoun without choosing the nearest noun.
        intro=re.search(r'(?:这就是|这是)([^，,。；;！!？?]+)',text)
        if intro:
            name=noun_phrase(intro.group(1))
            if name:anchors[name]=Mention(name,segment.id,position,segment.speaker)
        topic=re.search(r'^(?:呃|嗯)?(?:那个)?([^，,。；;]{2,24})呢[，,]',text)
        if topic:
            name=noun_phrase(topic.group(1))
            if name:anchors[name]=Mention(name,segment.id,position,segment.speaker);last_subject=anchors[name]
        sentence_subject: Mention | None=last_subject if topic else None
        last_verb: str | None=None
        for raw_clause in re.split(r'[，,。；;！!？?\n]+|并(?:且)?(?=(?:'+VERB+r'))',text):
            clause=raw_clause.strip()
            while FILLER.match(clause):clause=FILLER.sub('',clause,count=1)
            clause=re.sub(r'^就是要','',clause)
            if not clause or TRANSITION.search(clause):continue
            if clause.startswith(('这就是','这是')):continue
            if re.match(r'^(?:什么|谁|哪里|如何|怎么|为什么|多少)',clause) or clause.endswith(('吗','么')):continue
            # Capability clauses have their own modal/antecedent parser. Feeding
            # them through generic 是 would create a whole-sentence entity.
            if re.search(r'(?:能够|可以|(?<![功智])能)完成',clause):continue
            uncertain=bool(UNCERTAIN.search(clause) or NEGATIVE.search(clause))
            # Compound sentences carry negation scope only inside their own clause.
            clause=re.sub(r'^(?:但是|但|而是|而|不过)','',clause)
            jobs:list[tuple[str,str,str,bool]]=[]
            composition=re.fullmatch(r'(.+?)由(.+?)(?:组成|构成)',clause)
            membership=re.fullmatch(r'(.+?)是(.+?)的(?:一个|一种)?(?:分支|组成部分|子集|成员)',clause)
            passive=re.fullmatch(r'(.+?)(?:被|由)(.+?)('+VERB+r')(?:了)?',clause)
            means=re.fullmatch(r'(.+?)通过(.+?)('+VERB+r')(.+)',clause)
            method=re.fullmatch(r'(.+?)通过(分析|研究|使用|识别)(.+?)来(?:学习|推理|决策)',clause)
            extended_definition=re.fullmatch(r'(.+?)是(研究|开发|分析|理解|识别)(?:和|与)(研究|开发|分析|理解|识别)(.+)',clause)
            directional=re.fullmatch(r'(.+?)向(.+?)(歌唱|飞来|飞去|飞走)',clause)
            if method:
                subject,verb,objects=method.groups();jobs=[(subject,verb,objects,False)]
            elif extended_definition:
                subject,first,second,objects=extended_definition.groups()
                objects=re.sub(r'的(?:一门|一种|一个)?(?:技术领域|学科|领域)$','',objects)
                jobs=[(subject,first,objects,False),(subject,second,objects,False)]
                classification=re.search(r'一门(技术领域|学科|领域)',text)
                if classification:jobs.append((subject,'属于',classification.group(1),False))
            elif directional:
                subject,target,verb=directional.groups();jobs=[(subject,verb,target,False)]
            elif membership:
                subject,parent=membership.groups();jobs=[(subject,'属于',parent,False)]
            elif composition:
                subject,objects=composition.groups();jobs=[(subject,'包含',objects,False)]
            elif passive:
                patient,actor,verb=passive.groups();jobs=[(actor,verb,patient,True)]
            elif means:
                subject,tool,verb,objects=means.groups()
                jobs=[(subject,'使用',tool,False),(subject,verb,objects,False)]
            else:
                match=re.search(r'(.*?)('+VERB+r')(?:了|着)?(.+)',clause)
                if last_verb and re.match(r'^(还有|以及)',clause) and sentence_subject:
                    jobs=[(sentence_subject.name,last_verb,re.sub(r'^(还有|以及)','',clause),False)]
                    match=None
                if match:
                    subject,verb,objects=match.groups()
                    # Don't turn the 有 inside 没有/所有 into an assertion.
                    if verb=='有' and (subject.endswith(('没','所')) or not subject.strip()):continue
                    jobs=[(subject,verb,objects,False)]
            for subject,verb,objects,reversed_voice in jobs:
                subject=re.sub(r'(?:至少|主要|也|还|更|则|已经|正在|共同|能够|可以|将|要|并未|尚未|不|没有|可能|也许|计划|需要)+$','',subject.strip())
                subject=re.sub(r'(?:呢|就是要|就是)$','',subject)
                subject=re.sub(r'^(?:再)?根据.+?的(?:规律|结果)','',subject)
                if verb in {'生成','预测'}:
                    objects=re.sub(r'(?:或|并|和)(?:做出|进行)(?:预测|推理|决策)$','',objects)
                if re.search(r'作为|为了|更适合|使得|帮助|能够|通过',subject):
                    continue
                context: Mention | None=None
                possessive=re.fullmatch(r'(它|他|她)的(.+)',subject)
                if possessive:
                    subject=possessive.group(2)
                elif subject in PRONOUNS:
                    choices=[a for a in anchors.values() if 0<=position-a.position<=4 and a.speaker==segment.speaker]
                    if subject in {'他','她'}:choices=[a for a in choices if noun_kind(a.name)=='PERSON']
                    elif '项目' in subject:choices=[a for a in choices if '项目' in a.name]
                    elif '方案' in subject:choices=[a for a in choices if '方案' in a.name]
                    elif '平台' in subject:choices=[a for a in choices if '平台' in a.name]
                    elif '系统' in subject:choices=[a for a in choices if '系统' in a.name]
                    else:choices=[a for a in choices if noun_kind(a.name)!='PERSON']
                    if len(choices)==1 and subject not in {'他们','她们','它们'}:context=choices[0];subject=context.name
                    else:uncertain=True
                elif not subject:
                    # Omitted subjects inherit only within the same sentence/segment.
                    context=sentence_subject
                    if context:subject=context.name
                    else:continue
                heads=split_items(subject); tails=split_items(objects)
                if not heads or not tails:continue
                if len(heads)==1 and subject not in PRONOUNS and not uncertain:
                    mention=Mention(heads[0],segment.id,position,segment.speaker)
                    if not possessive:anchors[mention.name]=mention
                    sentence_subject=mention;last_subject=mention;last_verb=verb
                source_ids=sorted({segment.id,*([context.segment_id] if context else [])})
                local_cards=card_map.get(segment.id,[])
                specific=[c for c in local_cards if c.content.strip('，,。；;！!？? ') in raw_clause or raw_clause.strip() in c.content]
                sources={c.id:c for c in (specific or local_cards)}
                if context:
                    references=[c for c in card_map.get(context.segment_id,[]) if context.name in c.content]
                    # Use the explicit established mention, not every unrelated card
                    # whose evidence happens to share a long ASR segment.
                    established=[c for c in references if c.status=='active']
                    for card in (established or references)[:1]:sources[card.id]=card
                if not sources:continue
                confidence=min(.9,*(c.confidence for c in sources.values()),.49 if uncertain else .9)
                evidence=dict(confidence=confidence,evidence_segment_ids=source_ids,source_card_ids=sorted(sources))
                label,kind=SURFACES.get(verb,(verb,'其他'))
                for head in heads:
                    for tail in tails:
                        if head==tail or head in {'今天','明天','晚上','然后'}:continue
                        entities.extend(EntityCandidate(name=n,type=noun_kind(n),**evidence) for n in [head,tail])
                        relations.append(RelationCandidate(head=head,tail=tail,type=kind,predicate=label,**evidence))
    result=ExtractionCandidates(entities=entities,relations=relations)
    from .discourse_relations import application_bridges
    bridges=application_bridges(cards,segments,result)
    result.entities.extend(bridges.entities);result.relations.extend(bridges.relations)
    from .capability_relations import capability_bridges
    abilities=capability_bridges(cards,segments,result)
    result.entities.extend(abilities.entities);result.relations.extend(abilities.relations)
    return result

def relation_supported(candidate: RelationCandidate, segments: list[TranscriptSegment], rules: ExtractionCandidates) -> bool:
    """Approve only rule-backed triples or a locally explicit supported SVO span."""
    key=(candidate.head,canonical_label(candidate.predicate,candidate.type),candidate.tail)
    if any((r.head,r.predicate,r.tail)==key and r.confidence>=.75 and set(r.evidence_segment_ids)<=set(candidate.evidence_segment_ids) for r in rules.relations):return True
    if not key[1]:return False
    surfaces=[s for s,(label,_) in SURFACES.items() if label==key[1]] or [key[1]]
    for segment in segments:
        if segment.id not in candidate.evidence_segment_ids:continue
        for clause in re.split(r'[，,。；;！!？?\n]',simplified(segment.text)):
            if NEGATIVE.search(clause) or UNCERTAIN.search(clause):continue
            if any(re.search(re.escape(candidate.head)+r'.{0,6}'+re.escape(v)+r'(?:了|着)?[^，。;；]{0,6}'+re.escape(candidate.tail),clause) for v in surfaces):return True
    return False

