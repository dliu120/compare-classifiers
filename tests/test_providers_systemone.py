"""Offline tests for the three System One-shaped adapters: Jev, Cloudflare, Liquid.

HTTP is mocked with respx. The live tests at the end call the real services and are deselected
by default (``-m 'not live'`` in pyproject); they skip when the credentials are absent.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

from bakeoff import http
from bakeoff.config import Settings, load_settings
from bakeoff.providers import make_provider
from bakeoff.providers.base import Provider, ProviderResult
from bakeoff.providers.liquid import LiquidProvider
from bakeoff.systemone import (
    ChoiceAnswer,
    NonAnswer,
    NoulAnswer,
    ScoreAnswer,
    SystemOneRequest,
)
from tests.conftest import STATE, TINY_PNG
from tests.live import require_env, require_live

JEV_URL = "https://api.typesafe.ai/v1/systemone"
CLOUDFLARE_URL = (
    "https://api.cloudflare.com/client/v4/accounts/acct/ai/run/@cf/cloudflare/clef-flash"
)
LIQUID_URL = "https://api.liquid.ai/decisions/v1/systemone"

# TypeSafe's quickstart answers for the conftest ticket (docs.typesafe.ai; see test_systemone.py).
TYPESAFE_ANSWERS: dict[str, Any] = {
    "department": {
        "type": "choice",
        "choice": "technical",
        "probabilities": {"technical": 0.85, "sales": 0.0, "billing": 0.15},
        "confidence": 0.78,
    },
    "frustration": {
        "type": "score",
        "score": 1.0,
        "probabilities": {"0": 0.0, "1": 1.0, "2": 0.0},
        "legend": {"0": "Calm, just stating facts", "1": "Frustrated but civil", "2": "Very angry"},
        "confidence": 1.0,
    },
    "is_urgent": {"type": "noul", "noul": 1.0},
}


def system_one(model: str, answers: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
    return {"model": model, "answers": answers, "usage": usage}


def envelope(result: Any) -> dict[str, Any]:
    """The Workers AI REST envelope around a System One response."""
    return {"result": result, "success": True, "errors": [], "messages": []}


JEV_BODY = system_one("jev-1.13.0", TYPESAFE_ANSWERS, {"input_tokens": 392, "output_tokens": 65})
CLOUDFLARE_BODY = envelope(
    system_one("clef-flash", TYPESAFE_ANSWERS, {"input_tokens": 410, "output_tokens": 0})
)
LIQUID_BODY = system_one("d1", TYPESAFE_ANSWERS, {"input_tokens": 400, "output_tokens": 0})
LIQUID_D1_1_BODY = system_one(
    "d1.1", TYPESAFE_ANSWERS, {"input_tokens": 400, "output_tokens": 0, "cost": 0.000008}
)

# spec, provider id, endpoint, a realistic 200 body, price per M input, the key the header carries
VENDORS = [
    pytest.param("jev", "jev", JEV_URL, JEV_BODY, 0.042, "ts-test", id="jev"),
    pytest.param(
        "cloudflare/clef-flash",
        "cloudflare/clef-flash",
        CLOUDFLARE_URL,
        CLOUDFLARE_BODY,
        0.09,
        "cf-test",
        id="cloudflare",
    ),
    pytest.param(
        "liquid/d1", "liquid/d1", LIQUID_URL, LIQUID_BODY, 0.02, "liquid_test", id="liquid"
    ),
]
IMAGE_TOP_LEVEL = [
    pytest.param("cloudflare/clef-flash", CLOUDFLARE_URL, CLOUDFLARE_BODY, id="cloudflare"),
    pytest.param("liquid/d1", LIQUID_URL, LIQUID_BODY, id="liquid"),
    pytest.param("liquid/d1.1", LIQUID_URL, LIQUID_D1_1_BODY, id="liquid-d1.1"),
]


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http, "_backoff", lambda attempt: 0.0)


async def evaluate(spec: str, settings: Settings, request: SystemOneRequest) -> ProviderResult:
    provider = make_provider(spec, settings)
    try:
        return await provider.evaluate(request)
    finally:
        await provider.aclose()


def sent_body(route: respx.Route) -> dict[str, Any]:
    return json.loads(route.calls.last.request.content)


def causes(result: ProviderResult) -> set[str]:
    assert result.response is not None
    return {
        answer.cause for answer in result.response.answers.values() if isinstance(answer, NonAnswer)
    }


@respx.mock
@pytest.mark.parametrize(("spec", "provider_id", "url", "body", "price", "key"), VENDORS)
async def test_success_maps_vendor_response(
    spec: str,
    provider_id: str,
    url: str,
    body: dict[str, Any],
    price: float,
    key: str,
    settings: Settings,
    sample_request: SystemOneRequest,
) -> None:
    route = respx.post(url).mock(return_value=httpx.Response(200, json=body))

    result = await evaluate(spec, settings, sample_request)

    assert result.provider_id == provider_id
    assert result.http_status == 200 and result.attempts == 1 and result.error is None
    assert result.latency_s >= 0.0
    assert result.response is not None and causes(result) == set()
    answers = result.response.answers
    assert isinstance(answers["department"], ChoiceAnswer)
    assert answers["department"].choice == "technical"
    assert isinstance(answers["frustration"], ScoreAnswer)
    assert set(answers["frustration"].probabilities) == {"0", "1", "2"}
    assert isinstance(answers["is_urgent"], NoulAnswer)
    input_tokens = result.response.usage.input_tokens
    assert input_tokens is not None and input_tokens > 0
    assert result.cost_usd == pytest.approx(input_tokens * price / 1e6)
    assert result.response_raw == body
    assert route.call_count == 1
    assert route.calls.last.request.headers["authorization"] == f"Bearer {key}"


@respx.mock
@pytest.mark.parametrize(("spec", "provider_id", "url", "body", "price", "key"), VENDORS)
async def test_questions_pass_through_unchanged(
    spec: str,
    provider_id: str,
    url: str,
    body: dict[str, Any],
    price: float,
    key: str,
    settings: Settings,
    sample_request: SystemOneRequest,
) -> None:
    route = respx.post(url).mock(return_value=httpx.Response(200, json=body))

    result = await evaluate(spec, settings, sample_request)

    sent = sent_body(route)
    assert sent["model"] == make_provider(spec, settings).model
    assert sent["state"] == STATE
    assert "images" not in sent
    questions = sent["questions"]
    assert set(questions) == {"department", "frustration", "is_urgent"}
    assert questions["department"] == {
        "type": "choice",
        "instructions": "Which team should handle this?",
        "criteria": {
            "billing": "Payment or subscription issues",
            "technical": "Bugs or integration problems",
            "sales": "Pricing or account questions",
        },
    }
    assert questions["frustration"]["type"] == "score"
    assert questions["frustration"]["criteria"] == [
        "Calm, just stating facts",
        "Frustrated but civil",
        "Very angry",
    ]
    assert questions["is_urgent"] == {
        "type": "noul",
        "instructions": "Does this message convey urgency?",
    }
    assert result.request_raw == sent  # no images, so nothing to elide


@respx.mock
async def test_liquid_d1_1_uses_hosted_model_and_reported_cost(
    settings: Settings, sample_request: SystemOneRequest
) -> None:
    route = respx.post(LIQUID_URL).mock(return_value=httpx.Response(200, json=LIQUID_D1_1_BODY))

    result = await evaluate("liquid/d1.1", settings, sample_request)

    assert result.provider_id == "liquid/d1.1"
    assert sent_body(route)["model"] == "d1.1"
    assert result.cost_usd == pytest.approx(0.000008)
    assert make_provider("liquid/d1.1", settings).price_key == "d1.1"
    assert make_provider("liquid/d1.1", settings).max_input_tokens == 65_536


@respx.mock
async def test_liquid_d1_1_without_reported_cost_stays_unknown(
    settings: Settings, sample_request: SystemOneRequest
) -> None:
    body = system_one("d1.1", TYPESAFE_ANSWERS, {"input_tokens": 400, "output_tokens": 0})
    respx.post(LIQUID_URL).mock(return_value=httpx.Response(200, json=body))

    result = await evaluate("liquid/d1.1", settings, sample_request)

    assert result.cost_usd is None


@respx.mock
@pytest.mark.parametrize("reported_cost", [True, "0.01", -0.01, 10**400])
async def test_liquid_ignores_invalid_reported_cost(
    reported_cost: Any, settings: Settings, sample_request: SystemOneRequest
) -> None:
    body = system_one(
        "d1.1",
        TYPESAFE_ANSWERS,
        {"input_tokens": 400, "output_tokens": 0, "cost": reported_cost},
    )
    respx.post(LIQUID_URL).mock(return_value=httpx.Response(200, json=body))

    result = await evaluate("liquid/d1.1", settings, sample_request)

    assert result.cost_usd is None


@respx.mock
@pytest.mark.parametrize(("spec", "url", "body"), IMAGE_TOP_LEVEL)
async def test_cloudflare_and_liquid_send_top_level_images(
    spec: str, url: str, body: dict[str, Any], settings: Settings, image_request: SystemOneRequest
) -> None:
    route = respx.post(url).mock(return_value=httpx.Response(200, json=body))

    result = await evaluate(spec, settings, image_request)

    sent = sent_body(route)
    assert sent["images"] == [TINY_PNG]
    assert sent["state"] == STATE
    assert causes(result) == set()
    assert result.request_raw["images"][0]["$image"] == "image/png"
    assert TINY_PNG not in json.dumps(result.request_raw)


@pytest.mark.respx(assert_all_called=False)
async def test_jev_rejects_images_without_calling(
    settings: Settings, image_request: SystemOneRequest, respx_mock: respx.MockRouter
) -> None:
    route = respx_mock.post(JEV_URL).mock(return_value=httpx.Response(200, json=JEV_BODY))

    result = await evaluate("jev", settings, image_request)

    assert causes(result) == {"unsupported_modality"}
    assert set(result.response.answers) == set(image_request.questions)
    assert result.http_status is None and result.latency_s == 0.0
    assert route.call_count == 0


@pytest.mark.respx(assert_all_called=False)
async def test_liquid_free_tier_is_text_only(
    settings: Settings, image_request: SystemOneRequest, respx_mock: respx.MockRouter
) -> None:
    route = respx_mock.post(LIQUID_URL).mock(return_value=httpx.Response(200, json=LIQUID_BODY))
    provider = make_provider("liquid/d1:free", settings)
    assert isinstance(provider, LiquidProvider) and provider.supports_images is False

    result = await evaluate("liquid/d1:free", settings, image_request)

    assert causes(result) == {"unsupported_modality"}
    assert route.call_count == 0


@respx.mock
@pytest.mark.parametrize(("spec", "provider_id", "url", "body", "price", "key"), VENDORS)
async def test_429_after_retries_is_rate_limited(
    spec: str,
    provider_id: str,
    url: str,
    body: dict[str, Any],
    price: float,
    key: str,
    settings: Settings,
    sample_request: SystemOneRequest,
) -> None:
    route = respx.post(url).mock(return_value=httpx.Response(429, json={"error": "slow down"}))

    result = await evaluate(spec, settings, sample_request)

    assert causes(result) == {"rate_limited"}
    assert set(result.response.answers) == set(sample_request.questions)
    assert result.http_status == 429 and result.attempts == 4
    assert result.response_raw == {"error": "slow down"}
    assert result.cost_usd is None
    assert route.call_count == 4


@respx.mock
async def test_cloudflare_unwraps_envelope_and_keeps_it_raw(
    settings: Settings, sample_request: SystemOneRequest
) -> None:
    respx.post(CLOUDFLARE_URL).mock(return_value=httpx.Response(200, json=CLOUDFLARE_BODY))

    result = await evaluate("cloudflare/clef-flash", settings, sample_request)

    assert causes(result) == set()
    assert result.response.model == "clef-flash"
    assert result.response.usage.input_tokens == 410
    assert result.response_raw == CLOUDFLARE_BODY  # the envelope, as returned


@respx.mock
async def test_cloudflare_accepts_bare_system_one_body(
    settings: Settings, sample_request: SystemOneRequest
) -> None:
    bare = CLOUDFLARE_BODY["result"]
    respx.post(CLOUDFLARE_URL).mock(return_value=httpx.Response(200, json=bare))

    result = await evaluate("cloudflare/clef-flash", settings, sample_request)

    assert causes(result) == set()
    assert result.response.usage.input_tokens == 410


@respx.mock
async def test_cloudflare_failed_envelope_is_invalid_output(
    settings: Settings, sample_request: SystemOneRequest
) -> None:
    body = {
        "result": None,
        "success": False,
        "errors": [{"code": 7001, "message": "no"}],
        "messages": [],
    }
    respx.post(CLOUDFLARE_URL).mock(return_value=httpx.Response(200, json=body))

    result = await evaluate("cloudflare/clef-flash", settings, sample_request)

    assert causes(result) == {"invalid_output"}
    assert result.response_raw == body and result.http_status == 200


@respx.mock
@pytest.mark.parametrize(("spec", "provider_id", "url", "body", "price", "key"), VENDORS)
async def test_authorization_never_appears_in_request_raw(
    spec: str,
    provider_id: str,
    url: str,
    body: dict[str, Any],
    price: float,
    key: str,
    settings: Settings,
    image_request: SystemOneRequest,
    sample_request: SystemOneRequest,
) -> None:
    route = respx.post(url).mock(return_value=httpx.Response(200, json=body))
    request = sample_request if spec == "jev" else image_request

    result = await evaluate(spec, settings, request)

    assert route.calls.last.request.headers["authorization"] == f"Bearer {key}"
    captured = json.dumps(result.request_raw).lower()
    assert "authorization" not in captured and "bearer" not in captured and key not in captured
    assert key not in json.dumps(result.response_raw)
    assert TINY_PNG not in captured


@respx.mock
@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"unexpected": True}, id="wrong-shape"),
        pytest.param("<html>busy</html>", id="not-json"),
        pytest.param(
            {
                "model": "jev-1.13.0",
                "answers": {"department": {"type": "refusal", "name": "department"}},
                "usage": {},
            },
            id="unknown-answer-type",
        ),
    ],
)
async def test_unvalidatable_body_is_invalid_output(
    body: Any, settings: Settings, sample_request: SystemOneRequest
) -> None:
    if isinstance(body, str):
        response = httpx.Response(200, text=body)
    else:
        response = httpx.Response(200, json=body)
    respx.post(JEV_URL).mock(return_value=response)

    result = await evaluate("jev", settings, sample_request)

    assert causes(result) == {"invalid_output"}
    assert set(result.response.answers) == set(sample_request.questions)
    assert result.http_status == 200 and result.attempts == 1
    assert result.response_raw == body
    assert result.error is not None and "System One" in result.error
    assert result.request_raw["model"] == "jev-1.13.0"


@respx.mock
async def test_missing_answer_becomes_non_answer(
    settings: Settings, sample_request: SystemOneRequest
) -> None:
    partial = {key: value for key, value in TYPESAFE_ANSWERS.items() if key != "is_urgent"}
    body = system_one("jev-1.13.0", partial, {"input_tokens": 392, "output_tokens": 40})
    respx.post(JEV_URL).mock(return_value=httpx.Response(200, json=body))

    result = await evaluate("jev", settings, sample_request)

    answers = result.response.answers
    assert isinstance(answers["department"], ChoiceAnswer)
    assert isinstance(answers["is_urgent"], NonAnswer)
    assert answers["is_urgent"].cause == "invalid_output"
    assert result.cost_usd == pytest.approx(392 * 0.042 / 1e6)


@respx.mock
async def test_one_bad_answer_spoils_only_itself(
    settings: Settings, sample_request: SystemOneRequest
) -> None:
    answers = {**TYPESAFE_ANSWERS, "department": {"type": "refusal", "name": "department"}}
    body = system_one("jev-1.13.0", answers, {"input_tokens": 392, "output_tokens": 40})
    respx.post(JEV_URL).mock(return_value=httpx.Response(200, json=body))

    result = await evaluate("jev", settings, sample_request)

    assert causes(result) == {"invalid_output"}
    department = result.response.answers["department"]
    assert isinstance(department, NonAnswer) and "System One answer" in department.detail
    assert isinstance(result.response.answers["frustration"], ScoreAnswer)
    assert isinstance(result.response.answers["is_urgent"], NoulAnswer)
    assert result.response.usage.input_tokens == 392
    assert result.cost_usd == pytest.approx(392 * 0.042 / 1e6)
    assert result.error == department.detail


@respx.mock
async def test_missing_model_falls_back_to_the_provider_model(
    settings: Settings, sample_request: SystemOneRequest
) -> None:
    bare = {key: value for key, value in CLOUDFLARE_BODY["result"].items() if key != "model"}
    respx.post(CLOUDFLARE_URL).mock(return_value=httpx.Response(200, json=envelope(bare)))

    result = await evaluate("cloudflare/clef-flash", settings, sample_request)

    assert causes(result) == set()
    assert result.response.model == "clef-flash"


@respx.mock
async def test_transport_error_after_retries_is_error(
    settings: Settings, sample_request: SystemOneRequest
) -> None:
    route = respx.post(LIQUID_URL).mock(side_effect=httpx.ConnectError("refused"))

    result = await evaluate("liquid", settings, sample_request)

    assert causes(result) == {"error"}
    assert result.http_status is None
    assert route.call_count == 4 and result.attempts == 4
    assert result.request_raw["model"] == "d1"  # the body as sent is captured all the same
    assert result.latency_s > 0.0


@respx.mock
async def test_timeout_after_retries_is_timeout(
    settings: Settings, sample_request: SystemOneRequest
) -> None:
    route = respx.post(JEV_URL).mock(side_effect=httpx.ReadTimeout("slow"))

    result = await evaluate("jev", settings, sample_request)

    assert causes(result) == {"timeout"}
    assert route.call_count == 4 and result.attempts == 4
    assert result.request_raw["questions"] and result.cost_usd is None


@pytest.mark.parametrize(
    ("spec", "settings_without", "env_var"),
    [
        ("jev", Settings(), "TYPESAFE_API_KEY"),
        ("cloudflare/clef", Settings(cloudflare_auth_token="cf"), "CLOUDFLARE_ACCOUNT_ID"),
        ("cloudflare/clef", Settings(cloudflare_account_id="acct"), "CLOUDFLARE_AUTH_TOKEN"),
        ("liquid", Settings(), "LIQUID_API_KEY"),
    ],
)
def test_build_names_the_missing_env_var(
    spec: str, settings_without: Settings, env_var: str
) -> None:
    with pytest.raises(ValueError, match=env_var):
        make_provider(spec, settings_without)


@pytest.mark.parametrize(
    ("spec", "provider_id", "model", "supports_images", "max_input_tokens", "concurrency"),
    [
        ("jev", "jev", "jev-1.13.0", False, 32_000, 8),
        ("cloudflare/clef", "cloudflare/clef", "clef", True, 65_536, 4),
        ("cloudflare/clef-flash", "cloudflare/clef-flash", "clef-flash", True, 65_536, 4),
        ("liquid", "liquid/d1", "d1", True, 65_536, 4),
        ("liquid/d1", "liquid/d1", "d1", True, 65_536, 4),
        ("liquid/d1:free", "liquid/d1:free", "d1:free", False, 65_536, 4),
    ],
)
async def test_build_sets_provider_attributes(
    spec: str,
    provider_id: str,
    model: str,
    supports_images: bool,
    max_input_tokens: int | None,
    concurrency: int,
    settings: Settings,
) -> None:
    provider = make_provider(spec, settings)
    try:
        assert isinstance(provider, Provider)
        assert provider.id == provider_id
        assert provider.model == model and provider.price_key == model
        assert provider.supports_images is supports_images
        assert provider.max_input_tokens == max_input_tokens
        assert provider.concurrency == concurrency
        assert make_provider(provider.id, settings).id == provider_id  # ids round-trip as specs
    finally:
        await provider.aclose()


@pytest.mark.parametrize(
    "spec",
    [
        "jev/jev-1.13.0",
        "jev?x=1",
        "cloudflare",
        "cloudflare/clef-ultra",
        "liquid/d2",
        "liquid/d1?effort=low",
    ],
)
def test_build_rejects_unknown_specs(spec: str, settings: Settings) -> None:
    with pytest.raises(ValueError):
        make_provider(spec, settings)


async def test_aclose_releases_the_shared_client(settings: Settings) -> None:
    provider = make_provider("jev", settings)
    client = provider._client  # private on purpose: the test checks the resource is released
    assert client.is_closed is False
    await provider.aclose()
    assert client.is_closed is True


async def test_aclose_leaves_an_injected_client_open(settings: Settings) -> None:
    async with http.make_client() as client:
        first = LiquidProvider("liquid_test", client=client)
        second = LiquidProvider("liquid_test", "d1:free", client=client)
        await first.aclose()
        assert client.is_closed is False
        await second.aclose()
        assert client.is_closed is False


@pytest.mark.live
@pytest.mark.parametrize("spec", ["jev", "cloudflare/clef-flash", "liquid/d1:free"])
async def test_live_round_trip(spec: str, sample_request: SystemOneRequest) -> None:
    require_live()
    family = spec.split("/")[0]
    if family == "jev":
        require_env("TYPESAFE_API_KEY")  # not the use-jev key file: live spend is explicit
    live_settings = load_settings()
    if not live_settings.has(family):
        pytest.skip(f"no credentials for {family}")

    result = await evaluate(spec, live_settings, sample_request)

    assert result.http_status == 200, result.error
    assert causes(result) == set()
    assert isinstance(result.response.answers["department"], ChoiceAnswer)
    assert result.cost_usd is not None
