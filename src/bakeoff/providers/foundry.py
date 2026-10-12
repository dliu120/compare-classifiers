from __future__ import annotations

import asyncio
import time
from urllib.parse import urlsplit

import httpx

from bakeoff.config import Settings
from bakeoff.providers import parse_spec
from bakeoff.providers.base import Provider, ProviderResult
from bakeoff.providers.spec import require_credential
from bakeoff.providers.systemone_http import SystemOneProvider
from bakeoff.systemone import SystemOneRequest

MODEL = "Microsoft-Decision-1"
ROUTE = "/providers/microsoft/v1/systemone"


class FoundryProvider(SystemOneProvider):
    supports_images = False
    max_input_tokens = 32_768
    concurrency = 1
    price_key = MODEL

    def __init__(
        self,
        endpoint: str,
        access_token: str,
        deployment: str,
        requests_per_minute: int = 30,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme != "https"
            or not (parsed.hostname or "").endswith(".services.ai.azure.com")
            or parsed.port not in (None, 443)
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("FOUNDRY_ENDPOINT must be an HTTPS Foundry resource base URL")
        if requests_per_minute < 1:
            raise ValueError("FOUNDRY_REQUESTS_PER_MINUTE must be positive")
        if not deployment or "/" in deployment or "?" in deployment:
            raise ValueError("FOUNDRY_DEPLOYMENT_NAME must be one non-empty deployment name")
        super().__init__(access_token, client=client)
        self.id = f"foundry/{deployment}"
        self.model = deployment
        self.url = endpoint.rstrip("/") + ROUTE
        self._interval_s = 60.0 / requests_per_minute
        self._next_start = 0.0
        self._start_lock = asyncio.Lock()

    async def evaluate(self, request: SystemOneRequest) -> ProviderResult:
        if not request.images:
            async with self._start_lock:
                await asyncio.sleep(max(0.0, self._next_start - time.monotonic()))
                self._next_start = time.monotonic() + self._interval_s
        return await super().evaluate(request)


def build(spec: str, settings: Settings) -> Provider:
    family, path, query = parse_spec(spec)
    if family != "foundry" or len(path) > 1 or query:
        raise ValueError(f"a foundry spec is foundry[/<deployment>] without a query: {spec!r}")
    endpoint = require_credential(settings.foundry_endpoint, "FOUNDRY_ENDPOINT", spec)
    token = require_credential(settings.foundry_access_token, "FOUNDRY_ACCESS_TOKEN", spec)
    deployment = path[0] if path else settings.foundry_deployment_name
    return FoundryProvider(endpoint, token, deployment, settings.foundry_requests_per_minute)
