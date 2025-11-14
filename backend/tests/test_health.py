from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_endpoint_returns_ok_status() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "ok"
    assert payload["service"] == "SigmaTrader API"
    assert payload["environment"] in {"dev", "prod", "test"}


def test_root_endpoint_returns_message() -> None:
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()

    assert "message" in payload
    assert "SigmaTrader API" in payload["message"]

