import hashlib

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(main, "STORAGE_DIR", tmp_path / "releases")

    with TestClient(main.app) as test_client:
        yield test_client


def test_successful_release_upload(client):
    package_content = b"EdgeRelay automated testing package"

    response = client.post(
        "/releases",
        data={
            "name": "demo-app",
            "version": "1.0.0",
        },
        files={
            "package": ("demo-release.txt", package_content, "text/plain")
        },
    )

    expected_checksum = hashlib.sha256(package_content).hexdigest()

    assert response.status_code == 201
    assert response.json()["name"] == "demo-app"
    assert response.json()["version"] == "1.0.0"
    assert response.json()["filename"] == "demo-release.txt"
    assert response.json()["size_bytes"] == len(package_content)
    assert response.json()["sha256"] == expected_checksum
    assert response.json()["status"] == "stored"


def test_duplicate_release_rejected(client):
    package_content = b"EdgeRelay test package"

    upload_data = {
        "name": "demo-app",
        "version": "1.0.0",
    }

    first_response = client.post(
        "/releases",
        data=upload_data,
        files={
            "package": ("demo.txt", package_content, "text/plain")
        },
    )

    second_response = client.post(
        "/releases",
        data=upload_data,
        files={
            "package": ("demo.txt", package_content, "text/plain")
        },
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == (
        "This release name and version already exist"
    )


def test_invalid_release_name_rejected(client):
    response = client.post(
        "/releases",
        data={"name": "bad/name", "version": "1.0.0"},
        files={"package": ("demo.txt", b"test package", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid release name"


def test_invalid_release_version_rejected(client):
    response = client.post(
        "/releases",
        data={"name": "demo-app", "version": "1.0/0"},
        files={"package": ("demo.txt", b"test package", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid version"


def upload_test_release(client):
    package_content = b"EdgeRelay retrieval test package"

    response = client.post(
        "/releases",
        data={"name": "retrieval-app", "version": "1.0.0"},
        files={
            "package": ("retrieval.txt", package_content, "text/plain")
        },
    )

    assert response.status_code == 201
    return response.json(), package_content


def test_list_releases(client):
    release, _ = upload_test_release(client)

    response = client.get("/releases")

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["releases"][0]["id"] == release["id"]


def test_get_release_details(client):
    release, _ = upload_test_release(client)

    response = client.get(f"/releases/{release['id']}")

    assert response.status_code == 200
    assert response.json()["name"] == "retrieval-app"
    assert response.json()["version"] == "1.0.0"


def test_download_release(client):
    release, package_content = upload_test_release(client)

    response = client.get(
        f"/releases/{release['id']}/download"
    )

    assert response.status_code == 200
    assert response.content == package_content


def test_verify_release_integrity(client):
    release, _ = upload_test_release(client)

    response = client.get(
        f"/releases/{release['id']}/verify"
    )

    assert response.status_code == 200
    assert response.json()["integrity_verified"] is True
    assert (
        response.json()["expected_sha256"]
        == response.json()["actual_sha256"]
    )


def test_get_nonexistent_release(client):
    response = client.get("/releases/99999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Release not found"


def test_download_missing_package_file(client):
    release, _ = upload_test_release(client)

    package_path = (
        main.STORAGE_DIR / release["filename"]
    )

    # Remove the stored package file from test storage
    stored_files = list(main.STORAGE_DIR.glob("*.package"))
    assert len(stored_files) == 1
    stored_files[0].unlink()

    response = client.get(
        f"/releases/{release['id']}/download"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Package file not found"


def test_verify_missing_package_file(client):
    release, _ = upload_test_release(client)

    stored_files = list(main.STORAGE_DIR.glob("*.package"))
    assert len(stored_files) == 1
    stored_files[0].unlink()

    response = client.get(
        f"/releases/{release['id']}/verify"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Package file not found"
