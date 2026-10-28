/** Server-owned topic groups, witnessed bridges and linked evidence. */
'use client';
import {useEffect,useRef,useState} from 'react';
import cytoscape,{Core,ElementDefinition} from 'cytoscape';
import {api,type Snapshot} from '@/api/client';
import EntityEditor from './EntityEditor';
import {useStore} from '@/store/useStore';
type Node=Snapshot['entities'][number]&{group_id:string;group_name:string;group_color:string};
type Edge=Snapshot['relations'][number]&{cross_group:boolean};
type Group={id:string;name:string;color:string;entity_ids:string[]};
type Bridge={id:string;source:string;target:string;label:string;relation_ids:string[];evidence_segment_ids:string[];source_card_ids:string[]};
export type GroupGraph={nodes:Node[];edges:Edge[];groups:Group[];group_relations:Bridge[];revision:number};

/** Project existing facts, retaining one-hop cross-topic context when a group is selected. */
export function groupElements(graph:GroupGraph,selected:string|null,neighbors:boolean,overview:boolean,onlyBridges:boolean,query:string,type:string,focus:string|null):ElementDefinition[]{
  let nodes=graph.nodes.filter(n=>n.status==='active'&&!/^卡片\s*\d+$/.test(n.name));
  if(selected){const members=new Set(nodes.filter(n=>n.group_id===selected).map(n=>n.id));const ids=new Set(members);if(neighbors)for(const e of graph.edges)if(e.cross_group&&(members.has(e.head_entity_id)||members.has(e.tail_entity_id))){ids.add(e.head_entity_id);ids.add(e.tail_entity_id);}nodes=nodes.filter(n=>ids.has(n.id));}
  if(query)nodes=nodes.filter(n=>n.name.toLowerCase().includes(query.toLowerCase()));
  if(type)nodes=nodes.filter(n=>n.type===type);
  if(focus){const ids=new Set([focus]);for(const e of graph.edges)if(e.head_entity_id===focus||e.tail_entity_id===focus){ids.add(e.head_entity_id);ids.add(e.tail_entity_id);}nodes=nodes.filter(n=>ids.has(n.id));}
  const ids=new Set(nodes.map(n=>n.id)),edges=graph.edges.filter(e=>e.status==='active'&&ids.has(e.head_entity_id)&&ids.has(e.tail_entity_id)&&(!onlyBridges||e.cross_group));
  if(overview){const groups=graph.groups.filter(g=>g.entity_ids.some(id=>ids.has(id))),gids=new Set(groups.map(g=>g.id)),edgeIds=new Set(edges.map(e=>e.id));return [...groups.map(g=>({data:{id:'group:'+g.id,label:`${g.name}\n${g.entity_ids.filter(id=>ids.has(id)).length} 个实体`,color:g.color,width:180,height:70,groupId:g.id,overview:true}})),...graph.group_relations.filter(b=>gids.has(b.source)&&gids.has(b.target)&&b.relation_ids.some(id=>edgeIds.has(id))).map(b=>({data:{id:b.id,source:'group:'+b.source,target:'group:'+b.target,label:`${b.label} · ${b.relation_ids.filter(id=>edgeIds.has(id)).length} 条`,bridge:true,overview:true,color:'#b35076'}}))];}
  return [...nodes.map(n=>({data:{id:n.id,label:n.name,color:n.group_color,width:Math.min(190,Math.max(120,n.name.length*14+30)),height:n.name.length>10?72:54,groupId:n.group_id,external:!!selected&&n.group_id!==selected}})),...edges.map(e=>({data:{id:e.id,source:e.head_entity_id,target:e.tail_entity_id,label:e.predicate||e.type,bridge:e.cross_group,color:e.cross_group?'#b35076':'#71877d'}}))];
}

