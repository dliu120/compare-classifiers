"""The Own build engine: GPT-6 Luna through the OpenAI Responses API, emulating a decision API.

One System One request becomes one Responses call (``samples`` calls when k >= 2: concurrent on
the OpenAI Route, one after another on the Copilot Route) with a strict JSON schema; the output
is decoded into Answers and every failure into Non-answers (docs/adr/0003). ``evaluate`` never
raises.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from statistics import fmean
from typing import Any

import httpx

from bakeoff import budget, pricing
from bakeoff.config import Settings
from bakeoff.datasets.tokens import count_tokens, truncate_state
from bakeoff.http import DEFAULT_TIMEOUT, HttpError, elide_images, make_client, post_json
from bakeoff.ownbuild.config import OwnBuildConfig, price_key_for, wire_model_id
from bakeoff.ownbuild.logprobs import apply_logprobs
from bakeoff.ownbuild.prompt import build_input
from bakeoff.ownbuild.schema import (
    SCHEMA_NAME,
    AnswerSchema,
    build_answer_schema,
    choice_answer,
    decode_answers,
    legend_for,
    minimal_answer,
    score_answer,
)
from bakeoff.providers.base import Provider, ProviderResult
from bakeoff.providers.transport import MAX_ATTEMPTS, transport_cause, transport_detail
from bakeoff.systemone import (
    Answer,
    ChoiceAnswer,
    ChoiceQuestion,
    NonAnswer,
    NonAnswerCause,
    NoulAnswer,
    NoulQuestion,
    Question,
    ScoreAnswer,
    ScoreQuestion,
    SystemOneRequest,
    SystemOneResponse,
    Usage,
)

TOP_LOGPROBS = 20
FILTER_CODES = frozenset({"content_filter", "content_policy_violation"})
_FILTER_MESSAGE = re.compile(r"content[_ -]?filter", re.IGNORECASE)


@dataclass(slots=True)
class _Sample:
    """What one Responses call produced: Answers (or Non-answers) plus its accounting."""

    answers: dict[str, Answer]
    usage: Usage
    http_status: int | None
    attempts: int
    latency_s: float  # the answering attempt's wall time; the whole wait when every attempt failed
    raw: Any
    error: str | None


class OwnBuildEngine(Provider):
    supports_images = True

    def __init__(
        self, config: OwnBuildConfig, settings: Settings, client: httpx.AsyncClient | None = None
    ) -> None:
        self.config = config
        self.id = config.spec
        self.model = config.model
        self.price_key = price_key_for(config.model)
        self.max_input_tokens = config.max_in
        self.model_id = wire_model_id(config)
        # docs/adr/0002: the Copilot Route stops at the first 429 instead of retrying it
        self.max_attempts = 1 if config.route == "copilot" else MAX_ATTEMPTS
        if config.route == "openai":
            if not settings.openai_api_key:
                raise ValueError(
                    "route openai needs OPENAI_API_KEY (settings.openai_api_key is empty)"
                )
            self._url = settings.openai_base_url.rstrip("/") + "/responses"
            self._headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
        else:
            self._url = settings.aiproxy_base_url.rstrip("/") + "/responses"
            self._headers = {}
        self._client = client if client is not None else make_client()
        self._owns_client = client is None

    def estimate_cost_usd(self, approx_tokens: int | None) -> float:
        """What one request may cost, reserved against the budget before it is sent: ``samples``
        calls of the State's tokens in and up to the output cap out."""
        return budget.estimate_cost_usd(
            self.price_key, approx_tokens, self.config.cap or 0, self.config.samples
        )

    async def _call(self, request: SystemOneRequest) -> ProviderResult:
        body, truncated, answer_schema = self.build_body(request)
        if self.config.cap is not None:
            floor = minimal_output_tokens(request.questions, answer_schema)
            if self.config.cap < floor:
                detail = (
                    f"output cap {self.config.cap} is below the {floor} tokens of the shortest "
                    "complete answer; not sent"
                )
                return self._refuse(request, body, truncated, "truncated_output", detail)
        if self.config.route == "copilot":
            samples = await self._samples_in_turn(body, request.questions, answer_schema)
        else:
            calls = [
                self._sample(body, request.questions, answer_schema)
                for _ in range(self.config.samples)
            ]
            samples = list(await asyncio.gather(*calls))
        return self._combine(request, body, truncated, samples)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def build_body(self, request: SystemOneRequest) -> tuple[dict[str, Any], bool, AnswerSchema]:
        """The Responses request body, whether the State was truncated, and the answer schema."""
        state, truncated = request.state, False
        if self.config.max_in is not None:
            state, truncated = truncate_state(request.state, self.config.max_in)
        answer_schema = build_answer_schema(request.questions, discrete=self.config.discrete)
        body: dict[str, Any] = {
            "model": self.model_id,
            "input": build_input(state, request.images, request.questions, answer_schema),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": SCHEMA_NAME,
                    "schema": answer_schema.schema,
                    "strict": True,
                }
            },
        }
        if self.config.cap is not None:
            body["max_output_tokens"] = self.config.cap
        if self.config.effort is not None:
            body["reasoning"] = {"effort": self.config.effort}
        if self.config.mode == "logprobs":
            body["include"] = ["message.output_text.logprobs"]
            body["top_logprobs"] = TOP_LOGPROBS
        return body, truncated, answer_schema

    async def _samples_in_turn(
        self, body: dict[str, Any], questions: Mapping[str, Question], answer_schema: AnswerSchema
    ) -> list[_Sample]:
        """The Copilot Route's samples one at a time, so its modest concurrency counts calls, and
        no further ones after a failed call: the request is a Non-answer whatever they would say."""
        samples = []
        for _ in range(self.config.samples):
            sample = await self._sample(body, questions, answer_schema)
            samples.append(sample)
            if sample.http_status is None or sample.http_status >= 400:
                break
        return samples

    async def _sample(
        self, body: dict[str, Any], questions: Mapping[str, Question], answer_schema: AnswerSchema
    ) -> _Sample:
        started = time.perf_counter()
        try:
            result = await post_json(
                self._client,
                self._url,
                json=body,
                headers=self._headers,
                max_attempts=self.max_attempts,
                timeout=DEFAULT_TIMEOUT,
            )
        except HttpError as exc:
            cause = _http_error_cause(exc)
            detail = f"HTTP {exc.status}: {_short(exc.body)}"
            answers = non_answers(questions, cause, detail)
            waited = time.perf_counter() - started
            return _Sample(answers, Usage(), exc.status, exc.attempts, waited, exc.body, detail)
        except httpx.TransportError as exc:
            detail = transport_detail(exc)
            answers = non_answers(questions, transport_cause(exc), detail)
            waited = time.perf_counter() - started
            return _Sample(answers, Usage(), None, self.max_attempts, waited, None, detail)
        answers = self._decode(result.data, questions, answer_schema)
        error = next((a.detail for a in answers.values() if isinstance(a, NonAnswer)), None)
        usage = usage_from_body(result.data)
        return _Sample(
            answers, usage, result.status, result.attempts, result.latency_s, result.data, error
        )

    def _decode(
        self, body: Any, questions: Mapping[str, Question], answer_schema: AnswerSchema
    ) -> dict[str, Answer]:
        if not isinstance(body, dict):
            return non_answers(questions, "invalid_output", "response body is not a JSON object")
        status = body.get("status")
        if status == "incomplete":
            reason = _incomplete_reason(body)
            cause: NonAnswerCause = "filtered" if reason == "content_filter" else "truncated_output"
            return non_answers(questions, cause, reason)
        if status in ("failed", "cancelled"):
            return non_answers(questions, "error", f"response {status}: {_error_message(body)}")
        parts = _message_parts(body)
        refusal = next((part for part in parts if part.get("type") == "refusal"), None)
        if refusal is not None:
            return non_answers(questions, "refusal", str(refusal.get("refusal") or "refused"))
        text_part = next((part for part in parts if part.get("type") == "output_text"), None)
        if text_part is None:
            return non_answers(questions, "invalid_output", "no output_text in the response")
        text = text_part.get("text")
        try:
            data = json.loads(text)
        except (TypeError, ValueError) as exc:
            return non_answers(questions, "invalid_output", f"invalid JSON: {exc}")
        answers = decode_answers(data, questions, answer_schema)
        if self.config.mode == "logprobs":
            logprobs = text_part.get("logprobs") or []
            apply_logprobs(answers, str(text), logprobs, questions, answer_schema)
        return answers

    def _meta(self, truncated: bool) -> dict[str, Any]:
        return {"route": self.config.route, "truncated": truncated, "samples": self.config.samples}

    def _refuse(
        self,
        request: SystemOneRequest,
        body: dict[str, Any],
        truncated: bool,
        cause: NonAnswerCause,
        detail: str,
    ) -> ProviderResult:
        """A request the engine will not send: Non-answers at no cost and no attempt."""
        answers = non_answers(request.questions, cause, detail)
        return ProviderResult(
            provider_id=self.id,
            response=SystemOneResponse(model=self.model, answers=answers),
            latency_s=0.0,
            attempts=0,
            error=detail,
            request_raw={**elide_images(body), "meta": self._meta(truncated)},
            cost_usd=0.0,
        )

    def _combine(
        self,
        request: SystemOneRequest,
        body: dict[str, Any],
        truncated: bool,
        samples: list[_Sample],
    ) -> ProviderResult:
        """One result from the samples made; ``response_raw`` is the list of their bodies."""
        answers = {
            qid: average_answers([sample.answers[qid] for sample in samples], question)
            for qid, question in request.questions.items()
        }
        costs = [pricing.cost_usd(self.price_key, sample.usage) for sample in samples]
        known_costs = [cost for cost in costs if cost is not None]
        return ProviderResult(
            provider_id=self.id,
            response=SystemOneResponse(model=self.model, answers=answers, usage=sum_usage(samples)),
            http_status=next((s.http_status for s in samples if s.http_status is not None), None),
            latency_s=max(sample.latency_s for sample in samples),
            attempts=sum(sample.attempts for sample in samples),
            error=next((sample.error for sample in samples if sample.error), None),
            request_raw={**elide_images(body), "meta": self._meta(truncated)},
            response_raw=[sample.raw for sample in samples],
            cost_usd=sum(known_costs) if known_costs else None,
        )


