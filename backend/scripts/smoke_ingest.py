"""End-to-end smoke test for the Phase 3 ingestion pipeline.

Mints a JWT, uploads a file to ``POST /api/ingest``, then polls
``GET /api/ingest/{job_id}/status`` until the worker reports ``complete`` (or
``failed``). Requires the API, Celery worker, Postgres, Qdrant, and Redis to be
running. Reuses :func:`api.middleware.auth.create_access_token` so the signing
secret always matches the server's ``JWT_SECRET``.

Usage:
    python scripts/smoke_ingest.py path/to/any.pdf --doc-type policy
    python scripts/smoke_ingest.py any.pdf --base-url http://localhost:8000 --department hr
"""

import argparse
import sys
import time
from pathlib import Path
from uuid import UUID, uuid4

import httpx

# Allow running as `python scripts/smoke_ingest.py` from the backend dir.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.middleware.auth import create_access_token  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test the ingestion pipeline.")
    parser.add_argument("file", type=Path, help="Path to a .pdf/.docx/.html file")
    parser.add_argument("--doc-type", default="policy")
    parser.add_argument("--department", default=None)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument(
        "--user-id",
        default=None,
        help="UUID subject for the JWT; must exist in the users table "
        "(uploader_id is an FK). Defaults to a random UUID.",
    )
    parser.add_argument("--timeout", type=float, default=120.0, help="Poll timeout (s)")
    parser.add_argument("--interval", type=float, default=2.0, help="Poll interval (s)")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if not args.file.is_file():
        print(f"File not found: {args.file}", file=sys.stderr)
        return 2

    user_id = UUID(args.user_id) if args.user_id else uuid4()
    token = create_access_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client(base_url=args.base_url, timeout=30.0) as http:
        data = {"doc_type": args.doc_type}
        if args.department:
            data["department"] = args.department
        with args.file.open("rb") as fh:
            resp = http.post(
                "/api/ingest",
                headers=headers,
                data=data,
                files={"file": (args.file.name, fh, "application/octet-stream")},
            )
        if resp.status_code != 202:
            print(f"Upload failed [{resp.status_code}]: {resp.text}", file=sys.stderr)
            return 1
        body = resp.json()
        job_id = body["job_id"]
        print(f"Enqueued: job_id={job_id} document_id={body['document_id']}")

        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            status_resp = http.get(f"/api/ingest/{job_id}/status", headers=headers)
            if status_resp.status_code == 404:
                # Worker has not written the job record yet (still queued).
                print("  status=queued")
                time.sleep(args.interval)
                continue
            if status_resp.status_code != 200:
                print(f"Status check failed [{status_resp.status_code}]: {status_resp.text}")
                return 1
            state = status_resp.json()
            print(f"  status={state['status']} chunks={state.get('chunk_count')}")
            if state["status"] == "complete":
                print(f"DONE: {state.get('chunk_count')} chunks indexed.")
                return 0
            if state["status"] == "failed":
                print(f"FAILED: {state.get('error')}", file=sys.stderr)
                return 1
            time.sleep(args.interval)

    print("Timed out waiting for completion.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
