"""List prices per million tokens, with sources and the date each was read.

Decision APIs bill input tokens only. The Own build also pays for output (including reasoning)
and gets cached-input discounts. Unknown prices stay ``None`` so cost reports say "unknown"
rather than guessing.
"""

from __future__ import annotations

from dataclasses import dataclass

from bakeoff.systemone import Usage


@dataclass(frozen=True, slots=True)
class Price:
    input_per_m: float | None
    output_per_m: float | None = 0.0
    cached_input_per_m: float | None = None
    long_context_threshold: int | None = None  # input tokens above which the long tier applies
    long_input_per_m: float | None = None
    long_output_per_m: float | None = None
    source: str = ""
    read_on: str = "2026-10-06"
    long_cached_input_per_m: float | None = None


PRICES: dict[str, Price] = {
    "Microsoft-Decision-1": Price(
        0.042,
        0.0,
        source="https://commandline.microsoft.com/microsoft-decision-1-model-foundry/",
        read_on="2026-10-10",
    ),
    "jev-1.13.0": Price(0.042, 0.0, source="https://docs.typesafe.ai/models"),
    "clef": Price(0.24, 0.0, source="https://developers.cloudflare.com/workers-ai/models/clef/"),
    "clef-flash": Price(
        0.09, 0.0, source="https://developers.cloudflare.com/workers-ai/models/clef-flash/"
    ),
    "d1": Price(0.04, 0.0, source="https://www.liquid.ai/blog/d1-decision-model (methodology)"),
    "d1:free": Price(0.0, 0.0, source="docs.liquid.ai: text-only free tier"),
    "openai-decisions/gpt-6-luna": Price(
        0.10,
        0.0,
        cached_input_per_m=0.0,
        long_context_threshold=272_000,
        long_input_per_m=0.20,
        source="https://developers.openai.com/api/docs/guides/decisions",
        read_on="2026-10-12",
    ),
    "gpt-6-luna": Price(
        0.10,
        0.50,
        cached_input_per_m=0.01,
        long_context_threshold=272_000,
        long_input_per_m=0.20,
        long_output_per_m=0.75,
        long_cached_input_per_m=0.02,
        source="OpenAI pricing and docs.github.com Copilot models-and-pricing (same list rates)",
        read_on="2026-10-12",
    ),
    "gpt-5.4-mini": Price(None, None, source="unverified; fill from the OpenAI pricing page"),
}


def cost_usd(price_key: str | None, usage: Usage) -> float | None:
    """Cost of one request from reported usage. None when the price or usage is unknown."""
    if price_key is None or price_key not in PRICES:
        return None
    price = PRICES[price_key]
    if price.input_per_m is None or usage.input_tokens is None:
        return None
    input_tokens = usage.input_tokens
    cached = usage.cached_tokens or 0
    output = usage.output_tokens or 0
    in_rate, out_rate = price.input_per_m, price.output_per_m
    cached_rate = price.cached_input_per_m
    if price.long_context_threshold is not None and input_tokens > price.long_context_threshold:
        in_rate = price.long_input_per_m if price.long_input_per_m is not None else in_rate
        out_rate = price.long_output_per_m if price.long_output_per_m is not None else out_rate
        if price.long_cached_input_per_m is not None:
            cached_rate = price.long_cached_input_per_m
    if out_rate is None:
        return None
    uncached = max(0, input_tokens - cached)
    cached_rate = cached_rate if cached_rate is not None else in_rate
    return (uncached * in_rate + cached * cached_rate + output * out_rate) / 1_000_000
