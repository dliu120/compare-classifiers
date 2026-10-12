"""Shared async HTTP helper: retries with backoff, raw capture with secrets and images elided."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import random
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=60.0, pool=30.0)
RETRY_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
_DATA_URL = re.compile(r"^data:([a-z]+/[a-z0-9.+-]+);base64,(.*)$", re.DOTALL)


class HttpError(Exception):
    """Raised when a request fails after retries or with a non-retryable status."""

    def __init__(
        self, status: int | None, body: Any, *, attempts: int, retry_after: float | None = None
    ):
        super().__init__(f"HTTP {status} after {attempts} attempt(s)")
        self.status = status
        self.body = body
        self.attempts = attempts
        self.retry_after = retry_after


@dataclass(slots=True)
class HttpResult:
    status: int
    data: Any  # parsed JSON body, or the raw text when the body is not JSON
    attempts: int
    latency_s: float  # wall time of the successful attempt only


def make_client(timeout: httpx.Timeout = DEFAULT_TIMEOUT) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, follow_redirects=False)


def data_url_sha256(url: str) -> str | None:
    """SHA-256 of the decoded bytes of a base64 data URL, or None if it is not one."""
    match = _DATA_URL.match(url)
    if not match:
        return None
    return hashlib.sha256(base64.b64decode(match.group(2), validate=False)).hexdigest()


def elide_images(obj: Any) -> Any:
    """Return a copy with every base64 image data URL replaced by its hash and byte length."""
    if isinstance(obj, str):
        match = _DATA_URL.match(obj)
        if match and match.group(1).startswith("image/"):
            raw = base64.b64decode(match.group(2), validate=False)
            return {
                "$image": match.group(1),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
            }
        return obj
    if isinstance(obj, dict):
        return {key: elide_images(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [elide_images(value) for value in obj]
    return obj


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _parse_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


async def post_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    json: Any,
    headers: dict[str, str] | None = None,
    max_attempts: int = 4,
    timeout: httpx.Timeout | None = None,
) -> HttpResult:
    """POST JSON with retries on 408/429/5xx and transport errors.

    Honors ``Retry-After`` when present, else backs off 1, 2, 4 seconds with jitter. A
    non-retryable 4xx raises ``HttpError`` at once; exhausting retries raises the last
    failure, which is an ``HttpError`` or the last transport exception.
    """
    for attempt in range(1, max_attempts + 1):
        started = time.perf_counter()
        retry_after: float | None = None
        try:
            response = await client.post(
                url,
                json=json,
                headers=headers,
                # an explicit None would disable the client's timeout, not inherit it
                timeout=timeout if timeout is not None else httpx.USE_CLIENT_DEFAULT,
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            failure: Exception = exc
        else:
            body = _parse_body(response)
            if response.status_code < 400:
                return HttpResult(
                    response.status_code, body, attempt, time.perf_counter() - started
                )
            retry_after = _parse_retry_after(response.headers.get("retry-after"))
            failure = HttpError(
                response.status_code, body, attempts=attempt, retry_after=retry_after
            )
            if response.status_code not in RETRY_STATUSES:
                raise failure
        if attempt == max_attempts:
            raise failure
        await asyncio.sleep(retry_after if retry_after is not None else _backoff(attempt))
    raise AssertionError("unreachable")


def _backoff(attempt: int) -> float:
    return (2 ** (attempt - 1)) * (0.75 + random.random() * 0.5)
