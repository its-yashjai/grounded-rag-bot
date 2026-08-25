"""Turns token counts into an estimated dollar cost using configurable
per-million-token pricing. Never hardcodes pricing outside of settings."""
from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings


@dataclass
class CostEstimate:
    input_tokens: int
    output_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    model: str = ""

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def total_cost_usd(self) -> float:
        return round(self.input_cost_usd + self.output_cost_usd, 6)


class CostService:
    """Token counts -> dollar estimate. Pricing is per model tier so routed
    requests (fast model) are billed at their real rate, not the main one."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def estimate(self, input_tokens: int, output_tokens: int, tier: str = "main") -> CostEstimate:
        if tier == "fast":
            in_rate = self.settings.groq_fast_input_cost_per_million
            out_rate = self.settings.groq_fast_output_cost_per_million
            model = self.settings.groq_fast_model
        else:
            in_rate = self.settings.groq_input_cost_per_million
            out_rate = self.settings.groq_output_cost_per_million
            model = self.settings.groq_model
        input_cost = (input_tokens / 1_000_000) * in_rate
        output_cost = (output_tokens / 1_000_000) * out_rate
        return CostEstimate(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_cost_usd=round(input_cost, 6),
            output_cost_usd=round(output_cost, 6),
            model=model,
        )
