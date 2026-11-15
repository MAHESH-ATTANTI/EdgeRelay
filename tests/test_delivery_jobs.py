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
            "package": ("demo.txt", b"EdgeRelay test package", "text/plain")
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def create_test_node(client):
    response = client.post(
        "/nodes",
        data={"name": "edge-node-01"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_create_delivery_job(client):
    release_id = create_test_release(client)
    node_id = create_test_node(client)

    response = client.post(
        "/delivery-jobs",
        data={
            "release_id": release_id,
            "edge_node_id": node_id,
        },
    )

    assert response.status_code == 201
    assert response.json()["release_id"] == release_id
    assert response.json()["edge_node_id"] == node_id
    assert response.json()["status"] == "queued"


def test_duplicate_delivery_job_rejected(client):
    release_id = create_test_release(client)
    node_id = create_test_node(client)

    job_data = {
        "release_id": release_id,
        "edge_node_id": node_id,
    }

    first_response = client.post("/delivery-jobs", data=job_data)
    second_response = client.post("/delivery-jobs", data=job_data)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == (
        "Delivery job already exists for this release and node"
    )


def test_delivery_job_with_invalid_release(client):
    node_id = create_test_node(client)

    response = client.post(
        "/delivery-jobs",
        data={"release_id": 99999, "edge_node_id": node_id},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Release not found"


def test_delivery_job_with_invalid_node(client):
    release_id = create_test_release(client)

    response = client.post(
        "/delivery-jobs",
        data={"release_id": release_id, "edge_node_id": 99999},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Edge node not found"


def test_list_delivery_jobs(client):
    release_id = create_test_release(client)
    node_id = create_test_node(client)

    client.post(
        "/delivery-jobs",
        data={
            "release_id": release_id,
            "edge_node_id": node_id,
        },
    )

    response = client.get("/delivery-jobs")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["release_name"] == "demo-app"
    assert response.json()[0]["edge_node_name"] == "edge-node-01"