def minimal_output_tokens(questions: Mapping[str, Question], answer_schema: AnswerSchema) -> int:
    """Tokens of the shortest JSON the schema admits: the floor any complete answer needs."""
    text = json.dumps(minimal_answer(questions, answer_schema), separators=(",", ":"))
    return count_tokens(text)


# --- Non-answers and usage -----------------------------------------------------------------


def non_answers(
    questions: Mapping[str, Question], cause: NonAnswerCause, detail: str | None
) -> dict[str, Answer]:
    return {qid: NonAnswer(cause=cause, detail=detail) for qid in questions}


def _http_error_cause(exc: HttpError) -> NonAnswerCause:
    """A 429 is rate limiting whatever its message says; a content filter is told by its error
    code, or failing that by "content filter" in the message."""
    if exc.status == 429:
        return "rate_limited"
    body = exc.body if isinstance(exc.body, str) else json.dumps(exc.body, default=str)
    if _error_code(exc.body) in FILTER_CODES or _FILTER_MESSAGE.search(body):
        return "filtered"
    return "error"


def _error_code(body: Any) -> str | None:
    error = body.get("error") if isinstance(body, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    return code if isinstance(code, str) else None


def _short(body: Any, limit: int = 300) -> str:
    text = body if isinstance(body, str) else repr(body)
    return text if len(text) <= limit else text[:limit] + "..."


def _incomplete_reason(body: dict[str, Any]) -> str:
    details = body.get("incomplete_details")
    if isinstance(details, dict) and details.get("reason"):
        return str(details["reason"])
    return json.dumps(details, default=str) if details else "incomplete"


def _error_message(body: dict[str, Any]) -> str:
    error = body.get("error")
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])
    return _short(error) if error else "no error detail"


