"""
The only place in the codebase that talks to Groq directly. Verified against
groq-python 1.6.0's actual `AsyncGroq` client (chat.completions.create with
stream=True yields ChatCompletionChunk objects; token usage arrives on the
final chunk's `.x_groq.usage` / `.usage` field) — inspected live rather than
assumed, since SDK shapes change between versions.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from groq import AsyncGroq

from app.services.llm.base import LLMChunk, LLMProvider


class GroqProvider(LLMProvider):
    def __init__(
        self, api_key: str, model: str, fast_model: str | None = None,
        timeout_s: float = 30.0, max_retries: int = 2,
    ):
        self.model = model
        self.fast_model = fast_model
        self.max_retries = max_retries
        self._client = AsyncGroq(api_key=api_key, timeout=timeout_s, max_retries=0)

    async def stream_chat(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.2,
        max_tokens: int = 1024, fast: bool = False,
    ) -> AsyncIterator[LLMChunk]:
        chosen_model = self.fast_model if (fast and self.fast_model) else self.model
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                stream = await self._client.chat.completions.create(
                    model=chosen_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_completion_tokens=max_tokens,
                    stream=True,
                )
                async for event in stream:
                    choice = event.choices[0] if event.choices else None
                    delta_text = choice.delta.content if choice and choice.delta else None
                    usage = getattr(event, "x_groq", None)
                    usage = getattr(usage, "usage", None) if usage else getattr(event, "usage", None)

                    if delta_text:
                        yield LLMChunk(delta=delta_text)

                    if choice and choice.finish_reason:
                        yield LLMChunk(
                            delta="",
                            finished=True,
                            input_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
                            output_tokens=getattr(usage, "completion_tokens", None) if usage else None,
                        )
                return  # success — stop retry loop
            except Exception as e:  # noqa: BLE001 — deliberately broad: network/API errors, retried uniformly
                last_error = e
                msg = str(e)
                # Handle rate limits with longer backoff (Groq suggests 5-6s)
                is_rate_limit = "429" in msg or "rate_limit" in msg.lower() or "Rate limit" in msg
                if attempt < self.max_retries:
                    delay = 6.0 if is_rate_limit else 0.5 * (2 ** attempt)
                    # Try to parse retry-after from message e.g. "Please try again in 5.4375s"
                    import re
                    m = re.search(r"try again in ([\d.]+)s", msg)
                    if m:
                        try:
                            delay = float(m.group(1)) + 0.5
                        except: pass
                    await asyncio.sleep(delay)
                    continue
                raise RuntimeError(f"Groq request failed after retries: {e}") from last_error
