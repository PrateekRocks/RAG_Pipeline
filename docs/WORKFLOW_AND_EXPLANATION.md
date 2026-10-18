# 📖 Understanding the RAG Pipeline: A Layman's Guide & Complete Workflow

Welcome! If you have ever wondered:
- *"What actually happens when an AI searches through company documents?"*
- *"Why can't we just paste a 100-page PDF directly into ChatGPT?"*
- *"How do we stop an AI from making things up (hallucinating)?"*
- *"How does this specific codebase work under the hood?"*

This guide explains everything in plain, simple English without confusing jargon.

---

## 🧭 Table of Contents
1. [The Big Picture: What is RAG?](#1-the-big-picture-what-is-rag)
2. [The Real-World Analogy: The Open-Book Exam](#2-the-real-world-analogy-the-open-book-exam)
3. [The Two Main Lifecycles: Ingestion vs. Querying](#3-the-two-main-lifecycles-ingestion-vs-querying)
4. [Step-by-Step: The Ingestion Workflow (Storing Knowledge)](#4-step-by-step-the-ingestion-workflow-storing-knowledge)
5. [Step-by-Step: The Query Workflow (Answering Questions)](#5-step-by-step-the-query-workflow-answering-questions)
6. [The Magic Ingredients Explained in Plain English](#6-the-magic-ingredients-explained-in-plain-english)
   - [Chunking: Slicing text into bite-sized index cards](#a-chunking-index-cards)
   - [Embeddings: Giving sentences GPS coordinates](#b-embeddings-gps-coordinates-of-meaning)
   - [Hybrid Search & RRF: Combining the two best search methods](#c-hybrid-search--rrf-the-two-detectives)
   - [Abstention & Citation Verification: The strict fact-checker](#d-verbatim-citations--abstention-the-strict-fact-checker)
   - [Row-Level Security: Company security badges](#e-row-level-security-security-badges)
7. [Codebase Map: What Every File Does](#7-codebase-map-what-every-file-does)
8. [A Complete Walkthrough Example](#8-a-complete-walkthrough-example)

---

## 1. The Big Picture: What is RAG?

**RAG** stands for **Retrieval-Augmented Generation**.

- **Retrieval**: Finding relevant snippets of information from your own private database.
- **Augmented**: Adding those retrieved snippets to the prompt you send to the AI.
- **Generation**: Asking the Large Language Model (Google Gemini) to write a clear, natural-language answer based *only* on those snippets.

In short: Instead of relying on what the AI memorized from the public internet during its training, we hand it **our company's exact documents** and tell it: *"Read only these pages and answer the question."*

---

## 2. The Real-World Analogy: The Open-Book Exam

Think of traditional AI like a student taking a **closed-book exam from memory**:
- If you ask about something they studied years ago, they might remember it well, or they might misremember details and confidently make something up (**hallucination**).
- They also don't know what happened at your company yesterday, because your internal handbook was never in their textbook.

**Our RAG system turns the exam into an open-book exam with a strict proctor:**
1. You ask a question: *"How many sick days do I get?"*
2. A research assistant runs into your company library, finds the exact 2 paragraphs in the HR handbook discussing sick leave, and places those two index cards on the student's desk.
3. The student (Gemini) reads those cards and writes: *"You get 10 paid sick days per year."*
4. A proctor inspects the answer and ensures every single statement matches the index card **word-for-word**. If not, the proctor throws it out!

---

## 3. The Two Main Lifecycles: Ingestion vs. Querying

The codebase has two distinct pathways:

```
+-------------------------------------------------------------------+
|  1. INGESTION PIPELINE (Write Path - Done ahead of time)          |
|  Document -> Sliced into Chunks -> Vectors Created -> Saved in DB |
+-------------------------------------------------------------------+

+-------------------------------------------------------------------+
|  2. QUERY PIPELINE (Read Path - Done in real time when you ask)   |
|  User Question -> Hybrid Search -> Top Chunks -> Gemini -> Answer |
+-------------------------------------------------------------------+
```

Let's look at each one in detail.

---

## 4. Step-by-Step: The Ingestion Workflow (Storing Knowledge)

When you upload or save a new document (e.g., `sample_document.txt`):

```
[ Raw Document ]
       │
       ▼
[ FastAPI: POST /api/v1/ingest/ ]
       │  (Returns "Task Queued" immediately so you don't wait)
       ▼
[ Celery + Redis ] ──► (Background Worker picks up the job)
       │
       ▼
[ Step 1: Content Hashing ] ──► Check SHA-256 fingerprint (prevents duplicate work)
       │
       ▼
[ Step 2: Recursive Chunking ] ──► Split document into ~512-token pieces (app/services/chunking.py)
       │
       ▼
[ Step 3: Vector Embeddings ] ──► Send chunks to Google Gemini to get 1,536 numbers each (app/services/embeddings.py)
       │
       ▼
[ Step 4: Database Storage ] ──► Store chunk text + embedding in PostgreSQL (app/services/ingestion.py)
```

### Why use Celery and Redis here?
If someone uploads a 500-page policy manual, generating embeddings and saving thousands of chunks can take 15–30 seconds. If a web server made your browser wait 30 seconds, your request would freeze or timeout.
- **FastAPI** accepts the document, gives you a `task_id` in 5 milliseconds, and says: *"Got it! Worker #3 is working on it."*
- **Redis** acts as the inbox holding the job.
- **Celery** is the background worker doing the heavy lifting without slowing down the website.

---

## 5. Step-by-Step: The Query Workflow (Answering Questions)

When a user asks: *"What is the policy for parental leave?"*

```
[ User asks a Question ] (With header: X-User-Id: Alice)
       │
       ▼
[ FastAPI: POST /api/v1/query/ ]
       │
       ▼
[ PostgreSQL Row-Level Security ] ──► Verifies: "Does Alice have permission to view HR docs?"
       │
       ▼
[ Query Embedding ] ──► Question is converted into a 1,536-dimensional vector
       │
       ▼
[ Hybrid Search in Postgres ]
   ├── 1. Vector Search: Finds chunks with similar concepts (pgvector HNSW)
   └── 2. Keyword Search: Finds chunks with the exact words "parental", "leave" (tsvector GIN)
       │
       ▼
[ Reciprocal Rank Fusion (RRF) ] ──► Merges both lists to pick the true top 8 best chunks
       │
       ▼
[ Similarity Guardrail Check ]
   └── Is top vector similarity < 0.5?
          ├── YES ──► ABSTAIN: "I don't have enough information to answer that."
          └── NO  ──► Send Question + Top Chunks to Gemini 3.8 Flash
       │
       ▼
[ Gemini 3.8 Flash Generation ] ──► Produces JSON: { answer, citations: [{ chunk_id, quote }] }
       │
       ▼
[ Guardrail Verifier (app/services/generation.py) ]
   ├── 1. Did the model make up a fake chunk ID? (Hallucinated citation check)
   └── 2. Does the quoted text appear VERBATIM in that chunk? (Fake quote check)
          ├── FAILED ──► ABSTAIN: "I found related info but can't confidently answer."
          └── PASSED ──► Return clean answer + verified citations to user!
```

---

## 6. The Magic Ingredients Explained in Plain English

### A. Chunking (Index Cards)
*File: `app/services/chunking.py`*

**The Problem**: An entire employee handbook is thousands of words. If you throw the whole book at the AI every time someone asks a question, it's slow, expensive, and the AI gets distracted by irrelevant chapters.

**The Solution**: We slice the document into small pieces (chunks) of around 512 tokens (~350–400 words). 
- We don't just cut words in half randomly. 
- The algorithm splits recursively: first trying double paragraph breaks (`\n\n`), then single line breaks (`\n`), then sentences (`. `), then spaces.
- This ensures paragraphs stay intact as complete thoughts on their own index card.

---

### B. Embeddings (GPS Coordinates of Meaning)
*File: `app/services/embeddings.py`*

**The Problem**: Computers do not understand words; they only understand numbers. If you search for *"maternity benefits"*, but the document says *"parental leave"*, a basic keyword search will fail because the words don't match.

**The Solution**: We pass text through Google's `gemini-embedding-2` model. The model converts text into an array of 1,536 decimal numbers (a vector).
- You can imagine this like GPS coordinates on a giant 1,536-dimensional map.
- Words or concepts that mean the same thing end up right next to each other on this map!
  - *"Puppy"* and *"Dog"* are close together.
  - *"Parental leave"* and *"Maternity benefits"* are close together.
  - *"Automobile transmission"* is far away.

---

### C. Hybrid Search & RRF (The Two Detectives)
*File: `app/services/retrieval.py`*

Most RAG systems only use vector search. But vector search alone has blind spots (for example, specific product codes, part numbers like `TX-9000`, or rare acronyms).

This project uses **Hybrid Search**, which employs two different "detectives":
1. **Detective 1: Dense Vector Search (`pgvector` with HNSW)**
   - Understands semantics, concepts, and synonyms.
2. **Detective 2: Sparse Keyword Search (`tsvector` with GIN)**
   - Looks for exact character matches, error codes, and technical jargon.

**Reciprocal Rank Fusion (RRF)**:
How do you merge results from two different detectives? 
Each chunk gets an RRF score:
$$\text{Score} = \frac{1}{60 + \text{Rank}_{\text{vector}}} + \frac{1}{60 + \text{Rank}_{\text{keyword}}}$$
If a chunk appears near the top of *both* lists, its score skyrockets. The cream rises to the top!

---

### D. Verbatim Citations & Abstention (The Strict Fact-Checker)
*File: `app/services/generation.py`*

The biggest fear in enterprise AI is **hallucination**—when an AI invents policies or facts that do not exist.

This codebase protects against hallucinations with three interlocking shields:
1. **Low Similarity Cutoff**: If the highest matching chunk has a cosine similarity score below `0.5`, the system refuses to answer immediately:
   > *"I don't have enough information to answer that."*
2. **Strict System Prompt**: Gemini is instructed:
   > *"You answer ONLY using the provided context chunks. Every factual sentence must cite the chunk_id and include an exact, verbatim quotation."*
3. **Automated Verifier**: A Python function (`verify_citations`) inspects Gemini's answer before returning it to the user:
   - Did the AI reference a chunk ID that was never in the search results? 🚨 **REJECT.**
   - Did the AI paraphrase the quote instead of copying it character-for-character? 🚨 **REJECT.**

If any check fails, the system safely **abstains** rather than risk misleading the user.

---

### E. Row-Level Security (Security Badges)
*File: `schema_acl.sql` & `app/dependencies.py`*

In a real company, not everyone should see every document. An intern should not be able to read CEO compensation records or pending layoff lists.

Instead of trying to filter this in Python code (which is easy to mess up or bypass with a bug), we enforce this **directly inside the PostgreSQL database engine**:
- Every time a user sends a query, they include their identity: `X-User-Id`.
- The API sets `app.current_user_id` inside the active database transaction.
- PostgreSQL's **Row-Level Security (RLS)** policy hides unauthorized rows automatically. To the database query, unauthorized documents simply do not exist!

---

## 7. Codebase Map: What Every File Does

| File | What It Does (In Layman's Terms) |
| :--- | :--- |
| [`docker-compose.yml`](../docker-compose.yml) | Boots up the database (PostgreSQL with vector support) and the task queue (Redis) in Docker containers with one command. |
| [`schema.sql`](../schema.sql) | Creates the database tables (`documents`, `chunks`), creates full-text search indexes (`GIN`), and creates vector search indexes (`HNSW`). |
| [`schema_acl.sql`](../schema_acl.sql) | Sets up user groups, document access permissions, and PostgreSQL Row-Level Security rules. |
| [`requirements.txt`](../requirements.txt) | The shopping list of Python packages needed to run the project (FastAPI, Celery, pgvector, etc.). |
| [`sample_document.txt`](../sample_document.txt) | An example ACME Corp Employee Handbook used to test and demonstrate the pipeline. |
| [`app/main.py`](../app/main.py) | The front door of the API. Boots FastAPI, checks the database connection, and connects the API routes. |
| [`app/config.py`](../app/config.py) | Reads environment variables (database connection string, Gemini API key, Redis URL) from `.env`. |
| [`app/db.py`](../app/db.py) | Manages database connection pooling with SQLAlchemy so thousands of queries run efficiently. |
| [`app/celery_app.py`](../app/celery_app.py) | Configures the background worker system (Celery) and sets up recurring jobs (e.g. resyncing sources every 6 hours). |
| [`app/tasks.py`](../app/tasks.py) | Defines the background jobs that Celery executes (e.g., ingest document, retry up to 3 times on network failure). |
| [`app/dependencies.py`](../app/dependencies.py) | FastAPI dependency that checks the user's ID header and activates their database security badge for that request. |
| [`app/routers/ingest.py`](../app/routers/ingest.py) | Endpoints where users submit new documents to be processed and check the progress of their background jobs. |
| [`app/routers/query.py`](../app/routers/query.py) | Endpoint where users ask questions and receive verified, cited answers. |
| [`app/services/chunking.py`](../app/services/chunking.py) | Splits big documents into small, logical paragraphs that fit into embedding models. |
| [`app/services/embeddings.py`](../app/services/embeddings.py) | Sends text to Google Gemini to convert words into 1,536-dimensional numerical vectors. |
| [`app/services/ingestion.py`](../app/services/ingestion.py) | Coordinates the whole ingestion dance: hashes text, saves document, chunks it, embeds it, and writes chunks to the DB. |
| [`app/services/retrieval.py`](../app/services/retrieval.py) | Performs the Hybrid Search (combines pgvector cosine similarity with PostgreSQL keyword search using RRF). |
| [`app/services/generation.py`](../app/services/generation.py) | Prompts Gemini 3.8 Flash, verifies every citation quote verbatim, and abstains if facts cannot be proven. |

---

## 8. A Complete Walkthrough Example

Let's walk through an actual scenario using `sample_document.txt`:

### 1. Ingestion Phase
1. We send `sample_document.txt` (the ACME Employee Handbook) to `POST /api/v1/ingest/`.
2. Celery chops the handbook into individual sections:
   - Chunk 1: Section 1: Remote Work Policy
   - Chunk 2: Section 2: Paid Time Off
   - Chunk 3: Section 3: Parental Leave
   - ...and so on.
3. Each chunk is transformed into 1,536 numbers by Google Gemini embeddings.
4. All chunks and their vectors are saved in PostgreSQL.

### 2. Query Phase
A user asks:
> *"How much budget do I get for learning and conferences?"*

1. **Embedding**: The question is embedded into numbers.
2. **Hybrid Search**:
   - Vector search finds Chunk 7 (*Section 7: Professional Development*) because concepts like "learning", "budget", "conferences" match strongly.
   - Full-text search also finds Chunk 7 because words like "budget" and "conferences" appear literally.
3. **RRF Score**: Chunk 7 ranks #1 across both searches.
4. **LLM Generation**:
   Gemini receives Chunk 7:
   ```
   "Each employee receives an annual learning budget of 2000 dollars for courses, books, certifications, and conferences."
   ```
   Gemini writes:
   - **Answer**: *"Each employee receives an annual learning budget of 2000 dollars for courses, books, certifications, and conferences."*
   - **Citation**: Chunk ID `c7`, Quote: *"Each employee receives an annual learning budget of 2000 dollars for courses, books, certifications, and conferences."*
5. **Verification**: The verifier checks that the quote exists verbatim in Chunk 7. It matches!
6. **Delivery**: The verified answer and citation are returned to the user with `abstained: false`.

### 3. What if someone asks an off-topic question?
> *"What is the recipe for chocolate chip cookies?"*

1. Hybrid search finds no chunks with high similarity score.
2. The top similarity is `0.18` (well below `0.5`).
3. The abstention engine immediately returns:
   ```json
   {
     "answer": "I don't have enough information to answer that.",
     "citations": [],
     "abstained": true
   }
   ```
4. **No hallucination occurs.** The system remains 100% trustworthy.
