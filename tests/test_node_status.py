import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(main, "STORAGE_DIR", tmp_path / "releases")

    with TestClient(main.app) as test_client:
        yield test_client


def register_test_node(client):
    response = client.post(
        "/nodes",
        data={"name": "edge-node-01"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_update_node_status_online(client):
    node_id = register_test_node(client)

    response = client.patch(
        f"/nodes/{node_id}/status",
        data={"status": "online"},
    )

    assert response.status_code == 200
    assert response.json()["node"]["status"] == "online"
    assert response.json()["node"]["last_seen"] is not None


def test_update_node_status_offline(client):
    node_id = register_test_node(client)

    response = client.patch(
        f"/nodes/{node_id}/status",
        data={"status": "offline"},
    )

    assert response.status_code == 200
    assert response.json()["node"]["status"] == "offline"


def test_invalid_node_status_rejected(client):
    node_id = register_test_node(client)

    response = client.patch(
        f"/nodes/{node_id}/status",
        data={"status": "active"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Status must be online or offline"


def test_update_nonexistent_node_status(client):
    response = client.patch(
        "/nodes/99999/status",
        data={"status": "online"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Edge node not found"


def test_node_heartbeat(client):
    node_id = register_test_node(client)

    response = client.post(f"/nodes/{node_id}/heartbeat")

    assert response.status_code == 200
    assert response.json()["message"] == "Heartbeat received successfully"
    assert response.json()["node"]["status"] == "online"
    assert response.json()["node"]["last_seen"] is not None


def test_heartbeat_nonexistent_node(client):
    response = client.post("/nodes/99999/heartbeat")

    assert response.status_code == 404
    assert response.json()["detail"] == "Edge node not found"
