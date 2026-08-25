"""
Chat endpoint. Flow: normalize query -> check response cache -> hybrid
retrieve -> rerank -> guard (sufficient grounding?) -> build prompt -> stream
from Groq -> emit citations -> record metrics. Streamed as Server-Sent Events
so the frontend can render tokens incrementally instead of waiting for the
full answer.
"""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.agents.answer_agent import build_system_prompt, has_sufficient_grounding, NOT_FOUND_MESSAGE
from app.agents.query_agent import normalize_query
from app.agents.router_agent import is_complex_query
from app.config import Settings, get_settings
from app.deps import (
    get_cache,
    get_cost_service,
    get_doc_repo,
    get_llm_provider,
    get_reranker,
    get_retriever,
)
from app.repositories.conversations import ConversationRepository, get_conversation_repository
from app.repositories.documents import DocumentRepository
from app.schemas.api import ChatRequest
from app.services.citations.citation_service import build_citations, build_context_block
from app.services.cost.cost_service import CostService
from app.services.llm.base import LLMProvider
from app.services.observability.metrics_service import RequestLog, get_metrics_service
from app.services.retrieval.reranker import Reranker
from app.services.retrieval.retriever import HybridRetriever
from app.utils.hashing import new_id, sha256_text
from app.utils.tokens import count_tokens

