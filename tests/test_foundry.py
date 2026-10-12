from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from bakeoff import cli, http
from bakeoff.config import Settings
from bakeoff.providers import make_provider
from bakeoff.providers.foundry import ROUTE, FoundryProvider
from bakeoff.runner import secrets_of
from bakeoff.store import Store
from bakeoff.systemone import ChoiceAnswer, NonAnswer, NoulAnswer, ScoreAnswer, SystemOneRequest

ENDPOINT = "https://test.services.ai.azure.com"
TOKEN = "foundry-test-token"
BODY = {
    "model": "microsoft-decision-1",
    "answers": {
        "department": {
            "type": "choice",
            "choice": "technical",
            "probabilities": {"billing": 0.01, "technical": 0.98, "sales": 0.01},
            "confidence": 0.97,
        },
        "frustration": {
            "type": "score",
            "score": 1.0,
            "probabilities": {"0": 0.01, "1": 0.98, "2": 0.01},
        },
        "is_urgent": {"type": "noul", "noul": 0.99},
    },
    "usage": {"input_tokens": 132, "output_tokens": 3},
}


@pytest.fixture
def foundry_settings() -> Settings:
    return Settings(foundry_endpoint=ENDPOINT, foundry_access_token=TOKEN)


@respx.mock
async def test_live_wire_shape_all_question_types_and_input_only_price(
    foundry_settings: Settings, sample_request: SystemOneRequest
) -> None:
    route = respx.post(ENDPOINT + ROUTE).respond(200, json=BODY)
    provider = make_provider("foundry", foundry_settings)
    try:
        result = await provider.evaluate(sample_request)
    finally:
        await provider.aclose()

    assert provider.id == "foundry/decision-1"
    assert provider.max_input_tokens == 32_768 and provider.concurrency == 1
    assert result.http_status == 200 and result.error is None
    assert result.response.model == "microsoft-decision-1"
    assert isinstance(result.response.answers["department"], ChoiceAnswer)
    assert isinstance(result.response.answers["frustration"], ScoreAnswer)
    assert isinstance(result.response.answers["is_urgent"], NoulAnswer)
    assert result.response.usage.output_tokens == 3
    assert result.cost_usd == pytest.approx(132 * 0.042 / 1_000_000)
    sent = route.calls.last.request
    assert sent.headers["authorization"] == f"Bearer {TOKEN}"
    body = json.loads(sent.content)
    assert body["model"] == "decision-1"
    assert body["state"] == sample_request.state
    assert body["questions"] == {
        key: value.model_dump(mode="json", exclude_none=True)
        for key, value in sample_request.questions.items()
    }
    assert result.request_raw == body and TOKEN not in json.dumps(result.request_raw)
    assert result.response_raw == BODY


@respx.mock
async def test_deployment_override_and_structured_state(
    foundry_settings: Settings, sample_request: SystemOneRequest
) -> None:
    route = respx.post(ENDPOINT + ROUTE).respond(200, json=BODY)
    provider = make_provider("foundry/other", foundry_settings)
    request = sample_request.model_copy(update={"state": [{"ticket": "broken integration"}]})
    try:
        result = await provider.evaluate(request)
    finally:
        await provider.aclose()
    sent = json.loads(route.calls.last.request.content)
    assert sent["model"] == "other" and sent["state"] == request.state
    assert result.provider_id == "foundry/other"


async def test_configured_deployment_and_resource_lifetime(foundry_settings: Settings) -> None:
    settings = foundry_settings.model_copy(update={"foundry_deployment_name": "configured"})
    provider = make_provider("foundry", settings)
    assert provider.id == "foundry/configured"
    await provider.aclose()
    assert provider._client.is_closed
    async with httpx.AsyncClient() as client:
        provider = FoundryProvider(ENDPOINT, TOKEN, "decision-1", client=client)
        await provider.aclose()
        assert not client.is_closed


@respx.mock
async def test_absent_usage_keeps_cost_unknown(
    foundry_settings: Settings, sample_request: SystemOneRequest
) -> None:
    respx.post(ENDPOINT + ROUTE).respond(
        200, json={key: value for key, value in BODY.items() if key != "usage"}
    )
    provider = make_provider("foundry", foundry_settings)
    try:
        result = await provider.evaluate(sample_request)
    finally:
        await provider.aclose()
    assert result.http_status == 200 and result.error is None
    assert result.cost_usd is None


