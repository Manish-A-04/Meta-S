
# META-S

## Resource-Constrained Multi-Agent Email Triage System

### (4GB VRAM Optimized – Production Architecture Specification)

---

# 1. System Overview

META-S is a resource-constrained, multi-agent email triage system designed to operate within a strict **4GB VRAM limit** using a single 4-bit quantized Small Language Model (SLM).

The system uses:

* Single quantized LLM (loaded once)
* LangGraph hub-and-spoke orchestration
* Reflexion-based recursive refinement
* CPU-based embeddings for RAG
* Strict token control
* Production-ready database tracking

---

# 2. Architectural Principles

1. **Single Model Load Only**
2. **4-bit Quantized GGUF Model**
3. **CPU Embeddings**
4. **Maximum Context: 2048 tokens**
5. **Max Reflexion Loops: 2**
6. **Clear Separation of Concerns**
7. **Benchmark & Research Tracking Enabled**

---

# 3. Project File Structure

```
meta-s/
│
├── app/
│   ├── main.py
│   │
│   ├── core/
│   │   ├── config.py
│   │   ├── security.py
│   │   ├── rate_limiter.py
│   │   └── logger.py
│   │
│   ├── api/
│   │   ├── routes.py
│   │   └── deps.py
│   │
│   ├── schemas/
│   │   ├── request.py
│   │   ├── response.py
│   │   └── internal_state.py
│   │
│   ├── orchestrator/
│   │   ├── graph.py
│   │   ├── nodes.py
│   │   └── state.py
│   │
│   ├── services/
│   │   ├── email_service.py
│   │   └── reflection_service.py
│   │
│   ├── llm/
│   │   ├── model_loader.py
│   │   ├── prompt_templates.py
│   │   └── token_manager.py
│   │
│   ├── rag/
│   │   ├── embeddings.py
│   │   ├── vector_store.py
│   │   └── retriever.py
│   │
│   ├── db/
│   │   ├── base.py
│   │   ├── models.py
│   │   ├── session.py
│   │   └── migrations/
│   │
│   └── cache/
│       └── redis_client.py
│
├── requirements.txt
└── README.md
```

---

# 4. Business Logic Execution Flow

```
Client
  ↓
FastAPI Route
  ↓
email_service.py
  ↓
LangGraph Orchestrator
  ↓
Router Node
  ↓
Analyst Node (RAG)
  ↓
Scribe Node
  ↓
Reflector Node
    ↳ if quality low → loop back to Scribe (max 2)
  ↓
Persist Results
  ↓
Return Response
```

---

# 5. Database Schema

---

## 5.1 users

```
id              UUID (PK)
email           VARCHAR(255) UNIQUE NOT NULL
password_hash   TEXT NOT NULL
created_at      TIMESTAMP DEFAULT NOW()
is_active       BOOLEAN DEFAULT TRUE
```

Purpose:

* Authentication
* Email ownership

---

## 5.2 emails

```
id              UUID (PK)
user_id         UUID (FK → users.id)
subject         TEXT
body            TEXT NOT NULL
classification  VARCHAR(50)      -- Spam | Urgent | Work
status          VARCHAR(50)      -- pending | processed
created_at      TIMESTAMP DEFAULT NOW()
```

Purpose:

* Stores original emails
* Stores router classification

---

## 5.3 drafts

```
id              UUID (PK)
email_id        UUID (FK → emails.id)
version         INTEGER
content         TEXT NOT NULL
reflection_score INTEGER
approved        BOOLEAN DEFAULT FALSE
created_at      TIMESTAMP DEFAULT NOW()
```

Purpose:

* Stores each reflexion iteration
* Enables benchmarking
* Maintains audit trail

---

## 5.4 agent_logs

```
id              UUID (PK)
email_id        UUID (FK → emails.id)
agent_type      VARCHAR(50)  -- router | analyst | scribe | reflector
input_tokens    INTEGER
output_tokens   INTEGER
latency_ms      INTEGER
created_at      TIMESTAMP DEFAULT NOW()
```

Purpose:

* Token tracking
* Latency tracking
* Research benchmarking

---

## 5.5 rag_documents

```
id              UUID (PK)
title           TEXT
content         TEXT
embedding_id    VARCHAR(255)
created_at      TIMESTAMP DEFAULT NOW()
```

Purpose:

* Metadata for documents
* Embeddings stored in ChromaDB

---

# 6. Database Relationships

```
users (1) ─────────── (∞) emails
emails (1) ─────────── (∞) drafts
emails (1) ─────────── (∞) agent_logs
rag_documents → linked to ChromaDB embeddings
```

---

# 7. API Request Models

---

## 7.1 RegisterRequest

```
email: string (required, valid email)
password: string (required, minimum 8 characters)
```

---

## 7.2 LoginRequest

```
email: string (required)
password: string (required)
```

---

## 7.3 EmailTriageRequest

```
subject: string (optional)
body: string (required)
force_reflection: boolean (default=false)
max_reflections: integer (default=2, max=2)
```

Constraints:

* max_reflections capped at 2 (VRAM safe)
* body required

---

## 7.4 AddDocumentRequest

```
title: string
content: string
```

---

# 8. API Response Models

---

## 8.1 LoginResponse

```
access_token: string
refresh_token: string
token_type: string ("bearer")
expires_in: integer
```

---

## 8.2 EmailTriageResponse

```
email_id: UUID
classification: string

final_draft: string

reflection_count: integer
reflection_scores: list[integer]
approved: boolean

usage:
    input_tokens: integer
    output_tokens: integer
    total_tokens: integer
    latency_ms: integer
```

---

## 8.3 DraftHistoryResponse

```
email_id: UUID

drafts:
  - version: integer
    content: string
    reflection_score: integer
    approved: boolean
    created_at: datetime
```

---

## 8.4 MetricsResponse

```
total_emails_processed: integer
average_reflection_count: float
average_latency_ms: float
average_tokens_per_email: float
approval_rate: float
```

---

# 9. Internal Orchestrator State (Not Exposed)

```
EmailState

email_id: UUID
subject: string
body: string

classification: string
rag_context: string

draft: string
critique: string

reflection_count: integer
reflection_scores: list[integer]
approved: boolean

input_tokens: integer
output_tokens: integer
latency_ms: integer
```

This state flows through:

```
Router → Analyst → Scribe → Reflector → (Loop)
```

---

# 10. Token Allocation Strategy (4GB Constraint)

```
Max Context Window: 2048 tokens

System Prompt: 200
Email Body: 600
RAG Context: 600
Draft + Critique: 400
Output Buffer: 248

Reflection Loop Max: 2
```

---

# 11. Memory & Resource Allocation

| Component     | Runs On        |
| ------------- | -------------- |
| Quantized LLM | GPU (4GB VRAM) |
| Embeddings    | CPU            |
| ChromaDB      | CPU            |
| FastAPI       | CPU            |
| Redis         | RAM            |

Only one model loaded at runtime.

---

# 12. Final System Flow

```
Client
  ↓
FastAPI
  ↓
Auth + Validation
  ↓
email_service.py
  ↓
LangGraph Orchestrator
  ↓
Router
  ↓
Analyst (RAG Retrieval)
  ↓
Scribe
  ↓
Reflector (max 2 loops)
  ↓
Persist:
  - emails
  - drafts
  - agent_logs
  ↓
Return Final Draft
```

---

# 13. Architectural Guarantees

* Single quantized model
* No redundant services
* Clean business logic separation
* Research benchmarking ready
* Production database design
* Strict VRAM protection
* Reflexion-based quality improvement
* Fully extensible without architectural rewrite


