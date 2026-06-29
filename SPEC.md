# Autonomous Multi-Agent RAG Orchestrator with Automated Guardrails

**Trusted internal AI assistant — grounded answers, mandatory citations, zero hallucination tolerance**

---

## 1. Use Case

Employees ask questions in natural language. The system retrieves relevant chunks from approved company documents (HR policies, IT docs, SOPs, onboarding guides, compliance docs, benefits FAQs) and returns a grounded, cited answer — or refuses if evidence is insufficient.

**Rule:** No answer without evidence. No claim without a citation.

**Document formats:** PDF, DOCX, HTML  
**Users:** All employees (uniform read access; admin role for document management)  
**Versioning:** Soft-replace — old version archived, new version active, full audit trail preserved

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  FRONTEND — Next.js + React                                      │
│  Chat UI · Document Upload · Source Citations · Escalation Queue │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTPS / JWT
┌───────────────────────────▼─────────────────────────────────────┐
│  API LAYER — FastAPI (Python)                                    │
│  /query · /ingest · /documents · /escalations · /stats · /auth  │
└───────────────────────────┬─────────────────────────────────────┘
                            │ invokes
┌───────────────────────────▼─────────────────────────────────────┐
│  LANGGRAPH MULTI-AGENT ORCHESTRATOR                              │
│                                                                  │
│   router → retriever → answer → guardrail                        │
│                                  ↙          ↘                   │
│                             persist       escalation → persist   │
└──────────┬────────────────────────────────────────┬─────────────┘
           │                                        │
┌──────────▼──────────┐  ┌──────────────┐  ┌──────▼──────────────┐
│  Qdrant             │  │  PostgreSQL  │  │  Redis + Celery      │
│  Vector store       │  │  Relational  │  │  Async ingestion     │
│  1536-dim, hybrid   │  │  DB + audit  │  │  job queue           │
└─────────────────────┘  └──────────────┘  └─────────────────────┘
```

### Agent graph

```
router ─(safe)────────▶ retriever ─(evidence ok)─▶ answer ─▶ guardrail ─(approved)─▶ persist ─▶ END
  │                         │                                     │
  └(injection → refuse)     └(thin evidence → refuse)             └(flagged) ─▶ escalation ─▶ persist
```

---

## 3. Tech Stack

| Layer | Technology | Reason |
|-------|-----------|--------|
| Frontend | Next.js 16 + React 19 + Tailwind v4 | App Router SSR, strong TypeScript ecosystem |
| Backend API | FastAPI (Python, async) | Async-first, auto OpenAPI docs |
| Orchestration | LangGraph | Stateful multi-agent graph with conditional edges |
| Document parsing | Custom parsers (pdf_parser, docx_parser, html_parser) | Preserve page numbers, headings, structure |
| Chunking | Custom chunker | 512-token chunks, 50-token overlap, semantic boundary respect |
| LLM | GPT-4o | Structured output, grounded generation |
| LLM judge | GPT-4o-mini | Hallucination and toxicity checks at lower cost |
| Embeddings | text-embedding-3-small (1536-dim) | Cost-efficient, strong semantic retrieval |
| Vector DB | Qdrant | Hybrid dense+sparse, payload filtering, Docker-native |
| Hybrid search | Vector + BM25 sparse, RRF fusion | Best retrieval quality on enterprise docs |
| Rerank | FlashRank | Fast cross-encoder reranking |
| Relational DB | PostgreSQL (SQLAlchemy async + Alembic) | Docs metadata, audit log, escalations, users |
| Cache / queue | Redis + Celery | Session history, async ingestion workers |
| PII detection | Microsoft Presidio (fail-open) | Redacts names, emails, SSNs, phones, addresses |
| Eval | RAGAS + custom adversarial suite | Standard faithfulness metrics + safety gates |
| Observability | LangSmith (optional) | Full agent trace per query |
| Auth | JWT (HS256, bcrypt via passlib) | Stateless; RBAC hooks ready |

---

## 4. The 6 Agent Nodes

### Node 1 — Router (`agents/router.py`)
- **Input:** raw user query + session context
- **Actions:** detect prompt injection (regex + keyword patterns), detect jailbreak, validate query length and entropy
- **Output:** route decision with reason
- **Edges:** → retriever (safe) | → persist with refusal (injection / out-of-scope)

### Node 2 — Retriever (`agents/retriever.py`)
- **Input:** sanitized query
- **Actions:** embed with text-embedding-3-small → hybrid Qdrant search (dense + BM25 sparse, RRF) → FlashRank rerank → top-8 chunks → verify evidence sufficiency (top score ≥ 0.6, chunk count ≥ 2)
- **Output:** ranked chunks with source metadata, or evidence-failure signal
- **Edges:** → answer (evidence ok) | → persist with refusal (insufficient evidence)

### Node 3 — Answer (`agents/answer_node.py`)
- **Input:** query + verified chunks + session history
- **Actions:** GPT-4o generation under strict grounding prompt (cite only from provided context), format inline citations `[Source N]`, maintain session continuity
- **Output:** draft answer with citations
- **Edges:** → guardrail

### Node 4 — Guardrail (`agents/guardrail_node.py`)
- **Input:** draft answer + source chunks + original query
- **Checks (cheap-first short-circuit):**
  1. **Citation coverage** — every factual sentence maps to ≥1 cited chunk
  2. **Toxicity** — GPT-4o-mini content safety (threshold 0.1)
  3. **PII** — Presidio scan; redact then re-check
  4. **Confidence** — composite faithfulness score (threshold 0.7)
  5. **Hallucination** — GPT-4o-mini re-reads answer vs chunks, flags unsupported claims
- **Output:** approved answer | flagged answer
- **Edges:** → persist (approved, score ≥ 0.7) | → escalation (any check fails)

### Node 5 — Escalation (`agents/escalation_node.py`)
- **Input:** flagged query/answer + reason code
- **Actions:** insert open escalation record to DB, send optional email notification, return user-facing refusal with ticket ID
- **Output:** `{ refused: true, refusal_reason, ticket_id }`
- **Edges:** → persist

### Node 6 — Persist (`agents/persist_node.py`)
- **Input:** final agent state
- **Actions:** write query + response + audit rows to PostgreSQL, update session history in Redis
- **Owns all DB/Redis I/O** — other nodes are read-only
- **Edges:** END

---

## 5. Data Models

### PostgreSQL Tables

```sql
users (
  id            UUID PRIMARY KEY,
  email         TEXT UNIQUE NOT NULL,
  hashed_pw     TEXT NOT NULL,
  role          TEXT DEFAULT 'employee',   -- employee | admin
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  last_active   TIMESTAMPTZ
)

