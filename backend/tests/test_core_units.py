from app.utils.hashing import sha256_text, sha256_bytes, new_id
from app.services.ingestion.chunker import chunk_pages
from app.services.ingestion.extractor import Block
from app.services.cache.cache_service import CacheService
from app.config import Settings
from app.services.cost.cost_service import CostService
from app.agents.router_agent import is_complex_query
from app.services.retrieval.retriever import RetrievedChunk
from app.services.retrieval.reranker import Reranker
from app.agents.answer_agent import has_sufficient_grounding


def test_sha256_text_deterministic():
    assert sha256_text("hello") == sha256_text("hello")
    assert sha256_text("hello") != sha256_text("world")


def test_sha256_bytes_deterministic():
    assert sha256_bytes(b"abc") == sha256_bytes(b"abc")


def test_new_id_unique():
    assert new_id("doc") != new_id("doc")
    assert new_id("doc").startswith("doc_")


def test_chunker_respects_paragraph_boundaries():
    blocks = [
        Block(page_number=1, text="Para one."),
        Block(page_number=1, text="Para two."),
        Block(page_number=1, text="Para three."),
    ]
    chunks = chunk_pages(blocks, chunk_size=800, chunk_overlap=50)
    assert len(chunks) == 1
    assert "Para one." in chunks[0].text
    assert "Para three." in chunks[0].text


def test_chunker_splits_when_over_budget():
    long_para = " ".join(["word"] * 50)
    blocks = [Block(page_number=1, text=long_para) for _ in range(3)]
    chunks = chunk_pages(blocks, chunk_size=60, chunk_overlap=10)
    assert len(chunks) > 1
    for c in chunks:
        assert c.page_number == 1


def test_chunker_preserves_page_numbers():
    blocks = [
        Block(page_number=1, text="First page content here."),
        Block(page_number=2, text="Second page content here."),
    ]
    chunks = chunk_pages(blocks, chunk_size=800, chunk_overlap=50)
    page_numbers = {c.page_number for c in chunks}
    assert 1 in page_numbers or 2 in page_numbers


def test_chunker_overlap_actually_carries_forward():
    # Regression test: overlap_text used to always be computed from an
    # already-cleared buffer (flush() reset it before the tail was taken),
    # so consecutive chunks never shared any text despite chunk_overlap > 0.
    # Distinctly-labeled tokens per block make the assertion unambiguous.
    b0 = " ".join(f"alpha{i}" for i in range(20))
    b1 = " ".join(f"beta{i}" for i in range(20))
    blocks = [Block(page_number=1, text=b0), Block(page_number=1, text=b1)]
    chunks = chunk_pages(blocks, chunk_size=40, chunk_overlap=10)
    assert len(chunks) == 2
    assert "alpha19" in chunks[0].text
    # the tail of chunk 0 must reappear at the start of chunk 1
    assert "alpha19" in chunks[1].text
    assert "beta0" in chunks[1].text
    assert "alpha0" not in chunks[1].text  # only the tail carried over, not all of block 0


def test_chunker_does_not_merge_across_sections():
    blocks = [
        Block(page_number=1, text="Annual leave is 20 days.", section="Leave Policy"),
        Block(page_number=1, text="Base salary is reviewed in April.", section="Salary Policy"),
    ]
    chunks = chunk_pages(blocks, chunk_size=800, chunk_overlap=50)
    assert len(chunks) == 2
    assert chunks[0].section == "Leave Policy"
    assert chunks[1].section == "Salary Policy"


def test_chunker_keeps_table_atomic():
    blocks = [
        Block(page_number=1, text="Some intro paragraph.", section="Revenue"),
        Block(page_number=1, text="Q1 | Q2 | Q3\n100 | 200 | 300", is_table=True, section="Revenue"),
        Block(page_number=1, text="Some closing paragraph.", section="Revenue"),
    ]
    chunks = chunk_pages(blocks, chunk_size=800, chunk_overlap=50)
    table_chunks = [c for c in chunks if c.is_table]
    assert len(table_chunks) == 1
    assert "Q1 | Q2 | Q3" in table_chunks[0].text
    # table text wasn't merged with the surrounding prose
    assert "intro paragraph" not in table_chunks[0].text


def test_cache_set_get_roundtrip():
    cache = CacheService(default_ttl_s=60)
    cache.set("key1", {"a": 1})
    assert cache.get("key1") == {"a": 1}


def test_cache_miss_returns_none():
    cache = CacheService(default_ttl_s=60)
    assert cache.get("missing") is None


def test_cache_expiry():
    cache = CacheService(default_ttl_s=0)
    cache.set("key1", "value", ttl_s=0)
    import time
    time.sleep(0.01)
    assert cache.get("key1") is None


def test_cache_hit_rate_tracking():
    cache = CacheService(default_ttl_s=60)
    cache.set("k", "v")
    cache.get("k")       # hit
    cache.get("missing")  # miss
    assert 0 < cache.hit_rate < 1


