"""Consistent JSON, interoperable GraphML and linked Markdown exports."""
import json
import re
import networkx as nx
from ..schemas.domain import Snapshot
from .graph_store import network

def escape(text: str) -> str:
    """Escape Markdown metacharacters originating in untrusted transcript text."""
    return re.sub(r"([\\`*_{}\[\]<>])", r"\\\1", text)

def export(snap: Snapshot, format: str) -> tuple[str, str, str]:
    """Return (content, media type, suffix) for the exact current revision."""
    if format == "json":
        return json.dumps(snap.model_dump(), ensure_ascii=False, indent=2), "application/json", "json"
    if format == "graphml":
        return "\n".join(nx.generate_graphml(network(snap))), "application/graphml+xml", "graphml"
    names = {e.id: e.name for e in snap.entities if e.status == "active"}
    lines = [f"# {escape(snap.session.title)}", f"修订：{snap.revision}", ""]
    for c in snap.cards:
        if c.status == "deleted":
            continue
        lines += [f"## {escape(c.title)}", f"类型：{c.card_type} / 状态：{c.status}", escape(c.content), "关联：" + " ".join(f"[[{escape(names[e])}]]" for e in c.entity_ids if e in names), "来源：" + ", ".join(c.source_segment_ids), ""]
    lines += ["## 关系", *[f"- [[{escape(names[r.head_entity_id])}]] → {escape(r.predicate or r.type)} → [[{escape(names[r.tail_entity_id])}]]" for r in snap.relations if r.status == "active" and r.head_entity_id in names and r.tail_entity_id in names], "", "## 原文"]
    lines += [f"- {s.id} [{s.start_ms / 1000:.1f}–{s.end_ms / 1000:.1f}s] {escape(s.raw_text or s.text)}" for s in snap.segments]
    return "\n".join(lines), "text/markdown", "md"
