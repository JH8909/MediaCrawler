import asyncio

from fastapi.testclient import TestClient

from api.main import app
from api.routers import pipeline as pipeline_router


def test_pipeline_status_idle_returns_serializable_payload():
    client = TestClient(app)

    response = client.get("/api/pipeline/status")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] in {"idle", "running", "completed", "failed"}
    assert "logs" in data
    assert isinstance(data["last_result"], dict)


def test_pipeline_start_returns_immediately(monkeypatch):
    client = TestClient(app)
    started = {"value": False}

    async def fake_start(**_kwargs):
        started["value"] = True
        await asyncio.sleep(0.01)
        return {"status": "completed"}

    monkeypatch.setattr(pipeline_router.pipeline_manager, "status", "idle")
    monkeypatch.setattr(pipeline_router.pipeline_manager, "start", fake_start)

    response = client.post(
        "/api/pipeline/start",
        json={"platforms": ["xhs"], "keyword_count": 1, "max_notes": 1},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "started"
