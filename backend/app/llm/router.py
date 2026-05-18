"""
Central LLM gateway. All agents call this — never import anthropic SDK directly.
Tracks cost, enforces per-engagement budget cap, caches system prompts.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import anthropic

from app.config import settings

# Pricing per million tokens (input/output) — update when Anthropic reprices
_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-7":              (15.0, 75.0),
    "claude-sonnet-4-6":            (3.0,  15.0),
    "claude-haiku-4-5-20251001":    (0.8,  4.0),
}


@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class LLMRouter:
    engagement_id: str
    budget_usd: float
    _spent: float = 0.0
    _client: anthropic.Anthropic = field(init=False)

    def __post_init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def _cost(self, model: str, in_tok: int, out_tok: int) -> float:
        price_in, price_out = _PRICING.get(model, (15.0, 75.0))
        return (in_tok * price_in + out_tok * price_out) / 1_000_000

    def _check_budget(self, estimated_cost: float = 0.0) -> None:
        if self._spent + estimated_cost > self.budget_usd:
            raise RuntimeError(
                f"Budget cap reached: spent ${self._spent:.4f} of ${self.budget_usd:.2f}"
            )

    async def complete(
        self,
        *,
        model: str | None = None,
        system: str,
        messages: list[dict[str, Any]],
        max_tokens: int = 4096,
        temperature: float = 0.2,
        use_cache: bool = True,
    ) -> tuple[str, LLMUsage]:
        model = model or settings.llm_mid
        self._check_budget()

        sys_block: list[dict] = [{"type": "text", "text": system}]
        if use_cache:
            sys_block[0]["cache_control"] = {"type": "ephemeral"}

        response = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=sys_block,  # type: ignore[arg-type]
            messages=messages,
        )

        in_tok = response.usage.input_tokens
        out_tok = response.usage.output_tokens
        cost = self._cost(model, in_tok, out_tok)
        self._spent += cost

        usage = LLMUsage(input_tokens=in_tok, output_tokens=out_tok, cost_usd=cost)
        content = response.content[0].text if response.content else ""
        return content, usage

    @property
    def spent(self) -> float:
        return self._spent
