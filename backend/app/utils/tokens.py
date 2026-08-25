"""Approximate token counting. Uses tiktoken's cl100k encoding as a stand-in —
it doesn't exactly match Llama's tokenizer but is close enough for budgeting
context windows and estimating cost without adding a heavy dependency."""
import tiktoken

_enc = None


def _encoder():
    global _enc
    if _enc is None:
        _enc = tiktoken.get_encoding("cl100k_base")
    return _enc


def count_tokens(text: str) -> int:
    if not text:
        return 0
    try:
        return len(_encoder().encode(text))
    except Exception:
        # Fallback: rough heuristic (~4 chars/token) if tiktoken assets are unavailable
        return max(1, len(text) // 4)
