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
            "package": ("demo.txt", b"EdgeRelay completion test", "text/plain")
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


def create_test_job(client):
    release = create_test_release(client)
    node_id = create_test_node(client)

    response = client.post(
        "/delivery-jobs",
        data={
            "release_id": release["id"],
            "edge_node_id": node_id,
        },
    )
    assert response.status_code == 201

    return response.json(), release, node_id

def test_successful_delivery_completion(client):
    job, release, node_id = create_test_job(client)

    response = client.patch(
        f"/delivery-jobs/{job['id']}/complete",
        data={
            "edge_node_id": node_id,
            "verified_sha256": release["sha256"],
        },
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Delivery completed successfully"
    assert response.json()["job"]["status"] == "completed"
    assert response.json()["job"]["error_message"] is None

def test_delivery_completion_with_invalid_sha256(client):
    job, release, node_id = create_test_job(client)

    response = client.patch(
        f"/delivery-jobs/{job['id']}/complete",
        data={
            "edge_node_id": node_id,
            "verified_sha256": "invalid_checksum",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "SHA-256 verification failed"

def test_completion_from_wrong_edge_node(client):
    job, release, node_id = create_test_job(client)

    response = client.patch(
        f"/delivery-jobs/{job['id']}/complete",
        data={
            "edge_node_id": 99999,
            "verified_sha256": release["sha256"],
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Job does not belong to this edge node"

def test_already_completed_job_cannot_be_completed_again(client):
    job, release, node_id = create_test_job(client)

    first_response = client.patch(
        f"/delivery-jobs/{job['id']}/complete",
        data={
            "edge_node_id": node_id,
            "verified_sha256": release["sha256"],
        },
    )

    assert first_response.status_code == 200

    second_response = client.patch(
        f"/delivery-jobs/{job['id']}/complete",
        data={
            "edge_node_id": node_id,
            "verified_sha256": release["sha256"],
        },
    )

    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "Delivery job is not queued"