/** Render groups as reading aids; group arrows always unfold to real entity assertions. */
export default function GraphView({snap,onChange,readOnly=false}:{snap:Snapshot;onChange?:(s:Snapshot)=>void;readOnly?:boolean}){
  const [editingEntity,setEditingEntity]=useState(false);
  const canvas=useRef<HTMLDivElement>(null),cy=useRef<Core|null>(null);
  const [graph,setGraph]=useState<GroupGraph|null>(null),[error,setError]=useState(''),[mode,setMode]=useState('knowledge');
  const [group,setGroup]=useState<string|null>(null),[neighbors,setNeighbors]=useState(true),[overview,setOverview]=useState(false),[onlyBridges,setOnlyBridges]=useState(false);
  const [query,setQuery]=useState(''),[type,setType]=useState(''),[focus,setFocus]=useState<string|null>(null),[expanded,setExpanded]=useState(true);
  const [relationId,setRelationId]=useState<string|null>(null),[bridgeId,setBridgeId]=useState<string|null>(null);
  const {selectedEntity,selectedCard,selectEntity,selectCard,pathIds}=useStore();
  const selectedNode=snap.entities.find(e=>e.id===selectedEntity&&e.status!=='deleted');
  const bridge=graph?.group_relations.find(b=>b.id===bridgeId),relation=snap.relations.find(r=>r.id===relationId);
  const names=new Map(snap.entities.map(e=>[e.id,e.name])),groupNames=new Map(graph?.groups.map(g=>[g.id,g.name])||[]);
  useEffect(()=>{let alive=true;setGraph(null);setError('');setGroup(null);setRelationId(null);setBridgeId(null);api<GroupGraph>(`/sessions/${snap.session.id}/graph?mode=${mode}`).then(g=>{if(alive){if(g.revision===snap.revision)setGraph(g);else setError('记录已更新，请刷新图谱。');}}).catch(e=>alive&&setError(String(e)));return()=>{alive=false;};},[snap.session.id,snap.revision,mode]);
  useEffect(()=>{if(!canvas.current||!graph)return;const instance=cytoscape({container:canvas.current,elements:groupElements(graph,group,neighbors,overview,onlyBridges,query,type,focus),minZoom:.15,maxZoom:4,
    style:[
      {selector:'node',style:{shape:'round-rectangle',label:'data(label)',width:'data(width)',height:'data(height)','background-color':'data(color)','background-opacity':.18,'border-color':'data(color)','border-width':2,color:'#18322d','font-size':16,'font-weight':600,'font-family':'Microsoft YaHei, sans-serif','text-wrap':'wrap','text-max-width':'155px','text-valign':'center','text-halign':'center'}},
      {selector:'node[?external]',style:{'border-style':'dashed','background-opacity':.08}},
      {selector:'edge',style:{label:'data(label)',width:2,'curve-style':'bezier','control-point-step-size':65,'line-color':'data(color)','target-arrow-color':'data(color)','target-arrow-shape':'triangle','font-size':15,color:'#29483c','text-background-color':'#fff','text-background-opacity':.97,'text-background-padding':'4px','text-rotation':'autorotate'}},
      {selector:'edge[?bridge]',style:{width:4,'line-color':'#b35076','target-arrow-color':'#b35076',color:'#8f3559','font-weight':700}},
      {selector:'.highlight',style:{'border-width':4,'border-color':'#d99b2b','line-color':'#d99b2b','target-arrow-color':'#d99b2b'}}
    ],layout:{name:'cose',animate:false,randomize:false,nodeDimensionsIncludeLabels:true,nodeRepulsion:()=>11000,idealEdgeLength:()=>115,componentSpacing:120,nodeOverlap:30,padding:40,numIter:1200}});
    cy.current=instance;instance.on('tap','node',e=>{if(e.target.data('overview')){setGroup(e.target.data('groupId'));setOverview(false);}else selectEntity(e.target.id());});instance.on('tap','edge',e=>{if(e.target.data('overview')){setBridgeId(e.target.id());setRelationId(null);}else{setRelationId(e.target.id());setBridgeId(null);}});instance.on('dbltap','node',e=>{if(!e.target.data('overview'))setFocus(e.target.id());});const resize=new ResizeObserver(()=>instance.resize());resize.observe(canvas.current);return()=>{resize.disconnect();instance.destroy();cy.current=null;};
  },[graph,group,neighbors,overview,onlyBridges,query,type,focus,expanded,selectEntity]);
  useEffect(()=>{if(!cy.current||!graph)return;const card=snap.cards.find(c=>c.id===selectedCard),ids=new Set([...pathIds,...(card?.entity_ids||[]),...(card?.relation_ids||[]),...(selectedEntity?[selectedEntity]:[]),...(bridge?.relation_ids||[]),...(bridge?[bridge.id]:[]),...(relation?[relation.id,relation.head_entity_id,relation.tail_entity_id]:[])]);if(bridge)for(const r of graph.edges)if(bridge.relation_ids.includes(r.id)){ids.add(r.head_entity_id);ids.add(r.tail_entity_id);}for(const n of graph.nodes)if(ids.has(n.id))ids.add('group:'+n.group_id);cy.current.elements().removeClass('highlight');cy.current.elements().forEach(e=>{if(ids.has(e.id()))e.addClass('highlight');});},[graph,selectedCard,selectedEntity,pathIds,bridge,relation,snap,group,neighbors,overview,onlyBridges,query,type,focus,expanded]);
  function reset(){setGroup(null);setQuery('');setType('');setFocus(null);setOnlyBridges(false);setBridgeId(null);setRelationId(null);}
  const evidence=snap.relations.filter(r=>(bridge?.relation_ids||(relation?[relation.id]:[])).includes(r.id));
  return <section className={`graph-panel ${expanded?'is-expanded':''}`}>
    <div className="panel-heading"><div><span className="eyebrow">KNOWLEDGE MAP</span><h2>让想法建立连接</h2></div><span className="pill">{graph?.group_relations.length||0} 条组间关系</span></div>
    <p className="muted">同色为一个主题组，紫红色箭头连接不同主题。每条组间关系都可展开到具体实体和原文。</p>
    <label>图谱视图 <select aria-label="图谱视图" value={mode} onChange={e=>setMode(e.target.value)}><option value="knowledge">实体关系</option><option value="evidence">实体关系与证据</option></select></label>
    {error&&<p role="alert">{error}</p>}{!graph&&!error&&<p role="status">正在加载主题与组间联系…</p>}
    <div className="graph-tools"><button onClick={()=>setExpanded(!expanded)}>{expanded?'并排查看卡片':'展开大图'}</button><button onClick={()=>setOverview(!overview)}>{overview?'展开实体':'组间总览'}</button><button aria-label="放大图谱" onClick={()=>cy.current?.zoom(cy.current.zoom()*1.2)}>＋</button><button aria-label="缩小图谱" onClick={()=>cy.current?.zoom(cy.current.zoom()/1.2)}>−</button><input aria-label="搜索定位节点" placeholder="搜索定位节点…" value={query} onChange={e=>setQuery(e.target.value)}/><select aria-label="节点类型" value={type} onChange={e=>setType(e.target.value)}><option value="">所有类型</option>{['PERSON','ORG','CONCEPT','EVENT','TIME','LOCATION','OTHER'].map(t=><option key={t}>{t}</option>)}</select><button disabled={!selectedEntity||overview} onClick={()=>setFocus(selectedEntity)}>邻域</button><button onClick={reset}>全图</button></div>
    <div className="group-options"><label><input type="checkbox" checked={onlyBridges} onChange={e=>setOnlyBridges(e.target.checked)}/> 只看组间关系</label><label><input type="checkbox" checked={neighbors} onChange={e=>setNeighbors(e.target.checked)}/> 选组时保留跨组连接实体</label></div>
    <div className="relationship-groups" aria-label="关系分组"><button aria-pressed={!group} onClick={()=>{setGroup(null);setQuery('');setFocus(null);}}>全部关系组</button>{graph?.groups.map(g=><button key={g.id} aria-pressed={group===g.id} onClick={()=>{setGroup(g.id);setQuery('');setType('');setFocus(null);}}><i style={{background:g.color}}/>{g.name}<span>{g.entity_ids.length}</span></button>)}</div>
    {selectedNode&&onChange&&<section className="selected-entity-panel" aria-label="选中实体详情"><div><strong>{selectedNode.name}</strong><span className="muted"> · 图谱实体</span><button className="edit-card-button" disabled={readOnly} onClick={()=>setEditingEntity(v=>!v)}>{editingEntity?'收起编辑':'编辑实体'}</button></div>{editingEntity&&<EntityEditor key={selectedNode.id} entity={selectedNode} snap={snap} disabled={readOnly} onCancel={()=>setEditingEntity(false)} onSaved={s=>{onChange(s);setEditingEntity(false);}}/>}</section>}
    <div ref={canvas} className="graph-canvas" data-testid="graph-canvas"/>
    <div className="graph-footer"><span>拖拽节点 · 滚轮缩放 · 点击连线查看证据</span><span>{graph?.edges.length||0} 条实体关系 · {graph?.groups.length||0} 个主题组</span></div>
    <details className="group-bridges" open><summary>有证据的组间关系 · {graph?.group_relations.length||0}</summary><p className="muted">组间箭头汇总具体实体关系，不表示两组中每个实体都相互关联。</p><div className="relation-list">{graph?.group_relations.map(b=><button key={b.id} aria-pressed={bridgeId===b.id} onClick={()=>{setBridgeId(b.id);setRelationId(null);}}>{groupNames.get(b.source)} → {b.label} → {groupNames.get(b.target)}（{b.relation_ids.length} 条实体关系）</button>)}</div>{graph&&!graph.group_relations.length&&<p>当前没有已确认的跨组关系。未明确说出的关系不会自动补线。</p>}</details>
    <details className="semantic-relations"><summary>全部实体关系</summary><div className="relation-list">{graph?.edges.map(r=><button key={r.id} onClick={()=>{setRelationId(r.id);setBridgeId(null);}}>{names.get(r.head_entity_id)} → {r.predicate||r.type} → {names.get(r.tail_entity_id)}</button>)}</div></details>
    {!!evidence.length&&<div className="relation-evidence" role="region" aria-label="组间关系原文证据"><h3>{bridge?'组间联系的实体证据':'实体关系证据'}</h3>{evidence.map(r=><article key={r.id}><button onClick={()=>{selectEntity(r.head_entity_id);setOverview(false);setGroup(null);setQuery('');setType('');setFocus(null);}}>{names.get(r.head_entity_id)} → {r.predicate||r.type} → {names.get(r.tail_entity_id)}</button>{snap.segments.filter(s=>r.source_segment_ids.includes(s.id)).map(s=><p key={s.id}>[{(s.start_ms/1000).toFixed(1)} 秒] {s.text}</p>)}{r.evidence_card_ids.map(id=><button key={id} onClick={()=>selectCard(id)}>查看要点：{snap.cards.find(c=>c.id===id)?.title||'原文要点'}</button>)}</article>)}</div>}
  </section>;
}
