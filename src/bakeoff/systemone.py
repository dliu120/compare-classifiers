"""Canonical System One types shared by every Provider and the Own build.

Shape: TypeSafe's System One contract (https://docs.typesafe.ai/api) plus a top-level
``images`` list of base64 data URLs, as Cloudflare Clef and Liquid d1 accept. See CONTEXT.md
for the vocabulary and docs/adr/0001 for why this is the one surface every adapter speaks.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Json = str | dict[str, Any] | list[Any]

MIN_CHOICE_OPTIONS = 2
MAX_CHOICE_OPTIONS = 255
MIN_SCORE_LEVELS = 2
MAX_SCORE_LEVELS = 10
MAX_QUESTIONS = 64  # Cloudflare's documented cap is the lowest (OpenAI allows 200)


class NoulQuestion(BaseModel):
    """A yes/no Question. The Answer is the probability that the answer is yes."""

    model_config = ConfigDict(extra="forbid")
    type: Literal["noul"] = "noul"
    instructions: Json
    criteria: dict[Literal["true", "false"], Json] | None = None


class ChoiceQuestion(BaseModel):
    """Select one Option. ``criteria`` maps each Option name to its description or ``None``."""

    model_config = ConfigDict(extra="forbid")
    type: Literal["choice"] = "choice"
    instructions: Json
    criteria: dict[str, Json | None]

    @field_validator("criteria")
    @classmethod
    def _check_options(cls, value: dict[str, Json | None]) -> dict[str, Json | None]:
        if not MIN_CHOICE_OPTIONS <= len(value) <= MAX_CHOICE_OPTIONS:
            raise ValueError(
                f"choice needs {MIN_CHOICE_OPTIONS}..{MAX_CHOICE_OPTIONS} options, got {len(value)}"
            )
        if any(not name for name in value):
            raise ValueError("choice option names must be non-empty")
        return value


class ScoreQuestion(BaseModel):
    """Rate on an ordered rubric. ``criteria`` lists the Levels, lowest first."""

    model_config = ConfigDict(extra="forbid")
    type: Literal["score"] = "score"
    instructions: Json
    criteria: list[Json]

    @field_validator("criteria")
    @classmethod
    def _check_levels(cls, value: list[Json]) -> list[Json]:
        if not MIN_SCORE_LEVELS <= len(value) <= MAX_SCORE_LEVELS:
            raise ValueError(
                f"score needs {MIN_SCORE_LEVELS}..{MAX_SCORE_LEVELS} levels, got {len(value)}"
            )
        return value


Question = Annotated[NoulQuestion | ChoiceQuestion | ScoreQuestion, Field(discriminator="type")]


class SystemOneRequest(BaseModel):
    """One State, optional images, and a map of named Questions."""

    model_config = ConfigDict(extra="forbid")
    model: str
    state: Json
    questions: dict[str, Question]
    images: list[str] | None = None

    @field_validator("questions")
    @classmethod
    def _check_questions(cls, value: dict[str, Question]) -> dict[str, Question]:
        if not 1 <= len(value) <= MAX_QUESTIONS:
            raise ValueError(f"need 1..{MAX_QUESTIONS} questions, got {len(value)}")
        if any(not key for key in value):
            raise ValueError("question ids must be non-empty")
        return value

    @field_validator("images")
    @classmethod
    def _check_images(cls, value: list[str] | None) -> list[str] | None:
        for url in value or []:
            if not url.startswith("data:image/") or ";base64," not in url[:40]:
                raise ValueError("images must be base64 data URLs (data:image/<type>;base64,...)")
        return value


class NoulAnswer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["noul"] = "noul"
    noul: float = Field(ge=0.0, le=1.0)


class ChoiceAnswer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["choice"] = "choice"
    choice: str
    probabilities: dict[str, float]
    confidence: float | None = None  # the Provider's own figure; informational only (ADR 0004)

    @model_validator(mode="after")
    def _choice_in_probabilities(self) -> ChoiceAnswer:
        if self.probabilities and self.choice not in self.probabilities:
            raise ValueError(f"choice {self.choice!r} is not one of the options")
        return self


class ScoreAnswer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["score"] = "score"
    score: float
    probabilities: dict[str, float]  # keyed by level index as a string: "0", "1", ...
    legend: dict[str, str] | None = None
    confidence: float | None = None  # the Provider's own figure; informational only (ADR 0004)

    @field_validator("probabilities")
    @classmethod
    def _integer_keys(cls, value: dict[str, float]) -> dict[str, float]:
        for key in value:
            if not key.lstrip("-").isdigit():
                raise ValueError("score probabilities must be keyed by level index strings")
        return value


NonAnswerCause = Literal[
    "refusal",  # the Provider declined (OpenAI Decisions refusal answer)
    "truncated_output",  # output cap reached before a complete answer (Own build)
    "invalid_output",  # answer did not parse or violated the schema
    "filtered",  # content filter or safety block
    "error",  # transport or HTTP error after retries
    "rate_limited",  # 429 after retries
    "timeout",
    "state_truncated",  # the Provider silently truncated the State (detected via usage)
    "unsupported_modality",  # images sent to a text-only Provider
    "budget",  # the harness refused to spend (budget cap)
]


class NonAnswer(BaseModel):
    """A Question that produced no usable Answer. Scored as wrong (docs/adr/0003)."""

    model_config = ConfigDict(extra="ignore")
    type: Literal["non_answer"] = "non_answer"
    cause: NonAnswerCause
    detail: str | None = None


Answer = Annotated[NoulAnswer | ChoiceAnswer | ScoreAnswer | NonAnswer, Field(discriminator="type")]


class Usage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    cached_tokens: int | None = None


class SystemOneResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    model: str
    answers: dict[str, Answer]
    usage: Usage = Field(default_factory=Usage)


def normalize_probabilities(probabilities: Mapping[str, float]) -> dict[str, float]:
    """Clamp negatives to zero and rescale to sum 1. Uniform when the total is not positive."""
    clamped = {key: max(0.0, float(value)) for key, value in probabilities.items()}
    total = sum(clamped.values())
    if total <= 0.0:
        return {key: 1.0 / len(clamped) for key in clamped} if clamped else {}
    return {key: value / total for key, value in clamped.items()}


def choice_confidence(probabilities: Mapping[str, float]) -> float:
    """TypeSafe's documented Choice confidence: (n * p_max - 1) / (n - 1), clamped to [0, 1].

    Source: https://docs.typesafe.ai/confidence (``choiceConfidence``).
    """
    p = normalize_probabilities(probabilities)
    n = len(p)
    if n < 2:
        return 1.0
    return min(1.0, max(0.0, (n * max(p.values()) - 1.0) / (n - 1.0)))


def _ordered_levels(probabilities: Mapping[str, float]) -> list[float]:
    p = normalize_probabilities(probabilities)
    return [p[key] for key in sorted(p, key=int)]


def score_confidence(probabilities: Mapping[str, float]) -> float:
    """TypeSafe's documented Score confidence: 1 - spread / even_spread, clamped to [0, 1].

    ``spread`` is the probability-weighted distance of each Level from the peak Level;
    ``even_spread`` is the mean distance of every Level from the middle Level.
    Source: https://docs.typesafe.ai/confidence (``scoreConfidence``).
    """
    values = _ordered_levels(probabilities)
    n = len(values)
    if n < 2:
        return 1.0
    peak = max(range(n), key=lambda i: values[i])
    spread = sum(value * abs(i - peak) for i, value in enumerate(values))
    even_spread = sum(abs(i - (n - 1) / 2.0) for i in range(n)) / n
    return min(1.0, max(0.0, 1.0 - spread / even_spread))


def expected_score(probabilities: Mapping[str, float]) -> float:
    """Probability-weighted Level index, as every vendor defines ``score``."""
    return sum(i * value for i, value in enumerate(_ordered_levels(probabilities)))


def noul_confidence(probability: float) -> float:
    """Choice confidence with two Options: |2p - 1|."""
    return min(1.0, max(0.0, abs(2.0 * probability - 1.0)))


def recomputed_confidence(answer: Answer) -> float | None:
    """One Confidence for every Answer, recomputed from its probabilities (docs/adr/0004)."""
    match answer:
        case NoulAnswer():
            return noul_confidence(answer.noul)
        case ChoiceAnswer():
            return choice_confidence(answer.probabilities)
        case ScoreAnswer():
            return score_confidence(answer.probabilities)
        case _:
            return None
