from __future__ import annotations

from typing import Any

import pytest

from bakeoff.datasets.case import Reference
from bakeoff.metrics import ResultRow, Scored, aggregate, options_count, score_answer
from bakeoff.stats import mcnemar, paired_bootstrap_diff
from bakeoff.systemone import (
    ChoiceAnswer,
    ChoiceQuestion,
    NonAnswer,
    NoulAnswer,
    NoulQuestion,
    ScoreAnswer,
    ScoreQuestion,
    score_confidence,
)

approx = pytest.approx


def test_noul_scoring() -> None:
    question = NoulQuestion(instructions="?")
    scored = score_answer(question, Reference(kind="gold", noul=True), NoulAnswer(noul=0.8))
    assert scored.correct
    assert (scored.prob_ref, scored.prob_pred) == (approx(0.8), approx(0.8))
    assert scored.confidence == approx(0.6)
    scored = score_answer(question, Reference(kind="gold", noul=False), NoulAnswer(noul=0.8))
    assert not scored.correct
    assert (scored.prob_ref, scored.prob_pred) == (approx(0.2), approx(0.8))
    assert score_answer(question, Reference(kind="gold", noul=True), NoulAnswer(noul=0.5)).correct


def test_choice_scoring() -> None:
    question = ChoiceQuestion(instructions="?", criteria={"a": None, "b": None, "c": None})
    reference = Reference(kind="gold", choice="b")
    answer = ChoiceAnswer(choice="b", probabilities={"a": 0.2, "b": 0.7, "c": 0.1})
    scored = score_answer(question, reference, answer)
    assert scored.correct and scored.prob_ref == approx(0.7) and scored.prob_pred == approx(0.7)
    answer = ChoiceAnswer(choice="a", probabilities={"a": 0.5, "b": 0.3, "c": 0.2})
    scored = score_answer(question, reference, answer)
    assert not scored.correct
    assert scored.prob_ref == approx(0.3) and scored.prob_pred == approx(0.5)
    scored = score_answer(question, reference, ChoiceAnswer(choice="a", probabilities={"a": 1.0}))
    assert scored.prob_ref == 0.0
    assert scored.confidence is None  # one entry is no distribution to be confident about


def test_choice_is_judged_on_the_selected_option_and_its_probability() -> None:
    question = ChoiceQuestion(instructions="?", criteria={"a": None, "b": None})
    off_argmax = ChoiceAnswer(choice="a", probabilities={"a": 0.2, "b": 0.8})
    scored = score_answer(question, Reference(kind="gold", choice="a"), off_argmax)
    assert scored.correct and scored.prob_pred == approx(0.2) and scored.prob_ref == approx(0.2)
    scored = score_answer(question, Reference(kind="gold", choice="b"), off_argmax)
    assert not scored.correct and scored.prob_pred == approx(0.2)
    empty = ChoiceAnswer(choice="a", probabilities={})
    scored = score_answer(question, Reference(kind="gold", choice="a"), empty)
    assert scored.correct and scored.prob_pred is None and scored.confidence is None


def test_vendor_confidence_is_replaced_by_the_recomputed_one() -> None:
    """docs/adr/0004 at the scoring boundary: the Provider's figure is never stored."""
    choice = ChoiceQuestion(instructions="?", criteria={"a": None, "b": None, "c": None})
    answer = ChoiceAnswer(
        choice="a", probabilities={"a": 0.85, "b": 0.0, "c": 0.15}, confidence=0.78
    )
    scored = score_answer(choice, Reference(kind="gold", choice="a"), answer)
    assert scored.confidence == approx(0.775)
    score = ScoreQuestion(instructions="?", criteria=["low", "mid", "high"])
    probabilities = {"0": 0.008423954913615923, "1": 0.199283458194343, "2": 0.7922925868920411}
    scored = score_answer(
        score,
        Reference(kind="gold", score=2),
        ScoreAnswer(score=1.7839, probabilities=probabilities, confidence=0.7839),
    )
    assert scored.confidence == approx(score_confidence(probabilities))
    assert abs(scored.confidence - 0.7839) > 0.05


def test_score_scoring_breaks_ties_toward_the_lowest_level() -> None:
    question = ScoreQuestion(instructions="?", criteria=["low", "mid", "high"])
    answer = ScoreAnswer(score=1.0, probabilities={"0": 0.1, "1": 0.8, "2": 0.1})
    scored = score_answer(question, Reference(kind="gold", score=1), answer)
    assert scored.correct and scored.prob_ref == approx(0.8) and scored.prob_pred == approx(0.8)
    tie = ScoreAnswer(score=0.8, probabilities={"0": 0.4, "1": 0.4, "2": 0.2})
    assert score_answer(question, Reference(kind="gold", score=0), tie).correct
    scored = score_answer(question, Reference(kind="gold", score=1), tie)
    assert not scored.correct
    assert scored.prob_ref == approx(0.4) and scored.prob_pred == approx(0.4)


