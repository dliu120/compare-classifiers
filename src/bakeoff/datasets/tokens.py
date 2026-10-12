"""Token counting with the harness's proxy tokenizer: tiktoken ``o200k_base``."""

from __future__ import annotations

import json
from functools import cache

import tiktoken

from bakeoff.systemone import Json

ENCODING_NAME = "o200k_base"


@cache
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding(ENCODING_NAME)


def encode(text: str) -> list[int]:
    """Token ids of ``text``; special-token strings count as ordinary text."""
    return _encoding().encode(text, disallowed_special=())


def count_tokens(text: str) -> int:
    return len(encode(text))


def state_text(state: Json) -> str:
    """A State as text: a string as it is, a dict or list as compact JSON."""
    if isinstance(state, str):
        return state
    return json.dumps(state, separators=(",", ":"), ensure_ascii=False)


def truncate_state(state: Json, max_tokens: int) -> tuple[Json, bool]:
    """Keep the first ``max_tokens`` tokens of the State's text; the bool says whether it cut.

    A structured State that is cut comes back as text, because the cut JSON is no longer valid.
    """
    text = state_text(state)
    tokens = encode(text)
    if len(tokens) <= max_tokens:
        return state, False
    head = _encoding().decode_bytes(tokens[: max(0, max_tokens)])
    return head.decode("utf-8", errors="ignore"), True