router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/stream", summary="Ask a grounded question and stream the answer")
async def chat_stream(
    payload: ChatRequest,
    settings: Settings = Depends(get_settings),
    retriever: HybridRetriever = Depends(get_retriever),
    reranker: Reranker = Depends(get_reranker),
    llm: LLMProvider = Depends(get_llm_provider),
    cost_service: CostService = Depends(get_cost_service),
    doc_repo: DocumentRepository = Depends(get_doc_repo),
    conversations: ConversationRepository = Depends(get_conversation_repository),
):
    request_id = new_id("req")
    start = time.perf_counter()
    query = normalize_query(payload.message)
    # Cost routing: deterministic heuristic picks the cheap model for simple
    # grounded lookups, keeps the 70B for complex synthesis. No extra call.
    use_fast_model = settings.enable_model_routing and not is_complex_query(query)
    cost_tier = "fast" if use_fast_model else "main"
    metrics = get_metrics_service()
    cache = get_cache(settings)

    conversation_id = payload.conversation_id
    if conversation_id and not conversations.get(conversation_id):
        conversation_id = None  # stale id from a cleared store — start fresh
    if not conversation_id:
        conv = conversations.create(title=query)
        conversation_id = conv["conversation_id"]
    conversations.append_message(conversation_id, {"role": "user", "content": query})

    kb_version = doc_repo.kb_version
    cache_key = f"response:{kb_version}:{sha256_text(query + str(payload.document_ids))}"

    async def event_stream():
        cache_hit = False
        yield _sse("conversation", {"conversation_id": conversation_id})

        if settings.enable_response_cache:
            cached = cache.get(cache_key)
            if cached is not None:
                cache_hit = True
                yield _sse("citations", {"citations": cached["citations"]})
                yield _sse("token", {"delta": cached["answer"]})
                latency_ms = round((time.perf_counter() - start) * 1000, 1)
                metrics.record_request(RequestLog(
                    request_id=request_id, question=query, latency_ms=latency_ms,
                    input_tokens=0, output_tokens=0, estimated_cost_usd=0.0,
                    cache_hit=True, retrieved_chunks=0, reranked_chunks=len(cached["citations"]),
                ))
                conversations.append_message(conversation_id, {
                    "role": "assistant", "content": cached["answer"],
                    "citations": cached["citations"], "cache_hit": True,
                    "input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": 0.0,
                    "latency_ms": latency_ms, "model": "",
                })
                yield _sse("done", {
                    "request_id": request_id, "latency_ms": latency_ms, "cache_hit": True,
                    "input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": 0.0,
                    "model": "", "conversation_id": conversation_id,
                })
                return

        retrieved = retriever.retrieve(query, top_k=settings.top_k, document_ids=payload.document_ids)
        reranked = reranker.rerank(
            retrieved, top_k=settings.rerank_top_k,
            max_context_tokens=settings.max_context_tokens, query=query,
        )

        if not has_sufficient_grounding(reranked, min_relevance_score=settings.min_grounding_score):
            yield _sse("token", {"delta": NOT_FOUND_MESSAGE})
            latency_ms = round((time.perf_counter() - start) * 1000, 1)
            metrics.record_request(RequestLog(
                request_id=request_id, question=query, latency_ms=latency_ms,
                input_tokens=0, output_tokens=0, estimated_cost_usd=0.0,
                cache_hit=False, retrieved_chunks=len(retrieved), reranked_chunks=0,
            ))
            conversations.append_message(conversation_id, {
                "role": "assistant", "content": NOT_FOUND_MESSAGE,
                "citations": [], "cache_hit": False,
                "input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": 0.0,
                "latency_ms": latency_ms, "model": "",
            })
            yield _sse("done", {
                "request_id": request_id, "latency_ms": latency_ms, "cache_hit": False,
                "input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": 0.0,
                "model": "", "conversation_id": conversation_id,
            })
            return

        context_block = build_context_block(reranked)
        citations = build_citations(reranked)
        system_prompt = build_system_prompt(context_block)

        yield _sse("citations", {"citations": citations})

        full_answer = ""
        input_tokens = count_tokens(system_prompt + query)
        output_tokens = 0

        try:
            async for chunk in llm.stream_chat(system_prompt=system_prompt, user_prompt=query, fast=use_fast_model):
                if chunk.delta:
                    full_answer += chunk.delta
                    yield _sse("token", {"delta": chunk.delta})
                if chunk.finished:
                    input_tokens = chunk.input_tokens or input_tokens
                    output_tokens = chunk.output_tokens or count_tokens(full_answer)
        except Exception as e:
            # Graceful fallback for UI — ensures frontend always gets token + done, even without GROQ key
            # Distinguish rate limit vs missing key for clearer UX
            print(f"[chat] LLM stream failed: {e}")
            msg = str(e)
            if "429" in msg or "rate_limit" in msg.lower():
                fallback = "Rate limit reached for the language model (Groq TPM limit). Please wait ~6 seconds and try again — your documents were retrieved successfully with sources visible below."
            elif "Bearer" in msg or "api_key" in msg.lower() or "invalid" in msg.lower():
                fallback = "The language model is temporarily unavailable (missing or invalid GROQ_API_KEY). Your documents were retrieved successfully — please configure GROQ_API_KEY to get grounded answers."
            else:
                fallback = "The language model is temporarily unavailable. Your documents were retrieved successfully — please try again in a moment."
            if not full_answer:
                full_answer = fallback
                yield _sse("token", {"delta": fallback})

        if settings.enable_response_cache and full_answer:
            cache.set(cache_key, {"answer": full_answer, "citations": citations}, ttl_s=settings.cache_ttl)

        cost = cost_service.estimate(input_tokens, output_tokens, tier=cost_tier)
        latency_ms = round((time.perf_counter() - start) * 1000, 1)

        metrics.record_request(RequestLog(
            request_id=request_id, question=query, latency_ms=latency_ms,
            input_tokens=input_tokens, output_tokens=output_tokens,
            estimated_cost_usd=cost.total_cost_usd, cache_hit=cache_hit,
            retrieved_chunks=len(retrieved), reranked_chunks=len(reranked),
            model=cost.model,
        ))

        conversations.append_message(conversation_id, {
            "role": "assistant", "content": full_answer,
            "citations": citations, "cache_hit": cache_hit,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "estimated_cost_usd": cost.total_cost_usd,
            "latency_ms": latency_ms, "model": cost.model,
        })

        yield _sse("done", {
            "request_id": request_id, "latency_ms": latency_ms, "cache_hit": cache_hit,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "estimated_cost_usd": cost.total_cost_usd, "model": cost.model,
            "conversation_id": conversation_id,
        })

    return StreamingResponse(event_stream(), media_type="text/event-stream")
