import hashlib
import os
import re
import sqlite3
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse 

BASE_DIR = Path(__file__).resolve().parent

STORAGE_DIR = Path(
    os.getenv("EDGERELAY_STORAGE_DIR", str(BASE_DIR / "storage" / "releases"))
)

DB_PATH = Path(
    os.getenv("EDGERELAY_DB_PATH", str(BASE_DIR / "edgerelay.db"))
)

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB
CHUNK_SIZE = 1024 * 1024  # 1 MB


def get_db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection
def init_db():
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    with get_db() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS releases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(name, version)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS edge_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'offline'
                    CHECK(status IN ('online', 'offline')),
                last_seen TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS delivery_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                release_id INTEGER NOT NULL,
                edge_node_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued'
                    CHECK(status IN ('queued', 'processing', 'completed', 'failed')),
                retry_count INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(release_id) REFERENCES releases(id),
                FOREIGN KEY(edge_node_id) REFERENCES edge_nodes(id),
                UNIQUE(release_id, edge_node_id)
            )
        """)


async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="EdgeRelay",
    description="Offline-First Software Delivery Network",
    version="0.2.0",
    lifespan=lifespan,
)


@app.get("/")
def home():
    return {
        "project": "EdgeRelay",
        "status": "running",
        "message": "Software delivery platform is ready",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.post("/releases", status_code=201)
async def create_release(
    name: str = Form(...),
    version: str = Form(...),
    package: UploadFile = File(...),
):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", name):
        raise HTTPException(400, "Invalid release name")

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,49}", version):
        raise HTTPException(400, "Invalid version")

    if not package.filename:
        raise HTTPException(400, "Filename is required")

    original_filename = Path(package.filename).name
    if original_filename in ("", ".", ".."):
        raise HTTPException(400, "Invalid filename")

    release_id = uuid.uuid4().hex
    stored_filename = f"{release_id}.package"
    destination = STORAGE_DIR / stored_filename

    digest = hashlib.sha256()
    total_size = 0

    try:
        with destination.open("xb") as output:
            while True:
                chunk = await package.read(CHUNK_SIZE)
                if not chunk:
                    break

                total_size += len(chunk)
                if total_size > MAX_UPLOAD_SIZE:
                    raise HTTPException(
                        413, "Package exceeds the 50 MB upload limit"
                    )

                digest.update(chunk)
                output.write(chunk)

        checksum = digest.hexdigest()

        with get_db() as connection:
            cursor = connection.execute(
                """
                INSERT INTO releases
                (name, version, filename, stored_filename, sha256, size_bytes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    version,
                    original_filename,
                    stored_filename,
                    checksum,
                    total_size,
                ),
            )
            release_id_db = cursor.lastrowid

        return {
            "id": release_id_db,
            "name": name,
            "version": version,
            "filename": original_filename,
            "size_bytes": total_size,
            "sha256": checksum,
            "status": "stored",
            "note": "Checksum calculated. Digital signature verification "
                    "will be added in a later phase.",
        }

    except sqlite3.IntegrityError:
        destination.unlink(missing_ok=True)
        raise HTTPException(409, "This release name and version already exist")
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await package.close()


