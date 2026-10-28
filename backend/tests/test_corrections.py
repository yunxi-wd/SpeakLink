"""Correction priority, merge/split evidence, concurrency and rollback integration."""
def edit(client, snap, kind, target, action, payload):
    """Submit an operation using the current revision."""
    response = client.post('/api/corrections', json={"session_id": snap["session"]["id"], "target_type": kind, "target_id": target, "action": action, "payload": payload, "expected_revision": snap["revision"]})
    assert response.status_code == 200, response.text
    return response.json()

def test_manual_edit_replay_and_rollback(client, recording):
    """Renamed entities survive reprocessing, search reflects the edit, rollback restores."""
    original = next(e for e in recording["entities"] if e["name"] == "张三")
    snap = edit(client, recording, "entity", original["id"], "update", {"name": "张老师"})
    sid = snap["session"]["id"]
    snap = client.post(f'/api/sessions/{sid}/process').json()
    assert next(e for e in snap["entities"] if e["id"] == original["id"])["name"] == "张老师"
    assert client.post(f'/api/sessions/{sid}/search', json={"query":"张老师"}).json()["cards"]
    correction = client.get(f'/api/sessions/{sid}/corrections').json()[-1]
    rolled = client.post(f'/api/corrections/{correction["id"]}/rollback?expected_revision={snap["revision"]}')
    assert rolled.status_code == 200, rolled.text
    assert next(e for e in rolled.json()["entities"] if e["id"] == original["id"])["name"] == "张三"

def test_split_moves_evidence_and_edges(client, recording):
    """Splitting a multiply-mentioned concept moves only selected provenance and edges."""
    target = next(e for e in recording["entities"] if e["name"] == "语音项目")
    selected = [target["source_card_ids"][0]]
    snap = edit(client, recording, "entity", target["id"], "split", {"name":"语音项目二", "source_card_ids": selected})
    new = next(e for e in snap["entities"] if e["name"] == "语音项目二")
    assert new["source_card_ids"] == selected
    assert all(set(r["evidence_card_ids"]) <= set(selected) for r in snap["relations"] if new["id"] in [r["head_entity_id"],r["tail_entity_id"]])
    again = client.post(f'/api/sessions/{snap["session"]["id"]}/process').json()
    assert again["entities"] == snap["entities"]

def test_merge_delete_relation_and_stale_revision(client, recording):
    """Merged endpoints stay valid and stale clients cannot overwrite corrections."""
    nodes = [e for e in recording["entities"] if e["name"] in {"语音项目", "离线方案"}]
    snap = edit(client, recording, "entity", nodes[0]["id"], "merge", {"into_id":nodes[1]["id"]})
    assert next(e for e in snap["entities"] if e["id"] == nodes[0]["id"])["canonical_id"] == nodes[1]["id"]
    response = client.patch(f'/api/entities/{nodes[1]["id"]}', json={"name":"冲突", "expected_revision":recording["revision"]})
    assert response.status_code == 409
    relation = next(r for r in snap["relations"] if r["status"] == "active")
    snap = edit(client, snap, "relation", relation["id"], "delete", {})
    sid = snap["session"]["id"]
    assert relation["id"] not in {r["id"] for r in client.get(f'/api/sessions/{sid}/graph').json()["edges"]}
    assert next(r for r in client.post(f'/api/sessions/{sid}/process').json()["relations"] if r["id"] == relation["id"])["status"] == "deleted"

def test_cluster_and_card_edit(client, recording):
    """Manual topic merge and card edits persist through model processing."""
    a,b = recording["clusters"]
    snap = edit(client, recording, "cluster", a["id"], "merge", {"into_id":b["id"]})
    snap = edit(client, snap, "cluster", b["id"], "update", {"name":"人工主题"})
    snap = edit(client, snap, "card", snap["cards"][0]["id"], "update", {"title":"人工要点"})
    again = client.post(f'/api/sessions/{snap["session"]["id"]}/process').json()
    assert len(again["clusters"]) == 1 and again["clusters"][0]["name"] == "人工主题"
    assert again["cards"][0]["title"] == "人工要点"

def test_deleted_only_evidence_does_not_leave_active_relation(client, recording):
    """Deleting the only evidence card must remove its relationship from the main graph."""
    relation = next(r for r in recording['relations'] if len(r['evidence_card_ids']) == 1)
    snap = edit(client, recording, 'card', relation['evidence_card_ids'][0], 'delete', {})
    assert next(r for r in snap['relations'] if r['id'] == relation['id'])['status'] != 'active'
