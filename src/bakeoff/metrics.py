"""Scoring one Answer against its Reference, and aggregating a Run's rows into metrics."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

import numpy as np
from pydantic import BaseModel, TypeAdapter, ValidationError

from bakeoff.datasets.case import Reference
from bakeoff.systemone import (
    Answer,
    ChoiceAnswer,
    ChoiceQuestion,
    NonAnswer,
    NoulAnswer,
    NoulQuestion,
    Question,
    ScoreAnswer,
    ScoreQuestion,
    normalize_probabilities,
    recomputed_confidence,
)

ECE_BINS = 10
_ANSWER = TypeAdapter(Answer)


class Scored(BaseModel):
    """How one Answer fared. A Choice is judged on the Option the Provider selected and a
    Score on the harness argmax of its Levels (``score`` is an expectation, not a Level);
    ``prob_pred`` is the probability the Answer gave that judged Option or Level."""

    correct: bool
    prob_ref: float | None = None  # probability the Answer gave the reference Option or Level
    prob_pred: float | None = None  # probability of the judged Option or Level
    confidence: float | None = None  # recomputed from the probabilities (docs/adr/0004)
    non_answer_cause: str | None = None


class ResultRow(BaseModel):
    """One scored Question of one Case evaluation: the unit the store persists.

    ``latency_s``, the token counts and ``cost_usd`` describe the whole request, so every
    Question of one Case carries the same values; aggregates dedupe them per request.
    ``latency_s`` is the wall time of the HTTP attempt that answered; a request that failed
    after retries carries the whole time it took, backoff included. A request the harness
    never sent (a text-only Provider given an image, an unreadable Case) has no
    ``http_status`` and a latency of zero.
    """

    run_id: str
    case_id: str
    question_id: str
    rep: int
    qtype: str
    n_options: int
    reference_json: dict[str, Any]
    answer_json: dict[str, Any]
    non_answer_cause: str | None = None
    correct: bool
    prob_ref: float | None = None
    prob_pred: float | None = None
    confidence: float | None = None
    latency_s: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    cached_tokens: int | None = None
    cost_usd: float | None = None
    http_status: int | None = None
    attempts: int = 1
    over_limit: bool = False
    created_at: str


class RunMetrics(BaseModel):
    n: int
    n_answered: int
    n_correct: int = 0
    accuracy: float | None = None  # Non-answers count as wrong (docs/adr/0003)
    accuracy_answered: float | None = None  # over rows that produced an Answer; None if none did
    macro_f1: float | None = None  # Choice and Noul rows only
    chance: float | None = None  # mean over rows of 1 / n_options
    chance_corrected: float | None = None  # (accuracy - chance) / (1 - chance)
    ece: float | None = None  # 10 equal-width bins on prob_pred, answered rows only
    brier: float | None = None  # multiclass Brier over answered rows with probabilities
    brier_binary: float | None = None  # (1 - prob_ref)^2 over answered rows
    non_answer_rate: float | None = None
    non_answers_by_cause: dict[str, int]
    n_requests: int = 0  # (case, rep) evaluations
    n_requests_sent: int = 0  # of which reached the Provider
    latency_p50: float | None = None  # per request sent
    latency_p95: float | None = None  # per request sent
    mean_input_tokens: float | None = None  # per request
    cost_per_1k: float | None = None  # USD per 1000 requests (Cases); None if any cost unknown
    unknown_costs: int = 0  # requests whose cost is unknown
    over_limit_rate: float | None = None


def options_count(question: Question) -> int:
    match question:
        case NoulQuestion():
            return 2
        case ChoiceQuestion():
            return len(question.criteria)
        case ScoreQuestion():
            return len(question.criteria)
    raise TypeError(f"unknown question type {type(question).__name__}")


def score_answer(question: Question, reference: Reference, answer: Answer) -> Scored:
    """Score one Answer. A Non-answer or an Answer of the wrong type is wrong, no probabilities."""
    if isinstance(answer, NonAnswer):
        return Scored(correct=False, non_answer_cause=answer.cause)
    confidence = recomputed_confidence(answer)
    if isinstance(answer, ChoiceAnswer | ScoreAnswer) and len(answer.probabilities) < 2:
        confidence = None  # no distribution to be confident about
    match question, answer:
        case NoulQuestion(), NoulAnswer() if reference.noul is not None:
            return _score_noul(reference.noul, answer.noul, confidence)
        case ChoiceQuestion(), ChoiceAnswer() if reference.choice is not None:
            return _score_choice(reference.choice, answer, confidence)
        case ScoreQuestion(), ScoreAnswer() if reference.score is not None:
            return _score_score(reference.score, answer, confidence)
    return Scored(correct=False, non_answer_cause="invalid_output")


def _score_noul(reference: bool, noul: float, confidence: float | None) -> Scored:
    return Scored(
        correct=(noul >= 0.5) == reference,
        prob_ref=noul if reference else 1.0 - noul,
        prob_pred=max(noul, 1.0 - noul),
        confidence=confidence,
    )


def _score_choice(reference: str, answer: ChoiceAnswer, confidence: float | None) -> Scored:
    probabilities = normalize_probabilities(answer.probabilities)
    return Scored(
        correct=answer.choice == reference,
        prob_ref=probabilities.get(reference, 0.0) if probabilities else None,
        prob_pred=probabilities.get(answer.choice, 0.0) if probabilities else None,
        confidence=confidence,
    )


def _score_score(reference: int, answer: ScoreAnswer, confidence: float | None) -> Scored:
    probabilities = normalize_probabilities(answer.probabilities)
    if not probabilities:
        return Scored(correct=False, non_answer_cause="invalid_output")
    top = max(probabilities.values())
    predicted = min((int(key) for key, value in probabilities.items() if value == top), default=-1)
    return Scored(
        correct=predicted == reference,
        prob_ref=probabilities.get(str(reference), 0.0),
        prob_pred=top,
        confidence=confidence,
    )


def aggregate(rows: Iterable[ResultRow]) -> RunMetrics:
    rows = list(rows)
    n = len(rows)
    if n == 0:
        return RunMetrics(n=0, n_answered=0, non_answers_by_cause={})
    answered = [row for row in rows if row.non_answer_cause is None]
    n_correct = sum(row.correct for row in rows)
    accuracy = n_correct / n
    chance = sum(1.0 / row.n_options for row in rows) / n
    requests = _per_request(rows)
    sent = [request for request in requests if _was_sent(request)]
    latencies = [request.latency_s for request in sent]
    tokens = [request.input_tokens for request in requests if request.input_tokens is not None]
    costs = [request.cost_usd for request in requests]
    known_costs = [cost for cost in costs if cost is not None]
    return RunMetrics(
        n=n,
        n_answered=len(answered),
        n_correct=n_correct,
        accuracy=accuracy,
        accuracy_answered=(sum(row.correct for row in answered) / len(answered))
        if answered
        else None,
        macro_f1=_macro_f1(rows),
        chance=chance,
        chance_corrected=(accuracy - chance) / (1.0 - chance) if chance < 1.0 else None,
        ece=_ece([(row.prob_pred, row.correct) for row in answered if row.prob_pred is not None]),
        brier=_mean([value for value in map(_brier_row, answered) if value is not None]),
        brier_binary=_mean(
            [(1.0 - row.prob_ref) ** 2 for row in answered if row.prob_ref is not None]
        ),
        non_answer_rate=1.0 - len(answered) / n,
        non_answers_by_cause=dict(
            Counter(row.non_answer_cause for row in rows if row.non_answer_cause is not None)
        ),
        n_requests=len(requests),
        n_requests_sent=len(sent),
        latency_p50=float(np.percentile(latencies, 50)) if latencies else None,
        latency_p95=float(np.percentile(latencies, 95)) if latencies else None,
        mean_input_tokens=_mean(tokens),
        cost_per_1k=1000.0 * _mean(known_costs) if len(known_costs) == len(costs) else None,
        unknown_costs=len(costs) - len(known_costs),
        over_limit_rate=sum(row.over_limit for row in rows) / n,
    )


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _per_request(rows: list[ResultRow]) -> list[ResultRow]:
    """One row per (run, case, rep): the request-level fields repeat on every Question row."""
    seen: dict[tuple[str, str, int], ResultRow] = {}
    for row in rows:
        seen.setdefault((row.run_id, row.case_id, row.rep), row)
    return list(seen.values())


def _was_sent(row: ResultRow) -> bool:
    """A request that never left the harness has no HTTP status and took no time."""
    return row.http_status is not None or row.latency_s > 0.0


def _ece(pairs: list[tuple[float, bool]]) -> float | None:
    if not pairs:
        return None
    bins: list[list[tuple[float, bool]]] = [[] for _ in range(ECE_BINS)]
    for probability, correct in pairs:
        bins[min(int(probability * ECE_BINS), ECE_BINS - 1)].append((probability, correct))
    total = 0.0
    for members in bins:
        if not members:
            continue
        hit_rate = sum(correct for _, correct in members) / len(members)
        mean_confidence = sum(probability for probability, _ in members) / len(members)
        total += len(members) / len(pairs) * abs(hit_rate - mean_confidence)
    return total


def _parse_answer(data: dict[str, Any]) -> Answer | None:
    try:
        return _ANSWER.validate_python(data)
    except ValidationError:
        return None


def _brier_row(row: ResultRow) -> float | None:
    """Multiclass Brier for one row: sum over classes of (indicator - probability)^2."""
    answer = _parse_answer(row.answer_json)
    match answer:
        case NoulAnswer():
            truth = 1.0 if row.reference_json.get("noul") else 0.0
            return 2.0 * (truth - answer.noul) ** 2
        case ChoiceAnswer() if answer.probabilities:
            return _multiclass_brier(answer.probabilities, str(row.reference_json.get("choice")))
        case ScoreAnswer() if answer.probabilities:
            return _multiclass_brier(answer.probabilities, str(row.reference_json.get("score")))
    return None


def _multiclass_brier(probabilities: dict[str, float], reference: str) -> float:
    normalized = normalize_probabilities(probabilities)
    total = sum(
        (1.0 - value if key == reference else value) ** 2 for key, value in normalized.items()
    )
    if reference not in normalized:
        total += 1.0
    return total


def _labels(row: ResultRow) -> tuple[tuple[str, str], tuple[str, str] | None] | None:
    """(reference class, predicted class) for Choice and Noul rows, keyed by question id."""
    answered = row.non_answer_cause is None
    if row.qtype == "noul":
        reference = str(bool(row.reference_json.get("noul")))
        value = row.answer_json.get("noul") if answered else None
        predicted = str(float(value) >= 0.5) if value is not None else None
    elif row.qtype == "choice":
        reference = str(row.reference_json.get("choice"))
        predicted = row.answer_json.get("choice") if answered else None
    else:
        return None
    return (row.question_id, reference), ((row.question_id, predicted) if predicted else None)


def _macro_f1(rows: list[ResultRow]) -> float | None:
    pairs = [labels for labels in map(_labels, rows) if labels is not None]
    classes = sorted({reference for reference, _ in pairs})
    if not classes:
        return None
    scores = []
    for cls in classes:
        tp = sum(ref == cls and pred == cls for ref, pred in pairs)
        fp = sum(ref != cls and pred == cls for ref, pred in pairs)
        fn = sum(ref == cls and pred != cls for ref, pred in pairs)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return sum(scores) / len(scores)