def test_non_answer_and_type_mismatch_score_as_wrong() -> None:
    question = NoulQuestion(instructions="?")
    reference = Reference(kind="gold", noul=True)
    assert score_answer(question, reference, NonAnswer(cause="refusal")) == Scored(
        correct=False, non_answer_cause="refusal"
    )
    mismatch = ChoiceAnswer(choice="a", probabilities={"a": 1.0})
    scored = score_answer(question, reference, mismatch)
    assert not scored.correct and scored.non_answer_cause == "invalid_output"
    assert scored.prob_ref is None and scored.prob_pred is None


def test_options_count() -> None:
    assert options_count(NoulQuestion(instructions="?")) == 2
    assert options_count(ChoiceQuestion(instructions="?", criteria={"a": None, "b": None})) == 2
    assert options_count(ScoreQuestion(instructions="?", criteria=["1", "2", "3", "4"])) == 4


def make_row(case_id: str, **overrides: Any) -> ResultRow:
    base: dict[str, Any] = {
        "run_id": "r",
        "case_id": case_id,
        "question_id": "q",
        "rep": 0,
        "qtype": "choice",
        "n_options": 3,
        "reference_json": {"kind": "gold", "choice": "a"},
        "answer_json": {"type": "choice", "choice": "a", "probabilities": {"a": 1.0}},
        "correct": True,
        "prob_ref": 1.0,
        "prob_pred": 1.0,
        "confidence": 1.0,
        "latency_s": 1.0,
        "input_tokens": 100,
        "cost_usd": 0.001,
        "created_at": "2026-10-06T00:00:00+00:00",
    }
    return ResultRow.model_validate({**base, **overrides})


def choice_row(
    case_id: str, reference: str, choice: str, probabilities: dict[str, float], **kw: Any
) -> ResultRow:
    return make_row(
        case_id,
        reference_json={"kind": "gold", "choice": reference},
        answer_json={"type": "choice", "choice": choice, "probabilities": probabilities},
        correct=choice == reference,
        prob_ref=probabilities.get(reference, 0.0),
        prob_pred=max(probabilities.values()),
        **kw,
    )


def hand_built_rows() -> list[ResultRow]:
    return [
        choice_row("c0", "a", "a", {"a": 0.9, "b": 0.05, "c": 0.05}, latency_s=1.0),
        choice_row("c1", "b", "a", {"a": 0.6, "b": 0.3, "c": 0.1}, latency_s=2.0),
        choice_row("c2", "a", "a", {"a": 0.6, "b": 0.2, "c": 0.2}, latency_s=3.0),
        make_row(
            "c3",
            reference_json={"kind": "gold", "choice": "c"},
            answer_json={"type": "non_answer", "cause": "refusal"},
            non_answer_cause="refusal",
            correct=False,
            prob_ref=None,
            prob_pred=None,
            confidence=None,
            latency_s=4.0,
            over_limit=True,
        ),
    ]


def test_aggregate_on_hand_built_rows() -> None:
    metrics = aggregate(hand_built_rows())
    assert (metrics.n, metrics.n_answered) == (4, 3)
    assert metrics.n_correct == 2
    assert metrics.n_answered - metrics.n_correct == 1
    assert metrics.n - metrics.n_answered == 1
    assert metrics.accuracy == approx(0.5)
    assert metrics.accuracy_answered == approx(2 / 3)
    assert metrics.chance == approx(1 / 3)
    assert metrics.chance_corrected == approx(0.25)
    assert metrics.ece == approx(0.1)
    assert metrics.brier == approx((0.015 + 0.86 + 0.24) / 3)
    assert metrics.brier_binary == approx((0.01 + 0.49 + 0.16) / 3)
    assert metrics.macro_f1 == approx(0.8 / 3)
    assert metrics.non_answer_rate == approx(0.25)
    assert metrics.non_answers_by_cause == {"refusal": 1}
    assert metrics.latency_p50 == approx(2.5)
    assert metrics.latency_p95 == approx(3.85)
    assert metrics.mean_input_tokens == approx(100.0)
    assert metrics.cost_per_1k == approx(1.0)
    assert metrics.unknown_costs == 0
    assert metrics.over_limit_rate == approx(0.25)


def test_aggregate_edge_cases() -> None:
    empty = aggregate([])
    assert empty.n == 0 and empty.accuracy is None and empty.non_answers_by_cause == {}
    assert empty.n_correct == 0
    unanswered = aggregate([hand_built_rows()[-1]])
    assert (unanswered.n, unanswered.n_answered, unanswered.n_correct) == (1, 0, 0)
    assert unanswered.accuracy == 0.0 and unanswered.accuracy_answered is None
    rows = hand_built_rows()
    rows[0] = rows[0].model_copy(update={"cost_usd": None})
    metrics = aggregate(rows)
    assert metrics.cost_per_1k is None and metrics.unknown_costs == 1


