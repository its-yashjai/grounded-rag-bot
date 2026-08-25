"""LLMProvider interface — the rest of the app only depends on this, never on
a specific SDK, so swapping Groq for another provider means writing one new
class here."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass
class LLMChunk:
    delta: str
    finished: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMProvider(ABC):
    @abstractmethod
    async def stream_chat(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.2,
        max_tokens: int = 1024, fast: bool = False,
    ) -> AsyncIterator[LLMChunk]: ...
