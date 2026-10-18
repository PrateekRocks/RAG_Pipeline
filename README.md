# 🚀 Enterprise Multi-Tenant Hybrid RAG Pipeline

A production-grade, highly scalable **Retrieval-Augmented Generation (RAG)** pipeline designed for multi-tenant enterprise applications. Built with **FastAPI**, **Celery**, **Redis**, **PostgreSQL (pgvector)**, and **Google Gemini (GenAI)**.

---

## 📌 Architecture Overview

This pipeline solves the core challenges of enterprise AI: **accuracy**, **hallucination prevention**, **asynchronous scaling**, and **strict data access control (Row-Level Security)**.

```
                           +---------------------------+
                           |       Client / User       |
                           +-------------+-------------+
                                         |
                       +-----------------+-----------------+
                       |                                   |
              [ Document Ingestion ]               [ Query & Search ]
                       |                                   |
                       v                                   v
             POST /api/v1/ingest/                 POST /api/v1/query/
                       |                         (X-User-Id: <uuid>)
                       v                                   |
             +-------------------+                         v
             |   Celery Task     |               +-------------------+
             | (Redis Broker)    |               |  PostgreSQL RLS   |
             +---------+---------+               |  Session Config   |
                       |                         +---------+---------+
            +----------+----------+                        |
            |                     |                        v
            v                     v              +-------------------+
   [ Recursive Chunk ]   [ Gemini Embeddings ]   |   Hybrid Search   |
      (tiktoken)          (gemini-embedding-2)   | (Vector + BM25)   |
            |                     |              +---------+---------+
            +----------+----------+                        |
                       |                                   v
                       v                         +-------------------+
             +-------------------+               | Reciprocal Rank   |
             | Postgres pgvector |               |   Fusion (RRF)    |
             |  (HNSW + GIN TSV) |               +---------+---------+
             +-------------------+                         |
                                                           v
                                                 +-------------------+
                                                 | Gemini 3.8 Flash  |
                                                 | Grounded Answer   |
                                                 +---------+---------+
                                                           |
                                                           v
                                                 +-------------------+
                                                 | Citation Verifier |
                                                 |   & Abstention    |
                                                 +---------+---------+
                                                           |
                                                           v
                                                 [ Verified Response ]
```

---

## ✨ Key Features

### 1. 🔄 Asynchronous Distributed Ingestion
- Documents are accepted via FastAPI and handed off to background **Celery workers** backed by **Redis**.
- API calls return an immediate `task_id` without blocking network clients during heavy chunking or embedding calls.
- Task status can be polled at `/api/v1/ingest/status/{task_id}`.

### 2. ✂️ Recursive Token-Aware Chunking
- Splits text hierarchically using double-newlines, single-newlines, sentences, and words (`["\n\n", "\n", ". ", " "]`).
- Measures exact token lengths using OpenAI's `tiktoken` (`cl100k_base` encoding) up to a 512-token limit with overlap.

### 3. 🧠 Batch Embeddings with Resilience
- Uses Google GenAI's `gemini-embedding-2` model configured for 1536-dimensional embeddings.
- Automatic retry with exponential backoff using `tenacity` (handles rate limits seamlessly).
- Batching up to 100 texts with controlled concurrency via `asyncio.Semaphore`.

### 4. 🔍 Hybrid Retrieval with Reciprocal Rank Fusion (RRF)
- Combines two complementary search techniques inside PostgreSQL:
  1. **Dense Vector Search**: `pgvector` with **HNSW** cosine indexing for semantic similarity.
  2. **Sparse Full-Text Search**: Native PostgreSQL `tsvector` with **GIN** indexing and `ts_rank_cd` for exact keyword matching.
- Merges results using **Reciprocal Rank Fusion ($RRF\_Score = \frac{1}{60 + rank_{vec}} + \frac{1}{60 + rank_{text}}$)** to ensure high retrieval precision.

### 5. 🛡️ Hallucination Guardrails & Verbatim Citation Verification
- Generates answers using `gemini-3.8-flash` with structured Pydantic JSON schemas.
- **Strict Citation Verifier**:
  - Validates that every referenced `chunk_id` actually exists in the retrieved documents.
  - Checks that the cited quotation exists **verbatim (character-for-character)** inside the source chunk.
- **Abstention Engine**: If vector similarity is below threshold (`0.5`), context is insufficient, or citation verification fails, the system safely abstains instead of guessing.

### 6. 🔐 Multi-Tenant Security & Row-Level Security (RLS)
- Dynamic PostgreSQL Row-Level Security (`ALTER TABLE chunks FORCE ROW LEVEL SECURITY`).
- Reads client user context via `X-User-Id` header and sets `app.current_user_id` inside the database transaction.
- Documents and chunks are only visible if the user belongs to an authorized access group (`schema_acl.sql`).

---

## 📂 Project Structure

```
.
├── app/
│   ├── config.py             # Pydantic Settings & environment config
│   ├── db.py                 # Async SQLAlchemy engine & session maker
│   ├── dependencies.py       # User ID extraction & RLS session dependency
│   ├── celery_app.py         # Celery configuration & periodic schedules
│   ├── tasks.py              # Celery background tasks (ingestion, resync)
│   ├── main.py               # FastAPI application entrypoint
│   ├── routers/
│   │   ├── ingest.py         # Document ingestion & status endpoints
│   │   └── query.py          # Query & search endpoints
│   └── services/
│       ├── chunking.py       # Recursive token-based chunking
│       ├── embeddings.py     # Gemini embedding client with retries
│       ├── ingestion.py      # Core document processing & DB storage
│       ├── retrieval.py      # Hybrid search (pgvector + GIN tsvector RRF)
│       └── generation.py     # Gemini generation, citation checker & abstention
├── docs/
│   └── WORKFLOW_AND_EXPLANATION.md # Comprehensive layman explanation & workflow guide
├── docker-compose.yml        # PostgreSQL (pgvector) & Redis 7 services
├── requirements.txt          # Python dependencies
├── schema.sql                # Core database schema & HNSW / GIN indexes
├── schema_acl.sql            # Access Control List & Row-Level Security policies
├── sample_document.txt       # Sample document (ACME Employee Handbook)
└── .gitignore                # Git ignore rules
```

