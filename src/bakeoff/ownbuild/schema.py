"""The Own build's output contract: a strict JSON schema per request, and the decoding of the
model's JSON back into System One Answers.

Question ids and Option names become JSON property names. Names outside ``[A-Za-z0-9_]`` are
mapped to safe property names and mapped back on decode, so the model only sees safe keys.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from bakeoff.systemone import (
    Answer,
    ChoiceAnswer,
    ChoiceQuestion,
    Json,
    NonAnswer,
    NoulAnswer,
    NoulQuestion,
    Question,
    ScoreAnswer,
    ScoreQuestion,
    choice_confidence,
    expected_score,
    normalize_probabilities,
    score_confidence,
)

SCHEMA_NAME = "systemone_answers"
MAX_KEY_LENGTH = 48
_SAFE_KEY = re.compile(r"^[A-Za-z0-9_]+$")
_UNSAFE_RUN = re.compile(r"[^A-Za-z0-9_]+")


class SchemaViolation(ValueError):
    """The model's JSON does not fit the schema it was asked for."""


@dataclass(frozen=True, slots=True)
class KeyMap:
    """Bijection between original names and JSON-schema-safe property names."""

    to_safe: dict[str, str]
    to_original: dict[str, str]

    @classmethod
    def build(cls, originals: Iterable[str]) -> KeyMap:
        to_safe: dict[str, str] = {}
        for original in originals:
            to_safe[original] = _safe_key(original, to_safe.values())
        return cls(to_safe, {safe: original for original, safe in to_safe.items()})


def _safe_key(original: str, taken: Iterable[str]) -> str:
    taken = set(taken)
    if _SAFE_KEY.match(original) and len(original) <= MAX_KEY_LENGTH:
        base = original
    else:
        base = _UNSAFE_RUN.sub("_", original).strip("_")[:MAX_KEY_LENGTH] or "key"
    candidate, suffix = base, 2
    while candidate in taken:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


@dataclass(frozen=True, slots=True)
class AnswerSchema:
    schema: dict[str, Any]
    discrete: bool
    questions: KeyMap  # question id <-> property name
    options: dict[str, KeyMap]  # choice question id -> option name <-> property name


def build_answer_schema(questions: Mapping[str, Question], *, discrete: bool) -> AnswerSchema:
    """Strict schema with one object per Question.

    Probabilities mode: noul ``{probability_yes}``, choice ``{probabilities: {<option>: n}}``,
    score ``{probabilities: {"0": n, ..., "<n-1>": n}}``. Discrete mode: noul ``{answer: bool}``,
    choice ``{choice: <option enum>}``, score ``{level: <index enum>}``.
    """
    question_keys = KeyMap.build(questions)
    options: dict[str, KeyMap] = {}
    properties: dict[str, Any] = {}
    for qid, question in questions.items():
        if isinstance(question, ChoiceQuestion) and not discrete:
            options[qid] = KeyMap.build(question.criteria)
        key = question_keys.to_safe[qid]
        properties[key] = _question_schema(question, options.get(qid), discrete)
    return AnswerSchema(_object(properties), discrete, question_keys, options)


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _question_schema(
    question: Question, option_keys: KeyMap | None, discrete: bool
) -> dict[str, Any]:
    match question:
        case NoulQuestion():
            if discrete:
                return _object({"answer": {"type": "boolean"}})
            return _object({"probability_yes": {"type": "number"}})
        case ChoiceQuestion():
            if discrete:
                return _object({"choice": {"type": "string", "enum": list(question.criteria)}})
            assert option_keys is not None
            numbers = {key: {"type": "number"} for key in option_keys.to_original}
            return _object({"probabilities": _object(numbers)})
        case ScoreQuestion():
            levels = range(len(question.criteria))
            if discrete:
                return _object({"level": {"type": "integer", "enum": list(levels)}})
            return _object({"probabilities": _object({str(i): {"type": "number"} for i in levels})})
        case _:
            raise TypeError(f"unsupported question type: {type(question).__name__}")


def minimal_answer(
    questions: Mapping[str, Question], answer_schema: AnswerSchema
) -> dict[str, Any]:
    """The shortest JSON the schema admits, one entry per Question: what any complete answer
    costs in output tokens at the very least."""
    discrete = answer_schema.discrete
    out: dict[str, Any] = {}
    for qid, question in questions.items():
        key = answer_schema.questions.to_safe[qid]
        match question:
            case NoulQuestion():
                out[key] = {"answer": False} if discrete else {"probability_yes": 0}
            case ChoiceQuestion():
                if discrete:
                    out[key] = {"choice": min(question.criteria, key=len)}
                else:
                    option_keys = answer_schema.options[qid].to_original
                    out[key] = {"probabilities": dict.fromkeys(option_keys, 0)}
            case ScoreQuestion():
                levels = [str(index) for index in range(len(question.criteria))]
                out[key] = {"level": 0} if discrete else {"probabilities": dict.fromkeys(levels, 0)}
    return out


