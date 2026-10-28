"""Isolated temporary database fixtures; never touch the user's recording library."""
import os
from pathlib import Path
from uuid import uuid4
TEST_DATA = Path(__file__).resolve().parents[2] / "work" / ("test-" + uuid4().hex)
TEST_DATA.mkdir(parents=True)
os.environ["KNOWGPT_DATA_DIR"] = str(TEST_DATA)
os.environ["KNOWGPT_LLM_PROVIDER"] = "demo"
os.environ["KNOWGPT_EMBEDDING_PROVIDER"] = "hash"
import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture(scope="session")
def client():
    """Serve real routes against migrated SQLite inside application lifespan."""
    with TestClient(app) as value:
        yield value

@pytest.fixture
def recording(client):
    """Return a fresh processed multi-topic recording."""
    sid = client.post("/api/sessions", json={"title": "测试速记"}).json()["id"]
    lines = ["张三参与语音项目。", "他属于星河公司。", "语音项目依赖离线方案。", "那个方案导致成本下降。", "另外说，知识图谱属于人工智能。", "李四参与知识图谱。"]
    response = client.put(f"/api/sessions/{sid}/transcript", json={"segments": [{"text": t, "start_ms": i*5000, "end_ms": (i+1)*5000} for i,t in enumerate(lines)]})
    assert response.status_code == 200, response.text
    response = client.post(f"/api/sessions/{sid}/process")
    assert response.status_code == 200, response.text
    return response.json()
