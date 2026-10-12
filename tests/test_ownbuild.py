from __future__ import annotations

import json
import math
from typing import Any

import httpx
import pytest
import respx
from pydantic import ValidationError

from bakeoff import http
from bakeoff.config import Settings
from bakeoff.ownbuild import engine as engine_module
from bakeoff.ownbuild.config import OwnBuildConfig
from bakeoff.ownbuild.engine import OwnBuildEngine, minimal_output_tokens
from bakeoff.ownbuild.logprobs import logprob_distributions
from bakeoff.ownbuild.prompt import render_questions, render_state
from bakeoff.ownbuild.schema import build_answer_schema, decode_answers
from bakeoff.providers import make_provider
from bakeoff.providers.ownbuild import build
from bakeoff.systemone import (
    ChoiceAnswer,
    ChoiceQuestion,
    NonAnswer,
    NoulAnswer,
    NoulQuestion,
    ScoreAnswer,
    SystemOneRequest,
    choice_confidence,
)
from tests.conftest import STATE, TINY_PNG
from tests.live import require_live
from tests.tokenizer import needs_tokenizer

COPILOT_URL = "http://127.0.0.1:17688/v1/responses"
OPENAI_URL = "https://api.openai.com/v1/responses"

PROBABILITIES_TEXT = json.dumps(
    {
        "department": {"probabilities": {"billing": 0.2, "technical": 0.7, "sales": 0.3}},
        "frustration": {"probabilities": {"0": 0.1, "1": 0.8, "2": 0.1}},
        "is_urgent": {"probability_yes": 1.5},
    }
)
DISCRETE_TEXT = (
    '{"department":{"choice":"technical"},"frustration":{"level":1},"is_urgent":{"answer":true}}'
)
USAGE = {
    "input_tokens": 100,
    "output_tokens": 20,
    "output_tokens_details": {"reasoning_tokens": 5},
    "input_tokens_details": {"cached_tokens": 10},
}
SINGLE_COST = (90 * 0.10 + 10 * 0.01 + 20 * 0.50) / 1e6

pytestmark = needs_tokenizer  # the engine measures the shortest answer against the output cap


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    monkeypatch.setattr(http, "_backoff", lambda attempt: 0.0)


