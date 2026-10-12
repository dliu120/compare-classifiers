"""Non-answers for the transport failures ``bakeoff.http.post_json`` raises.

``post_json`` retries a timeout or connection error until its attempts are spent and only then
raises it, so an adapter that catches one knows every attempt was made.
"""

from __future__ import annotations

from typing import Any

import httpx

from bakeoff.providers.base import Provider, ProviderResult
from bakeoff.systemone import NonAnswerCause, SystemOneRequest

MAX_ATTEMPTS = 4  # what the adapters pass to post_json


def transport_cause(exc: httpx.TransportError) -> NonAnswerCause:
    return "timeout" if isinstance(exc, httpx.TimeoutException) else "error"


def transport_detail(exc: httpx.TransportError) -> str:
    return f"{type(exc).__name__}: {exc}"


def transport_non_answer(
    provider: Provider,
    request: SystemOneRequest,
    exc: httpx.TransportError,
    *,
    latency_s: float,
    request_raw: Any,
    attempts: int = MAX_ATTEMPTS,
) -> ProviderResult:
    """Every Question a Non-answer: ``timeout`` for a timeout, ``error`` for any other failure."""
    return provider.non_answer(
        request,
        transport_cause(exc),
        transport_detail(exc),
        latency_s=latency_s,
        request_raw=request_raw,
        attempts=attempts,
    )
