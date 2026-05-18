"""
Central LLM gateway. All agents call this — never import anthropic SDK directly.

Priority:
  1. Anthropic (primary, budget-tracked)
  2. OpenRouter free models (fallback when budget exhausted or ANTHROPIC_API_KEY unset)

Tracks cost, enforces per-engagement budget cap, caches system prompts.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import anthropic
import httpx

from app.config import settings

# Anthropic pricing per million tokens (input / output)
_ANTHROPIC_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-7":              (15.0, 75.0),
    "claude-sonnet-4-6":            (3.0,  15.0),
    "claude-haiku-4-5-20251001":    (0.8,   4.0),
}

# OpenRouter free-tier fallback models (no cost, rate-limited)
_OR_FREE: dict[str, str] = {
    "heavy": "deepseek/deepseek-r1-distill-qwen-32b:free",
    "mid":   "mistralai/mistral-small-3.1-24b-instruct:free",
    "light": "google/gemma-3-27b-it:free",
}

# Map Anthropic model IDs → tier for fallback selection
_ANTHROPIC_TIER: dict[str, str] = {
    "claude-opus-4-7":              "heavy",
    "claude-sonnet-4-6":            "mid",
    "claude-haiku-4-5-20251001":    "light",
}

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"


@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    provider: str = "anthropic"


@dataclass
class LLMRouter:
    engagement_id: str
    budget_usd: float
    _spent: float = 0.0
    _client: anthropic.Anthropic = field(init=False)

    def __post_init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def _cost(self, model: str, in_tok: int, out_tok: int) -> float:
        price_in, price_out = _ANTHROPIC_PRICING.get(model, (15.0, 75.0))
        return (in_tok * price_in + out_tok * price_out) / 1_000_000

    def _check_budget(self, estimated_cost: float = 0.0) -> None:
        if self._spent + estimated_cost > self.budget_usd:
            raise RuntimeError(
                f"Budget cap reached: spent ${self._spent:.4f} of ${self.budget_usd:.2f}"
            )

    def _or_model(self, anthropic_model: str) -> str:
        """Pick the best OpenRouter free model for a given Anthropic model tier."""
        tier = _ANTHROPIC_TIER.get(anthropic_model, "mid")
        # Allow override via settings: openrouter_model_heavy/mid/light
        override = getattr(settings, f"openrouter_model_{tier}", "")
        return override or _OR_FREE[tier]

    async def _complete_openrouter(
        self,
        anthropic_model: str,
        system: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        temperature: float,
    ) -> tuple[str, LLMUsage]:
        or_model = self._or_model(anthropic_model)
        or_messages = [{"role": "system", "content": system}, *messages]

        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"{_OPENROUTER_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "HTTP-Referer": "https://github.com/zwanski2019/ZWAN-CODEX-V2",
                    "X-Title": "ZWAN-CODEX",
                    "Content-Type": "application/json",
                },
                json={
                    "model": or_model,
                    "messages": or_messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            r.raise_for_status()
            data = r.json()

        content = data["choices"][0]["message"]["content"] or ""
        usage_raw = data.get("usage", {})
        in_tok = usage_raw.get("prompt_tokens", 0)
        out_tok = usage_raw.get("completion_tokens", 0)

        usage = LLMUsage(
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=0.0,  # free tier
            provider=f"openrouter:{or_model}",
        )
        return content, usage

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

        # ── Anthropic path ────────────────────────────────────────────────
        if settings.anthropic_api_key:
            try:
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

                usage = LLMUsage(
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cost_usd=cost,
                    provider="anthropic",
                )
                content = response.content[0].text if response.content else ""
                return content, usage

            except RuntimeError as exc:
                # Budget exhausted — try OpenRouter if available
                if settings.openrouter_api_key:
                    return await self._complete_openrouter(
                        model, system, messages, max_tokens, temperature
                    )
                raise

        # ── OpenRouter path (no Anthropic key set) ────────────────────────
        if settings.openrouter_api_key:
            return await self._complete_openrouter(
                model, system, messages, max_tokens, temperature
            )

        raise RuntimeError(
            "No LLM provider configured. Set ANTHROPIC_API_KEY or OPENROUTER_API_KEY."
        )

    @property
    def spent(self) -> float:
        return self._spent