def responses_body(
    text: str | None = None,
    *,
    status: str = "completed",
    refusal: str | None = None,
    logprobs: list[dict[str, Any]] | None = None,
    incomplete: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if refusal is not None:
        content: list[dict[str, Any]] = [{"type": "refusal", "refusal": refusal}]
    else:
        part: dict[str, Any] = {"type": "output_text", "text": text, "annotations": []}
        if logprobs is not None:
            part["logprobs"] = logprobs
        content = [part]
    message = {"type": "message", "id": "msg_1", "role": "assistant", "content": content}
    return {
        "id": "resp_1",
        "object": "response",
        "status": status,
        "model": "gpt-6-luna",
        "incomplete_details": incomplete,
        "output": [{"type": "reasoning", "id": "rs_1", "summary": []}, message],
        "usage": USAGE,
    }


def mock_copilot(body: dict[str, Any]) -> respx.Route:
    return respx.post(COPILOT_URL).mock(return_value=httpx.Response(200, json=body))


def engine_for(settings: Settings, **fields: Any) -> OwnBuildEngine:
    return OwnBuildEngine(OwnBuildConfig(route="copilot", **fields), settings)


def openai_engine(settings: Settings, **fields: Any) -> OwnBuildEngine:
    return OwnBuildEngine(OwnBuildConfig(route="openai", **fields), settings)


def sent_body(route: respx.Route) -> dict[str, Any]:
    return json.loads(route.calls.last.request.content)


def causes(result) -> set[str]:
    return {answer.cause for answer in result.response.answers.values()}


# --- Probabilities and discrete modes -----------------------------------------------------


@respx.mock
async def test_probabilities_are_parsed_and_normalized(settings, sample_request):
    route = mock_copilot(responses_body(PROBABILITIES_TEXT))
    engine = engine_for(settings, effort="low", cap=512)
    result = await engine.evaluate(sample_request)
    await engine.aclose()

    answers = result.response.answers
    department = answers["department"]
    assert isinstance(department, ChoiceAnswer)
    assert department.choice == "technical"
    expected = {"billing": 0.2 / 1.2, "technical": 0.7 / 1.2, "sales": 0.3 / 1.2}
    assert department.probabilities == pytest.approx(expected)
    assert department.confidence == pytest.approx(choice_confidence(expected))
    frustration = answers["frustration"]
    assert isinstance(frustration, ScoreAnswer)
    assert frustration.score == pytest.approx(1.0)
    assert frustration.legend == {
        "0": "Calm, just stating facts",
        "1": "Frustrated but civil",
        "2": "Very angry",
    }
    assert answers["is_urgent"] == NoulAnswer(noul=1.0)  # 1.5 clamped into [0, 1]

    usage = result.response.usage
    assert (usage.input_tokens, usage.output_tokens) == (100, 20)
    assert (usage.reasoning_tokens, usage.cached_tokens) == (5, 10)
    assert result.cost_usd == pytest.approx(SINGLE_COST)
    assert result.http_status == 200
    assert result.error is None
    assert result.request_raw["meta"] == {"route": "copilot", "truncated": False, "samples": 1}
    assert result.response_raw == [responses_body(PROBABILITIES_TEXT)]  # one body per sample

    body = sent_body(route)
    assert body["max_output_tokens"] == 512
    assert body["reasoning"] == {"effort": "low"}
    text_format = body["text"]["format"]
    assert (text_format["type"], text_format["strict"]) == ("json_schema", True)
    assert "include" not in body
    assert body["input"][0]["role"] == "system"
    assert "noul" in body["input"][0]["content"]


@respx.mock
async def test_discrete_mode_gives_one_hot_answers(settings, sample_request):
    route = mock_copilot(responses_body(DISCRETE_TEXT))
    engine = engine_for(settings, mode="discrete")
    result = await engine.evaluate(sample_request)

    answers = result.response.answers
    assert answers["department"].choice == "technical"
    assert answers["department"].probabilities == {"billing": 0.0, "technical": 1.0, "sales": 0.0}
    assert answers["frustration"].score == 1.0
    assert answers["frustration"].probabilities == {"0": 0.0, "1": 1.0, "2": 0.0}
    assert answers["is_urgent"].noul == 1.0

    schema = sent_body(route)["text"]["format"]["schema"]
    department = schema["properties"]["department"]["properties"]["choice"]
    assert department["enum"] == ["billing", "technical", "sales"]
    assert schema["properties"]["frustration"]["properties"]["level"]["enum"] == [0, 1, 2]
    assert schema["properties"]["is_urgent"]["properties"]["answer"] == {"type": "boolean"}


def test_schema_is_strict_and_maps_unsafe_names_back():
    questions = {
        "needs follow-up?": ChoiceQuestion(
            instructions="?",
            criteria={"Payment / billing": "money", "Payment_billing": None, "ok": "fine"},
        ),
        "is_urgent": NoulQuestion(instructions="?"),
    }
    answer_schema = build_answer_schema(questions, discrete=False)
    assert answer_schema.questions.to_safe == {
        "needs follow-up?": "needs_follow_up",
        "is_urgent": "is_urgent",
    }
    assert answer_schema.options["needs follow-up?"].to_safe == {
        "Payment / billing": "Payment_billing",
        "Payment_billing": "Payment_billing_2",
        "ok": "ok",
    }
    for node in _objects(answer_schema.schema):
        assert node["additionalProperties"] is False
        assert node["required"] == list(node["properties"])

    data = {
        "needs_follow_up": {
            "probabilities": {"Payment_billing": 0.5, "Payment_billing_2": 0.25, "ok": 0.25}
        },
        "is_urgent": {"probability_yes": "high"},
    }
    answers = decode_answers(data, questions, answer_schema)
    follow_up = answers["needs follow-up?"]
    assert follow_up.choice == "Payment / billing"
    assert follow_up.probabilities == {
        "Payment / billing": 0.5,
        "Payment_billing": 0.25,
        "ok": 0.25,
    }
    assert answers["is_urgent"] == NonAnswer(
        cause="invalid_output", detail="is_urgent: probability_yes is not a number"
    )

    rendered = render_questions(questions, answer_schema)
    assert '## Question "needs_follow_up" (choice)' in rendered
    assert '- Payment_billing (Option "Payment / billing"): money' in rendered
    assert "- ok: fine" in rendered


def _objects(node: Any):
    if isinstance(node, dict):
        if node.get("type") == "object":
            yield node
        for value in node.values():
            yield from _objects(value)


def test_structured_state_is_sent_compact_as_it_is_measured():
    state = [{"id": i, "body": "some ticket text"} for i in range(3)]
    text = render_state(state, has_image=False)
    assert json.dumps(state, separators=(",", ":")) in text
    assert "\n  " not in text  # no pretty-printing: what is counted is what is sent


# --- Failure modes become Non-answers ------------------------------------------------------


@respx.mock
async def test_incomplete_response_is_truncated_output(settings, sample_request):
    body = responses_body(
        '{"department": {"prob', status="incomplete", incomplete={"reason": "max_output_tokens"}
    )
    mock_copilot(body)
    result = await engine_for(settings, cap=64).evaluate(sample_request)
    assert causes(result) == {"truncated_output"}
    assert result.error == "max_output_tokens"
    assert result.response.usage.input_tokens == 100  # still billed (docs/adr/0003)
    assert result.cost_usd == pytest.approx(SINGLE_COST)


@pytest.mark.respx(assert_all_called=False)
async def test_a_cap_below_the_shortest_answer_is_not_sent(settings, sample_request, respx_mock):
    route = respx_mock.post(COPILOT_URL).mock(return_value=httpx.Response(200, json={}))
    answer_schema = build_answer_schema(sample_request.questions, discrete=False)
    floor = minimal_output_tokens(sample_request.questions, answer_schema)
    assert floor > 8
    result = await engine_for(settings, cap=8).evaluate(sample_request)
    assert route.call_count == 0
    assert causes(result) == {"truncated_output"}
    assert f"output cap 8 is below the {floor} tokens" in result.error
    assert (result.cost_usd, result.attempts, result.http_status) == (0.0, 0, None)
    assert result.request_raw["meta"]["samples"] == 1
    discrete = build_answer_schema(sample_request.questions, discrete=True)
    assert minimal_output_tokens(sample_request.questions, discrete) < floor


@respx.mock
async def test_invalid_json_is_invalid_output(settings, sample_request):
    mock_copilot(responses_body("not json {"))
    result = await engine_for(settings).evaluate(sample_request)
    assert causes(result) == {"invalid_output"}
    assert result.error.startswith("invalid JSON")


@respx.mock
async def test_refusal_part_is_refusal(settings, sample_request):
    mock_copilot(responses_body(refusal="I cannot help with that."))
    result = await engine_for(settings).evaluate(sample_request)
    assert causes(result) == {"refusal"}
    assert result.response.answers["department"].detail == "I cannot help with that."


@respx.mock
async def test_filtered_error_body_is_filtered(settings, sample_request):
    error = {
        "error": {"message": "Request blocked by the content filter", "code": "content_filter"}
    }
    respx.post(COPILOT_URL).mock(return_value=httpx.Response(400, json=error))
    result = await engine_for(settings).evaluate(sample_request)
    assert causes(result) == {"filtered"}
    assert result.http_status == 400
    assert result.response_raw == [error]
    assert result.cost_usd is None

    by_code = {"error": {"message": "Blocked", "code": "content_policy_violation"}}
    respx.post(COPILOT_URL).mock(return_value=httpx.Response(400, json=by_code))
    assert causes(await engine_for(settings).evaluate(sample_request)) == {"filtered"}


@respx.mock
async def test_a_429_mentioning_policy_is_rate_limited_not_filtered(settings, sample_request):
    body = {"error": {"message": "Rate limit exceeded per usage policy", "code": "rate_limit"}}
    respx.post(COPILOT_URL).mock(return_value=httpx.Response(429, json=body))
    result = await engine_for(settings).evaluate(sample_request)
    assert causes(result) == {"rate_limited"}
    plain = {"error": {"message": "Your request violates our usage policy", "code": "x"}}
    respx.post(COPILOT_URL).mock(return_value=httpx.Response(400, json=plain))
    assert causes(await engine_for(settings).evaluate(sample_request)) == {"error"}


@respx.mock
async def test_copilot_route_stops_at_the_first_429(settings, sample_request):
    route = respx.post(COPILOT_URL).mock(
        return_value=httpx.Response(429, headers={"retry-after": "0"}, json={"error": "slow"})
    )
    result = await engine_for(settings).evaluate(sample_request)
    assert causes(result) == {"rate_limited"}
    assert route.call_count == 1 and result.attempts == 1  # docs/adr/0002: no retry


@respx.mock
async def test_openai_route_retries_and_counts_every_attempt(settings, sample_request):
    route = respx.post(OPENAI_URL).mock(
        return_value=httpx.Response(429, headers={"retry-after": "0"}, json={"error": "slow"})
    )
    result = await openai_engine(settings, effort="none").evaluate(sample_request)
    assert causes(result) == {"rate_limited"}
    assert route.call_count == 4 and result.attempts == 4

    route.mock(side_effect=httpx.ReadTimeout("slow"))
    result = await openai_engine(settings, effort="none").evaluate(sample_request)
    assert causes(result) == {"timeout"}
    assert route.call_count == 8 and result.attempts == 4  # every attempt timed out
    assert result.http_status is None and result.latency_s > 0.0


@respx.mock
async def test_latency_is_the_answering_attempts_time(settings, sample_request):
    route = respx.post(OPENAI_URL).mock(
        side_effect=[
            httpx.Response(503, headers={"retry-after": "0.2"}, text="down"),
            httpx.Response(200, json=responses_body(PROBABILITIES_TEXT)),
        ]
    )
    result = await openai_engine(settings, effort="none").evaluate(sample_request)
    assert route.call_count == 2 and result.attempts == 2
    assert result.http_status == 200
    assert result.latency_s < 0.15  # the 0.2 s wait before the second attempt is not latency


# --- Request shape -------------------------------------------------------------------------


@respx.mock
async def test_image_becomes_an_input_image_part(settings, image_request):
    route = mock_copilot(responses_body(PROBABILITIES_TEXT))
    result = await engine_for(settings).evaluate(image_request)

    user = sent_body(route)["input"][1]
    assert user["role"] == "user"
    assert [part["type"] for part in user["content"]] == ["input_text", "input_image", "input_text"]
    assert user["content"][1]["image_url"] == TINY_PNG
    assert "The attached image is part of the State." in user["content"][0]["text"]
    assert STATE in user["content"][0]["text"]
    assert "Which team should handle this?" in user["content"][2]["text"]

    captured = result.request_raw["input"][1]["content"][1]["image_url"]
    assert captured["$image"] == "image/png"
    assert TINY_PNG not in json.dumps(result.request_raw)


@respx.mock
async def test_max_in_truncates_the_state_and_flags_it(settings, sample_request, monkeypatch):
    def cut_words(state, max_tokens):
        words = state.split()
        if len(words) <= max_tokens:
            return state, False
        return " ".join(words[:max_tokens]), True

    monkeypatch.setattr(engine_module, "truncate_state", cut_words)
    route = mock_copilot(responses_body(PROBABILITIES_TEXT))
    result = await engine_for(settings, max_in=4).evaluate(sample_request)
    assert result.request_raw["meta"]["truncated"] is True
    state_text = sent_body(route)["input"][1]["content"][0]["text"]
    assert state_text.endswith("Hi, I've been trying")
    assert STATE not in state_text

    result = await engine_for(settings, max_in=1000).evaluate(sample_request)
    assert result.request_raw["meta"]["truncated"] is False
    assert STATE in sent_body(route)["input"][1]["content"][0]["text"]


@respx.mock
async def test_copilot_route_prefixes_the_model_and_sends_no_auth(settings, sample_request):
    route = mock_copilot(responses_body(PROBABILITIES_TEXT))
    await engine_for(settings).evaluate(sample_request)
    assert sent_body(route)["model"] == "github-copilot/gpt-6-luna"
    assert "authorization" not in route.calls.last.request.headers
    already = OwnBuildConfig(route="copilot", model="github-copilot/gpt-6-luna")
    engine = OwnBuildEngine(already, settings)
    assert engine.model_id == "github-copilot/gpt-6-luna"
    assert engine.price_key == "gpt-6-luna"  # the prefix does not hide the price


@respx.mock
async def test_openai_route_sends_bearer_and_never_temperature(settings, sample_request):
    route = respx.post(OPENAI_URL).mock(
        return_value=httpx.Response(200, json=responses_body(PROBABILITIES_TEXT))
    )
    engine = OwnBuildEngine(OwnBuildConfig(route="openai", effort="none"), settings)
    result = await engine.evaluate(sample_request)
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer sk-test"
    body = json.loads(request.content)
    assert body["model"] == "gpt-6-luna"
    assert "temperature" not in body
    assert body["reasoning"] == {"effort": "none"}
    assert "sk-test" not in json.dumps(result.request_raw)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        OwnBuildEngine(OwnBuildConfig(route="openai"), Settings())


# --- Samples -------------------------------------------------------------------------------


@respx.mock
async def test_samples_average_distributions_and_sum_usage(settings, sample_request):
    first = {
        "department": {"probabilities": {"billing": 0.2, "technical": 0.8, "sales": 0.0}},
        "frustration": {"probabilities": {"0": 0.0, "1": 1.0, "2": 0.0}},
        "is_urgent": {"probability_yes": 0.9},
    }
    second = {
        "department": {"probabilities": {"billing": 0.6, "technical": 0.4, "sales": 0.0}},
        "frustration": {"probabilities": {"0": 1.0, "1": 0.0, "2": 0.0}},
        "is_urgent": {"probability_yes": 0.5},
    }
    route = respx.post(COPILOT_URL).mock(
        side_effect=[
            httpx.Response(200, json=responses_body(json.dumps(first))),
            httpx.Response(200, json=responses_body(json.dumps(second))),
        ]
    )
    result = await engine_for(settings, samples=2).evaluate(sample_request)
    assert route.call_count == 2

    answers = result.response.answers
    expected = {"billing": 0.4, "technical": 0.6, "sales": 0.0}
    assert answers["department"].probabilities == pytest.approx(expected)
    assert answers["department"].choice == "technical"
    assert answers["frustration"].probabilities == pytest.approx({"0": 0.5, "1": 0.5, "2": 0.0})
    assert answers["frustration"].score == pytest.approx(0.5)
    assert answers["is_urgent"].noul == pytest.approx(0.7)

    usage = result.response.usage
    assert (usage.input_tokens, usage.output_tokens) == (200, 40)
    assert (usage.reasoning_tokens, usage.cached_tokens) == (10, 20)
    assert result.cost_usd == pytest.approx(2 * SINGLE_COST)
    assert result.attempts == 2
    assert isinstance(result.response_raw, list)
    assert len(result.response_raw) == 2
    assert result.request_raw["meta"]["samples"] == 2


@respx.mock
async def test_a_failed_sample_makes_the_question_a_non_answer(settings, sample_request):
    respx.post(COPILOT_URL).mock(
        side_effect=[
            httpx.Response(200, json=responses_body(PROBABILITIES_TEXT)),
            httpx.Response(200, json=responses_body(refusal="no")),
        ]
    )
    result = await engine_for(settings, samples=2).evaluate(sample_request)
    assert causes(result) == {"refusal"}
    assert result.response.usage.input_tokens == 200


@respx.mock
async def test_copilot_samples_run_in_turn_and_stop_after_a_failed_call(settings, sample_request):
    route = respx.post(COPILOT_URL).mock(
        side_effect=[
            httpx.Response(429, json={"error": "slow"}),
            httpx.Response(200, json=responses_body(PROBABILITIES_TEXT)),
        ]
    )
    result = await engine_for(settings, samples=3).evaluate(sample_request)
    assert route.call_count == 1  # the second and third samples were never sent
    assert causes(result) == {"rate_limited"}
    assert result.attempts == 1 and len(result.response_raw) == 1
    assert result.response.usage.input_tokens is None and result.cost_usd is None


def test_estimate_covers_samples_and_the_output_cap(settings):
    engine = engine_for(settings, cap=512, samples=2)
    assert engine.estimate_cost_usd(1000) == pytest.approx(2 * (1000 * 0.10 + 512 * 0.50) / 1e6)
    assert engine_for(settings).estimate_cost_usd(1000) == pytest.approx(1000 * 0.10 / 1e6)
    assert engine_for(settings).estimate_cost_usd(None) == 0.0
    assert engine_for(settings, model="gpt-6-pro").estimate_cost_usd(1000) == 0.0  # unpriced


# --- Logprobs mode -------------------------------------------------------------------------

PIECES = [
    '{"', "department", '":{"', "choice", '":"', "technical", '"},"', "frustration", '":{"',
    "level", '":', "1", '},"', "is", "_urgent", '":{"', "answer", '":', "true", "}}",
]  # fmt: skip
TOP = {
    "technical": [("technical", 0.7), ("bill", 0.2), ("sales", 0.1)],
    "1": [("1", 0.6), ("2", 0.3), ("0", 0.1)],
    "true": [("true", 0.8), ("false", 0.2)],
}


def synthetic_logprobs(pieces: list[str], top: dict[str, list[tuple[str, float]]]):
    entries = []
    for piece in pieces:
        alternatives = [{"token": tok, "logprob": math.log(p)} for tok, p in top.get(piece, [])]
        logprob = alternatives[0]["logprob"] if alternatives else 0.0
        entries.append({"token": piece, "logprob": logprob, "top_logprobs": alternatives})
    return entries


@respx.mock
async def test_logprobs_mode_derives_distributions(settings, sample_request):
    assert "".join(PIECES) == DISCRETE_TEXT
    body = responses_body(DISCRETE_TEXT, logprobs=synthetic_logprobs(PIECES, TOP))
    route = respx.post(OPENAI_URL).mock(return_value=httpx.Response(200, json=body))
    config = OwnBuildConfig(route="openai", effort="none", mode="logprobs")
    result = await OwnBuildEngine(config, settings).evaluate(sample_request)

    sent = sent_body(route)
    assert sent["include"] == ["message.output_text.logprobs"]
    assert sent["top_logprobs"] == 20
    department = sent["text"]["format"]["schema"]["properties"]["department"]
    assert department["properties"]["choice"]["enum"]

    answers = result.response.answers
    expected = {"billing": 0.2, "technical": 0.7, "sales": 0.1}
    assert answers["department"].probabilities == pytest.approx(expected)
    assert answers["department"].choice == "technical"
    assert answers["frustration"].probabilities == pytest.approx({"0": 0.1, "1": 0.6, "2": 0.3})
    assert answers["frustration"].score == pytest.approx(1.2)
    assert answers["is_urgent"].noul == pytest.approx(0.8)


@respx.mock
async def test_logprobs_credit_a_shared_first_token_to_the_sampled_option(settings):
    request = SystemOneRequest(
        model="x",
        state="where is my card",
        questions={
            "intent": ChoiceQuestion(
                instructions="?",
                criteria={"card_arrival": None, "card_delivery_estimate": None, "cash": None},
            )
        },
    )
    text = '{"intent":{"choice":"card_delivery_estimate"}}'
    pieces = ['{"intent":{"choice":"', "card", "_delivery", "_estimate", '"}}']
    top = {"card": [("card", 0.8), ("cash", 0.2)]}
    assert "".join(pieces) == text
    body = responses_body(text, logprobs=synthetic_logprobs(pieces, top))
    respx.post(OPENAI_URL).mock(return_value=httpx.Response(200, json=body))
    config = OwnBuildConfig(route="openai", effort="none", mode="logprobs")
    result = await OwnBuildEngine(config, settings).evaluate(request)

    intent = result.response.answers["intent"]
    assert intent.choice == "card_delivery_estimate"  # what the model answered, kept
    expected = {"card_arrival": 0.0, "card_delivery_estimate": 0.8, "cash": 0.2}
    assert intent.probabilities == pytest.approx(expected)

    # Without the sampled value, an ambiguous token is split rather than counted twice.
    answer_schema = build_answer_schema(request.questions, discrete=True)
    derived = logprob_distributions(
        text, synthetic_logprobs(pieces, top), request.questions, answer_schema
    )
    assert derived["intent"] == pytest.approx(
        {"card_arrival": 0.4, "card_delivery_estimate": 0.4, "cash": 0.2}
    )


def test_logprobs_keep_one_hot_when_only_the_sampled_token_matches(sample_request):
    answer_schema = build_answer_schema(sample_request.questions, discrete=True)
    garbage = {"technical": [("xyz", 0.9)], "1": [("x", 0.5)], "true": [("?", 0.5)]}
    derived = logprob_distributions(
        DISCRETE_TEXT, synthetic_logprobs(PIECES, garbage), sample_request.questions, answer_schema
    )
    assert derived["department"] == {"billing": 0.0, "technical": 1.0, "sales": 0.0}
    assert derived["frustration"] == {"0": 0.0, "1": 1.0, "2": 0.0}
    assert derived["is_urgent"] == {"true": 1.0, "false": 0.0}


def test_logprobs_are_ignored_when_tokens_do_not_match_the_text(sample_request):
    questions = sample_request.questions
    answer_schema = build_answer_schema(questions, discrete=True)
    misaligned = synthetic_logprobs(PIECES[:-1], TOP)
    assert logprob_distributions(DISCRETE_TEXT, misaligned, questions, answer_schema) == {}
    assert logprob_distributions(DISCRETE_TEXT, [], questions, answer_schema) == {}


def test_logprobs_handle_a_token_that_straddles_the_quote(sample_request):
    pieces = [
        '{"department":{"choice":',
        '"tech',
        'nical"},"frustration":{"level":1},',
        '"is_urgent":{"answer":true}}',
    ]
    top = {'"tech': [('"tech', 0.5), ('"bill', 0.3), ('"sales"', 0.2)]}
    answer_schema = build_answer_schema(sample_request.questions, discrete=True)
    derived = logprob_distributions(
        DISCRETE_TEXT, synthetic_logprobs(pieces, top), sample_request.questions, answer_schema
    )
    assert derived["department"] == pytest.approx({"billing": 0.3, "technical": 0.5, "sales": 0.2})
    assert derived["frustration"] == {"0": 0.0, "1": 1.0, "2": 0.0}  # sampled token only


def test_logprobs_mode_needs_openai_route_and_no_reasoning(settings):
    with pytest.raises(ValidationError, match="logprobs"):
        OwnBuildConfig(route="openai", mode="logprobs", effort="low")
    with pytest.raises(ValueError, match="logprobs"):
        build("ownbuild/copilot/gpt-6-luna?mode=logprobs&effort=none", settings)
    with pytest.raises(ValueError, match="logprobs"):
        build("ownbuild/openai/gpt-6-luna?mode=logprobs", settings)
    provider = build("ownbuild/openai/gpt-6-luna?mode=logprobs&effort=none", settings)
    assert provider.config.mode == "logprobs"


# --- Provider adapter ----------------------------------------------------------------------


def test_spec_is_normalized_in_the_documented_key_order(settings):
    query = "samples=1&mode=probabilities&max_in=64000&cap=512&effort=low"
    provider = make_provider(f"ownbuild/copilot/gpt-6-luna?{query}", settings)
    normalized = "effort=low&cap=512&max_in=64000&mode=probabilities&samples=1"
    assert provider.id == f"ownbuild/copilot/gpt-6-luna?{normalized}"
    assert provider.model == "gpt-6-luna"
    assert provider.max_input_tokens == 64000
    assert provider.concurrency == 2
    assert provider.price_key == "gpt-6-luna"
    assert provider.supports_images is True

    openai = make_provider("ownbuild/openai/gpt-6-luna", settings)
    assert openai.id == "ownbuild/openai/gpt-6-luna?mode=probabilities&samples=1"
    assert openai.max_input_tokens is None  # no documented limit; max_in is the only cap
    assert openai.concurrency == 8
    assert make_provider("ownbuild/copilot", settings).model == "gpt-6-luna"
    assert make_provider("ownbuild/copilot/gpt-6-luna?effort=", settings).config.effort is None

    with pytest.raises(ValueError, match="bogus"):
        build("ownbuild/copilot/gpt-6-luna?bogus=1", settings)
    with pytest.raises(ValueError, match="route"):
        build("ownbuild", settings)
    with pytest.raises(ValidationError):
        build("ownbuild/bedrock/gpt-6-luna", settings)
    with pytest.raises(ValidationError):
        build("ownbuild/copilot/gpt-6-luna?samples=0", settings)


def test_price_key_follows_the_model(settings):
    mini = make_provider("ownbuild/copilot/gpt-5.4-mini", settings)
    assert mini.price_key == "gpt-5.4-mini"  # listed, unpriced: cost reads unknown
    assert mini.estimate_cost_usd(10_000) == 0.0
    unknown = make_provider("ownbuild/openai/gpt-6-pro", settings)
    assert unknown.price_key is None
    luna = make_provider("ownbuild/openai/gpt-6-luna?cap=512&samples=2", settings)
    assert luna.estimate_cost_usd(1000) == pytest.approx(2 * (1000 * 0.10 + 512 * 0.50) / 1e6)


@respx.mock
async def test_provider_evaluates_in_process(settings, sample_request):
    mock_copilot(responses_body(PROBABILITIES_TEXT))
    provider = make_provider("ownbuild/copilot/gpt-6-luna?effort=low", settings)
    result = await provider.evaluate(sample_request)
    await provider.aclose()
    assert result.provider_id == provider.id
    assert isinstance(result.response.answers["department"], ChoiceAnswer)
    assert result.cost_usd == pytest.approx(SINGLE_COST)


# --- Live ----------------------------------------------------------------------------------


@pytest.mark.live
async def test_live_aiproxy_answers_the_stripe_sample(settings, sample_request: SystemOneRequest):
    require_live()
    try:
        async with httpx.AsyncClient(timeout=3.0) as probe:
            await probe.get(settings.aiproxy_base_url + "/models")
    except httpx.HTTPError:
        pytest.skip("aiproxy is not reachable")
    engine = engine_for(settings, effort="low", cap=512)
    result = await engine.evaluate(sample_request)
    await engine.aclose()
    print(json.dumps(result.response_raw, indent=1)[:3000])  # shown with -s: the live shape
    assert result.error is None, result.error
    assert isinstance(result.response.answers["department"], ChoiceAnswer)
    assert result.response.answers["department"].choice == "technical"