def _message_parts(body: dict[str, Any]) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    for item in body.get("output") or []:
        if isinstance(item, dict) and item.get("type") == "message":
            parts.extend(part for part in item.get("content") or [] if isinstance(part, dict))
    return parts


def usage_from_body(body: Any) -> Usage:
    usage = body.get("usage") if isinstance(body, dict) else None
    if not isinstance(usage, dict):
        return Usage()
    output_details = usage.get("output_tokens_details") or {}
    input_details = usage.get("input_tokens_details") or {}
    return Usage(
        input_tokens=_count(usage.get("input_tokens")),
        output_tokens=_count(usage.get("output_tokens")),
        reasoning_tokens=_count(output_details.get("reasoning_tokens")),
        cached_tokens=_count(input_details.get("cached_tokens")),
    )


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def sum_usage(samples: list[_Sample]) -> Usage:
    totals: dict[str, int | None] = {}
    for name in Usage.model_fields:
        values = [getattr(sample.usage, name) for sample in samples]
        known = [value for value in values if value is not None]
        totals[name] = sum(known) if known else None
    return Usage(**totals)


# --- Samples: averaging k independent distributions ----------------------------------------


def average_answers(answers: list[Answer], question: Question) -> Answer:
    """The mean distribution over samples; any Non-answer among them wins (the batch is
    incomplete)."""
    if len(answers) == 1:
        return answers[0]
    for answer in answers:
        if isinstance(answer, NonAnswer):
            return answer
    match question:
        case NoulQuestion():
            nouls = [answer.noul for answer in answers if isinstance(answer, NoulAnswer)]
            return NoulAnswer(noul=fmean(nouls))
        case ChoiceQuestion():
            return choice_answer(_mean_distribution(answers, list(question.criteria)))
        case ScoreQuestion():
            legend = legend_for(question)
            return score_answer(_mean_distribution(answers, list(legend)), legend)
        case _:
            return NonAnswer(cause="invalid_output", detail="unsupported question type")


def _mean_distribution(answers: list[Answer], keys: list[str]) -> dict[str, float]:
    distributions = [a.probabilities for a in answers if isinstance(a, ChoiceAnswer | ScoreAnswer)]
    return {key: fmean(d.get(key, 0.0) for d in distributions) for key in keys}


__all__ = [
    "FILTER_CODES",
    "TOP_LOGPROBS",
    "OwnBuildConfig",
    "OwnBuildEngine",
    "average_answers",
    "minimal_output_tokens",
    "non_answers",
    "sum_usage",
    "usage_from_body",
    "wire_model_id",
]
