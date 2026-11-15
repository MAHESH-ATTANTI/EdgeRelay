import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(main, "STORAGE_DIR", tmp_path / "releases")

    with TestClient(main.app) as test_client:
        yield test_client


def test_register_node(client):
    response = client.post(
        "/nodes",
        data={"name": "edge-node-01"},
    )

    assert response.status_code == 201
    assert response.json()["name"] == "edge-node-01"
    assert response.json()["status"] == "offline"


def test_duplicate_node_rejected(client):
    client.post("/nodes", data={"name": "edge-node-01"})

    response = client.post(
        "/nodes",
        data={"name": "edge-node-01"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Node name already exists"


def test_empty_node_name_rejected(client):
    response = client.post("/nodes", data={"name": "   "})

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Node name must be between 1 and 100 characters"
    )


def test_long_node_name_rejected(client):
    response = client.post("/nodes", data={"name": "a" * 101})

    assert response.status_code == 400


def test_list_nodes(client):
    client.post("/nodes", data={"name": "edge-node-01"})
    client.post("/nodes", data={"name": "edge-node-02"})

    response = client.get("/nodes")

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.json()[0]["name"] == "edge-node-01"
    assert response.json()[1]["name"] == "edge-node-02"
