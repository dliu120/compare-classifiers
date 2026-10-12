"""System One over HTTP: the base that Jev, Cloudflare and Liquid share.

POST a System One body with a Bearer token, validate the reply answer by answer, and turn
anything else into Non-answers (docs/adr/0003). Subclasses set the Provider attributes and
``url``; they override ``_body`` when the vendor wants images somewhere other than the
top-level list, and ``_unwrap`` when the vendor wraps the response in an envelope.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from bakeoff.http import HttpResult, elide_images, make_client, post_json
from bakeoff.providers.base import Provider, ProviderResult
from bakeoff.providers.transport import MAX_ATTEMPTS, transport_non_answer
from bakeoff.systemone import Answer, NonAnswer, SystemOneRequest, SystemOneResponse, Usage

_ANSWER = TypeAdapter(Answer)


class _Envelope(BaseModel):
    """A System One response with its answers left raw, so one bad answer spoils only itself."""

    model_config = ConfigDict(extra="ignore")
    model: str | None = None  # not every vendor echoes it; the Provider's model stands in
    answers: dict[str, Any]
    usage: Usage = Field(default_factory=Usage)


class SystemOneProvider(Provider):
    url: str = ""

    def __init__(self, api_key: str, *, client: httpx.AsyncClient | None = None) -> None:
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = client if client is not None else make_client()
        self._owns_client = client is None

    async def _call(self, request: SystemOneRequest) -> ProviderResult:
        body = self._body(request)
        request_raw = elide_images(body)
        started = time.perf_counter()
        try:
            sent = await post_json(
                self._client, self.url, json=body, headers=self._headers, max_attempts=MAX_ATTEMPTS
            )
        except httpx.TransportError as exc:
            return transport_non_answer(
                self, request, exc, latency_s=time.perf_counter() - started, request_raw=request_raw
            )
        return self._result(request, request_raw, sent)

    def _body(self, request: SystemOneRequest) -> dict[str, Any]:
        """The canonical System One body: images, if any, as a top-level list (docs/adr/0001)."""
        body: dict[str, Any] = {
            "model": self.model,
            "state": request.state,
            "questions": dump_questions(request),
        }
        if request.images:
            body["images"] = list(request.images)
        return body

    def _unwrap(self, data: Any) -> Any:
        """The System One response inside the vendor body. Default: the body itself."""
        return data

    def _result(
        self, request: SystemOneRequest, request_raw: Any, sent: HttpResult
    ) -> ProviderResult:
        try:
            envelope = _Envelope.model_validate(self._unwrap(sent.data))
        except ValidationError as exc:
            return self.non_answer(
                request,
                "invalid_output",
                f"not a System One response: {_first_error(exc)}",
                latency_s=sent.latency_s,
                http_status=sent.status,
                request_raw=request_raw,
                response_raw=sent.data,
                attempts=sent.attempts,
            )
        answers = {qid: _answer(envelope.answers.get(qid)) for qid in request.questions}
        response = SystemOneResponse(
            model=envelope.model or self.model, answers=answers, usage=envelope.usage
        )
        return ProviderResult(
            provider_id=self.id,
            response=response,
            http_status=sent.status,
            latency_s=sent.latency_s,
            attempts=sent.attempts,
            error=next((a.detail for a in answers.values() if isinstance(a, NonAnswer)), None),
            request_raw=request_raw,
            response_raw=sent.data,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def dump_questions(request: SystemOneRequest) -> dict[str, Any]:
    """The Questions as System One JSON, unchanged except that unset optional fields are omitted."""
    return {
        qid: question.model_dump(mode="json", exclude_none=True)
        for qid, question in request.questions.items()
    }


def _answer(raw: Any) -> Answer:
    if raw is None:
        return NonAnswer(cause="invalid_output", detail="no answer for this question")
    try:
        return _ANSWER.validate_python(raw)
    except ValidationError as exc:
        detail = f"not a System One answer: {_first_error(exc)}"
        return NonAnswer(cause="invalid_output", detail=detail)


def _first_error(exc: ValidationError) -> str:
    first = exc.errors()[0]
    where = ".".join(str(part) for part in first["loc"]) or "<body>"
    return f"{first['msg']} (at {where}; {exc.error_count()} error(s))"


__all__ = ["SystemOneProvider", "dump_questions"]
