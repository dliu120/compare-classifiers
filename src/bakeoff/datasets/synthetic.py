"""Synthetic support-ticket routing Cases: one model authors and labels, a second answers blind.

Only tickets where both models pick the same department survive; references are Silver. The
``Generator`` is injectable: a coroutine that takes a Responses API request body and returns
the parsed JSON object the model produced, so tests run offline against a fake.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict

from bakeoff.config import Settings
from bakeoff.datasets.case import Case, Reference
from bakeoff.datasets.family import FamilyManifest
from bakeoff.datasets.tokens import count_tokens
from bakeoff.http import post_json
from bakeoff.systemone import ChoiceQuestion, NoulQuestion, Question, ScoreQuestion

log = logging.getLogger(__name__)

Generator = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

FAMILY = "routing-synthetic"
AUTHOR_MODEL = "github-copilot/claude-sonnet-5.5"
JUDGE_MODEL = "github-copilot/gpt-5.4-mini"
BATCH_SIZE = 10
AUTHOR_MAX_OUTPUT_TOKENS = 4000
JUDGE_MAX_OUTPUT_TOKENS = 4000

DEPARTMENTS: dict[str, str] = {
    "billing": "Charges, invoices, refunds, payment methods, subscription renewals",
    "technical": "Bugs, errors, outages, login failures, device and integration problems",
    "sales": "Pricing, plans, upgrades, quotes, trials, pre-purchase questions",
    "shipping": "Delivery status, lost or damaged packages, address changes, return logistics",
    "other": "Anything that fits none of the other departments",
}
FRUSTRATION_LABELS = ["calm", "frustrated", "angry"]
FRUSTRATION_LEVELS = [
    "Calm: states the problem neutrally",
    "Frustrated: annoyed but civil",
    "Angry: hostile, insulting, or threatening to leave",
]
URGENT_DEFINITION = "true when the customer needs a response within hours rather than days"

QUESTIONS: dict[str, Question] = {
    "department": ChoiceQuestion(
        instructions="Which department should handle this support ticket?",
        criteria=dict(DEPARTMENTS),
    ),
    "is_urgent": NoulQuestion(
        instructions="Does the customer need a response within hours rather than days?"
    ),
    "frustration": ScoreQuestion(
        instructions="How frustrated does the customer appear?", criteria=list(FRUSTRATION_LEVELS)
    ),
}

THEMES = [
    "small business owners",
    "first-time buyers",
    "long-time customers",
    "IT administrators at mid-size companies",
    "non-native English speakers",
    "customers writing from their phones",
    "procurement and finance staff",
    "hobbyists and home users",
]

Department = Literal["billing", "technical", "sales", "shipping", "other"]
Frustration = Literal["calm", "frustrated", "angry"]


class Labels(BaseModel):
    model_config = ConfigDict(extra="ignore")
    department: Department
    is_urgent: bool
    frustration: Frustration


class AuthoredCase(Labels):
    state: str


class AuthoredBatch(BaseModel):
    model_config = ConfigDict(extra="ignore")
    cases: list[AuthoredCase]


class Verdict(Labels):
    index: int


class JudgedBatch(BaseModel):
    model_config = ConfigDict(extra="ignore")
    answers: list[Verdict]


@dataclass
class SyntheticResult:
    cases: list[Case] = field(default_factory=list)
    batches: int = 0
    failures: int = 0
    authored: int = 0
    unjudged: int = 0
    disagreed: int = 0
    duplicates: int = 0


def _object_schema(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(properties),
    }


LABEL_PROPERTIES: dict[str, Any] = {
    "department": {"type": "string", "enum": list(DEPARTMENTS)},
    "is_urgent": {"type": "boolean"},
    "frustration": {"type": "string", "enum": list(FRUSTRATION_LABELS)},
}
_AUTHORED_ITEM = _object_schema({"state": {"type": "string"}, **LABEL_PROPERTIES})
_VERDICT_ITEM = _object_schema({"index": {"type": "integer"}, **LABEL_PROPERTIES})
AUTHOR_SCHEMA = _object_schema({"cases": {"type": "array", "items": _AUTHORED_ITEM}})
JUDGE_SCHEMA = _object_schema({"answers": {"type": "array", "items": _VERDICT_ITEM}})


def _definitions() -> str:
    departments = "; ".join(f"{name}: {text}" for name, text in DEPARTMENTS.items())
    levels = ", ".join(
        f"{label} ({level.split(': ', 1)[1]})"
        for label, level in zip(FRUSTRATION_LABELS, FRUSTRATION_LEVELS, strict=True)
    )
    return f"- department: {departments}\n- is_urgent: {URGENT_DEFINITION}\n- frustration: {levels}"


def author_prompt(batch: int, batches: int, count: int) -> str:
    per_department = max(1, count // len(DEPARTMENTS))
    theme = THEMES[batch % len(THEMES)]
    return (
        "You write realistic customer support tickets for Lumen Labs, a company that sells a "
        "subscription software product (Starter, Team and Business plans) together with "
        "physical hardware add-ons that ship by courier, so billing, technical, sales, shipping "
        "and other tickets all occur.\n\n"
        f"Write exactly {count} tickets as the customers would type them: one to six sentences "
        "each, varied tone and length, concrete details (order numbers, product names, dates, "
        "error codes), and no two tickets about the same situation. This is batch "
        f"{batch + 1} of {batches}; the customers in this batch are {theme}.\n\n"
        f"Include exactly {per_department} tickets for each department.\n\n"
        f"Label every ticket yourself:\n{_definitions()}\n\n"
        "Respond with only a JSON object, no prose and no code fences, in exactly this shape:\n"
        '{"cases": [{"state": "<ticket text>", "department": "<billing|technical|sales|'
        'shipping|other>", "is_urgent": <true|false>, "frustration": "<calm|frustrated|angry>"}]}'
    )


def judge_prompt(states: list[str]) -> str:
    listing = "\n".join(f"{i}. {state}" for i, state in enumerate(states, start=1))
    return (
        "Classify each customer support ticket below, sent to Lumen Labs (subscription software "
        "with hardware add-ons shipped by courier). Judge every ticket on its own.\n\n"
        f"Definitions:\n{_definitions()}\n\n"
        f"Tickets:\n{listing}\n\n"
        "Respond with only a JSON object, no prose and no code fences, in exactly this shape, "
        "with one answer per ticket in order:\n"
        '{"answers": [{"index": 1, "department": "<billing|technical|sales|shipping|other>", '
        '"is_urgent": <true|false>, "frustration": "<calm|frustrated|angry>"}]}'
    )


def request_body(
    model: str, prompt: str, schema_name: str, schema: dict[str, Any], cap: int
) -> dict:
    return {
        "model": model,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
        "max_output_tokens": cap,
        "text": {
            "format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}
        },
    }


def author_request(batch: int, batches: int, count: int, model: str = AUTHOR_MODEL) -> dict:
    prompt = author_prompt(batch, batches, count)
    return request_body(model, prompt, "routing_batch", AUTHOR_SCHEMA, AUTHOR_MAX_OUTPUT_TOKENS)


def judge_request(states: list[str], model: str = JUDGE_MODEL) -> dict:
    prompt = judge_prompt(states)
    return request_body(model, prompt, "routing_answers", JUDGE_SCHEMA, JUDGE_MAX_OUTPUT_TOKENS)


_FENCE = re.compile(r"^\s*```[a-zA-Z0-9]*\s*|\s*```\s*$")


def parse_json_object(text: str) -> dict[str, Any]:
    """The JSON object in a model's text, tolerating code fences and surrounding prose."""
    stripped = _FENCE.sub("", text).strip()
    try:
        parsed = json.loads(stripped)
    except ValueError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start < 0 or end <= start:
            raise ValueError(f"no JSON object in model output: {stripped[:120]!r}") from None
        parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, dict):
        raise TypeError("model output is not a JSON object")
    return parsed


