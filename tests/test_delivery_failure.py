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
            "package": ("demo.txt", b"EdgeRelay failure test", "text/plain")
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

def test_successful_delivery_failure_report(client):
    job, release, node_id = create_test_job(client)

    response = client.patch(
        f"/delivery-jobs/{job['id']}/fail",
        data={
            "edge_node_id": node_id,
            "error_message": "Package download failed",
        },
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Delivery marked as failed"
    assert response.json()["job"]["status"] == "failed"
    assert response.json()["job"]["retry_count"] == 1
    assert response.json()["job"]["error_message"] == "Package download failed"

def test_failure_report_from_wrong_edge_node(client):
    job, release, node_id = create_test_job(client)

    response = client.patch(
        f"/delivery-jobs/{job['id']}/fail",
        data={
            "edge_node_id": 99999,
            "error_message": "Package download failed",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Job does not belong to this edge node"

def test_already_failed_job_cannot_fail_again(client):
    job, release, node_id = create_test_job(client)

    first_response = client.patch(
        f"/delivery-jobs/{job['id']}/fail",
        data={
            "edge_node_id": node_id,
            "error_message": "First failure",
        },
    )

    assert first_response.status_code == 200

    second_response = client.patch(
        f"/delivery-jobs/{job['id']}/fail",
        data={
            "edge_node_id": node_id,
            "error_message": "Second failure",
        },
    )

    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "Delivery job is not queued"
def test_failure_report_for_nonexistent_job(client):
    response = client.patch(
        "/delivery-jobs/99999/fail",
        data={
            "edge_node_id": 1,
            "error_message": "Package download failed",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Delivery job not found"
