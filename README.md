# Domain Knowledge Bot

> **Repo:** https://github.com/its-yashjai/grounded-rag-bot

Upload your domain knowledge. Ask anything. Get a fast, grounded answer with sources.

A hackathon-scoped RAG chatbot: upload PDF/DOCX/TXT documents, ask natural-language
questions, and get streamed answers grounded strictly in the uploaded content —
with clickable citations back to the exact document and page. If the answer
isn't in your documents, it says so instead of guessing.

## Overview

- Multi-document upload with live ingestion progress (extract → chunk → embed → index)
- Structure-aware extraction via `unstructured`: section headings, table
  detection, and OCR fallback for scanned pages
- Hybrid retrieval: semantic search (Chroma) + keyword search (BM25), fused with
  Reciprocal Rank Fusion, then reranked by a cross-encoder for precision
- Streamed, cited answers via Groq — never claims something is in a document that isn't
- Content-hash deduplication so re-uploading the same file doesn't reprocess it
- In-memory caching (embedding cache, response cache) keyed on a knowledge-base
  version, so uploads automatically invalidate stale cached answers
- A small observability panel: latency, tokens, estimated cost, cache hit rate,
  and a recent-requests table
- Clean, warm-neutral UI in the spirit of modern AI chat apps (no emojis, real icons)

## Architecture

```
Browser (HTML/CSS/JS)
        |
     FastAPI
        |
  +-----+------+-------------+
  |            |             |
Documents     Chat        Metrics
  |            |
Ingestion   Query normalize
  |            |
Embeddings  Hybrid Retrieval (semantic + BM25 -> RRF, top 40 candidates)
  |            |
Chroma      Cross-Encoder Rerank (dedup + relevance rescoring + token-budget select)
             |
          Guard (relevance score clears MIN_GROUNDING_SCORE?)
             |
          Groq (streamed)
             |
          Citations + Metrics
```

Backend layout:
```
backend/app/
  main.py, config.py, deps.py
  api/v1/          health, documents, chat, metrics
  agents/           ingestion, query, answer (system prompt), guard logic
  services/
    llm/            LLMProvider interface + GroqProvider
    embeddings/      batched, cached embedding generation
    ingestion/       extraction (PDF/DOCX/TXT), structure-aware chunking
    retrieval/       hybrid retriever (BM25 + Chroma + RRF), reranker
    cache/           in-memory TTL cache (swap-in point for Redis)
    cost/            token -> $ estimation
    citations/       context block + citation building
    observability/   structured logs + in-memory metrics
  repositories/       VectorStore abstraction (Chroma), document repository
  models/, schemas/, utils/
```

## RAG Pipeline

1. **Extraction** — `unstructured` for PDF/DOCX (page numbers, section headings
   via `parent_id` chains, element type — paragraph vs. table vs. list — and
   OCR fallback for scanned pages, all from one library); plain read + paragraph
   split for TXT.
2. **Chunking** — structure-aware: packs blocks up to `CHUNK_SIZE` tokens,
   never merging across a section-heading boundary and never merging a table
   into surrounding prose (tables stay atomic). Only hard-splits a single
   oversized block. Small token overlap between chunks, carried forward
   correctly across a flush (see chunker.py docstring). Configurable via
   `CHUNK_SIZE` / `CHUNK_OVERLAP`.
3. **Embedding** — `sentence-transformers` (`all-MiniLM-L6-v2` by default),
   batched, with a content-hash cache so identical chunks are never re-embedded.
4. **Storage** — Chroma (embedded, persisted to disk) behind a `VectorStore`
   interface — swapping in Qdrant/pgvector later means writing one new class.
5. **Retrieval** — semantic search (Chroma) + keyword search (BM25 over an
   in-memory index) combined with Reciprocal Rank Fusion, over a `TOP_K`
   (default 40) candidate pool per leg.
6. **Reranking** — dedup by content hash, then a cross-encoder
   (`cross-encoder/ms-marco-MiniLM-L-6-v2`) rescores every candidate against
   the query and the top `RERANK_TOP_K` are kept within a `MAX_CONTEXT_TOKENS`
   budget. Falls back to plain RRF-score selection if
   `ENABLE_CROSS_ENCODER_RERANKER=false`.
7. **Guard** — if no reranked chunk clears `MIN_GROUNDING_SCORE` on the
   cross-encoder's calibrated relevance score (falls back to a looser
   RRF-score threshold when the cross-encoder is disabled), the bot answers
   "I couldn't find enough information..." without ever calling the LLM.
8. **Generation** — Groq (`GROQ_MODEL`, default `llama-3.3-70b-versatile`),
   streamed via Server-Sent Events, with a system prompt that forbids outside
   knowledge and requires citing `[Source N]` labels.
9. **Citations** — returned as structured metadata (document, page, section,
   excerpt, relevance score) alongside the answer; the frontend renders them
   as clickable chips.

## Caching

Four logical cache namespaces, currently backed by an in-memory TTL cache
(`services/cache/cache_service.py`) whose get/set/delete interface mirrors
what a Redis-backed implementation would expose — swapping in
`redis.asyncio` later is a drop-in replacement, nothing above that layer
needs to change:

- **Document hash cache** — `file_hash -> document_id`, prevents reprocessing
  duplicate uploads.
- **Embedding cache** — `chunk_hash -> embedding`, avoids re-embedding
  identical text.
- **Response cache** — `query + kb_version -> answer + citations`. The
  in-memory `DocumentRepository` tracks a `kb_version` integer that increments
  on every document change, so the cache key changes automatically whenever
  the knowledge base changes — no manual invalidation logic needed.