def output_text(response: dict[str, Any]) -> str:
    """The text of a Responses API reply; raises when it is incomplete, a refusal, or empty."""
    if response.get("status") == "incomplete":
        raise ValueError(f"incomplete response: {response.get('incomplete_details')}")
    texts = []
    for item in response.get("output") or []:
        for part in item.get("content") or []:
            if part.get("type") == "refusal":
                raise ValueError(f"refusal: {part.get('refusal')}")
            if part.get("type") == "output_text":
                texts.append(part.get("text") or "")
    text = "".join(texts) or response.get("output_text") or ""
    if not text:
        raise ValueError("empty model output")
    return text


def aiproxy_generator(settings: Settings, client: httpx.AsyncClient) -> Generator:
    """A Generator over the local aiproxy's OpenAI-compatible Responses API (no auth)."""
    url = f"{settings.aiproxy_base_url}/responses"

    async def generate(body: dict[str, Any]) -> dict[str, Any]:
        result = await post_json(client, url, json=body)
        return parse_json_object(output_text(result.data))

    return generate


def normalize_state(text: str) -> str:
    """Casefolded letters only, single-spaced: digits and punctuation do not distinguish tickets."""
    return " ".join(re.sub(r"[^a-z]+", " ", text.casefold()).split())


async def generate_routing_cases(
    generate: Generator,
    *,
    target: int,
    max_batches: int,
    batch_size: int = BATCH_SIZE,
    author_model: str = AUTHOR_MODEL,
    judge_model: str = JUDGE_MODEL,
    family: str = FAMILY,
) -> SyntheticResult:
    """Author batches, judge them blind, and keep up to ``target`` agreed, distinct Cases."""
    result = SyntheticResult()
    seen: set[str] = set()
    for batch in range(max_batches):
        if len(result.cases) >= target:
            break
        result.batches += 1
        try:
            authored = AuthoredBatch.model_validate(
                await generate(author_request(batch, max_batches, batch_size, author_model))
            )
            states = [item.state for item in authored.cases]
            judged = JudgedBatch.model_validate(await generate(judge_request(states, judge_model)))
        except Exception as exc:  # noqa: BLE001 - a bad batch is counted, never fatal
            log.warning("synthetic batch %d failed: %s: %s", batch, type(exc).__name__, exc)
            result.failures += 1
            if result.authored == 0:
                break  # nothing has worked yet: the generator is most likely down
            continue
        result.authored += len(authored.cases)
        verdicts = {verdict.index: verdict for verdict in judged.answers}
        for position, item in enumerate(authored.cases, start=1):
            verdict = verdicts.get(position)
            if verdict is None:
                result.unjudged += 1
                continue
            if verdict.department != item.department:
                result.disagreed += 1
                continue
            key = normalize_state(item.state)
            if key in seen:
                result.duplicates += 1
                continue
            seen.add(key)
            index = len(result.cases)
            result.cases.append(make_case(family, index, item, verdict, author_model, judge_model))
            if len(result.cases) >= target:
                break
    return result


