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
            "package": ("demo.txt", b"EdgeRelay download test", "text/plain")
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

def test_successful_delivery_job_download(client):
    job, release, node_id = create_test_job(client)

    client.patch(
        f"/nodes/{node_id}/status",
        data={"status": "online"},
    )

    response = client.get(
        f"/delivery-jobs/{job['id']}/download"
    )

    assert response.status_code == 200
    assert response.content == b"EdgeRelay download test"
    assert response.headers["X-Release-SHA256"] == release["sha256"]
    assert response.headers["X-Delivery-Job-ID"] == str(job["id"])

def test_offline_node_cannot_download(client):
    job, release, node_id = create_test_job(client)

    response = client.get(
        f"/delivery-jobs/{job['id']}/download"
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Edge node is offline"

def test_download_nonexistent_delivery_job(client):
    response = client.get("/delivery-jobs/99999/download")

    assert response.status_code == 404
    assert response.json()["detail"] == "Delivery job not found"

def test_download_missing_package_file(client):
    job, release, node_id = create_test_job(client)

    client.patch(
        f"/nodes/{node_id}/status",
        data={"status": "online"},
    )

    package_path = next(main.STORAGE_DIR.glob("*.package"))
    package_path.unlink()

    response = client.get(
        f"/delivery-jobs/{job['id']}/download"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Package file not found"
