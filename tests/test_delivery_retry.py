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
            "package": ("demo.txt", b"EdgeRelay retry test", "text/plain")
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


def fail_test_job(client, job_id, node_id):
    response = client.patch(
        f"/delivery-jobs/{job_id}/fail",
        data={
            "edge_node_id": node_id,
            "error_message": "Temporary download failure",
        },
    )
    assert response.status_code == 200
    return response.json()

def test_successful_delivery_job_retry(client):
    job, release, node_id = create_test_job(client)

    # First bring the node online
    client.patch(
        f"/nodes/{node_id}/status",
        data={"status": "online"},
    )

    # Then mark the delivery job as failed
    fail_test_job(client, job["id"], node_id)

    # Retry the failed job
    response = client.patch(
        f"/delivery-jobs/{job['id']}/retry"
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Delivery job requeued successfully"
    assert response.json()["job"]["status"] == "queued"
    assert response.json()["job"]["retry_count"] == 1
    assert response.json()["job"]["error_message"] is None

def test_retry_failed_job_while_node_offline(client):
    job, release, node_id = create_test_job(client)

    fail_test_job(client, job["id"], node_id)

    response = client.patch(
        f"/delivery-jobs/{job['id']}/retry"
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Edge node is offline. Retry when node is online"
    )

def test_queued_job_cannot_be_retried(client):
    job, release, node_id = create_test_job(client)

    response = client.patch(
        f"/delivery-jobs/{job['id']}/retry"
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Only failed jobs can be retried"

def test_retry_rejected_after_maximum_retries(client):
    job, release, node_id = create_test_job(client)

    client.patch(
        f"/nodes/{node_id}/status",
        data={"status": "online"},
    )

    for attempt in range(3):
        fail_test_job(client, job["id"], node_id)

        if attempt < 2:
            retry_response = client.patch(
                f"/delivery-jobs/{job['id']}/retry"
            )
            assert retry_response.status_code == 200

    response = client.patch(
        f"/delivery-jobs/{job['id']}/retry"
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Maximum retry limit reached"

def test_retry_nonexistent_delivery_job(client):
    response = client.patch(
        "/delivery-jobs/99999/retry"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Delivery job not found"
