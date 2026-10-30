from __future__ import annotations

import math
from typing import Any

import httpx

from bakeoff.config import Settings
from bakeoff.http import HttpResult
from bakeoff.providers.base import Provider, ProviderResult
from bakeoff.providers.spec import require_credential, select_model
from bakeoff.providers.systemone_http import SystemOneProvider
from bakeoff.systemone import SystemOneRequest

URL = "https://api.liquid.ai/decisions/v1/systemone"
ENV_VAR = "LIQUID_API_KEY"
DEFAULT_MODEL = "d1"
MODELS = {"d1": "d1", "d1.1": "d1.1", "d1:free": "d1:free"}
TEXT_ONLY_MODELS = frozenset({"d1:free"})


class LiquidProvider(SystemOneProvider):
    max_input_tokens = 65_536
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

    def _result(
        self, request: SystemOneRequest, request_raw: Any, sent: HttpResult
    ) -> ProviderResult:
        result = super()._result(request, request_raw, sent)
        if self.model != "d1.1":
            return result
        usage = sent.data.get("usage") if isinstance(sent.data, dict) else None
        reported_cost = usage.get("cost") if isinstance(usage, dict) else None
        if isinstance(reported_cost, (int, float)) and not isinstance(reported_cost, bool):
            try:
                cost = float(reported_cost)
            except OverflowError:
                return result
            if math.isfinite(cost) and cost >= 0:
                result.cost_usd = cost
        return result


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
