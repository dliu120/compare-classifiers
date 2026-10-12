"""Liquid d1 and d1:free: System One with top-level images; d1:free is text only.

Facts (docs.liquid.ai, read 2026-10-06): up to 8 JPEG/PNG/WebP/GIF images as data URLs with the
body under 4.5 MB; context undocumented; usage.output_tokens is 0 and every Question is billed
as its own prompt including all images; $0.04 per M input for d1, d1:free is free.
"""

from __future__ import annotations

import httpx

from bakeoff.config import Settings
from bakeoff.providers.base import Provider
from bakeoff.providers.spec import require_credential, select_model
from bakeoff.providers.systemone_http import SystemOneProvider

URL = "https://api.liquid.ai/decisions/v1/systemone"
ENV_VAR = "LIQUID_API_KEY"
DEFAULT_MODEL = "d1"
MODELS = {"d1": "d1", "d1:free": "d1:free"}
TEXT_ONLY_MODELS = frozenset({"d1:free"})


class LiquidProvider(SystemOneProvider):
    max_input_tokens = 65_536  # from d1's 422 error: 65,536 tokens or 250 KB per question
    concurrency = 4
    url = URL

    def __init__(
        self, api_key: str, model: str = DEFAULT_MODEL, *, client: httpx.AsyncClient | None = None
    ) -> None:
        super().__init__(api_key, client=client)
        self.id = f"liquid/{model}"
        self.model = model
        self.price_key = model
        self.supports_images = model not in TEXT_ONLY_MODELS


def build(spec: str, settings: Settings) -> Provider:
    model = select_model(spec, "liquid", MODELS, default=DEFAULT_MODEL)
    api_key = require_credential(settings.liquid_api_key, ENV_VAR, spec)
    return LiquidProvider(api_key, model)


__all__ = [
    "DEFAULT_MODEL",
    "ENV_VAR",
    "MODELS",
    "TEXT_ONLY_MODELS",
    "URL",
    "LiquidProvider",
    "build",
]
