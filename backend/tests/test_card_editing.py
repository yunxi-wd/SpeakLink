"""Audited inline card edits: validation, persistence, retrieval, replay and rollback."""

def prepare(client):
    """Create an isolated processed recording through public endpoints."""
    sid = client.post('/api/sessions', json={'title': 'card editing'}).json()['id']
    client.put(f'/api/sessions/{sid}/transcript', json={'segments':[
        {'text':'人工智能能够完成任务。','start_ms':0,'end_ms':3000},
        {'text':'任务包括语言理解和图像识别。','start_ms':3000,'end_ms':6000},
    ]})
    response = client.post(f'/api/sessions/{sid}/process')
    assert response.status_code == 200, response.text
    return response.json()


def test_card_edit_persists_and_graph_links_remain_consistent(client):
    """One edited revision drives current cards, search, exports and graph links."""
    before = prepare(client); sid = before['session']['id']; card = before['cards'][0]
    updated = client.patch(f'/api/cards/{card["id"]}', json={
        'expected_revision':before['revision'], 'title':'  紫藤札记标题  ',
        'content':'人工整理后的正文。\n保留第二段内容。', 'card_type':'conclusion'})
    assert updated.status_code == 200, updated.text
    snap = updated.json(); edited = next(c for c in snap['cards'] if c['id']==card['id'])
    assert edited['title']=='紫藤札记标题' and edited['card_type']=='conclusion' and edited['manual_edited']
    assert edited['source_segment_ids']==card['source_segment_ids']
    assert edited['entity_ids']==card['entity_ids'] and edited['relation_ids']==card['relation_ids']
    assert snap['segments']==before['segments'] and snap['entities']==before['entities'] and snap['relations']==before['relations']
    assert next(c for c in client.get(f'/api/sessions/{sid}').json()['cards'] if c['id']==card['id'])==edited
    graph = client.get(f'/api/sessions/{sid}/graph').json()
    assert graph['revision']==snap['revision']
    results = client.post(f'/api/sessions/{sid}/search',json={'query':'紫藤札记标题'}).json()['cards']
    assert any(c['id']==card['id'] and c['title']=='紫藤札记标题' for c in results)
    exported = client.get(f'/api/sessions/{sid}/export?format=json').json()
    assert any(c['id']==card['id'] and c['title']=='紫藤札记标题' for c in exported['cards'])
    history = client.get(f'/api/sessions/{sid}/corrections').json()
    assert history[-1]['target_type']=='card' and history[-1]['target_id']==card['id']
    rerun = client.post(f'/api/sessions/{sid}/process').json()
    assert next(c for c in rerun['cards'] if c['id']==card['id'])['content']==edited['content']
    rolled = client.post(f'/api/corrections/{history[-1]["id"]}/rollback?expected_revision={rerun["revision"]}')
    assert rolled.status_code==200, rolled.text
    restored = next(c for c in rolled.json()['cards'] if c['id']==card['id'])
    assert restored['title']==card['title'] and restored['content']==card['content']


def test_card_edit_validation_and_stale_revision(client):
    """Reject blank, oversized, unsupported and stale updates without changing the card."""
    before = prepare(client); card = before['cards'][0]; sid = before['session']['id']
    for payload in [{'title':'   '},{'content':'\n\t'},{'title':'a'*201},{'content':'a'*10001},{'card_type':'made-up'},{'source_segment_ids':['foreign']},{'content':None},{}]:
        response=client.patch(f'/api/cards/{card["id"]}',json={'expected_revision':before['revision'],**payload})
        assert response.status_code==422,(payload.keys(),response.text)
    assert client.get(f'/api/sessions/{sid}').json()['revision']==before['revision']
    saved=client.patch(f'/api/cards/{card["id"]}',json={'expected_revision':before['revision'],'title':'人工修改'}).json()
    stale=client.patch(f'/api/cards/{card["id"]}',json={'expected_revision':before['revision'],'title':'不该覆盖'})
    assert stale.status_code==409
    assert client.get(f'/api/sessions/{sid}').json()['revision']==saved['revision']
    # The older general correction form must apply the same blank-text validation.
    invalid=client.post('/api/corrections',json={'session_id':sid,'target_type':'card','target_id':card['id'],
        'action':'update','payload':{'content':'   '},'expected_revision':saved['revision']})
    assert invalid.status_code==422


def test_card_editor_entity_name_edit_preserves_relations(client):
    """Changing a real graph label retains IDs and is visible in cards and graph."""
    before = prepare(client); entity = next(e for e in before['entities'] if e['status']=='active')
    result = client.patch(f'/api/entities/{entity["id"]}',json={'expected_revision':before['revision'],'name':'手工实体名称','type':'CONCEPT'})
    assert result.status_code==200, result.text
    snap=result.json(); sid=snap['session']['id']
    assert any(e['id']==entity['id'] and e['name']=='手工实体名称' for e in snap['entities'])
    assert snap['relations']==before['relations']
    graph=client.get(f'/api/sessions/{sid}/graph').json()
    assert any(e['id']==entity['id'] and e['name']=='手工实体名称' for e in graph['nodes'])
    assert client.patch('/api/cards/nonexistent',json={'expected_revision':snap['revision'],'title':'不存在'}).status_code==404