@pytest.mark.respx(assert_all_called=False)
async def test_images_are_non_answers_without_sending(
    foundry_settings: Settings, image_request: SystemOneRequest, respx_mock: respx.MockRouter
) -> None:
    route = respx_mock.post(ENDPOINT + ROUTE).respond(200, json=BODY)
    provider = make_provider("foundry", foundry_settings)
    try:
        result = await provider.evaluate(image_request)
    finally:
        await provider.aclose()
    assert route.call_count == 0 and result.http_status is None
    assert all(
        isinstance(answer, NonAnswer) and answer.cause == "unsupported_modality"
        for answer in result.response.answers.values()
    )


@respx.mock
@pytest.mark.parametrize(
    ("status", "cause", "attempts"), [(401, "error", 1), (429, "rate_limited", 4)]
)
async def test_authentication_and_rate_limit_errors(
    foundry_settings: Settings,
    sample_request: SystemOneRequest,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    cause: str,
    attempts: int,
) -> None:
    monkeypatch.setattr(http, "_backoff", lambda attempt: 0.0)
    route = respx.post(ENDPOINT + ROUTE).respond(status, json={"error": "rejected"})
    provider = make_provider("foundry", foundry_settings)
    try:
        result = await provider.evaluate(sample_request)
    finally:
        await provider.aclose()
    assert result.http_status == status and result.attempts == attempts
    assert route.call_count == attempts
    assert all(answer.cause == cause for answer in result.response.answers.values())


@respx.mock
@pytest.mark.parametrize("status", [200, 422])
async def test_starts_are_paced_without_inflating_attempt_latency(
    foundry_settings: Settings,
    sample_request: SystemOneRequest,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    clock = [100.0]
    sleeps = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)
        clock[0] += delay

    monkeypatch.setattr("bakeoff.providers.foundry.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("bakeoff.providers.foundry.time.perf_counter", lambda: clock[0])
    monkeypatch.setattr("bakeoff.providers.foundry.asyncio.sleep", sleep)
    respx.post(ENDPOINT + ROUTE).respond(status, json=BODY if status == 200 else {"error": "limit"})
    provider = make_provider("foundry", foundry_settings)
    try:
        first = await provider.evaluate(sample_request)
        second = await provider.evaluate(sample_request)
    finally:
        await provider.aclose()
    assert sleeps == [0.0, 2.0]
    assert first.latency_s < 2.0 and second.latency_s < 2.0


@pytest.mark.parametrize(
    ("settings", "missing"),
    [
        (Settings(foundry_access_token=TOKEN), "FOUNDRY_ENDPOINT"),
        (Settings(foundry_endpoint=ENDPOINT), "FOUNDRY_ACCESS_TOKEN"),
    ],
)
def test_missing_credentials(settings: Settings, missing: str) -> None:
    with pytest.raises(ValueError, match=missing):
        make_provider("foundry", settings)
    assert not settings.has("foundry")


async def test_probe_skips_foundry_when_unconfigured() -> None:
    row = await cli._probe_one("foundry", Settings())
    assert row == ["foundry", "skipped", "", "no credentials for foundry", ""]
    assert "foundry" in cli.DEFAULT_PROBE_SPECS


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://test.services.ai.azure.com",
        "https://evil.example",
        "https://test.services.ai.azure.com.evil.example",
        "https://user:test@test.services.ai.azure.com",
        "https://test.services.ai.azure.com/path",
        "https://test.services.ai.azure.com?query=1",
        "https://test.services.ai.azure.com#fragment",
        "https://test.services.ai.azure.com:8443",
    ],
)
def test_credentials_cannot_be_sent_to_an_insecure_or_non_foundry_endpoint(endpoint: str) -> None:
    with pytest.raises(ValueError, match="FOUNDRY_ENDPOINT"):
        FoundryProvider(endpoint, TOKEN, "decision-1")


@pytest.mark.parametrize("spec", ["foundry/a/b", "foundry?x=1", "foundry/a?effort=none"])
def test_invalid_specs(spec: str, foundry_settings: Settings) -> None:
    with pytest.raises(ValueError, match="foundry spec"):
        make_provider(spec, foundry_settings)


def test_token_echo_is_scrubbed_from_persisted_capture(
    tmp_path: Path, foundry_settings: Settings
) -> None:
    with Store(tmp_path, redact=secrets_of(foundry_settings)) as store:
        store.write_raw("echo", {"response_raw": {"message": TOKEN}})
    captured = (tmp_path / "raw" / "echo.jsonl").read_text()
    assert TOKEN not in captured and "***" in captured


@pytest.mark.parametrize("rate", [0, -1])
def test_pacing_must_be_positive(rate: int) -> None:
    with pytest.raises(ValueError, match="FOUNDRY_REQUESTS_PER_MINUTE"):
        FoundryProvider(ENDPOINT, TOKEN, "decision-1", rate)
    with pytest.raises(ValueError):
        Settings(foundry_requests_per_minute=rate)