documents (
  id              UUID PRIMARY KEY,
  filename        TEXT NOT NULL,
  original_filename TEXT,
  doc_type        TEXT,          -- policy | hr | it | sop | compliance | faq
  department      TEXT,
  upload_date     TIMESTAMPTZ DEFAULT NOW(),
  version         INTEGER DEFAULT 1,
  status          TEXT DEFAULT 'processing',  -- processing | active | archived
  uploader_id     UUID REFERENCES users(id),
  file_size_bytes INTEGER,
  page_count      INTEGER
)

document_chunks (
  id             UUID PRIMARY KEY,
  document_id    UUID REFERENCES documents(id),
  chunk_index    INTEGER,
  content        TEXT NOT NULL,
  page_number    INTEGER,
  section        TEXT,
  char_count     INTEGER,
  qdrant_point_id UUID
)

queries (
  id             UUID PRIMARY KEY,
  session_id     TEXT NOT NULL,
  user_id        UUID REFERENCES users(id),
  query_text     TEXT NOT NULL,
  timestamp      TIMESTAMPTZ DEFAULT NOW(),
  agent_trace_id TEXT
)

responses (
  id                UUID PRIMARY KEY,
  query_id          UUID REFERENCES queries(id),
  answer_text       TEXT,
  citations         JSONB,    -- [{doc_id, filename, page, section, chunk_id}]
  confidence_score  FLOAT,
  guardrail_result  TEXT,     -- approved | flagged | refused
  guardrail_details JSONB,
  latency_ms        INTEGER,
  llm_tokens_used   INTEGER,
  refused           BOOLEAN DEFAULT FALSE,
  refusal_reason    TEXT
)

escalations (
  id               UUID PRIMARY KEY,
  query_id         UUID REFERENCES queries(id),
  reason_code      TEXT NOT NULL,  -- insufficient_evidence | hallucination | injection | toxicity | pii
  status           TEXT DEFAULT 'open',  -- open | in_progress | resolved
  assigned_to      TEXT,
  created_at       TIMESTAMPTZ DEFAULT NOW(),
  resolved_at      TIMESTAMPTZ,
  resolution_notes TEXT
)

