"""
Central configuration. All tunables come from environment variables so the
system can be reconfigured without code changes (see .env.example).
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_name: str = "domain-knowledge-bot"

    # LLM (Groq)
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_timeout_s: float = 30.0
    groq_max_retries: int = 2

    # Cost routing: simple grounded lookups go to the fast/cheap model,
    # complex synthesis stays on the main model. Routing itself is a
    # deterministic heuristic — no extra LLM call, no added latency.
    enable_model_routing: bool = True
    groq_fast_model: str = "openai/gpt-oss-20b"

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"

    # Chunking
    chunk_size: int = 800
    chunk_overlap: int = 120

    # Table structure extraction (unstructured "hi_res" path). Off by
    # default: enabling it downloads a layout-detection model from
    # huggingface.co on first use, which fails at request time in network-
    # restricted deployments unless the model is pre-cached into the image
    # at build time. Turn on only if the deployment env has that egress
    # (or the model is pre-baked) and table-heavy documents are expected.
    enable_table_extraction: bool = False

    # Retrieval
    top_k: int = 40  # candidate pool per retrieval leg, before RRF fusion
    rerank_top_k: int = 8  # chunks kept after reranking, sent to the LLM
    max_context_tokens: int = 5000

    # Reranking. Downloads a model from Hugging Face on first use unless
    # pre-cached (see scripts/warm_models.py, run at Docker build time).
    # Falls back to plain RRF-score reranking when disabled.
    enable_cross_encoder_reranker: bool = True
    min_grounding_score: float = 0.5  # see answer_agent.MIN_GROUNDING_SCORE_RELEVANCE

    # Cache
    enable_response_cache: bool = True
    enable_retrieval_cache: bool = True
    enable_embedding_cache: bool = True
    cache_ttl: int = 600

    # Storage
    chroma_persist_dir: str = "./data/chroma"
    upload_dir: str = "./data/uploads"
    max_file_size_mb: int = 25

    # Cost (per-model pricing, USD per 1M tokens; kept configurable, never hardcoded silently)
    groq_input_cost_per_million: float = 0.15
    groq_output_cost_per_million: float = 0.60
    groq_fast_input_cost_per_million: float = 0.075
    groq_fast_output_cost_per_million: float = 0.30


@lru_cache
def get_settings() -> Settings:
    return Settings()
