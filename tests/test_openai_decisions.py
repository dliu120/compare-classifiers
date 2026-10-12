from __future__ import annotations

import json

import httpx
import pytest
import respx

from bakeoff import http
from bakeoff.config import Settings
from bakeoff.providers import make_provider
from bakeoff.providers.openai_decisions import OpenAIDecisionsProvider, build, build_body
from bakeoff.systemone import (
    ChoiceAnswer,
    ChoiceQuestion,
    NonAnswer,
    NoulAnswer,
    NoulQuestion,
    ScoreAnswer,
    ScoreQuestion,
    SystemOneRequest,
)
from tests.conftest import STATE, TINY_PNG

URL = "https://api.openai.com/v1/decisions"

# A well-formed Decisions answers array for conftest's sample_request.
SAMPLE_ANSWERS = [
    {
        "type": "choice",
        "name": "department",
        "choice": "technical",
        "confidence": 0.78,
        "probabilities": [
            {"value": "technical", "probability": 0.85},
            {"value": "billing", "probability": 0.15},
        ],
    },
    {
        "type": "score",
        "name": "frustration",
        "score": 1.2,
        "confidence": 0.5,
        "probabilities": [
            {"value": 0, "label": "Calm, just stating facts", "probability": 0.1},
            {"value": 1, "label": "Frustrated but civil", "probability": 0.6},
            {"value": 2, "label": "Very angry", "probability": 0.3},
        ],
    },
    {"type": "predicate", "name": "is_urgent", "probability": 0.97},
]


@pytest.fixture
async def provider(settings: Settings):
    provider = build("openai-decisions", settings)
    yield provider
    await provider.aclose()


def sent_body(route: respx.Route) -> dict:
    return json.loads(route.calls.last.request.content)


def causes(result) -> set[str]:
    return {answer.cause for answer in result.response.answers.values()}


async def test_build_normalizes_spec_and_sets_provider_facts(settings: Settings):
    provider = build("openai-decisions", settings)
    assert isinstance(provider, OpenAIDecisionsProvider)
    assert provider.id == "openai-decisions/gpt-6-luna"
    assert provider.model == "gpt-6-luna"
    assert provider.price_key == "openai-decisions/gpt-6-luna"
    assert provider.supports_images is True
    assert provider.max_input_tokens is None
    assert provider.concurrency == 8
    explicit = build("openai-decisions/gpt-6-luna", settings)
    registered = make_provider("openai-decisions", settings)
    other = build("openai-decisions/other-model", settings)
    assert explicit.id == registered.id == provider.id
    assert other.id == other.price_key == "openai-decisions/other-model"
    for built in (provider, explicit, registered, other):
        await built.aclose()


def test_build_rejects_missing_key_and_bad_specs(settings: Settings):
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build("openai-decisions", Settings())
    with pytest.raises(ValueError):
        build("openai-decisions?effort=low", settings)
    with pytest.raises(ValueError):
        build("openai-decisions/a/b", settings)
    with pytest.raises(ValueError):
        build("jev", settings)


@respx.mock
async def test_request_body_maps_each_question_type(provider, sample_request):
    route = respx.post(URL).mock(return_value=httpx.Response(200, json={"answers": SAMPLE_ANSWERS}))
    result = await provider.evaluate(sample_request)
    body = sent_body(route)
    assert body["model"] == "gpt-6-luna"
    assert body["input"] == STATE
    assert [q["name"] for q in body["questions"]] == list(sample_request.questions)
    department, frustration, is_urgent = body["questions"]
    assert department == {
        "type": "choice",
        "name": "department",
        "instructions": "Which team should handle this?",
        "choices": [
            {"value": "billing", "description": "Payment or subscription issues"},
            {"value": "technical", "description": "Bugs or integration problems"},
            {"value": "sales", "description": "Pricing or account questions"},
        ],
    }
    assert frustration == {
        "type": "score",
        "name": "frustration",
        "instructions": "How frustrated does the customer appear?",
        "levels": [
            {"label": "Calm, just stating facts"},
            {"label": "Frustrated but civil"},
            {"label": "Very angry"},
        ],
    }
    assert is_urgent == {
        "type": "predicate",
        "name": "is_urgent",
        "instructions": "Does this message convey urgency?",
    }
    assert route.calls.last.request.headers["authorization"] == "Bearer sk-test"
    assert result.request_raw == body
    assert "authorization" not in json.dumps(result.request_raw).lower()
    assert "sk-test" not in json.dumps(result.request_raw)