def test_aggregate_counts_each_request_once() -> None:
    rows = [
        choice_row("c0", "a", "a", {"a": 1.0}, question_id="q1", latency_s=5.0, cost_usd=0.002),
        choice_row("c0", "a", "a", {"a": 1.0}, question_id="q2", latency_s=5.0, cost_usd=0.002),
        choice_row("c1", "a", "a", {"a": 1.0}, question_id="q1", latency_s=1.0, cost_usd=0.001),
    ]
    metrics = aggregate(rows)
    assert metrics.n == 3 and metrics.n_requests == 2
    assert metrics.n_correct == 3
    assert metrics.latency_p50 == approx(3.0)
    assert metrics.cost_per_1k == approx(1.5)


def test_aggregate_keeps_requests_of_different_runs_apart() -> None:
    """Rows pooled across Families reuse case ids; the run id tells their requests apart."""
    rows = [
        choice_row("c0", "a", "a", {"a": 1.0}, run_id="r1", latency_s=1.0, cost_usd=0.001),
        choice_row("c0", "a", "a", {"a": 1.0}, run_id="r2", latency_s=3.0, cost_usd=0.003),
    ]
    metrics = aggregate(rows)
    assert metrics.n_requests == 2
    assert metrics.latency_p50 == approx(2.0)
    assert metrics.cost_per_1k == approx(2.0)


def test_aggregate_latency_counts_only_requests_that_were_sent() -> None:
    rows = [
        choice_row("c0", "a", "a", {"a": 1.0}, latency_s=1.0, http_status=200),
        choice_row("c1", "a", "a", {"a": 1.0}, latency_s=3.0, http_status=None),  # a timeout
        make_row(
            "c2",
            answer_json={"type": "non_answer", "cause": "unsupported_modality"},
            non_answer_cause="unsupported_modality",
            correct=False,
            prob_ref=None,
            prob_pred=None,
            confidence=None,
            latency_s=0.0,
            http_status=None,
            cost_usd=0.0,
        ),
    ]
    metrics = aggregate(rows)
    assert (metrics.n_requests, metrics.n_requests_sent) == (3, 2)
    assert metrics.latency_p50 == approx(2.0)
    assert metrics.cost_per_1k == approx(1000 * (0.001 + 0.001 + 0.0) / 3)
    unsent = aggregate([rows[2]])
    assert unsent.n_requests_sent == 0 and unsent.latency_p50 is None


def test_noul_brier_and_macro_f1() -> None:
    rows = [
        make_row(
            "n0", qtype="noul", n_options=2,
            reference_json={"kind": "gold", "noul": True},
            answer_json={"type": "noul", "noul": 0.9}, correct=True, prob_ref=0.9, prob_pred=0.9,
        ),
        make_row(
            "n1", qtype="noul", n_options=2,
            reference_json={"kind": "gold", "noul": False},
            answer_json={"type": "noul", "noul": 0.9}, correct=False, prob_ref=0.1, prob_pred=0.9,
        ),
    ]  # fmt: skip
    metrics = aggregate(rows)
    assert metrics.chance == approx(0.5)
    assert metrics.brier == approx((2 * 0.1**2 + 2 * 0.9**2) / 2)
    # class True: tp 1, fp 1 -> P .5, R 1 -> F1 2/3; class False: tp 0 -> 0; macro 1/3
    assert metrics.macro_f1 == approx(1 / 3)


def test_bootstrap_and_mcnemar_on_identical_runs() -> None:
    correct = {f"c{index}": index % 2 == 0 for index in range(20)}
    assert paired_bootstrap_diff(correct, correct) == (0.0, 0.0, 0.0)
    assert mcnemar(correct, correct) == (0, 0, 1.0)


def test_bootstrap_and_mcnemar_detect_a_difference() -> None:
    always = {f"c{index}": True for index in range(30)}
    partial = {f"c{index}": index < 10 for index in range(30)}
    diff, low, high = paired_bootstrap_diff(always, partial, n_boot=500, seed=1)
    assert diff == approx(20 / 30)
    assert 0.0 < low <= diff <= high <= 1.0
    only_a, only_b, p_value = mcnemar(always, partial)
    assert (only_a, only_b) == (20, 0)
    assert p_value == approx(2 * 0.5**20)
    assert mcnemar({"x": True, "y": False}, {"y": True, "z": True}) == (0, 1, 1.0)
    with pytest.raises(ValueError, match="share no case ids"):
        mcnemar({"a": True}, {"b": True})
