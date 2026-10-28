"""End-to-end API, coreference, convergence and projection invariants."""
import json
import networkx as nx
from app.services.common import normalize
from app.services.asr import clean_text

def test_normalization_and_source_cleanup():
    """Unicode/case/punctuation variants normalize without aggressive stemming."""
    assert normalize(" ＡＩ-Project ") == normalize("ai project")
    assert normalize("项目们") == normalize("项目")
    assert clean_text("嗯，张三参与项目。。") == "张三参与项目。"

def test_pipeline_provenance_and_coreference(recording, client):
    """Accepted graph resolves unique pronouns and all inverse evidence links match."""
    snap = recording
    names = {e["name"] for e in snap["entities"] if e["status"] == "active"}
    assert "他" not in names and "那个方案" not in names
    assert {"张三", "离线方案", "知识图谱"} <= names
    assert len(snap["clusters"]) == 2
    assert snap["clusters"][1]["reason"] == "显式话题切换词"
    for card in snap["cards"]:
        assert set(card["source_segment_ids"]) <= {s["id"] for s in snap["segments"]}
        assert set(card["entity_ids"]) == {e["id"] for e in snap["entities"] if card["id"] in e["source_card_ids"] and e["status"] != "deleted"}
    assert client.get(f'/api/sessions/{snap["session"]["id"]}/graph').json()["revision"] == snap["revision"]

def test_repeat_processing_stable(recording, client):
    """Candidate cache makes cards/entities/edges stable across reruns."""
    repeated = client.post(f'/api/sessions/{recording["session"]["id"]}/process').json()
    for field in ["cards", "entities", "relations", "clusters"]:
        assert recording[field] == repeated[field]
    assert repeated["session"]["metadata"]["candidate_cache_hit"] is True

def test_uncertainty_isolated(client):
    """Ambiguous pronouns and weak cards never enter the accepted graph."""
    sid = client.post('/api/sessions', json={"title": "模糊指代"}).json()["id"]
    client.put(f'/api/sessions/{sid}/transcript', json={"segments": [{"text": "张三参与项目，李四参与项目。"}, {"text": "他依赖方案。"}, {"text": "云服务可能导致泄露，待确认。"}]})
    snap = client.post(f'/api/sessions/{sid}/process').json()
    graph = client.get(f'/api/sessions/{sid}/graph').json()
    assert any(e["name"] == "他" and e["status"] == "pending" for e in snap["entities"])
    assert "他" not in {e["name"] for e in graph["nodes"]}
    assert graph["pending_count"] > 0

def test_search_and_exports(recording, client):
    """Hybrid search paths use real graph edges and exports roundtrip externally."""
    sid = recording["session"]["id"]
    result = client.post(f'/api/sessions/{sid}/search', json={"query": "张三与星河公司"}).json()
    assert result["cards"] and result["paths"]
    for a,b in zip(result["paths"][0], result["paths"][0][1:]):
        assert any({r["head_entity_id"], r["tail_entity_id"]} == {a,b} for r in result["relations"])
    exported = client.get(f'/api/sessions/{sid}/export?format=json')
    assert exported.json()["cards"] == recording["cards"]
    graphml = client.get(f'/api/sessions/{sid}/export?format=graphml').text
    graph = nx.parse_graphml(graphml)
    assert graph.number_of_nodes() == len([e for e in recording["entities"] if e["status"] == "active"])
    assert "[[张三]]" in client.get(f'/api/sessions/{sid}/export?format=markdown').text

def test_invalid_input_and_missing_session(client):
    """Reject invalid timestamps, missing resources and empty uploads."""
    assert client.get('/api/sessions/no-such-session').status_code == 404
    sid = client.post('/api/sessions', json={}).json()["id"]
    assert client.put(f'/api/sessions/{sid}/transcript', json={"segments": [{"text":"x","start_ms":10,"end_ms":0}]}).status_code == 422
    assert client.post(f'/api/sessions/{sid}/audio', files={"file": ("test.wav", b"", "audio/wav")}).status_code == 422
    assert client.post(f'/api/sessions/{sid}/audio', files={"file": ("test.exe", b"abc", "audio/wav")}).status_code == 415