@app.get("/releases")
def list_releases():
    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT id, name, version, filename, sha256,
                   size_bytes, created_at
            FROM releases
            ORDER BY id DESC
            """
        ).fetchall()

    return {"count": len(rows), "releases": [dict(row) for row in rows]}


@app.get("/releases/{release_id}")
def get_release(release_id: int):
    with get_db() as connection:
        row = connection.execute(
            """
            SELECT id, name, version, filename, sha256,
                   size_bytes, created_at
            FROM releases WHERE id = ?
            """,
            (release_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(404, "Release not found")

    return dict(row)
@app.get("/releases/{release_id}/download")
def download_release(release_id: int):
    with get_db() as conn:
        release = conn.execute(
            "SELECT * FROM releases WHERE id = ?",
            (release_id,),
        ).fetchone()

    if release is None:
        raise HTTPException(status_code=404, detail="Release not found")

    package_path = STORAGE_DIR / release["stored_filename"]

    if not package_path.is_file():
        raise HTTPException(status_code=404, detail="Package file not found")

    return FileResponse(
        path=package_path,
        media_type="application/octet-stream",
        filename=release["filename"],
    )
@app.get("/releases/{release_id}/verify")
def verify_release(release_id: int):
    with get_db() as conn:
        release = conn.execute(
            "SELECT * FROM releases WHERE id = ?",
            (release_id,),
        ).fetchone()

    if release is None:
        raise HTTPException(status_code=404, detail="Release not found")

    package_path = STORAGE_DIR / release["stored_filename"]

    if not package_path.is_file():
        raise HTTPException(status_code=404, detail="Package file not found")

    sha256 = hashlib.sha256()

    with package_path.open("rb") as package:
        for chunk in iter(lambda: package.read(CHUNK_SIZE), b""):
            sha256.update(chunk)

    actual_checksum = sha256.hexdigest()
    expected_checksum = release["sha256"]

    return {
        "release_id": release_id,
        "filename": release["filename"],
        "expected_sha256": expected_checksum,
        "actual_sha256": actual_checksum,
        "integrity_verified": actual_checksum == expected_checksum,
    }
@app.post("/nodes", status_code=201)
def register_node(name: str = Form(...)):
    name = name.strip()

    if not name or len(name) > 100:
        raise HTTPException(
            status_code=400,
            detail="Node name must be between 1 and 100 characters",
        )

    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM edge_nodes WHERE name = ?",
            (name,),
        ).fetchone()

        if existing:
            raise HTTPException(
                status_code=409,
                detail="Node name already exists",
            )

        cursor = conn.execute(
            "INSERT INTO edge_nodes (name) VALUES (?)",
            (name,),
        )

        node_id = cursor.lastrowid

        node = conn.execute(
            "SELECT * FROM edge_nodes WHERE id = ?",
            (node_id,),
        ).fetchone()

    return dict(node)


@app.get("/nodes")
def list_nodes():
    with get_db() as conn:
        nodes = conn.execute(
            "SELECT * FROM edge_nodes ORDER BY id"
        ).fetchall()

    return [dict(node) for node in nodes]
@app.post("/delivery-jobs", status_code=201)
def create_delivery_job(
    release_id: int = Form(...),
    edge_node_id: int = Form(...),
):
    with get_db() as conn:
        release = conn.execute(
            "SELECT id FROM releases WHERE id = ?",
            (release_id,),
        ).fetchone()

        if release is None:
            raise HTTPException(
                status_code=404,
                detail="Release not found",
            )

        node = conn.execute(
            "SELECT * FROM edge_nodes WHERE id = ?",
            (edge_node_id,),
        ).fetchone()

        if node is None:
            raise HTTPException(
                status_code=404,
                detail="Edge node not found",
            )

        existing_job = conn.execute(
            """
            SELECT id FROM delivery_jobs
            WHERE release_id = ? AND edge_node_id = ?
            """,
            (release_id, edge_node_id),
        ).fetchone()

        if existing_job:
            raise HTTPException(
                status_code=409,
                detail="Delivery job already exists for this release and node",
            )

        cursor = conn.execute(
            """
            INSERT INTO delivery_jobs (release_id, edge_node_id, status)
            VALUES (?, ?, 'queued')
            """,
            (release_id, edge_node_id),
        )

        job = conn.execute(
            "SELECT * FROM delivery_jobs WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()

    return dict(job)


@app.get("/delivery-jobs")
def list_delivery_jobs():
    with get_db() as conn:
        jobs = conn.execute(
            """
            SELECT
                delivery_jobs.*,
                releases.name AS release_name,
                releases.version AS release_version,
                edge_nodes.name AS edge_node_name,
                edge_nodes.status AS edge_node_status
            FROM delivery_jobs
            JOIN releases ON releases.id = delivery_jobs.release_id
            JOIN edge_nodes ON edge_nodes.id = delivery_jobs.edge_node_id
            ORDER BY delivery_jobs.id
            """
        ).fetchall()

    return [dict(job) for job in jobs]
@app.patch("/nodes/{node_id}/status")
def update_node_status(
    node_id: int,
    status: str = Form(...),
):
    status = status.strip().lower()

    if status not in ("online", "offline"):
        raise HTTPException(
            status_code=400,
            detail="Status must be online or offline",
        )

    with get_db() as conn:
        node = conn.execute(
            "SELECT id FROM edge_nodes WHERE id = ?",
            (node_id,),
        ).fetchone()

        if node is None:
            raise HTTPException(
                status_code=404,
                detail="Edge node not found",
            )

        conn.execute(
            """
            UPDATE edge_nodes
            SET status = ?,
                last_seen = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, node_id),
        )
        recovered_jobs = 0

        if status == "online":
            cursor = conn.execute(
                """
                UPDATE delivery_jobs
                SET status = 'queued',
                    error_message = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE edge_node_id = ?
                  AND status = 'failed'
                  AND retry_count < 3
                """,
                (node_id,),
            )

            recovered_jobs = cursor.rowcount

        updated_node = conn.execute(
            "SELECT * FROM edge_nodes WHERE id = ?",
            (node_id,),
        ).fetchone()

    return {
        "node": dict(updated_node),
        "recovered_jobs": recovered_jobs,
    }
