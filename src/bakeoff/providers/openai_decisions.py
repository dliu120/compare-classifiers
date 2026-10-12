"""OpenAI Decisions adapter: the one Provider whose wire shape is not System One.

Request: each Question becomes one entry of the ``questions`` array in the request's own
order (noul -> predicate, choice -> choices, score -> levels), and the State becomes
``input``: a plain string, or one user message holding the text and then each image.
Response: the ``answers`` array is paired with the Questions by ``name``, falling back to
position, and every entry becomes an Answer or a Non-answer (docs/adr/0003).
Source: https://developers.openai.com/api/docs/guides/decisions (read 2026-10-06).
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from bakeoff.config import Settings
from bakeoff.http import elide_images, make_client, post_json
from bakeoff.providers import parse_spec
from bakeoff.providers.base import Provider, ProviderResult
from bakeoff.providers.transport import MAX_ATTEMPTS, transport_non_answer
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
    SystemOneRequest,
    SystemOneResponse,
    Usage,
)

FAMILY = "openai-decisions"
DEFAULT_MODEL = "gpt-6-luna"
MAX_LABEL_CHARS = 60  # longer Level text becomes a description under a "level <i>" label


class OpenAIDecisionsProvider(Provider):
    supports_images = True
    max_input_tokens = None  # no documented input limit
    concurrency = 8

    def __init__(
        self, model: str, api_key: str, base_url: str, client: httpx.AsyncClient | None = None
    ) -> None:
        self.model = model
        self.id = f"{FAMILY}/{model}"
        self.price_key = f"{FAMILY}/{model}"
        self._url = base_url.rstrip("/") + "/decisions"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = client if client is not None else make_client()
        self._owns_client = client is None

    async def _call(self, request: SystemOneRequest) -> ProviderResult:
        body = build_body(self.model, request)
        request_raw = elide_images(body)
        started = time.perf_counter()
        try:
            result = await post_json(
                self._client, self._url, json=body, headers=self._headers, max_attempts=MAX_ATTEMPTS
            )
        except httpx.TransportError as exc:
            return transport_non_answer(
                self, request, exc, latency_s=time.perf_counter() - started, request_raw=request_raw
            )
        return ProviderResult(
            provider_id=self.id,
            response=parse_response(self.model, request, result.data),
            http_status=result.status,
            latency_s=result.latency_s,
            attempts=result.attempts,
            request_raw=request_raw,
            response_raw=result.data,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def build(spec: str, settings: Settings) -> Provider:
    """``openai-decisions[/<model>]``; the model defaults to gpt-6-luna. Needs OPENAI_API_KEY."""
    family, path, options = parse_spec(spec)
    if family != FAMILY:
        raise ValueError(f"not an {FAMILY} spec: {spec!r}")
    if len(path) > 1 or options:
        raise ValueError(f"{FAMILY} takes one optional model segment and no options: {spec!r}")
    if not settings.openai_api_key:
        raise ValueError(f"{FAMILY} needs OPENAI_API_KEY (settings.openai_api_key is empty)")
    model = path[0] if path else DEFAULT_MODEL
    return OpenAIDecisionsProvider(model, settings.openai_api_key, settings.openai_base_url)


# --- Request: System One -> Decisions ------------------------------------------------------


def build_body(model: str, request: SystemOneRequest) -> dict[str, Any]:
    questions = [_question(name, question) for name, question in request.questions.items()]
    return {"model": model, "input": _input(request), "questions": questions}


def _input(request: SystemOneRequest) -> str | list[dict[str, Any]]:
    text = _as_text(request.state)
    if not request.images:
        return text
    content: list[dict[str, Any]] = [{"type": "input_text", "text": text}]
    for url in request.images:
        content.append({"type": "input_image", "image_url": url})
    return [{"role": "user", "content": content}]


def _question(name: str, question: Question) -> dict[str, Any]:
    match question:
        case NoulQuestion():
            instructions = _predicate_instructions(question)
            return {"type": "predicate", "name": name, "instructions": instructions}
        case ChoiceQuestion():
            return {
                "type": "choice",
                "name": name,
                "instructions": _as_text(question.instructions),
                "choices": _choices(question),
            }
        case ScoreQuestion():
            return {
                "type": "score",
                "name": name,
                "instructions": _as_text(question.instructions),
                "levels": [_level(index, text) for index, text in enumerate(question.criteria)],
            }
        case _:
            raise TypeError(f"unsupported question type: {type(question).__name__}")


def _predicate_instructions(question: NoulQuestion) -> str:
    """Decisions predicates take no criteria, so the yes/no descriptions join the instructions."""
    lines = [_as_text(question.instructions)]
    criteria = question.criteria or {}
    if "true" in criteria:
        lines.append(f"Yes means: {_as_text(criteria['true'])}")
    if "false" in criteria:
        lines.append(f"No means: {_as_text(criteria['false'])}")
    return "\n".join(lines)


def _choices(question: ChoiceQuestion) -> list[dict[str, str]]:
    choices = []
    for option, description in question.criteria.items():
        entry = {"value": option}
        if description is not None:
            entry["description"] = _as_text(description)
        choices.append(entry)
    return choices


def _level(index: int, criterion: Json) -> dict[str, str]:
    if isinstance(criterion, str) and len(criterion) <= MAX_LABEL_CHARS:
        return {"label": criterion}
    return {"label": f"level {index}", "description": _as_text(criterion)}


def _as_text(value: Json) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


# --- Response: Decisions -> System One -----------------------------------------------------


def parse_response(model: str, request: SystemOneRequest, body: Any) -> SystemOneResponse:
    names = list(request.questions)
    if not isinstance(body, dict) or not isinstance(body.get("answers"), list):
        detail = "response has no answers array"
        answers = {name: NonAnswer(cause="invalid_output", detail=detail) for name in names}
        return SystemOneResponse(model=model, answers=answers)
    matched = _match_answers(names, body["answers"])
    answers = {name: _answer(request.questions[name], matched[name]) for name in names}
    reported_model = body.get("model")
    if not isinstance(reported_model, str):
        reported_model = model
    return SystemOneResponse(model=reported_model, answers=answers, usage=_usage(body.get("usage")))


def _match_answers(names: list[str], answers: list[Any]) -> dict[str, Any]:
    """Pair Questions with answers by name; an unclaimed answer at the same position fills a gap."""
    wanted = set(names)
    by_name: dict[str, Any] = {}
    for item in answers:
        name = _name_of(item)
        if name in wanted and name not in by_name:
            by_name[name] = item
    matched: dict[str, Any] = {}
    for index, name in enumerate(names):
        item = by_name.get(name)
        if item is None and index < len(answers) and _name_of(answers[index]) not in by_name:
            item = answers[index]
        matched[name] = item
    return matched


def _name_of(item: Any) -> str | None:
    if isinstance(item, dict) and isinstance(item.get("name"), str):
        return item["name"]
    return None


def _answer(question: Question, item: Any) -> Answer:
    if not isinstance(item, dict):
        return NonAnswer(cause="invalid_output", detail="no answer for this question")
    kind = item.get("type")
    try:
        if kind == "refusal":
            return NonAnswer(cause="refusal", detail=_refusal_detail(item))
        if kind == "predicate" and isinstance(question, NoulQuestion):
            return NoulAnswer(noul=item["probability"])
        if kind == "choice" and isinstance(question, ChoiceQuestion):
            return _choice_answer(question, item)
        if kind == "score" and isinstance(question, ScoreQuestion):
            return _score_answer(question, item)
    except (KeyError, TypeError, ValueError) as exc:  # pydantic's ValidationError is a ValueError
        return NonAnswer(cause="invalid_output", detail=f"{type(exc).__name__}: {exc}")
    detail = f"unexpected answer type {kind!r} for a {question.type} question"
    return NonAnswer(cause="invalid_output", detail=detail)


def _choice_answer(question: ChoiceQuestion, item: dict[str, Any]) -> ChoiceAnswer:
    reported = {entry["value"]: entry["probability"] for entry in item["probabilities"]}
    probabilities = {option: reported.get(option, 0.0) for option in question.criteria}
    return ChoiceAnswer(
        choice=item["choice"], probabilities=probabilities, confidence=item.get("confidence")
    )


def _score_answer(question: ScoreQuestion, item: dict[str, Any]) -> ScoreAnswer:
    """Probabilities keyed by Level index. An entry is matched to the request's Levels by the
    label the request sent, else by its position; the vendor's ``value`` is not relied on
    because whether it counts from 0 or 1 is undocumented."""
    by_label = {_level(index, text)["label"]: index for index, text in enumerate(question.criteria)}
    probabilities: dict[str, float] = {}
    legend: dict[str, str] = {}
    for position, entry in enumerate(item["probabilities"]):
        label = entry.get("label")
        key = str(by_label.get(label, position))
        probabilities[key] = entry["probability"]
        if isinstance(label, str):
            legend[key] = label
    return ScoreAnswer(
        score=item["score"],
        probabilities=probabilities,
        legend=legend or None,
        confidence=item.get("confidence"),
    )


def _refusal_detail(item: dict[str, Any]) -> str | None:
    for key in ("refusal", "reason", "message"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _usage(raw: Any) -> Usage:
    """Decisions bills input only; whatever output count it reports is not a charge."""
    input_tokens = raw.get("input_tokens") if isinstance(raw, dict) else None
    if not isinstance(input_tokens, int):
        input_tokens = None
    return Usage(input_tokens=input_tokens, output_tokens=0)