---

## 🛠️ Tech Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Framework** | FastAPI | High-performance asynchronous REST API |
| **Task Queue** | Celery + Redis | Asynchronous background document processing |
| **Database** | PostgreSQL 16 + pgvector | Multi-tenant storage, vector search & full-text search |
| **Vector Index** | HNSW (`vector_cosine_ops`) | Fast approximate nearest neighbor search |
| **Text Index** | GIN (`tsvector`) | Full-text keyword search |
| **Embeddings** | Google Gemini (`gemini-embedding-2`) | 1536-dimensional semantic vectors |
| **LLM Generation** | Google Gemini (`gemini-3.8-flash`) | Structured JSON generation with strict grounding |
| **Tokenizer** | `tiktoken` (`cl100k_base`) | Token-accurate document chunking |

---

## 🚦 Quickstart Guide

### 1. Prerequisites
- [Docker](https://www.docker.com/) & Docker Compose
- Python 3.10+
- Google Gemini API Key ([Google AI Studio](https://aistudio.google.com/))

### 2. Environment Configuration
Create a `.env` file in the root directory:

```env
DATABASE_URL=postgresql+asyncpg://rag_user:rag_password@localhost:5432/rag_db
REDIS_URL=redis://localhost:6379/0
GEMINI_API_KEY=your_gemini_api_key_here
```

### 3. Start Database and Redis
Start PostgreSQL with `pgvector` and Redis using Docker:

```bash
docker compose up -d
```

### 4. Initialize Database Schema
Execute the SQL schemas to set up tables, vector extension, and indexes:

```bash
# Apply core schema (documents, chunks, HNSW & GIN indexes)
docker exec -i $(docker compose ps -q db) psql -U rag_user -d rag_db < schema.sql

# (Optional) Apply Access Control & Row-Level Security
docker exec -i $(docker compose ps -q db) psql -U rag_user -d rag_db < schema_acl.sql
```

### 5. Install Dependencies
Set up your Python virtual environment:

```bash
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 6. Run the Celery Worker
In a separate terminal, launch the Celery task processor:

```bash
# Windows:
celery -A app.celery_app.celery_app worker --loglevel=info -P solo

# Linux/macOS:
celery -A app.celery_app.celery_app worker --loglevel=info
```

### 7. Run the FastAPI Application
Start the API web server:

```bash
uvicorn app.main:app --reload --port 8000
```

The interactive API documentation is now live at: [http://localhost:8000/docs](http://localhost:8000/docs).

---

## 📡 API Usage Examples

### 📥 1. Ingest a Document
Queue a document for background chunking, embedding, and indexing.

**Request:**
```bash
curl -X POST "http://localhost:8000/api/v1/ingest/" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "source_uri": "s3://company-docs/handbook.txt",
    "title": "ACME Corp Employee Handbook",
    "raw_text": "Employees may work remotely up to three days per week with manager approval. Core hours are 10:00 AM to 4:00 PM. Full-time employees accrue 20 days of paid time off per year."
  }'
```

**Response:**
```json
{
  "task_id": "673f3c4e-bf27-466d-8b09-fa986df9c55b",
  "status": "queued"
}
```

### ⏳ 2. Check Ingestion Task Status
Check whether the background Celery task has finished:

```bash
curl "http://localhost:8000/api/v1/ingest/status/673f3c4e-bf27-466d-8b09-fa986df9c55b"
```

**Response:**
```json
{
  "task_id": "673f3c4e-bf27-466d-8b09-fa986df9c55b",
  "status": "SUCCESS",
  "result": "4a13d332-9c98-4448-9366-0d12e6cb1301"
}
```

### 🔎 3. Query the RAG Pipeline
Ask a question against your indexed documents. Include `X-User-Id` for Row-Level Security verification:

**Request:**
```bash
curl -X POST "http://localhost:8000/api/v1/query/" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: 00000000-0000-0000-0000-000000000001" \
  -d '{
    "query": "What is the remote work policy and how many days can I work from home?",
    "top_k": 5
  }'
```

**Response (Grounded with Verbatim Citations):**
```json
{
  "answer": "Employees are permitted to work remotely up to three days per week with manager approval, and must be reachable during core hours from 10:00 AM to 4:00 PM.",
  "citations": [
    {
      "chunk_id": "63f73369-0eb6-455a-bd6e-ba9d45f9ec08",
      "quote": "Employees may work remotely up to three days per week with manager approval."
    }
  ],
  "abstained": false
}
```

### 🛑 4. Safe Abstention on Missing / Irrelevant Information
When an irrelevant question is asked:

**Request:**
```bash
curl -X POST "http://localhost:8000/api/v1/query/" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: 00000000-0000-0000-0000-000000000001" \
  -d '{
    "query": "What is the speed of sound on Mars?",
    "top_k": 5
  }'
```

**Response:**
```json
{
  "answer": "I don't have enough information to answer that.",
  "citations": [],
  "abstained": true
}
```

---

## 📚 In-Depth Workflow & Layman Guide

For a step-by-step walkthrough of the pipeline written in simple everyday language with real-world analogies, read:
👉 **[docs/WORKFLOW_AND_EXPLANATION.md](docs/WORKFLOW_AND_EXPLANATION.md)**.
