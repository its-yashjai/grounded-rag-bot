"""
Answer Agent (system prompt) + Guard Agent (pre-flight check before we even
call the LLM). The guard here is deterministic: if retrieval returned nothing
usable, we short-circuit with the fixed "not found" message instead of
spending a Groq call on a prompt with no grounding context — cheaper and
strictly avoids the model improvising when there's nothing to ground on.
"""

SYSTEM_PROMPT = """You are Domain Knowledge Bot.

You answer questions using only the supplied document context below.

Rules:
1. Never invent facts.
2. Never use outside knowledge when answering document questions.
3. If the context does not contain enough information, clearly say so.
4. Cite the document and page whenever possible using the [Source N] labels given.
5. Prefer concise answers.
6. If multiple documents support the answer, cite all relevant documents.
7. Distinguish between directly stated information and reasonable synthesis.
8. Never claim that something is in the document when it is not.

Document context:
{context}
"""

NOT_FOUND_MESSAGE = "I couldn't find enough information about that in the uploaded documents."

# Below this fused-score threshold, retrieved chunks are considered too weak
# to ground an answer on. This is the fallback used only when no reranker
# produced a real relevance_score (e.g. CrossEncoderReranker disabled) — RRF
# fused_score reflects rank position, not relevance, so this threshold is
# deliberately loose; it exists to catch the empty-corpus case more than to
# do meaningful filtering.
MIN_GROUNDING_SCORE_FUSED_FALLBACK = 0.01

# Default threshold on the sigmoid-calibrated cross-encoder relevance_score
# (0-1 scale; 0.5 = model finds the chunk more likely relevant to the query
# than not). This is a principled starting point, not an empirically tuned
# one — the cross-encoder model couldn't be downloaded and tested end-to-end
# in the environment these changes were made in (no Hugging Face egress
# there either). Validate this against real queries once deployed, ideally
# as part of the evaluation suite, and adjust via settings.min_grounding_score.
MIN_GROUNDING_SCORE_RELEVANCE = 0.5


def has_sufficient_grounding(chunks, min_relevance_score: float = MIN_GROUNDING_SCORE_RELEVANCE) -> bool:
    if not chunks:
        return False
    if chunks[0].relevance_score is not None:
        return any(
            c.relevance_score is not None and c.relevance_score >= min_relevance_score
            for c in chunks
        )
    return any(c.fused_score >= MIN_GROUNDING_SCORE_FUSED_FALLBACK for c in chunks)


def build_system_prompt(context_block: str) -> str:
    return SYSTEM_PROMPT.format(context=context_block)
