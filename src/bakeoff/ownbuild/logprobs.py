"""Logprobs mode: a distribution for each discrete Answer from the model's top_logprobs at the
first token of its value.

The sampled value is known from the decoded Answer, so the mass of the token the model
actually produced goes to that value even when other values share the token (``card_arrival``
and ``card_delivery_estimate`` both start with ``card``). A token that several values share is
split evenly among them, so no mass is counted twice.
"""

from __future__ import annotations

import itertools
import math
import re
from bisect import bisect_right
from collections.abc import Mapping
from typing import Any

from bakeoff.ownbuild.schema import AnswerSchema, choice_answer, legend_for, score_answer
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
)


def apply_logprobs(
    answers: dict[str, Answer],
    text: str,
    logprobs: list[dict[str, Any]],
    questions: Mapping[str, Question],
    answer_schema: AnswerSchema,
) -> None:
    """Replace each discrete Answer's one-hot distribution with one derived from the logprobs."""
    sampled = {qid: sampled_value(answer) for qid, answer in answers.items()}
    derived = logprob_distributions(text, logprobs, questions, answer_schema, sampled)
    for qid, distribution in derived.items():
        if isinstance(answers[qid], NonAnswer):
            continue
        answers[qid] = answer_from_distribution(questions[qid], distribution)


def sampled_value(answer: Answer) -> str | None:
    """The value a discrete Answer carries, as the model wrote it: an Option name, ``true`` or
    ``false``, or a Level index."""
    match answer:
        case NoulAnswer():
            return "true" if answer.noul >= 0.5 else "false"
        case ChoiceAnswer():
            return answer.choice
        case ScoreAnswer() if answer.probabilities:
            return max(answer.probabilities, key=lambda key: answer.probabilities[key])
        case _:
            return None


def logprob_distributions(
    text: str,
    logprobs: list[dict[str, Any]],
    questions: Mapping[str, Question],
    answer_schema: AnswerSchema,
    sampled: Mapping[str, str | None] | None = None,
) -> dict[str, dict[str, float]]:
    """Per Question id, the top_logprobs mass at the first token of its value, matched to the
    answer values (Option names, "true"/"false", Level indices) by prefix and normalized.
    Questions whose token cannot be located, or where nothing matches, are left out."""
    tokens = [str(entry.get("token", "")) for entry in logprobs]
    if not tokens or "".join(tokens) != text:
        return {}
    starts = list(itertools.accumulate((len(token) for token in tokens), initial=0))
    derived: dict[str, dict[str, float]] = {}
    for qid, question in questions.items():
        match = _value_pattern(answer_schema.questions.to_safe[qid], question.type).search(text)
        if match is None:
            continue
        index = bisect_right(starts, match.end()) - 1
        if index >= len(tokens):
            continue
        lead = tokens[index][: match.end() - starts[index]]
        chosen = sampled.get(qid) if sampled is not None else None
        mass = _candidate_mass(logprobs[index], lead, _value_names(question), chosen)
        if mass:
            derived[qid] = normalize_probabilities(mass)
    return derived


def _value_pattern(key: str, question_type: str) -> re.Pattern[str]:
    field = {"noul": "answer", "choice": "choice", "score": "level"}[question_type]
    quote = '"' if question_type == "choice" else ""
    return re.compile(rf'"{re.escape(key)}"\s*:\s*\{{\s*"{field}"\s*:\s*{quote}')


def _value_names(question: Question) -> list[str]:
    match question:
        case NoulQuestion():
            return ["true", "false"]
        case ChoiceQuestion():
            return list(question.criteria)
        case ScoreQuestion():
            return [str(index) for index in range(len(question.criteria))]
        case _:
            return []


def _candidate_mass(
    entry: dict[str, Any], lead: str, names: list[str], sampled: str | None
) -> dict[str, float]:
    """Probability mass per answer value from the sampled token and its top_logprobs."""
    mass = dict.fromkeys(names, 0.0)
    matched = False
    seen: set[str] = set()
    for position, candidate in enumerate([entry, *(entry.get("top_logprobs") or [])]):
        token, logprob = str(candidate.get("token", "")), candidate.get("logprob")
        if token in seen or not isinstance(logprob, int | float) or not token.startswith(lead):
            continue
        seen.add(token)
        value = token[len(lead) :].lstrip()
        if not value:
            continue
        matches = [name for name in names if name.startswith(value) or value.startswith(name)]
        if not matches:
            continue
        if position == 0 and sampled in matches:
            matches = [sampled]  # the sampled token went on to spell the sampled value
        share = math.exp(logprob) / len(matches)
        for name in matches:
            mass[name] += share
        matched = True
    return mass if matched else {}


def answer_from_distribution(question: Question, distribution: dict[str, float]) -> Answer:
    match question:
        case NoulQuestion():
            return NoulAnswer(noul=distribution.get("true", 0.0))
        case ChoiceQuestion():
            return choice_answer(distribution)
        case ScoreQuestion():
            return score_answer(distribution, legend_for(question))
        case _:
            return NonAnswer(cause="invalid_output", detail="unsupported question type")
