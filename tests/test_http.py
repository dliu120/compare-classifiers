from __future__ import annotations

import httpx
import pytest
import respx

from bakeoff import http
from bakeoff.http import HttpError, post_json

URL = "https://example.test/v1/decide"


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    monkeypatch.setattr(http, "_backoff", lambda attempt: 0.0)


@respx.mock
async def test_retries_on_429_then_succeeds():
    route = respx.post(URL).mock(
        side_effect=[
            httpx.Response(429, headers={"retry-after": "0"}),
            httpx.Response(200, json={"ok": 1}),
        ]
    )
    async with http.make_client() as client:
        result = await post_json(client, URL, json={"a": 1})
    assert result.status == 200 and result.data == {"ok": 1} and result.attempts == 2
    assert route.call_count == 2


@respx.mock
async def test_non_retryable_4xx_raises_at_once():
    respx.post(URL).mock(return_value=httpx.Response(400, json={"error": "bad"}))
    async with http.make_client() as client:
        with pytest.raises(HttpError) as info:
            await post_json(client, URL, json={})
    assert (
        info.value.status == 400
        and info.value.attempts == 1
        and info.value.body == {"error": "bad"}
    )


@respx.mock
async def test_exhausted_retries_raise_last_status():
    respx.post(URL).mock(return_value=httpx.Response(503, text="down"))
    async with http.make_client() as client:
        with pytest.raises(HttpError) as info:
            await post_json(client, URL, json={}, max_attempts=3)
    assert info.value.status == 503 and info.value.attempts == 3 and info.value.body == "down"


@respx.mock
async def test_transport_errors_retry_then_propagate():
    respx.post(URL).mock(side_effect=httpx.ConnectError("refused"))
    async with http.make_client() as client:
        with pytest.raises(httpx.ConnectError):
            await post_json(client, URL, json={}, max_attempts=2)


@respx.mock
async def test_post_json_inherits_the_client_timeout_when_none_is_given():
    route = respx.post(URL).mock(return_value=httpx.Response(200, json={}))
    async with http.make_client(timeout=httpx.Timeout(7.0)) as client:
        await post_json(client, URL, json={})
        await post_json(client, URL, json={}, timeout=httpx.Timeout(3.0))
    inherited, explicit = (call.request.extensions["timeout"] for call in route.calls)
    assert inherited == {"connect": 7.0, "read": 7.0, "write": 7.0, "pool": 7.0}
    assert explicit["read"] == 3.0
