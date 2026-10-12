"""Prompt for the Own build: a system message that defines the task in System One terms, and a
user message carrying the State, the optional image, and the Questions with their criteria.

The model answers under the schema's safe keys, so Questions and Options are rendered with
those keys (and the original name beside a key that had to be changed). A structured State is
rendered as compact JSON, the form ``bakeoff.datasets.tokens`` measures and ``max_in`` caps,
and the form the vendors receive on the wire.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from bakeoff.ownbuild.schema import AnswerSchema, compact_text
from bakeoff.systemone import ChoiceQuestion, Json, NoulQuestion, Question, ScoreQuestion

_PREAMBLE = (
    "You are a decision API. Each request carries one State and one or more named Questions "
    "about it. Return one Answer per Question, as JSON in the required schema, and nothing else."
)

_RULES = (
    "Rules:\n"
    "- Each Question's criteria are its rubric: the Option and Level descriptions define what "
    "each one means. Apply them as written.\n"
    "- Judge only from the State (its text, and its image when one is attached) and the "
    "Question. Do not assume facts the State does not contain.\n"
    "- Use exactly the Question keys and Option keys given in the request."
)

_TYPES_PROBABILITIES = (
    "Question types:\n"
    "- noul: a yes/no Question. Return the probability, between 0 and 1, that the answer "
    "is yes.\n"
    "- choice: select one of the named Options. Return a probability for every Option "
    "under its key; the probabilities must sum to 1.\n"
    "- score: rate the State on an ordered rubric of Levels, numbered from 0 (lowest) "
    "upward. Return a probability for every Level index; the probabilities must sum to 1."
)

_TYPES_DISCRETE = (
    "Question types:\n"
    "- noul: a yes/no Question. Return true or false.\n"
    "- choice: select exactly one of the named Options. Return its name.\n"
    "- score: rate the State on an ordered rubric of Levels, numbered from 0 (lowest) "
    "upward. Return the index of the one Level that fits best."
)

_CALIBRATION_RULE = (
    "- Probabilities are calibrated beliefs: concentrate them when the State is clear and "
    "spread them when it is ambiguous."
)
_SINGLE_ANSWER_RULE = "- Pick the single best answer even when the State is ambiguous."

SYSTEM_PROBABILITIES = "\n\n".join(
    [_PREAMBLE, _TYPES_PROBABILITIES, f"{_RULES}\n{_CALIBRATION_RULE}"]
)

SYSTEM_DISCRETE = "\n\n".join([_PREAMBLE, _TYPES_DISCRETE, f"{_RULES}\n{_SINGLE_ANSWER_RULE}"])


def system_message(*, discrete: bool) -> str:
    return SYSTEM_DISCRETE if discrete else SYSTEM_PROBABILITIES


def build_input(
    state: Json,
    images: list[str] | None,
    questions: Mapping[str, Question],
    answer_schema: AnswerSchema,
) -> list[dict[str, Any]]:
    """The Responses API ``input`` list: a system message and one user message."""
    state_text = render_state(state, bool(images))
    content: list[dict[str, Any]] = [{"type": "input_text", "text": state_text}]
    for url in images or []:
        content.append({"type": "input_image", "image_url": url})
    content.append({"type": "input_text", "text": render_questions(questions, answer_schema)})
    return [
        {"role": "system", "content": system_message(discrete=answer_schema.discrete)},
        {"role": "user", "content": content},
    ]


def render_state(state: Json, has_image: bool) -> str:
    lines = ["# State"]
    if has_image:
        lines.append("The attached image is part of the State.")
    lines.append(compact_text(state))
    return "\n\n".join(lines)


def render_questions(questions: Mapping[str, Question], answer_schema: AnswerSchema) -> str:
    blocks = ["# Questions"]
    for qid, question in questions.items():
        key = answer_schema.questions.to_safe[qid]
        blocks.append(_render_question(key, question, answer_schema.options.get(qid)))
    return "\n\n".join(blocks)


def _render_question(key: str, question: Question, option_keys) -> str:
    lines = [f'## Question "{key}" ({question.type})', compact_text(question.instructions)]
    match question:
        case NoulQuestion():
            if question.criteria:
                lines.append("Criteria:")
                for truth in ("true", "false"):
                    if truth in question.criteria:
                        lines.append(f"- {truth}: {compact_text(question.criteria[truth])}")
        case ChoiceQuestion():
            lines.append("Options:")
            for option, description in question.criteria.items():
                lines.append(_render_option(option, description, option_keys))
        case ScoreQuestion():
            lines.append("Levels, lowest first:")
            for index, level in enumerate(question.criteria):
                lines.append(f"- {index}: {compact_text(level)}")
    return "\n".join(lines)


def _render_option(option: str, description: Json | None, option_keys) -> str:
    key = option_keys.to_safe[option] if option_keys is not None else option
    label = key if key == option else f'{key} (Option "{option}")'
    if description is None:
        return f"- {label}"
    return f"- {label}: {compact_text(description)}"
