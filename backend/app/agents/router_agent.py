"""Query Complexity Router — deterministic, zero-cost model routing.

Grounded QA over supplied context is mostly an extraction task, which small
instruct models handle nearly as well as large ones — the retrieved context
does the heavy lifting. Complex synthesis (comparisons, causal "why",
multi-part questions) benefits from the 70B. Routing on a regex heuristic
instead of an LLM classifier keeps this free and adds no latency.

Tier economics (per 1M tokens):
  main: llama-3.3-70b-versatile  $0.59 in / $0.79 out
  fast: llama-3.1-8b-instant     $0.05 in / $0.08 out   (~12x cheaper)
"""
import re

_COMPLEX_SIGNALS = re.compile(
    r"\b("
    r"why|explain|compare|contrast|analyz\w*|summar\w*|evaluate|assess"
    r"|implications?|trade-?offs?|pros and cons|elaborate|walk me through"
    r"|how do(es)?|how would|what happens if|relationship between"
    r")\b",
    re.IGNORECASE,
)

# At or above this word count, treat the question as multi-part/synthesis.
COMPLEX_WORD_THRESHOLD = 14


def is_complex_query(query: str) -> bool:
    """True -> use the main (70B) model; False -> fast (8B) model."""
    q = query.strip()
    if not q:
        return False
    if _COMPLEX_SIGNALS.search(q):
        return True
    # Multiple distinct questions imply synthesis across topics.
    if q.count("?") > 1:
        return True
    return len(q.split()) >= COMPLEX_WORD_THRESHOLD