def test_cost_estimate_scales_with_tokens():
    settings = Settings(groq_input_cost_per_million=1.0, groq_output_cost_per_million=2.0)
    service = CostService(settings)
    estimate = service.estimate(input_tokens=1_000_000, output_tokens=1_000_000)
    assert estimate.input_cost_usd == 1.0
    assert estimate.output_cost_usd == 2.0
    assert estimate.total_cost_usd == 3.0


def test_cost_estimate_zero_tokens():
    settings = Settings()
    service = CostService(settings)
    estimate = service.estimate(0, 0)
    assert estimate.total_cost_usd == 0.0


def test_cost_estimate_fast_tier_uses_fast_pricing_and_model():
    settings = Settings(
        groq_input_cost_per_million=1.0, groq_output_cost_per_million=2.0,
        groq_fast_input_cost_per_million=0.05, groq_fast_output_cost_per_million=0.08,
        groq_model="main-model", groq_fast_model="fast-model",
    )
    service = CostService(settings)
    est = service.estimate(1_000_000, 1_000_000, tier="fast")
    assert est.input_cost_usd == 0.05
    assert est.output_cost_usd == 0.08
    assert est.model == "fast-model"
    main = service.estimate(1_000_000, 1_000_000, tier="main")
    assert main.model == "main-model"


def test_router_simple_lookup_goes_fast():
    assert not is_complex_query("What causes post-harvest losses?")
    assert not is_complex_query("When was the policy introduced?")
    assert not is_complex_query("How many storage facilities are listed?")


def test_router_complex_synthesis_stays_on_main():
    assert is_complex_query("Why did cold storage adoption remain low?")
    assert is_complex_query("Compare the two approaches and their trade-offs.")
    assert is_complex_query("Summarize the key findings across all documents.")


def test_router_long_or_multi_question_is_complex():
    long_q = " ".join(["word"] * 14) + "?"
    assert is_complex_query(long_q)
    assert is_complex_query("What is X? And how does it relate to Y?")


def test_reranker_scans_full_candidate_pool():
    # Regression test: the scan window used to be capped at top_k * 3, so
    # with a wide candidate pool (e.g. 40) and a small top_k (e.g. 8), most
    # candidates were silently dropped before ever being considered.
    chunks = [
        RetrievedChunk(chunk_id=f"c{i}", text=f"unique text number {i}",
                        metadata={}, fused_score=1.0 / (i + 1))
        for i in range(40)
    ]
    out = Reranker().rerank(chunks, top_k=8, max_context_tokens=100_000)
    assert len(out) == 8
    assert out[0].chunk_id == "c0"  # highest fused_score, still wins


def test_grounding_uses_relevance_score_when_present():
    grounded = [RetrievedChunk(chunk_id="a", text="t", metadata={}, relevance_score=0.9)]
    not_grounded = [RetrievedChunk(chunk_id="a", text="t", metadata={}, relevance_score=0.1)]
    assert has_sufficient_grounding(grounded) is True
    assert has_sufficient_grounding(not_grounded) is False


def test_grounding_falls_back_to_fused_score_without_reranker():
    # When no cross-encoder ran, relevance_score is None on every chunk and
    # the guard must fall back to the RRF-based threshold, not treat the
    # missing score as zero (which would refuse every answer).
    grounded = [RetrievedChunk(chunk_id="a", text="t", metadata={}, fused_score=0.02)]
    not_grounded = [RetrievedChunk(chunk_id="a", text="t", metadata={}, fused_score=0.001)]
    assert has_sufficient_grounding(grounded) is True
    assert has_sufficient_grounding(not_grounded) is False


def test_grounding_empty_chunks_refuses():
    assert has_sufficient_grounding([]) is False


def _fresh_reranker(monkeypatch, enabled: str):
    """Build the reranker the app would use, for a given setting value."""
    from app import deps
    from app.config import get_settings

    monkeypatch.setenv("ENABLE_CROSS_ENCODER_RERANKER", enabled)
    get_settings.cache_clear()
    deps.get_reranker.cache_clear()
    try:
        return deps.get_reranker()
    finally:
        get_settings.cache_clear()
        deps.get_reranker.cache_clear()


def test_cross_encoder_reranker_is_used_when_enabled(monkeypatch):
    # Regression test: get_reranker() used to return the plain Reranker in
    # both branches, so the cross-encoder never ran even when enabled.
    # The model itself loads lazily, so this does not download anything.
    from app.services.retrieval.reranker import CrossEncoderReranker

    assert isinstance(_fresh_reranker(monkeypatch, "true"), CrossEncoderReranker)


def test_plain_reranker_is_used_when_cross_encoder_disabled(monkeypatch):
    from app.services.retrieval.reranker import CrossEncoderReranker

    reranker = _fresh_reranker(monkeypatch, "false")
    assert isinstance(reranker, Reranker)
    assert not isinstance(reranker, CrossEncoderReranker)
