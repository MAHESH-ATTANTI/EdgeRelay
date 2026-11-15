import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(main, "STORAGE_DIR", tmp_path / "releases")

    with TestClient(main.app) as test_client:
        yield test_client


def create_test_release(client):
    response = client.post(
        "/releases",
        data={"name": "demo-app", "version": "1.0.0"},
        files={
            "package": ("demo.txt", b"EdgeRelay pending job package", "text/plain")
        },
    )
    assert response.status_code == 201
    return response.json()


def create_test_node(client):
    response = client.post(
        "/nodes",
        data={"name": "edge-node-01"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_online_node_fetches_pending_jobs(client):
    release = create_test_release(client)
    node_id = create_test_node(client)

    client.post(
        "/delivery-jobs",
        data={
            "release_id": release["id"],
            "edge_node_id": node_id,
        },
    )

    client.patch(
        f"/nodes/{node_id}/status",
        data={"status": "online"},
    )

    response = client.get(f"/nodes/{node_id}/pending-jobs")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["release_name"] == "demo-app"
    assert response.json()[0]["release_version"] == "1.0.0"
    assert response.json()[0]["job_status"] == "queued"
    assert response.json()[0]["sha256"] == release["sha256"]


def test_offline_node_cannot_fetch_pending_jobs(client):
    node_id = create_test_node(client)

    response = client.get(f"/nodes/{node_id}/pending-jobs")

    assert response.status_code == 409
    assert response.json()["detail"] == "Edge node is offline"


def test_nonexistent_node_pending_jobs(client):
    response = client.get("/nodes/99999/pending-jobs")

    assert response.status_code == 404
    assert response.json()["detail"] == "Edge node not found"


def test_online_node_with_no_pending_jobs(client):
    node_id = create_test_node(client)

    client.patch(
        f"/nodes/{node_id}/status",
        data={"status": "online"},
    )

    response = client.get(f"/nodes/{node_id}/pending-jobs")

    assert response.status_code == 200
    assert response.json() == []
