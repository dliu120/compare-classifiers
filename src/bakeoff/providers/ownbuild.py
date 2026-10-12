"""Own build adapter: ``ownbuild/<route>/<model>?effort=&cap=&max_in=&mode=&samples=&via=``.

The engine runs in-process by default. ``via=<http base>`` sends the System One request to a
running Own build server (bakeoff.ownbuild.server) at ``<base>/v1/systemone`` instead.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from pydantic import ValidationError

from bakeoff import budget
from bakeoff.config import Settings
from bakeoff.http import DEFAULT_TIMEOUT, elide_images, make_client, post_json
from bakeoff.ownbuild.config import OwnBuildConfig, price_key_for
from bakeoff.ownbuild.engine import OwnBuildEngine
from bakeoff.providers.base import Provider, ProviderResult
from bakeoff.providers.transport import MAX_ATTEMPTS, transport_non_answer
from bakeoff.systemone import SystemOneRequest, SystemOneResponse

CONCURRENCY = {"copilot": 2, "openai": 8}  # docs/adr/0002: the Copilot Route runs at modest scale


def build(spec: str, settings: Settings) -> Provider:
    config, extra = OwnBuildConfig.from_spec(spec)
    via = extra.pop("via", "") or None
    if extra:
        raise ValueError(f"unknown ownbuild spec keys {sorted(extra)} in {spec!r}")
    return OwnBuildProvider(config, settings, via=via)


def server_base(via: str) -> str:
    """Normalize a ``via`` base so that ``<base>/v1/systemone`` is the endpoint."""
    base = via.rstrip("/")
    return base.removesuffix("/v1")


class OwnBuildProvider(Provider):
    supports_images = True

    def __init__(
        self,
        config: OwnBuildConfig,
        settings: Settings,
        *,
        via: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self.via = server_base(via) if via else None
        self.id = config.spec if self.via is None else f"{config.spec}&via={self.via}"
        self.model = config.model
        self.price_key = price_key_for(config.model)
        # No input limit is documented for GPT-6 Luna on either Route: max_in is the only cap.
        self.max_input_tokens = config.max_in
        self.concurrency = CONCURRENCY[config.route]
        self._engine: OwnBuildEngine | None = None
        self._client: httpx.AsyncClient | None = None
        if self.via is None:
            self._engine = OwnBuildEngine(config, settings, client)
        else:
            self._client = client if client is not None else make_client()
        self._owns_client = client is None

    def estimate_cost_usd(self, approx_tokens: int | None) -> float:
        """What one request may cost, reserved against the budget before it is sent: ``samples``
        calls of the State's tokens in and up to the output cap out."""
        return budget.estimate_cost_usd(
            self.price_key, approx_tokens, self.config.cap or 0, self.config.samples
        )

    async def _call(self, request: SystemOneRequest) -> ProviderResult:
        if self._engine is not None:
            result = await self._engine.evaluate(request)
            result.provider_id = self.id
            return result
        return await self._call_server(request)

    async def _call_server(self, request: SystemOneRequest) -> ProviderResult:
        assert self._client is not None
        body: dict[str, Any] = request.model_dump(mode="json", exclude_none=True)
        request_raw = {**elide_images(body), "meta": {"via": self.via}}
        started = time.perf_counter()
        try:
            result = await post_json(
                self._client,
                f"{self.via}/v1/systemone",
                json=body,
                max_attempts=MAX_ATTEMPTS,
                timeout=DEFAULT_TIMEOUT,
            )
        except httpx.TransportError as exc:
            return transport_non_answer(
                self, request, exc, latency_s=time.perf_counter() - started, request_raw=request_raw
            )
        try:
            response = SystemOneResponse.model_validate(result.data)
        except ValidationError as exc:
            return self.non_answer(
                request,
                "invalid_output",
                f"not a System One response: {exc.errors()[0]['msg']}",
                latency_s=result.latency_s,
                http_status=result.status,
                request_raw=request_raw,
                response_raw=result.data,
                attempts=result.attempts,
            )
        return ProviderResult(
            provider_id=self.id,
            response=response,
            http_status=result.status,
            latency_s=result.latency_s,
            attempts=result.attempts,
            request_raw=request_raw,
            response_raw=result.data,
        )

    async def aclose(self) -> None:
        if self._engine is not None:
            await self._engine.aclose()
        if self._client is not None and self._owns_client:
            await self._client.aclose()
