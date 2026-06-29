# Shared Upload Volume Fix

**Date:** 2026-06-29
**Status:** Approved

## Problem

`backend` writes uploaded files to `/tmp/rag_uploads` inside its container, then passes the path string to a Celery task. `celery` runs in a separate container with no shared filesystem — it cannot read the path. All uploads silently fail at the parse step.

Affected code:
- `backend/api/routes/ingest.py:101` — `ingest_document.delay(str(document.id), str(tmp_path), metadata)`
- `infra/docker-compose.prod.yml:51` — `celery` service has no shared volume with `backend`

## Solution

Add a named Docker volume `uploads` mounted at `/tmp/rag_uploads` in both `backend` and `celery`. Both containers see the same filesystem path pointing to the same underlying storage. No application code changes required.

## Changes

### `infra/docker-compose.yml` (base / dev)

Add `uploads` to the top-level `volumes` block. Mount it on `backend`:

```yaml
backend:
  volumes:
    - uploads:/tmp/rag_uploads

volumes:
  uploads:
```

Dev has no separate `celery` service, so no celery mount needed in base compose.

### `infra/docker-compose.prod.yml` (prod override)

Mount `uploads` on both `backend` and `celery`, and declare it in the prod `volumes` block:

```yaml
backend:
  volumes:
    - uploads:/tmp/rag_uploads

celery:
  volumes:
    - uploads:/tmp/rag_uploads

volumes:
  uploads:
```

## Data Flow (after fix)

```
Browser → POST /api/ingest
  → backend writes bytes to /tmp/rag_uploads/<uuid>_<filename>   [shared volume]
  → Celery task enqueued with file path string
  → celery reads /tmp/rag_uploads/<uuid>_<filename>              [same shared volume]
  → parse → embed → index → unlink file
```

## What Does Not Change

- `ingest.py` — `UPLOAD_DIR` path unchanged
- `worker.py` — `file_path` handling unchanged
- File cleanup logic (`Path(file_path).unlink`) — still works, celery deletes from shared volume after commit

## Constraints

- Single-host only. If `backend` and `celery` ever move to separate machines, replace with MinIO object storage.
- Volume is ephemeral relative to the host (not backed up). In-flight uploads are lost on host reboot. Acceptable: files are only needed transiently during ingestion.

## Testing

1. `docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml up --build`
2. Upload a PDF via `POST /api/ingest`
3. Poll `GET /api/ingest/{job_id}/status` — status should reach `complete`
4. Confirm file deleted from volume after completion: `docker compose exec celery ls /tmp/rag_uploads` → empty
