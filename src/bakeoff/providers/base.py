"""Provider: one endpoint plus one model that answers System One requests.

Every failure becomes a Non-answer in the returned response (docs/adr/0003); ``evaluate``
never raises. Subclasses implement ``_call`` and set the class attributes.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

import httpx
from pydantic import BaseModel

from bakeoff import pricing
from bakeoff.http import HttpError
from bakeoff.systemone import NonAnswer, NonAnswerCause, SystemOneRequest, SystemOneResponse


class ProviderResult(BaseModel):
    provider_id: str
    response: SystemOneResponse | None = None
    http_status: int | None = None
    latency_s: float
    attempts: int = 1
    error: str | None = None
    request_raw: Any = (
        None  # body as sent, auth stripped, images elided (bakeoff.http.elide_images)
    )
    response_raw: Any = None  # body as returned
    cost_usd: float | None = None


class Provider(ABC):
    id: str = "abstract"
    model: str = "abstract"
    supports_images: bool = False
    max_input_tokens: int | None = None  # documented input limit; None when undocumented
    concurrency: int = 4  # max in-flight requests the runner may issue to this Provider
    price_key: str | None = None  # key into bakeoff.pricing.PRICES

    async def evaluate(self, request: SystemOneRequest) -> ProviderResult:
        if request.images and not self.supports_images:
            return self.non_answer(
                request, "unsupported_modality", "provider is text-only", latency_s=0.0
            )
        started = time.perf_counter()
        try:
            result = await self._call(request)
        except HttpError as exc:
            cause: NonAnswerCause = "rate_limited" if exc.status == 429 else "error"
            return self.non_answer(
                request,
                cause,
                f"HTTP {exc.status}: {_short(exc.body)}",
                latency_s=time.perf_counter() - started,
                http_status=exc.status,
                response_raw=exc.body,
                attempts=exc.attempts,
            )
        except httpx.TimeoutException as exc:
            return self.non_answer(
                request, "timeout", repr(exc), latency_s=time.perf_counter() - started
            )
        except Exception as exc:  # noqa: BLE001 - a Provider bug must surface as data, not a crash
            return self.non_answer(
                request,
                "error",
                f"{type(exc).__name__}: {exc}",
                latency_s=time.perf_counter() - started,
            )
        if result.cost_usd is None and result.response is not None:
            result.cost_usd = pricing.cost_usd(self.price_key, result.response.usage)
        return result

    @abstractmethod
    async def _call(self, request: SystemOneRequest) -> ProviderResult:
        """Send the request and return a ProviderResult. May raise; ``evaluate`` maps errors."""

    def non_answer(
        self,
        request: SystemOneRequest,
        cause: NonAnswerCause,
        detail: str | None,
        *,
        latency_s: float,
        http_status: int | None = None,
        request_raw: Any = None,
        response_raw: Any = None,
        attempts: int = 1,
    ) -> ProviderResult:
        answers = {qid: NonAnswer(cause=cause, detail=detail) for qid in request.questions}
        return ProviderResult(
            provider_id=self.id,
            response=SystemOneResponse(model=self.model, answers=answers),
            http_status=http_status,
            latency_s=latency_s,
            attempts=attempts,
            error=detail,
            request_raw=request_raw,
            response_raw=response_raw,
        )

    async def aclose(self) -> None:
        """Release connections. Default: nothing to release."""


def _short(body: Any, limit: int = 300) -> str:
    text = body if isinstance(body, str) else repr(body)
    return text if len(text) <= limit else text[:limit] + "..."
