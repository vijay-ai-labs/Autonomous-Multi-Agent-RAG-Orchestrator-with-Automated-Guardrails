# RBAC Document Access Control — Design

**Date:** 2026-06-15
**Status:** Approved for planning

## Problem

Document retrieval scope is currently controlled by the client, not by identity:

- `POST /api/query` accepts `department` and `doc_type` from the **request body**
  ([query.py:27-28](../../../backend/api/routes/query.py)) and passes them straight to
  the retriever. A client can omit them (sees everything) or set them to any value.
- `GET /api/documents` reads `department`/`doc_type` from query params with no identity
  check ([documents.py:42-43](../../../backend/api/routes/documents.py)), leaking the
  document catalog across departments.
- JWTs carry only `sub` (the user id) ([auth.py:28](../../../backend/api/middleware/auth.py));
  no role or department is available to enforce scope.

Result: any authenticated employee can retrieve and list any department's documents. This
is a security hole, not a polish item.

## Goal

Retrieval and listing scope is **server-derived from the authenticated user's identity**.
Client-supplied filters may only *narrow within* the allowed scope, never widen it.

## Access model — role + department tiers

Roles already exist on `users.role` (`admin` / `manager` / `employee`).

| Role | Sees |
|------|------|
| `admin` | All active documents (department ignored) |
| `manager` | Documents in any of its `departments` + shared (NULL) |
| `employee` | Documents in its (single) department + shared (NULL) |

`department IS NULL` means **shared / company-wide** (e.g. handbook, HR policy) and is
visible to every authenticated user.

## Data model

Add a `departments` column to `users`:

- Type: `TEXT[]` (Postgres array), `NOT NULL DEFAULT '{}'`.
- `employee`: one entry. `manager`: many. `admin`: empty (means "all").
- New Alembic migration in `backend/migrations/versions/`.
- Update the `User` ORM model in [tables.py](../../../backend/models/tables.py).

## Scope resolution (auth layer)

New dependency `get_current_user` in [auth.py](../../../backend/api/middleware/auth.py)
returning a `UserScope` value object:

```
UserScope:
    id: UUID
    role: str          # admin | manager | employee
    departments: list[str]
```

- Loads the user row from Postgres, builds `UserScope`.
- Caches `UserScope` in Redis under key `userscope:{id}` with **TTL 60s** (short, so role
  or department changes take effect quickly).
- Cache entry is deleted on any user update (and naturally expires via TTL as a backstop).
- The existing `get_current_user_id` dependency stays for back-compat; call sites that need
  scope migrate to `get_current_user`.

## Enforcement points

### 1. Query retrieval
`retrieve()` ([service.py](../../../backend/retrieval/service.py)) and `hybrid_search()` /
`_build_filter()` ([searcher.py](../../../backend/retrieval/searcher.py)) take a `UserScope`.

Filter construction:
- **admin**: `must=[status=active]` (current behavior, unchanged).
- **manager/employee**:
  ```
  must = [ status == active,
           Filter(should=[ MatchAny(key="department", any=scope.departments),
                           IsNull(key="department") ]) ]
  ```
  `IsNull` matches shared docs — the indexer writes `department: None` as JSON null
  ([indexer.py:51](../../../backend/ingestion/indexer.py)), so `IsNullCondition` matches.
- Optional client `department` / `doc_type`: validated as a **subset** of the allowed
  scope. If outside scope → `403`. If inside → applied as an additional `must` narrowing.

### 2. Documents listing
`list_documents` ([documents.py](../../../backend/api/routes/documents.py)) applies the same
predicate in SQL:
- non-admin: `Document.department.in_(scope.departments) | Document.department.is_(None)`
- admin: unfiltered.
- Client `department` filter validated ⊆ scope (`403` if outside).

### 3. Document delete
`delete_document`: a manager/employee may only delete a document whose `department` is in
its scope (or NULL); otherwise `403`. Admin unrestricted.

### 4. Upload / ingestion
The ingest route may only accept a target `department` that is within the uploader's scope
(admin: any). Blocks the write-side leak (employee uploading into another department).

## Audit & errors

- Every denial writes `AuditLog(event_type="access_denied", details={user_id,
  attempted_department, endpoint})` ([tables.py AuditLog](../../../backend/models/tables.py)).
- Out-of-scope client filter returns `403` (not a silent empty result), so the caller learns
  the request was rejected rather than assuming no matching docs.

## Testing

**Unit**
- Scope resolver for each role (admin empty-departments = all; manager multi; employee single).
- `_build_filter` for admin vs scoped vs shared/NULL inclusion.
- Subset-validation helper (in-scope passes, out-of-scope raises 403).

**Integration**
- Employee token cannot read another department's docs via client `department` param (403).
- Employee token cannot list another department's docs.
- Manager token spans all its departments; nothing outside.
- Admin sees all.
- Shared (NULL) docs visible to every role.
- Redis cache invalidation: changing a user's role/departments takes effect within TTL.

## Out of scope (YAGNI)

- Admin UI for managing department membership (set via DB / existing tooling for now).
- Login/registration changes beyond reading the new column.
- Per-document ACLs and sensitivity-level clearances (different access models, not chosen).

## Affected files

- `backend/migrations/versions/000X_add_user_departments.py` (new)
- `backend/models/tables.py` — `User.departments`
- `backend/api/middleware/auth.py` — `UserScope`, `get_current_user`, Redis cache
- `backend/retrieval/searcher.py` — scope-aware `_build_filter` / `hybrid_search`
- `backend/retrieval/service.py` — thread `UserScope` through
- `backend/answer/pipeline.py` — pass scope from route into retrieval
- `backend/api/routes/query.py` — use `get_current_user`, validate client filters
- `backend/api/routes/documents.py` — scoped listing + delete
- `backend/api/routes/ingest.py` — scoped upload department
- `backend/tests/` — unit + integration coverage
