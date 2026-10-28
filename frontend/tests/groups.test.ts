/** Cross-topic filtering and overview must preserve real witness edges. */
import {describe,it,expect} from 'vitest';
import {groupElements,type GroupGraph} from '../src/components/GraphView';
const nodes=['a','b','c','d'].map((id,i)=>({id,name:id,status:'active',type:'CONCEPT',group_id:i<2?'g1':'g2',group_name:i<2?'甲主题':'乙主题',group_color:i<2?'#247c68':'#536fb4'}));
const graph={nodes,edges:[{id:'ab',head_entity_id:'a',tail_entity_id:'b',predicate:'包含',status:'active',cross_group:false},{id:'cd',head_entity_id:'c',tail_entity_id:'d',predicate:'支持',status:'active',cross_group:false},{id:'bc',head_entity_id:'b',tail_entity_id:'c',predicate:'依赖',status:'active',cross_group:true}],groups:[{id:'g1',name:'甲主题',color:'#247c68',entity_ids:['a','b']},{id:'g2',name:'乙主题',color:'#536fb4',entity_ids:['c','d']}],group_relations:[{id:'bridge',source:'g1',target:'g2',label:'依赖',relation_ids:['bc'],evidence_segment_ids:['s'],source_card_ids:['card']}],revision:1} as GroupGraph;
describe('witnessed group display',()=>{
 it('keeps distinct group colors despite a real crossing edge',()=>{const elements=groupElements(graph,null,true,false,false,'','',null);expect(elements.find(e=>e.data.id==='a')?.data.color).not.toBe(elements.find(e=>e.data.id==='c')?.data.color);expect(elements.find(e=>e.data.id==='bc')?.data.bridge).toBe(true);});
 it('retains only one-hop context when selecting a group',()=>{expect(groupElements(graph,'g1',true,false,false,'','',null).map(e=>e.data.id)).toEqual(['a','b','c','ab','bc']);});
 it('permits explicit isolation without dangling edges',()=>{expect(groupElements(graph,'g1',false,false,false,'','',null).map(e=>e.data.id)).toEqual(['a','b','ab']);});
 it('shows witnessed arrows in folded overview',()=>{const elements=groupElements(graph,null,true,true,false,'','',null);expect(elements.map(e=>e.data.id)).toEqual(['group:g1','group:g2','bridge']);expect(elements[2].data.label).toBe('依赖 · 1 条');});
 it('does not invent an overview edge after witnesses are filtered out',()=>{expect(groupElements(graph,'g1',false,true,false,'','',null).map(e=>e.data.id)).toEqual(['group:g1']);});
 it('only-bridge filter hides internal relations',()=>{const elements=groupElements(graph,null,true,false,true,'','',null);expect(elements.filter(e=>e.data.source).map(e=>e.data.id)).toEqual(['bc']);});
});
