/** Visual groups derived from accepted graph connectivity; never creates fact edges. */
import type { Snapshot } from '@/api/client';
export const GROUP_PALETTE = [
  {fill:'#d9eee8',border:'#247c68'}, {fill:'#e0e8fb',border:'#536fb4'},
  {fill:'#fbe6d5',border:'#bd7742'}, {fill:'#eee2f5',border:'#9365ac'},
  {fill:'#f8e0e5',border:'#b95d77'}, {fill:'#e8edce',border:'#829444'},
  {fill:'#d9eef3',border:'#388ca0'}, {fill:'#f5ebca',border:'#a58a35'},
];
/** Compute stable connected components before filters so group colors do not jump. */
export function relationGroups(snap: Snapshot) {
  const nodes=snap.entities.filter(e=>e.status==='active');
  const neighbors=new Map(nodes.map(n=>[n.id,new Set<string>()]));
  for(const edge of snap.relations) if(edge.status==='active' && neighbors.has(edge.head_entity_id) && neighbors.has(edge.tail_entity_id)) {
    neighbors.get(edge.head_entity_id)!.add(edge.tail_entity_id); neighbors.get(edge.tail_entity_id)!.add(edge.head_entity_id);
  }
  const seen=new Set<string>(), groups: string[][]=[];
  for(const id of [...neighbors.keys()].sort()) {
    if(seen.has(id))continue;
    const component:string[]=[], queue=[id];seen.add(id);
    while(queue.length){const next=queue.pop()!;component.push(next);for(const neighbor of neighbors.get(next)!)if(!seen.has(neighbor)){seen.add(neighbor);queue.push(neighbor);}}
    groups.push(component.sort());
  }
  return new Map(groups.flatMap((ids,index)=>ids.map(id=>[id,{...(GROUP_PALETTE[index] || {fill:`hsl(${(index*137.508)%360}, 48%, 89%)`,border:`hsl(${(index*137.508)%360}, 42%, 40%)`}),group:index+1}] as const)));
}