# --- Decoding: model JSON -> Answers ------------------------------------------------------


def decode_answers(
    data: Any, questions: Mapping[str, Question], answer_schema: AnswerSchema
) -> dict[str, Answer]:
    """One Answer per Question; a schema violation makes that Question an ``invalid_output``."""
    if not isinstance(data, dict):
        detail = "output is not a JSON object"
        return {qid: NonAnswer(cause="invalid_output", detail=detail) for qid in questions}
    answers: dict[str, Answer] = {}
    for qid, question in questions.items():
        value = data.get(answer_schema.questions.to_safe[qid])
        try:
            option_keys = answer_schema.options.get(qid)
            answers[qid] = _decode_one(value, question, option_keys, answer_schema.discrete)
        except SchemaViolation as exc:
            answers[qid] = NonAnswer(cause="invalid_output", detail=f"{qid}: {exc}")
    return answers


def _decode_one(
    value: Any, question: Question, option_keys: KeyMap | None, discrete: bool
) -> Answer:
    if not isinstance(value, dict):
        raise SchemaViolation("missing or not an object")
    match question:
        case NoulQuestion():
            if discrete:
                return NoulAnswer(noul=1.0 if _bool(value, "answer") else 0.0)
            return NoulAnswer(noul=min(1.0, max(0.0, _number(value, "probability_yes"))))
        case ChoiceQuestion():
            if discrete:
                choice = _string(value, "choice")
                if choice not in question.criteria:
                    raise SchemaViolation(f"{choice!r} is not an option")
                return choice_answer(one_hot(question.criteria, choice))
            assert option_keys is not None
            return choice_answer(_distribution(value, option_keys.to_original))
        case ScoreQuestion():
            legend = legend_for(question)
            if discrete:
                level = _integer(value, "level")
                if not 0 <= level < len(question.criteria):
                    raise SchemaViolation(f"level {level} is out of range")
                return score_answer(one_hot(legend, str(level)), legend)
            return score_answer(_distribution(value, {key: key for key in legend}), legend)
        case _:
            raise SchemaViolation(f"unsupported question type: {type(question).__name__}")


def _distribution(value: dict[str, Any], keys: Mapping[str, str]) -> dict[str, float]:
    """``value["probabilities"]`` keyed by safe name, returned keyed by original name."""
    raw = value.get("probabilities")
    if not isinstance(raw, dict):
        raise SchemaViolation("probabilities missing or not an object")
    distribution: dict[str, float] = {}
    for safe, original in keys.items():
        distribution[original] = _number(raw, safe)
    return distribution


def _number(fields: dict[str, Any], name: str) -> float:
    value = fields.get(name)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise SchemaViolation(f"{name} is not a number")
    return float(value)


def _integer(fields: dict[str, Any], name: str) -> int:
    value = fields.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchemaViolation(f"{name} is not an integer")
    return value


def _bool(fields: dict[str, Any], name: str) -> bool:
    value = fields.get(name)
    if not isinstance(value, bool):
        raise SchemaViolation(f"{name} is not a boolean")
    return value


def _string(fields: dict[str, Any], name: str) -> str:
    value = fields.get(name)
    if not isinstance(value, str):
        raise SchemaViolation(f"{name} is not a string")
    return value


# --- Answer construction shared with the engine --------------------------------------------


def one_hot(keys: Iterable[str], chosen: str) -> dict[str, float]:
    return {key: 1.0 if key == chosen else 0.0 for key in keys}


def choice_answer(probabilities: Mapping[str, float]) -> ChoiceAnswer:
    """Normalize, pick the argmax (first on ties), and fill TypeSafe's Choice confidence."""
    normalized = normalize_probabilities(probabilities)
    choice = max(normalized, key=lambda key: normalized[key])
    return ChoiceAnswer(
        choice=choice, probabilities=normalized, confidence=choice_confidence(normalized)
    )


def score_answer(probabilities: Mapping[str, float], legend: dict[str, str]) -> ScoreAnswer:
    """Normalize, take the expected Level index as the score, fill TypeSafe's Score confidence."""
    normalized = normalize_probabilities(probabilities)
    return ScoreAnswer(
        score=expected_score(normalized),
        probabilities=normalized,
        legend=legend,
        confidence=score_confidence(normalized),
    )


def legend_for(question: ScoreQuestion) -> dict[str, str]:
    return {str(index): compact_text(level) for index, level in enumerate(question.criteria)}


def compact_text(value: Json) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