audit_log (
  id          UUID PRIMARY KEY,
  event_type  TEXT NOT NULL,  -- doc_uploaded | doc_archived | query | escalation | refusal
  entity_id   UUID,
  agent_name  TEXT,
  details     JSONB,
  timestamp   TIMESTAMPTZ DEFAULT NOW()
)
```

### Qdrant Collection

```
Collection:  company_docs
Dimensions:  1536 (text-embedding-3-small)
Distance:    Cosine
Sparse:      BM25 (hybrid search)

Payload per point:
  document_id:  string
  chunk_id:     string
  doc_type:     string
  department:   string
  filename:     string
  page_number:  int
  section:      string
  upload_date:  string (ISO)
  status:       "active" | "archived"
  chunk_index:  int

Indexed fields: doc_type, department, status, upload_date
```

---

## 6. Document Ingestion Flow

```
Admin uploads file via Next.js UI
  → POST /api/ingest (FastAPI) — file + metadata
  → Validate file type (PDF/DOCX/HTML), max MAX_FILE_SIZE_MB
  → Insert to documents (status: processing)
  → Push job to Redis queue
  → Return job_id (frontend polls /ingest/{job_id}/status)

Celery worker picks up job:
  → Parse:
      PDF   → pdf_parser.py  (preserve page numbers)
      DOCX  → docx_parser.py (preserve headings as sections)
      HTML  → html_parser.py (strip nav/footer noise)
  → Chunk: 512 tokens, 50-token overlap, semantic boundary respect
  → Extract metadata per chunk (page, section, position)
  → Batch embed: text-embedding-3-small, batch size 100
  → Upsert to Qdrant (dense + sparse + payload)
  → Insert document_chunks to PostgreSQL
  → If same filename exists:
      Archive old version (status → archived, Qdrant payload updated)
      Activate new version
  → Update documents.status = 'active'
  → Write audit_log (event: doc_uploaded)
```

---

## 7. Query Flow

```
User submits question in chat
  → POST /api/query { query, session_id } + JWT
  → FastAPI validates JWT → extracts user_id
  → Load session history from Redis (TTL: 1 hour)
  → Insert to queries, get query_id
  → LangGraph graph.invoke(AgentState)

AgentState flows through nodes:
  router    → classify + sanitize → route decision
  retriever → embed → hybrid search → rerank → verify evidence
  answer    → GPT-4o grounded generation → draft with citations
  guardrail → 5-check pipeline → approve or escalate
  escalation (if triggered) → log + notify → refusal payload
  persist   → write all DB rows + update Redis session

Success response:
  {
    answer:     string,
    citations:  [{ filename, page, section, excerpt }],
    confidence: float,
    refused:    false,
    session_id: string,
    query_id:   string
  }

Refusal response:
  {
    refused:        true,
    refusal_reason: string,
    ticket_id:      string | null
  }