@respx.mock
async def test_image_state_becomes_one_user_message(provider, image_request):
    route = respx.post(URL).mock(return_value=httpx.Response(200, json={"answers": SAMPLE_ANSWERS}))
    result = await provider.evaluate(image_request)
    assert sent_body(route)["input"] == [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": STATE},
                {"type": "input_image", "image_url": TINY_PNG},
            ],
        }
    ]
    elided = result.request_raw["input"][0]["content"][1]["image_url"]
    assert elided["$image"] == "image/png" and elided["bytes"] > 0
    assert TINY_PNG not in json.dumps(result.request_raw)


def test_criteria_fold_into_predicates_and_long_levels_become_descriptions():
    request = SystemOneRequest(
        model="test",
        state={"ticket": 42, "text": "hello"},
        questions={
            "refund": NoulQuestion(
                instructions={"ask": "Is a refund due?"},
                criteria={"true": "A refund is owed", "false": {"no": "refund"}},
            ),
            "only_yes": NoulQuestion(instructions="Spam?", criteria={"true": "Unsolicited ads"}),
            "tone": ChoiceQuestion(
                instructions="Tone?", criteria={"warm": None, "cold": ["icy", "curt"]}
            ),
            "severity": ScoreQuestion(
                instructions="Severity?", criteria=["Low", "x" * 61, {"level": "critical"}]
            ),
        },
    )
    body = build_body("gpt-6-luna", request)
    assert body["input"] == '{"ticket":42,"text":"hello"}'
    refund, only_yes, tone, severity = body["questions"]
    assert refund["instructions"] == (
        '{"ask":"Is a refund due?"}\nYes means: A refund is owed\nNo means: {"no":"refund"}'
    )
    assert only_yes["instructions"] == "Spam?\nYes means: Unsolicited ads"
    assert tone["choices"] == [
        {"value": "warm"},
        {"value": "cold", "description": '["icy","curt"]'},
    ]
    assert severity["levels"] == [
        {"label": "Low"},
        {"label": "level 1", "description": "x" * 61},
        {"label": "level 2", "description": '{"level":"critical"}'},
    ]


@respx.mock
async def test_response_maps_answers_by_name_including_a_refusal(provider, sample_request):
    questions = {**sample_request.questions, "blocked": NoulQuestion(instructions="Is this spam?")}
    request = sample_request.model_copy(update={"questions": questions})
    refusal = {"type": "refusal", "name": "blocked", "refusal": "declined by policy"}
    answers = [*SAMPLE_ANSWERS, refusal]
    answers.reverse()  # order differs from the request: pairing must go by name
    usage = {"input_tokens": 1234, "output_tokens": 4}
    body = {"model": "gpt-6-luna-2026", "answers": answers, "usage": usage}
    respx.post(URL).mock(return_value=httpx.Response(200, json=body))
    result = await provider.evaluate(request)
    response = result.response
    assert response.model == "gpt-6-luna-2026"
    assert response.answers["department"] == ChoiceAnswer(
        choice="technical",
        probabilities={"billing": 0.15, "technical": 0.85, "sales": 0.0},
        confidence=0.78,
    )
    assert response.answers["frustration"] == ScoreAnswer(
        score=1.2,
        probabilities={"0": 0.1, "1": 0.6, "2": 0.3},
        legend={"0": "Calm, just stating facts", "1": "Frustrated but civil", "2": "Very angry"},
        confidence=0.5,
    )
    assert response.answers["is_urgent"] == NoulAnswer(noul=0.97)
    assert response.answers["blocked"] == NonAnswer(cause="refusal", detail="declined by policy")
    assert response.usage.input_tokens == 1234 and response.usage.output_tokens == 0
    assert result.cost_usd == pytest.approx(1234 * 0.10 / 1e6)
    assert result.http_status == 200 and result.attempts == 1 and result.error is None
    assert result.response_raw == body


@respx.mock
async def test_unnamed_answers_fall_back_to_position(provider, sample_request):
    unnamed = [{k: v for k, v in item.items() if k != "name"} for item in SAMPLE_ANSWERS]
    unnamed[2] = {"type": "banana"}
    respx.post(URL).mock(return_value=httpx.Response(200, json={"answers": unnamed}))
    answers = (await provider.evaluate(sample_request)).response.answers
    assert isinstance(answers["department"], ChoiceAnswer)
    assert isinstance(answers["frustration"], ScoreAnswer)
    assert answers["is_urgent"].cause == "invalid_output"
    assert "banana" in answers["is_urgent"].detail


