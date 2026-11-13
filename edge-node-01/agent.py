import requests
import hashlib
import time
from pathlib import Path

# Exponential Backoff Configuration
INITIAL_RETRY_DELAY = 5
MAX_RETRY_DELAY = 60

# EdgeRelay server URL
SERVER_URL = "http://127.0.0.1:8000"

# Edge node details
NODE_ID = 1

# Package storage directory
PACKAGE_DIR = Path(__file__).parent / "packages"
PACKAGE_DIR.mkdir(parents=True, exist_ok=True)


def fetch_pending_jobs():
    url = f"{SERVER_URL}/nodes/{NODE_ID}/pending-jobs"

    response = requests.get(url, timeout=10)
    response.raise_for_status()

    return response.json()

def send_heartbeat():
    url = f"{SERVER_URL}/nodes/{NODE_ID}/heartbeat"

    response = requests.post(url, timeout=10)
    response.raise_for_status()

    print("Heartbeat sent successfully!")

    return response.json()

def get_retry_delay(retry_count):
    delay = INITIAL_RETRY_DELAY * (2 ** retry_count)

    return min(delay, MAX_RETRY_DELAY)

def calculate_sha256(file_path):
    sha256 = hashlib.sha256()

    with open(file_path, "rb") as file:
        for chunk in iter(lambda: file.read(4096), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def download_package(job):
    job_id = job["job_id"]
    filename = Path(job["filename"]).name
    expected_hash = job["sha256"]

    url = f"{SERVER_URL}/delivery-jobs/{job_id}/download"

    # Use a job-specific filename to avoid package conflicts
    destination = PACKAGE_DIR / f"{job_id}-{filename}"

    # Check whether a valid package already exists locally
    if destination.exists():
        existing_hash = calculate_sha256(destination)

        if existing_hash == expected_hash:
            print("Valid package already exists locally.")
            print("Reusing downloaded package.")
            return destination

        print("Existing package is corrupted. Downloading again.")
        destination.unlink()

    # Download package from server
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    destination.write_bytes(response.content)

    print("Package downloaded successfully!")

    return destination

def report_failure(job_id, error_message):
    url = f"{SERVER_URL}/delivery-jobs/{job_id}/fail"

    response = requests.patch(
        url,
        data={
            "edge_node_id": NODE_ID,
            "error_message": error_message
        },
        timeout=10
    )

    response.raise_for_status()

    print("Failure reported successfully!")
    print("Server response:", response.json())


def process_job(job):
    job_id = job["job_id"]

    print(f"\nProcessing Job ID: {job_id}")

    # Step 1: Download package
    try:
        package_path = download_package(job)

    except (requests.RequestException, OSError) as error:
        print("Package download failed:", error)
        report_failure(job_id, f"Package download failed: {error}")
        return

    # Step 2: Verify SHA-256
    try:
        actual_hash = calculate_sha256(package_path)
        expected_hash = job["sha256"]

        if actual_hash != expected_hash:
            print("SHA-256 verification failed!")

            package_path.unlink(missing_ok=True)

            report_failure(
                job_id,
                "SHA-256 checksum mismatch"
            )
            return

        print("SHA-256 verification successful!")

    except OSError as error:
        print("Package verification error:", error)
        report_failure(
            job_id,
            f"Package verification error: {error}"
        )
        return

    # Step 3: Report successful completion
    completion_url = (
        f"{SERVER_URL}/delivery-jobs/{job_id}/complete"
    )

    response = requests.patch(
        completion_url,
        data={
            "edge_node_id": NODE_ID,
            "verified_sha256": actual_hash
        },
        timeout=10
    )

    response.raise_for_status()

    print("Delivery completion reported successfully!")
    print("Server response:", response.json())


if __name__ == "__main__":
    print("EdgeRelay Continuous Edge Node Agent started")

    heartbeat_interval = 30
    polling_interval = 10

    last_heartbeat = 0
    retry_count = 0

    while True:
        try:
            current_time = time.monotonic()

            # Send heartbeat every 30 seconds
            if current_time - last_heartbeat >= heartbeat_interval:
                heartbeat = send_heartbeat()
                print("Heartbeat response:", heartbeat)
                last_heartbeat = current_time

            # Check for pending jobs
            jobs = fetch_pending_jobs()

            if jobs:
                print(f"Pending jobs found: {len(jobs)}")

                for job in jobs:
                    process_job(job)
            else:
                print("No pending jobs available.")

            # Reset retry count after successful server communication
            retry_count = 0
            wait_time = polling_interval

        except requests.RequestException as error:
            retry_count += 1
            wait_time = get_retry_delay(retry_count - 1)

            print("Connection error:", error)
            print(f"Retry attempt: {retry_count}")
            print(f"Retrying in {wait_time} seconds...")

        except Exception as error:
            print("Unexpected agent error:", error)
            wait_time = polling_interval

        time.sleep(wait_time)
