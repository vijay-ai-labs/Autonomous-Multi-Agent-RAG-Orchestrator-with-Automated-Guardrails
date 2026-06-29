# Autonomous Multi-Agent RAG Orchestrator with Automated Guardrails

Production-grade internal knowledge assistant: employees ask natural-language questions, the system retrieves evidence from company documents and returns **grounded answers with inline citations** — or refuses and escalates to a human when it cannot answer safely.

Every answer passes five sequential guardrail checks (citation coverage, hallucination, PII, toxicity, faithfulness) before reaching the user. Orchestration runs as a **LangGraph multi-agent graph** — not a monolithic LLM call. See [SPEC.md](SPEC.md) for the full technical design.

---

## Architecture

```
                   ┌──────────────┐
 PDF / DOCX / HTML │   Ingestion  │   parse → chunk → embed → index
 upload  ─────────▶│   (Celery)   │ ─────────────────────────────────┐
                   └──────────────┘                                   ▼
                                                               ┌───────────┐
                                                               │  Qdrant   │ vectors
                                                               │ (hybrid)  │
                                                               └───────────┘
 ┌──────────┐   POST /api/query   ┌────────────────────────────────────────┐
 │  Client  │ ──────────────────▶ │         LangGraph agent graph           │
 │ (Next.js)│ ◀─ answer/refusal ─ │  router → retriever → answer →         │
 └──────────┘                     │      guardrail → (persist | escalation) │
                                  └────────────────────────────────────────┘
                                       │            │              │
                                  PostgreSQL      Redis        OpenAI
                               (docs, audit,   (jobs, cache,  (embeddings,
                                escalations)    sessions)      LLM, judge)
```

### Agent graph

```
router ─(safe)────────▶ retriever ─(evidence ok)─▶ answer ─▶ guardrail ─(approved)─▶ persist ─▶ END
  │                         │                                     │
  └(injection → refuse)     └(thin evidence → refuse)             └(flagged) ─▶ escalation ─▶ persist
```

| Node | Responsibility |
|------|---------------|
| **router** | Block prompt-injection / jailbreak (regex + keyword). Pure sync. |
| **retriever** | Embed → hybrid search (dense+sparse, RRF) → FlashRank rerank → verify evidence sufficiency. |
| **answer** | GPT-4o grounded generation with `[Source N]` inline citations. |
| **guardrail** | 5 checks in order: citation → toxicity → PII → confidence → hallucination. Cheap-first short-circuit. |
| **escalation** | Persist open escalation for human review; optional email notification. |
| **persist** | Write query / response / audit rows + session history. Owns all DB/Redis I/O. |

State is a single `TypedDict` threaded through the graph; `agent_trace` accumulates visited nodes for observability.

---

## Quick start

### 1. Configure

```bash
cp infra/.env.example .env
```

Required: `OPENAI_API_KEY`, `JWT_SECRET`. If ports `5432` / `6379` are occupied, override `POSTGRES_HOST_PORT` and `REDIS_HOST_PORT` in `.env`.

### 2. Start the stack

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up
```

- API → http://localhost:8000
- Swagger → http://localhost:8000/docs

### 3. Frontend

```bash
cd frontend && npm install && npm run dev   # http://localhost:3000
```

---

## API

All routes under `/api`. Every route except `/auth/*` and `/health` requires `Authorization: Bearer <token>`.

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/auth/register` | Create user (`employee` \| `admin`), returns JWT |
| `POST` | `/auth/login` | Exchange credentials for JWT |
| `POST` | `/ingest` | Upload document (PDF/DOCX/HTML), enqueue ingestion |
| `GET`  | `/ingest/{job_id}/status` | Poll ingestion job progress |
| `GET`  | `/documents` | List active documents (filter by `doc_type`, `department`) |
| `DELETE` | `/documents/{id}` | Soft-delete (archive in Postgres + Qdrant) |
| `POST` | `/query` | Ask a question → grounded answer + citations, or refusal |
| `GET`  | `/escalations` | Human-review queue of flagged answers |
| `GET`  | `/stats` | Dashboard metrics (queries, refusal rate, avg latency) |
| `GET`  | `/health` | Liveness / dependency check |

Supported `doc_type`: `policy`, `hr`, `it`, `sop`, `compliance`, `faq`.  
Supported uploads: `.pdf`, `.docx`, `.html` / `.htm` (max `MAX_FILE_SIZE_MB`).

### Example

```bash
# Register / login
TOKEN=$(curl -s -X POST localhost:8000/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"a@co.com","password":"pw","role":"admin"}' | jq -r .access_token)

# Upload a document
curl -X POST localhost:8000/api/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -F file=@handbook.pdf -F doc_type=hr

# Query (after doc status = ACTIVE)
curl -X POST localhost:8000/api/query \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"query":"What is the PTO policy?"}'
```

Success response: `answer`, ordered `citations`, `confidence`, `refused: false`.  
Refusal response: `refused: true`, `refusal_reason`.

---

## Configuration

Set in `.env` (see [infra/.env.example](infra/.env.example)):

| Variable | Default | Effect |
|----------|---------|--------|
| `MAX_CHUNKS_PER_QUERY` | `8` | Top-K chunks kept after rerank |
| `EVIDENCE_THRESHOLD` | `0.6` | Min reranker score for retriever to proceed |
| `FAITHFULNESS_THRESHOLD` | `0.7` | Min score for guardrail to auto-approve |
| `MAX_FILE_SIZE_MB` | `50` | Upload size cap |

---

## Testing

```bash
# Unit + integration tests
cd backend && pytest

# Offline safety eval (router injection detection + guardrail checks)
cd backend && python -m evals.run_evals
```

The eval harness scores router and guardrails against labeled datasets and reports precision / recall / F1.

---

## Tech stack

| Layer | Choice |
|-------|--------|
| API | FastAPI (async), JWT auth (HS256 / bcrypt) |
| Orchestration | LangGraph state graph |
| Vector store | Qdrant (hybrid dense + sparse, RRF fusion) |
| Rerank | FlashRank |
| Relational DB | PostgreSQL (SQLAlchemy async + Alembic) |
| Cache / queue / sessions | Redis + Celery |
| LLM / embeddings | OpenAI (`gpt-4o`, `text-embedding-3-small`, `gpt-4o-mini` judge) |
| PII detection | Microsoft Presidio (fail-open) |
| Observability | LangSmith (optional) |
| Frontend | Next.js 16 App Router, React 19, Tailwind v4 |

---

## Project layout

```
backend/
  api/          FastAPI app, routes, auth middleware
  agents/       LangGraph nodes + graph wiring + shared state
  retrieval/    embed → hybrid search → rerank pipeline
  answer/       generation, formatter, refusal, session, query pipeline
  guardrails/   citation / toxicity / PII / hallucination checks
  ingestion/    parsers (PDF/DOCX/HTML), chunker, embedder, indexer, Celery worker
  evals/        offline evaluation harness
  eval/         RAGAS eval + adversarial test suite
  models/       SQLAlchemy tables
  migrations/   Alembic
  tests/        pytest suite
frontend/       Next.js client (chat, admin dashboard, escalation queue)
infra/          docker-compose + env template
docs/           Architecture decision records
```
