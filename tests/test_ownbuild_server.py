from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from bakeoff import http
from bakeoff.ownbuild.config import OwnBuildConfig
from bakeoff.ownbuild.server import create_app
from bakeoff.providers.base import ProviderResult
from bakeoff.providers.ownbuild import OwnBuildProvider
from bakeoff.systemone import (
    ChoiceAnswer,
    NonAnswer,
    NoulAnswer,
    ScoreAnswer,
    SystemOneRequest,
    SystemOneResponse,
    Usage,
)
from tests.test_ownbuild import COPILOT_URL, PROBABILITIES_TEXT, responses_body
from tests.tokenizer import needs_tokenizer

SPEC = "ownbuild/copilot/gpt-6-luna?effort=low&cap=512"
NORMALIZED = "ownbuild/copilot/gpt-6-luna?effort=low&cap=512&mode=probabilities&samples=1"


class FakeEngine:
    """Answers every Question with a fixed Answer, or with Non-answers when asked to fail."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.requests: list[SystemOneRequest] = []
        self.closed = False

    async def evaluate(self, request: SystemOneRequest) -> ProviderResult:
        self.requests.append(request)
        answers = {qid: self._answer(question) for qid, question in request.questions.items()}
        response = SystemOneResponse(
            model="gpt-6-luna", answers=answers, usage=Usage(input_tokens=10, output_tokens=2)
        )
        return ProviderResult(provider_id="fake", response=response, latency_s=0.1234)

    def _answer(self, question):
        if self.fail:
            return NonAnswer(cause="truncated_output", detail="max_output_tokens")
        match question.type:
            case "choice":
                first = next(iter(question.criteria))
                probabilities = {option: 0.0 for option in question.criteria} | {first: 1.0}
                return ChoiceAnswer(choice=first, probabilities=probabilities)
            case "score":
                return ScoreAnswer(score=0.0, probabilities={"0": 1.0, "1": 0.0, "2": 0.0})
            case _:
                return NoulAnswer(noul=0.25)

    async def aclose(self) -> None:
        self.closed = True


def test_server_round_trip_with_a_mocked_engine(settings, sample_request):
    app = create_app(SPEC, settings)
    fake = FakeEngine()
    app.state.engine = fake
    with TestClient(app) as client:
        response = client.post("/v1/systemone", json=sample_request.model_dump(mode="json"))
        assert response.status_code == 200
        assert response.headers["x-bakeoff-latency-ms"] == "123.4"
        parsed = SystemOneResponse.model_validate(response.json())
        assert parsed.model == "gpt-6-luna"
        assert isinstance(parsed.answers["department"], ChoiceAnswer)
        assert parsed.answers["department"].choice == "billing"
        assert parsed.answers["is_urgent"] == NoulAnswer(noul=0.25)
        assert parsed.usage.input_tokens == 10
        assert fake.requests == [sample_request]

        models = client.get("/v1/models").json()
        assert [model["id"] for model in models["data"]] == ["gpt-6-luna"]
        assert models["data"][0]["spec"] == NORMALIZED
    assert fake.closed


def test_server_returns_non_answers_as_data_and_422_for_bad_requests(settings, sample_request):
    app = create_app(SPEC, settings)
    app.state.engine = FakeEngine(fail=True)
    with TestClient(app) as client:
        response = client.post("/v1/systemone", json=sample_request.model_dump(mode="json"))
        assert response.status_code == 200
        parsed = SystemOneResponse.model_validate(response.json())
        assert all(isinstance(answer, NonAnswer) for answer in parsed.answers.values())

        assert client.post("/v1/systemone", json={"model": "x"}).status_code == 422
        extra = {**sample_request.model_dump(mode="json"), "bogus": 1}
        assert client.post("/v1/systemone", json=extra).status_code == 422
        too_few = {"model": "x", "state": "s", "questions": {}}
        assert client.post("/v1/systemone", json=too_few).status_code == 422


def test_server_rejects_via_in_its_spec(settings):
    with pytest.raises(ValueError, match="via"):
        create_app(SPEC + "&via=http://127.0.0.1:1", settings)


@needs_tokenizer
@respx.mock
def test_server_drives_the_real_engine(settings, sample_request):
    body = responses_body(PROBABILITIES_TEXT)
    respx.post(COPILOT_URL).mock(return_value=httpx.Response(200, json=body))
    app = create_app(SPEC, settings)
    with TestClient(app) as client:
        response = client.post("/v1/systemone", json=sample_request.model_dump(mode="json"))
    assert response.status_code == 200
    parsed = SystemOneResponse.model_validate(response.json())
    assert parsed.answers["department"].choice == "technical"
    assert float(response.headers["x-bakeoff-latency-ms"]) >= 0.0


async def test_via_provider_round_trips_through_the_server(settings, sample_request):
    app = create_app(SPEC, settings)
    app.state.engine = FakeEngine()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://server") as client:
        provider = OwnBuildProvider(
            OwnBuildConfig(route="copilot"), settings, via="http://server/v1/", client=client
        )
        assert provider.id == (
            "ownbuild/copilot/gpt-6-luna?mode=probabilities&samples=1&via=http://server"
        )
        result = await provider.evaluate(sample_request)
        await provider.aclose()
        assert not client.is_closed  # an injected client is the caller's to close
    assert result.provider_id == provider.id
    assert result.http_status == 200
    assert isinstance(result.response.answers["department"], ChoiceAnswer)
    assert result.request_raw["meta"] == {"via": "http://server"}
    assert "questions" in result.request_raw
    assert result.cost_usd == pytest.approx((10 * 0.10 + 2 * 0.50) / 1e6)


@respx.mock
async def test_via_provider_maps_a_bad_body_and_a_failing_server(
    settings, sample_request, monkeypatch
):
    monkeypatch.setattr(http, "_backoff", lambda attempt: 0.0)
    url = "http://server/v1/systemone"
    route = respx.post(url).mock(return_value=httpx.Response(200, json={"unexpected": True}))
    provider = OwnBuildProvider(OwnBuildConfig(route="copilot"), settings, via="http://server")

    result = await provider.evaluate(sample_request)
    assert {a.cause for a in result.response.answers.values()} == {"invalid_output"}
    assert "not a System One response" in result.error
    assert result.http_status == 200 and result.attempts == 1
    assert result.request_raw["meta"] == {"via": "http://server"}
    assert result.response_raw == {"unexpected": True}

    route.mock(return_value=httpx.Response(503, text="down"))
    result = await provider.evaluate(sample_request)
    assert {a.cause for a in result.response.answers.values()} == {"error"}
    assert result.http_status == 503 and result.attempts == 4

    route.mock(side_effect=httpx.ConnectError("refused"))
    result = await provider.evaluate(sample_request)
    assert {a.cause for a in result.response.answers.values()} == {"error"}
    assert result.http_status is None and result.attempts == 4
    assert result.request_raw["meta"] == {"via": "http://server"}
    await provider.aclose()
