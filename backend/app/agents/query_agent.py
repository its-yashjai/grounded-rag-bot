"""Query Understanding Agent — deterministic normalization only (no LLM call)
to keep latency and cost down, per the lean-MVP scoping. A query-expansion
LLM call could be added here later without changing callers."""
import re


def normalize_query(raw_query: str) -> str:
    q = raw_query.strip()
    q = re.sub(r"\s+", " ", q)
    return q