## Observability

Lean stand-in for OpenTelemetry: every chat request logs a structured JSON
line (`services/observability/metrics_service.py`) with latency, token
counts, cache hit/miss, and retrieved/reranked chunk counts — the same
fields an `rag.request` OTel span would carry. An in-memory `MetricsService`
aggregates these for the `/api/v1/metrics/summary` and `/api/v1/metrics`
endpoints that power the UI's Observability panel.

**Note:** the spec's fuller OpenTelemetry/Redis/Postgres setup was scoped
down for the "few hours" build. See *Known limitations* below for what a
harder deployment would swap in.

## Running locally

Requires Python 3.11+, and a Groq API key.

```bash
git clone https://github.com/its-yashjai/grounded-rag-bot.git
cd grounded-rag-bot
cd backend
cp .env.example .env        # then fill in GROQ_API_KEY
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000 — the frontend is served directly by FastAPI.

## Docker

```bash
git clone https://github.com/its-yashjai/grounded-rag-bot.git
cd grounded-rag-bot
cp backend/.env.example backend/.env   # fill in GROQ_API_KEY
docker compose up --build
```

Open http://localhost:8000.

## Environment variables

See `backend/.env.example` for the full list. The essentials:

```env
GROQ_API_KEY=            # required
GROQ_MODEL=llama-3.3-70b-versatile

EMBEDDING_MODEL=all-MiniLM-L6-v2

CHUNK_SIZE=800
CHUNK_OVERLAP=120
TOP_K=12
RERANK_TOP_K=5
MAX_CONTEXT_TOKENS=5000

ENABLE_RESPONSE_CACHE=true
ENABLE_RETRIEVAL_CACHE=true
ENABLE_EMBEDDING_CACHE=true
CACHE_TTL=600

GROQ_INPUT_COST_PER_MILLION=0.59   # check current Groq pricing for your model
GROQ_OUTPUT_COST_PER_MILLION=0.79
```

## API

OpenAPI docs at `/docs` and `/redoc`.

| Endpoint | Description |
|---|---|
| `GET /api/v1/health`, `/health/live`, `/health/ready` | Health checks |
| `POST /api/v1/documents/upload` | Multi-file upload (multipart/form-data) |
| `GET /api/v1/documents` | List all documents |
| `GET /api/v1/documents/{id}` | Get one document |
| `GET /api/v1/documents/{id}/status` | Poll processing status |
| `DELETE /api/v1/documents/{id}` | Delete a document and its vectors |
| `POST /api/v1/chat/stream` | Ask a question, streamed via SSE |
| `GET /api/v1/metrics/summary` | Aggregate metrics |
| `GET /api/v1/metrics` | Recent request log |

## Testing

```bash
cd backend
pytest tests/ -v
```

23 unit tests included: chunking (paragraph boundaries, hard-split,
page-number preservation, overlap, section-boundary and table-atomicity
behavior), reranking (candidate-pool scan window), grounding-threshold
logic, hashing, cache TTL/hit-rate, cost calculation — plus API integration
tests (upload, dedup, chat streaming with citations, metrics).
The Groq network call is mocked in tests — everything else runs against the
real pipeline.

## Known limitations

- **Caching/metadata storage is in-memory**, not Redis/Postgres — fine for a
  single-process demo; state resets on restart. The interfaces are written
  so swapping in real Redis/Postgres doesn't require touching business logic.
- **Table structure extraction is opt-in** (`ENABLE_TABLE_EXTRACTION=false` by
  default) — enabling it triggers `unstructured`'s hi_res layout model, which
  downloads from huggingface.co on first use unless pre-cached via
  `scripts/warm_models.py` (run automatically at `docker build` time). Without
  that pre-caching, enabling this in a network-restricted deployment will fail
  at request time rather than at build time.
- **OpenTelemetry itself isn't wired up** — structured logs + an in-memory
  metrics aggregator stand in for it; the fields already match what OTel
  spans would carry, so adding real OTel exporters later is additive, not
  a rewrite.
- **BM25 keyword index is in-memory** and rebuilt lazily; fine at hackathon
  scale, would move to a real search backend at production scale.
- **The cross-encoder reranker's default grounding threshold
  (`MIN_GROUNDING_SCORE=0.5`) is a principled default, not an empirically
  tuned one** — 0.5 is the model's natural decision boundary once its raw
  score is passed through a sigmoid, but it hasn't been validated against
  real query/document pairs (the model couldn't be downloaded in the
  sandboxed environment this was built in — no huggingface.co egress there).
  Validate it against your own documents, ideally as part of an evaluation
  suite, before relying on it in a demo.
- The Groq call and the `sentence-transformers`/cross-encoder model downloads
  were not exercised against live networks during this build (sandboxed
  environment) — verify both once running locally with a real `GROQ_API_KEY`
  and internet access. `docker build` should complete the model downloads
  ahead of time via `scripts/warm_models.py`; if that step fails, the app
  will still run but will fall back to a live download on first request.

## Future improvements

- Redis for real multi-process caching; Postgres for document metadata
- Parent-child context expansion (section/neighbor context around a
  retrieved chunk) — the `section` metadata needed for this is already
  captured at extraction time, just not yet used for expansion
- MMR for result diversity after reranking
- Gated multi-query retrieval for complex/multi-part questions
- An evaluation suite (Recall@K, MRR, faithfulness) to validate retrieval
  and grounding-threshold choices with real measurements
- Real OpenTelemetry exporters (OTLP endpoint is already configurable)
- Conversation history / multi-turn context
- PDF inline preview in the source modal