@respx.mock
async def test_answers_claimed_by_name_are_not_reused_by_position(provider, sample_request):
    respx.post(URL).mock(return_value=httpx.Response(200, json={"answers": [SAMPLE_ANSWERS[2]]}))
    answers = (await provider.evaluate(sample_request)).response.answers
    assert answers["is_urgent"] == NoulAnswer(noul=0.97)
    assert answers["department"].cause == "invalid_output"
    assert answers["frustration"].cause == "invalid_output"


@respx.mock
async def test_malformed_answers_become_invalid_output_per_question(provider, sample_request):
    not_an_option = {**SAMPLE_ANSWERS[0], "choice": "zzz"}
    wrong_type = {"type": "choice", "name": "is_urgent", "choice": "x", "probabilities": []}
    body = {"answers": [not_an_option, SAMPLE_ANSWERS[1], wrong_type]}
    respx.post(URL).mock(return_value=httpx.Response(200, json=body))
    answers = (await provider.evaluate(sample_request)).response.answers
    assert answers["department"].cause == "invalid_output"
    assert isinstance(answers["frustration"], ScoreAnswer)
    assert answers["is_urgent"].cause == "invalid_output"


@respx.mock
async def test_score_levels_are_matched_by_label_then_position(provider, sample_request):
    """Whether Decisions numbers Levels from 0 or 1 is undocumented: the label the request
    sent, or failing that the entry's position, decides the Level index."""
    one_based = {
        "type": "score", "name": "frustration", "score": 2.2, "confidence": 0.5,
        "probabilities": [
            {"value": 1, "label": "Calm, just stating facts", "probability": 0.1},
            {"value": 2, "label": "Frustrated but civil", "probability": 0.6},
            {"value": 3, "label": "Very angry", "probability": 0.3},
        ],
    }  # fmt: skip
    entries = [{"value": value, "probability": p} for value, p in ((1, 0.1), (2, 0.6), (3, 0.3))]
    unlabeled = {"type": "score", "name": "frustration", "score": 2.2, "probabilities": entries}
    for item in (one_based, unlabeled):
        respx.post(URL).mock(return_value=httpx.Response(200, json={"answers": [item]}))
        frustration = (await provider.evaluate(sample_request)).response.answers["frustration"]
        assert isinstance(frustration, ScoreAnswer)
        assert frustration.probabilities == {"0": 0.1, "1": 0.6, "2": 0.3}
    assert frustration.legend is None


@respx.mock
async def test_timeout_after_retries_counts_every_attempt(provider, sample_request, monkeypatch):
    monkeypatch.setattr(http, "_backoff", lambda attempt: 0.0)
    route = respx.post(URL).mock(side_effect=httpx.ReadTimeout("slow"))
    result = await provider.evaluate(sample_request)
    assert route.call_count == 4 and result.attempts == 4
    assert causes(result) == {"timeout"}
    assert result.http_status is None and result.request_raw["model"] == "gpt-6-luna"


@respx.mock
async def test_body_without_answers_array_is_invalid_output(provider, sample_request):
    respx.post(URL).mock(return_value=httpx.Response(200, json={"id": "resp_1"}))
    result = await provider.evaluate(sample_request)
    assert causes(result) == {"invalid_output"}
    assert result.response.usage.input_tokens is None and result.cost_usd is None


@respx.mock
async def test_429_after_retries_is_rate_limited(provider, sample_request, monkeypatch):
    monkeypatch.setattr(http, "_backoff", lambda attempt: 0.0)
    body = {"error": {"message": "slow down"}}
    route = respx.post(URL).mock(return_value=httpx.Response(429, json=body))
    result = await provider.evaluate(sample_request)
    assert route.call_count == 4 and result.attempts == 4
    assert result.http_status == 429
    assert causes(result) == {"rate_limited"}
    assert "slow down" in result.error


@respx.mock
async def test_400_is_an_error_without_retry(provider, sample_request):
    body = {"error": {"message": "bad"}}
    route = respx.post(URL).mock(return_value=httpx.Response(400, json=body))
    result = await provider.evaluate(sample_request)
    assert route.call_count == 1 and result.attempts == 1
    assert causes(result) == {"error"}