def make_case(
    family: str,
    index: int,
    item: AuthoredCase,
    verdict: Labels,
    author_model: str,
    judge_model: str,
) -> Case:
    return Case(
        id=f"{family}-{index:03d}",
        family=family,
        track="text",
        state=item.state,
        questions=QUESTIONS,
        reference={
            "department": Reference(
                kind="silver",
                choice=item.department,
                source=f"{author_model}, agreed by {judge_model}",
            ),
            "is_urgent": Reference(kind="silver", noul=item.is_urgent, source=author_model),
            "frustration": Reference(
                kind="silver", score=FRUSTRATION_LABELS.index(item.frustration), source=author_model
            ),
        },
        meta={"judge": verdict.model_dump(include={"department", "is_urgent", "frustration"})},
        approx_tokens=count_tokens(item.state),
    )


def manifest(
    created: date,
    *,
    author_model: str = AUTHOR_MODEL,
    judge_model: str = JUDGE_MODEL,
    family: str = FAMILY,
    notes: str | None = None,
) -> FamilyManifest:
    return FamilyManifest(
        name=family,
        track="text",
        source="synthetic: tickets authored by a model through the local aiproxy",
        license="synthetic; generated by this project, no third-party content",
        reference_kind="silver",
        generated_by=f"author={author_model}; judge={judge_model}",
        created=created,
        notes=notes,
    )
