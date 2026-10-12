from __future__ import annotations

import pytest
from pydantic import ValidationError

from bakeoff import pricing
from bakeoff.http import elide_images
from bakeoff.systemone import (
    ChoiceAnswer,
    ChoiceQuestion,
    NonAnswer,
    NoulAnswer,
    ScoreAnswer,
    ScoreQuestion,
    SystemOneRequest,
    SystemOneResponse,
    Usage,
    choice_confidence,
    expected_score,
    noul_confidence,
    recomputed_confidence,
    score_confidence,
)
from tests.conftest import TINY_PNG


def test_choice_confidence_matches_typesafe_quickstart_example():
    # docs.typesafe.ai quickstart: probabilities technical .85 / sales 0 / billing .15 -> 0.78
    # (3 * 0.85 - 1) / 2 = 0.775, which the docs display as 0.78
    assert choice_confidence({"technical": 0.85, "sales": 0.0, "billing": 0.15}) == pytest.approx(
        0.775
    )


def test_choice_confidence_matches_a_second_documented_example():
    probs = {
        "positive": 0.020649883775315993,
        "mixed": 0.9503497962668123,
        "negative": 0.02900031995787183,
    }
    assert round(choice_confidence(probs), 4) == 0.9255


def test_score_confidence_matches_typesafe_examples():
    assert score_confidence({"0": 0.0, "1": 1.0, "2": 0.0}) == 1.0  # quickstart: confidence 1.0
    # confidence explorer default [0, 5, 90, 5, 0]: spread 0.10, even_spread (2+1+0+1+2)/5 = 1.2
    assert score_confidence({"0": 0, "1": 5, "2": 90, "3": 5, "4": 0}) == pytest.approx(
        1 - 0.10 / 1.2
    )


def test_score_confidence_differs_from_another_vendors_field():
    # another vendor's documented score answer reports 0.7839 where TypeSafe's formula gives
    # about 0.68, which is why the harness recomputes confidence (ADR 0004)
    probs = {"0": 0.008423954913615923, "1": 0.199283458194343, "2": 0.7922925868920411}
    assert round(expected_score(probs), 4) == 1.7839
    assert abs(score_confidence(probs) - 0.7839) > 0.05


def test_recomputed_confidence_by_answer_type():
    assert recomputed_confidence(NoulAnswer(noul=0.95)) == pytest.approx(0.9)
    assert noul_confidence(0.5) == 0.0
    assert (
        recomputed_confidence(ChoiceAnswer(choice="a", probabilities={"a": 0.5, "b": 0.5})) == 0.0
    )
    assert recomputed_confidence(NonAnswer(cause="refusal")) is None
    assert recomputed_confidence(ScoreAnswer(score=1.0, probabilities={"0": 0, "1": 1})) == 1.0


def test_question_validation():
    with pytest.raises(ValidationError):
        ChoiceQuestion(instructions="x", criteria={"only": None})
    with pytest.raises(ValidationError):
        ScoreQuestion(instructions="x", criteria=[f"level {i}" for i in range(11)])
    with pytest.raises(ValidationError):
        SystemOneRequest(model="m", state="s", questions={})
    with pytest.raises(ValidationError):
        SystemOneRequest(
            model="m",
            state="s",
            questions={"q": {"type": "noul", "instructions": "?"}},
            images=["https://x/y.png"],
        )


def test_request_and_response_round_trip(sample_request):
    data = sample_request.model_dump(mode="json")
    assert set(data["questions"]) == {"department", "frustration", "is_urgent"}
    assert SystemOneRequest.model_validate(data) == sample_request
    response = SystemOneResponse.model_validate(
        {
            "model": "jev-1.13.0",
            "answers": {
                "department": {
                    "type": "choice",
                    "choice": "technical",
                    "confidence": 0.78,
                    "probabilities": {"technical": 0.85, "sales": 0.0, "billing": 0.15},
                },
                "frustration": {
                    "type": "score",
                    "score": 1.0,
                    "confidence": 1.0,
                    "legend": {"0": "Calm", "1": "Frustrated", "2": "Angry"},
                    "probabilities": {"0": 0.0, "1": 1.0, "2": 0.0},
                },
                "is_urgent": {"type": "noul", "noul": 1.0},
            },
            "usage": {"input_tokens": 392, "output_tokens": 65},
        }
    )
    assert isinstance(response.answers["department"], ChoiceAnswer)
    assert response.usage.input_tokens == 392


def test_choice_answer_must_name_an_option():
    with pytest.raises(ValidationError):
        ChoiceAnswer(choice="zzz", probabilities={"a": 1.0})


def test_elide_images_replaces_data_urls(image_request):
    elided = elide_images(image_request.model_dump(mode="json"))
    assert elided["images"][0]["$image"] == "image/png"
    assert elided["images"][0]["bytes"] > 0
    assert TINY_PNG not in str(elided)


def test_pricing_input_only_and_long_context():
    assert pricing.cost_usd(
        "jev-1.13.0", Usage(input_tokens=1_000_000, output_tokens=500)
    ) == pytest.approx(0.042)
    luna = pricing.cost_usd(
        "gpt-6-luna", Usage(input_tokens=1000, output_tokens=100, cached_tokens=500)
    )
    assert luna == pytest.approx((500 * 0.10 + 500 * 0.01 + 100 * 0.50) / 1e6)
    long_ctx = pricing.cost_usd("gpt-6-luna", Usage(input_tokens=300_000, output_tokens=0))
    assert long_ctx == pytest.approx(300_000 * 0.20 / 1e6)
    assert pricing.cost_usd("gpt-5.4-mini", Usage(input_tokens=10)) is None
    assert pricing.cost_usd(None, Usage(input_tokens=10)) is None


@pytest.mark.parametrize("input_tokens,rate", [(272_000, 0.10), (272_001, 0.20), (900_000, 0.20)])
def test_decisions_long_context_pricing(input_tokens, rate):
    usage = Usage(input_tokens=input_tokens, output_tokens=500)
    assert pricing.cost_usd("openai-decisions/gpt-6-luna", usage) == pytest.approx(
        input_tokens * rate / 1e6
    )


def test_luna_long_context_cached_input_pricing():
    usage = Usage(input_tokens=300_000, cached_tokens=200_000, output_tokens=100)
    assert pricing.cost_usd("gpt-6-luna", usage) == pytest.approx(
        (100_000 * 0.20 + 200_000 * 0.02 + 100 * 0.75) / 1e6
    )
