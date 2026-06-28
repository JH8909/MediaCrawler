from fastapi.testclient import TestClient

from api.main import app


def test_auto_demand_status_endpoint():
    client = TestClient(app)

    response = client.get("/api/auto-demand/status")

    assert response.status_code == 200
    data = response.json()
    assert "config" in data
    assert "running" in data


def test_auto_demand_config_update():
    client = TestClient(app)

    response = client.post("/api/auto-demand/config", json={"interval": "6h", "platforms": ["xhs"], "keyword_count": 2})

    assert response.status_code == 200
    assert response.json()["config"]["interval"] == "6h"


def test_auto_demand_rejects_invalid_interval():
    client = TestClient(app)

    response = client.post("/api/auto-demand/config", json={"interval": "1h"})

    assert response.status_code == 422