```

---

## 8. Guardrail Detail

### Input guardrails (Router node)

| Check | Method | Action |
|-------|--------|--------|
| Prompt injection | Regex patterns + keyword list | Hard refuse + escalate |
| Jailbreak | Keyword list + semantic similarity to known patterns | Hard refuse + escalate |
| Query length | > 2000 chars | Hard refuse |
| Empty / gibberish | Length + entropy check | Soft refuse |

### Output guardrails (Guardrail node)

| Check | Method | Threshold | Action on fail |
|-------|--------|-----------|---------------|
| Citation coverage | Every factual sentence has ≥1 inline citation | 100% | Escalate |
| Toxicity | GPT-4o-mini content safety | score > 0.1 | Hard refuse |
| PII | Presidio scan | Any PII detected | Redact → re-check |
| Confidence | Composite faithfulness score | < 0.7 | Escalate |
| Hallucination | GPT-4o-mini re-reads answer vs chunks | Any unsupported claim | Escalate |

### Hard refusal triggers
- Router detects injection or jailbreak
- Retriever: no chunks above 0.6 relevance, or fewer than 2 relevant chunks
- Guardrail: toxicity score > 0.1
- Guardrail: hallucination confirmed after one retry

**Refusal message:**
> "I don't have reliable information in the company documents to answer this question. If this is urgent, please contact the relevant team directly. A ticket has been logged for the knowledge team to review this gap."

---

## 9. Eval Suite

### RAGAS metrics

| Metric | Target | Measures |
|--------|--------|---------|
| Faithfulness | ≥ 0.85 | Answer claims supported by retrieved context |
| Answer Relevancy | ≥ 0.80 | Answer addresses the question |
| Context Precision | ≥ 0.75 | Retrieved chunks are relevant |
| Context Recall | ≥ 0.70 | Important context not missed |

### Adversarial test suite (`eval/adversarial/`)

| Test set | Size | Pass criterion |
|----------|------|----------------|
| Prompt injection | 50 | 100% refused |
| "Answer not in docs" | 50 | 100% refused (no hallucination) |
| PII-containing queries | 50 | 100% PII redacted from output |
| Jailbreak attempts | 20 | 100% refused |

### CI gates
- RAGAS faithfulness < 0.85 → fail
- Refusal accuracy < 0.95 → fail
- Any PII leakage → fail

---

## 10. Repository Structure

```
backend/
├── api/
│   ├── routes/         query.py · ingest.py · documents.py · escalations.py
│   │                   stats.py · auth.py · health.py
│   ├── middleware/     auth.py (JWT validation)
│   └── main.py
├── agents/
│   ├── graph.py        LangGraph StateGraph definition
│   ├── state.py        AgentState TypedDict
│   ├── router.py
│   ├── retriever.py
│   ├── answer_node.py
│   ├── guardrail_node.py
│   ├── escalation_node.py
│   └── persist_node.py
├── ingestion/
│   ├── parsers/        pdf_parser.py · docx_parser.py · html_parser.py · base.py
│   ├── chunker.py
│   ├── embedder.py
│   ├── indexer.py
│   └── dispatcher.py  (Celery worker entrypoint)
├── answer/             generator.py · formatter.py · refusal.py · session.py · pipeline.py
├── guardrails/         citation_check.py · hallucination_check.py · pii_check.py · toxicity_check.py
├── retrieval/          qdrant_client.py · hybrid_search.py · reranker.py (via core/qdrant.py)
├── eval/               ragas_eval.py · runner.py · adversarial/ · conftest.py
├── evals/              run_evals.py · metrics.py (offline harness)
├── models/             tables.py (ORM) · database.py
├── migrations/         Alembic versions
├── core/               config.py · database.py · qdrant.py · redis_client.py · access.py
└── tests/              pytest suite

frontend/
├── app/
│   ├── page.tsx        Root (redirects to /chat or /login)
│   ├── login/          Auth flow
│   ├── chat/           Chat UI with citation cards
│   └── admin/          stats · documents · escalations
├── components/
└── lib/                api.ts · auth.ts

infra/
├── docker-compose.yml      All services
├── docker-compose.dev.yml  Dev overrides (bind mounts, hot reload)
├── nginx.conf
└── .env.example

.github/workflows/
├── ci.yml              Test + eval on PR
└── deploy.yml          Deploy on main merge

docs/adr/               Architecture decision records
```

---

## 11. Environment Variables

```bash
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_LLM_MODEL=gpt-4o
OPENAI_GUARDRAIL_MODEL=gpt-4o-mini

# PostgreSQL
POSTGRES_USER=rag
POSTGRES_PASSWORD=...
POSTGRES_DB=rag_db
POSTGRES_URL=postgresql+asyncpg://rag:...@postgres:5432/rag_db
POSTGRES_HOST_PORT=15432          # host-side port (avoid conflict with local PG)

# Qdrant
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=company_docs

# Redis
REDIS_URL=redis://redis:6379/0
REDIS_HOST_PORT=16379             # host-side port

# Auth
JWT_SECRET=...                    # min 32 chars, random
JWT_EXPIRY_HOURS=8

# LangSmith (optional)
LANGCHAIN_API_KEY=ls-...
LANGCHAIN_PROJECT=rag-orchestrator
LANGCHAIN_TRACING_V2=true

# Email (escalation notifications — optional)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=admin@company.com
SMTP_PASSWORD=...
ESCALATION_EMAIL=hr-it@company.com

# App
APP_ENV=development
LOG_LEVEL=INFO
MAX_FILE_SIZE_MB=50
MAX_CHUNKS_PER_QUERY=8
EVIDENCE_THRESHOLD=0.6
FAITHFULNESS_THRESHOLD=0.7
CORS_ORIGINS=*

# Frontend (build-time — baked into client bundle)
NEXT_PUBLIC_API_URL=http://localhost:8000/api
```

> **Note:** `NEXT_PUBLIC_API_URL` must point to the browser-reachable backend address, not the internal Docker service name. Pass it as a build arg in Docker: `--build-arg NEXT_PUBLIC_API_URL=...`.

> **Security:** `POST /api/auth/register` is unauthenticated to allow first-admin bootstrapping. Gate or disable it before production exposure.