@app.post("/nodes/{node_id}/heartbeat")
def node_heartbeat(node_id: int):

    with get_db() as conn:
        node = conn.execute(
            "SELECT id FROM edge_nodes WHERE id = ?",
            (node_id,),
        ).fetchone()

        if node is None:
            raise HTTPException(
                status_code=404,
                detail="Edge node not found",
            )

        # Update node status and heartbeat timestamp
        conn.execute(
            """
            UPDATE edge_nodes
            SET status = 'online',
                last_seen = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (node_id,),
        )

        # Recover eligible failed jobs
        cursor = conn.execute(
            """
            UPDATE delivery_jobs
            SET status = 'queued',
                error_message = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE edge_node_id = ?
              AND status = 'failed'
              AND retry_count < 3
            """,
            (node_id,),
        )

        recovered_jobs = cursor.rowcount

        updated_node = conn.execute(
            "SELECT * FROM edge_nodes WHERE id = ?",
            (node_id,),
        ).fetchone()

    return {
        "message": "Heartbeat received successfully",
        "node": dict(updated_node),
        "recovered_jobs": recovered_jobs,
    }


@app.get("/nodes/{node_id}/pending-jobs")
def get_pending_jobs(node_id: int):
    with get_db() as conn:
        node = conn.execute(
            "SELECT * FROM edge_nodes WHERE id = ?",
            (node_id,),
        ).fetchone()

        if node is None:
            raise HTTPException(
                status_code=404,
                detail="Edge node not found",
            )

        if node["status"] != "online":
            raise HTTPException(
                status_code=409,
                detail="Edge node is offline",
            )

        jobs = conn.execute(
            """
            SELECT
                delivery_jobs.id AS job_id,
                delivery_jobs.release_id,
                delivery_jobs.edge_node_id,
                delivery_jobs.status AS job_status,
                delivery_jobs.retry_count,
                releases.name AS release_name,
                releases.version AS release_version,
                releases.filename,
                releases.size_bytes,
                releases.sha256
            FROM delivery_jobs
            JOIN releases
                ON releases.id = delivery_jobs.release_id
            WHERE delivery_jobs.edge_node_id = ?
              AND delivery_jobs.status = 'queued'
            ORDER BY delivery_jobs.id
            """,
            (node_id,),
        ).fetchall()

    return [dict(job) for job in jobs]
@app.get("/delivery-jobs/{job_id}/download")
def download_delivery_job(job_id: int):
    with get_db() as conn:
        job = conn.execute(
            """
            SELECT
                delivery_jobs.*,
                releases.stored_filename,
                releases.filename,
                releases.sha256
            FROM delivery_jobs
            JOIN releases
                ON releases.id = delivery_jobs.release_id
            WHERE delivery_jobs.id = ?
            """,
            (job_id,),
        ).fetchone()

        if job is None:
            raise HTTPException(
                status_code=404,
                detail="Delivery job not found",
            )

        node = conn.execute(
            """
            SELECT status
            FROM edge_nodes
            WHERE id = ?
            """,
            (job["edge_node_id"],),
        ).fetchone()

        if node is None:
            raise HTTPException(
                status_code=404,
                detail="Edge node not found",
            )

        if node["status"] != "online":
            raise HTTPException(
                status_code=409,
                detail="Edge node is offline",
            )

        if job["status"] != "queued":
            raise HTTPException(
                status_code=409,
                detail="Delivery job is not queued",
            )

    package_path = STORAGE_DIR / job["stored_filename"]

    if not package_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Package file not found",
        )

    return FileResponse(
        path=package_path,
        media_type="application/octet-stream",
        filename=job["filename"],
        headers={
            "X-Release-SHA256": job["sha256"],
            "X-Delivery-Job-ID": str(job_id),
        },
    )
@app.patch("/delivery-jobs/{job_id}/complete")
def complete_delivery_job(
    job_id: int,
    edge_node_id: int = Form(...),
    verified_sha256: str = Form(...),
):
    with get_db() as conn:
        job = conn.execute(
            """
            SELECT
                delivery_jobs.*,
                releases.sha256
            FROM delivery_jobs
            JOIN releases
                ON releases.id = delivery_jobs.release_id
            WHERE delivery_jobs.id = ?
            """,
            (job_id,),
        ).fetchone()

        if job is None:
            raise HTTPException(
                status_code=404,
                detail="Delivery job not found",
            )

        if job["edge_node_id"] != edge_node_id:
            raise HTTPException(
                status_code=403,
                detail="Job does not belong to this edge node",
            )

        if job["status"] != "queued":
            raise HTTPException(
                status_code=409,
                detail="Delivery job is not queued",
            )

        if verified_sha256.lower() != job["sha256"].lower():
            raise HTTPException(
                status_code=400,
                detail="SHA-256 verification failed",
            )

        conn.execute(
            """
            UPDATE delivery_jobs
            SET status = 'completed',
                error_message = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (job_id,),
        )

        updated_job = conn.execute(
            "SELECT * FROM delivery_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()

    return {
        "message": "Delivery completed successfully",
        "job": dict(updated_job),
    }
@app.patch("/delivery-jobs/{job_id}/fail")
def fail_delivery_job(
    job_id: int,
    edge_node_id: int = Form(...),
    error_message: str = Form(...),
):
    with get_db() as conn:
        job = conn.execute(
            """
            SELECT * FROM delivery_jobs
            WHERE id = ?
            """,
            (job_id,),
        ).fetchone()

        if job is None:
            raise HTTPException(
                status_code=404,
                detail="Delivery job not found",
            )

        if job["edge_node_id"] != edge_node_id:
            raise HTTPException(
                status_code=403,
                detail="Job does not belong to this edge node",
            )

        if job["status"] != "queued":
            raise HTTPException(
                status_code=409,
                detail="Delivery job is not queued",
            )

        conn.execute(
            """
            UPDATE delivery_jobs
            SET status = 'failed',
                retry_count = retry_count + 1,
                error_message = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (error_message, job_id),
        )

        updated_job = conn.execute(
            "SELECT * FROM delivery_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()

    return {
        "message": "Delivery marked as failed",
        "job": dict(updated_job),
    }
@app.patch("/delivery-jobs/{job_id}/retry")
def retry_delivery_job(job_id: int):
    MAX_RETRIES = 3

    with get_db() as conn:
        job = conn.execute(
            """
            SELECT
                delivery_jobs.*,
                edge_nodes.status AS node_status
            FROM delivery_jobs
            JOIN edge_nodes
                ON edge_nodes.id = delivery_jobs.edge_node_id
            WHERE delivery_jobs.id = ?
            """,
            (job_id,),
        ).fetchone()

        if job is None:
            raise HTTPException(
                status_code=404,
                detail="Delivery job not found",
            )

        if job["status"] != "failed":
            raise HTTPException(
                status_code=409,
                detail="Only failed jobs can be retried",
            )

        if job["node_status"] != "online":
            raise HTTPException(
                status_code=409,
                detail="Edge node is offline. Retry when node is online",
            )

        if job["retry_count"] >= MAX_RETRIES:
            raise HTTPException(
                status_code=409,
                detail="Maximum retry limit reached",
            )

        conn.execute(
            """
            UPDATE delivery_jobs
            SET status = 'queued',
                error_message = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (job_id,),
        )

        updated_job = conn.execute(
            "SELECT * FROM delivery_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()

    return {
        "message": "Delivery job requeued successfully",
        "job": dict(updated_job),
    }
