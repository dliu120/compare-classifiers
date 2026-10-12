"""Public benchmark loaders from the HF Hub: BANKING77, When2Call, CLINC150 plus out-of-scope.

Repo ids, splits and licenses were read from the Hub on 2026-10-06. Downloads go through the
``datasets`` package and are cached under ``<data_dir>/_cache``. Every loader takes an
injectable ``fetch`` so tests run against an in-memory table.
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

from bakeoff.datasets.case import Case, Reference
from bakeoff.datasets.family import FamilyManifest
from bakeoff.datasets.tokens import count_tokens, state_text
from bakeoff.systemone import ChoiceQuestion, Json

CACHE_DIR_NAME = "_cache"
LICENSE_READ_ON = "2026-10-06"


@dataclass(frozen=True, slots=True)
class PublicDataset:
    family: str
    repo: str
    config: str
    split: str
    license: str
    reference_kind: Literal["gold", "silver"]
    notes: str | None = None

    @property
    def source(self) -> str:
        return f"hf:{self.repo} ({self.config}/{self.split})"


@dataclass(frozen=True, slots=True)
class Table:
    """Rows of one split with ClassLabel columns decoded to names, plus every label list."""

    rows: list[dict[str, Any]]
    labels: dict[str, list[str]] = field(default_factory=dict)


Fetch = Callable[[PublicDataset, Path], Table]

BANKING77 = PublicDataset(
    "banking77",
    "legacy-datasets/banking77",
    "default",
    "test",
    "cc-by-4.0",
    "gold",
    notes=f"License read from the HF dataset card on {LICENSE_READ_ON}. "
    "Option names are the dataset's 77 intent labels verbatim.",
)
WHEN2CALL = PublicDataset(
    "when2call",
    "nvidia/When2Call",
    "test",
    "mcq",
    "cc-by-4.0",
    "silver",
    notes=f"License read from the HF dataset card on {LICENSE_READ_ON}. Labels are "
    "model-generated, so references are Silver. The mcq test split has no 'direct' gold "
    "labels (cannot_answer 1295, tool_call 1295, request_for_info 1062 of 3652).",
)
CLINC150 = PublicDataset(
    "clinc150",
    "clinc/clinc_oos",
    "plus",
    "test",
    "cc-by-3.0",
    "gold",
    notes=f"License read from the HF dataset card on {LICENSE_READ_ON}. "
    "151 options: the 150 intents plus 'oos' (out of scope).",
)
DATASETS: dict[str, PublicDataset] = {d.family: d for d in (BANKING77, WHEN2CALL, CLINC150)}

BANKING77_INSTRUCTIONS = "Which banking intent does this customer message express?"
CLINC150_INSTRUCTIONS = (
    "Which intent does this request express? Choose 'oos' when it matches none of the others."
)
CLINC_OOS = "oos"
CLINC_OOS_DESCRIPTION = "Out of scope: the request matches none of the other intents"
WHEN2CALL_INSTRUCTIONS = (
    "Given the user's question and the available tools, which kind of response should the "
    "assistant give?"
)
WHEN2CALL_OPTIONS: dict[str, Json | None] = {
    "direct": "Answer the user directly from the assistant's own knowledge, without any tool",
    "tool_call": "Call one of the available tools; the question supplies every required argument",
    "request_for_info": "Ask the user for the information a tool still needs before calling it",
    "cannot_answer": "No available tool can fulfil the request and it cannot be answered directly",
}


def cache_dir(data_dir: Path) -> Path:
    return data_dir / CACHE_DIR_NAME


def fetch_table(spec: PublicDataset, cache: Path) -> Table:
    """Download one split through the ``datasets`` package, caching under ``cache``."""
    import datasets as hf  # slow to import and only needed online

    cache.mkdir(parents=True, exist_ok=True)
    (cache / ".gitignore").write_text("*\n", encoding="utf-8")
    split = hf.load_dataset(spec.repo, spec.config, split=spec.split, cache_dir=str(cache))
    labels = {
        name: list(feature.names)
        for name, feature in split.features.items()
        if isinstance(feature, hf.ClassLabel)
    }
    rows = []
    for row in split:
        decoded = dict(row)
        for column, names in labels.items():
            decoded[column] = names[row[column]]
        rows.append(decoded)
    return Table(rows, labels)


def sample_rows[T](rows: Sequence[T], limit: int | None, seed: int) -> list[tuple[int, T]]:
    """A deterministic sample of (source index, row), kept in source order."""
    indices: Sequence[int] = range(len(rows))
    if limit is not None and limit < len(rows):
        indices = sorted(random.Random(seed).sample(indices, limit))
    return [(index, rows[index]) for index in indices]


def load_banking77(
    data_dir: Path, limit: int | None = None, seed: int = 0, *, fetch: Fetch = fetch_table
) -> list[Case]:
    table = fetch(BANKING77, cache_dir(data_dir))
    criteria: dict[str, Json | None] = dict.fromkeys(table.labels["label"])
    return [
        _choice_case(
            BANKING77,
            index,
            state=row["text"],
            question_id="intent",
            instructions=BANKING77_INSTRUCTIONS,
            criteria=criteria,
            answer=row["label"],
        )
        for index, row in sample_rows(table.rows, limit, seed)
    ]


def load_when2call(
    data_dir: Path, limit: int | None = None, seed: int = 0, *, fetch: Fetch = fetch_table
) -> list[Case]:
    table = fetch(WHEN2CALL, cache_dir(data_dir))
    cases = []
    for index, row in sample_rows(table.rows, limit, seed):
        state = {"question": row["question"], "tools": [_parse_tool(t) for t in row["tools"]]}
        meta = {key: row.get(key) for key in ("uuid", "source", "source_id", "target_tool")}
        cases.append(
            _choice_case(
                WHEN2CALL,
                index,
                state=state,
                question_id="response_type",
                instructions=WHEN2CALL_INSTRUCTIONS,
                criteria=WHEN2CALL_OPTIONS,
                answer=row["correct_answer"],
                meta=meta,
            )
        )
    return cases


def load_clinc150(
    data_dir: Path, limit: int | None = None, seed: int = 0, *, fetch: Fetch = fetch_table
) -> list[Case]:
    table = fetch(CLINC150, cache_dir(data_dir))
    criteria: dict[str, Json | None] = {
        name: CLINC_OOS_DESCRIPTION if name == CLINC_OOS else None
        for name in table.labels["intent"]
    }
    return [
        _choice_case(
            CLINC150,
            index,
            state=row["text"],
            question_id="intent",
            instructions=CLINC150_INSTRUCTIONS,
            criteria=criteria,
            answer=row["intent"],
        )
        for index, row in sample_rows(table.rows, limit, seed)
    ]


Loader = Callable[..., list[Case]]
LOADERS: dict[str, Loader] = {
    "banking77": load_banking77,
    "when2call": load_when2call,
    "clinc150": load_clinc150,
}


def manifest(family: str, created: date) -> FamilyManifest:
    spec = DATASETS[family]
    return FamilyManifest(
        name=spec.family,
        track="text",
        source=spec.source,
        license=spec.license,
        reference_kind=spec.reference_kind,
        generated_by=f"bakeoff.datasets.public.load_{family}",
        created=created,
        notes=spec.notes,
    )


def _parse_tool(text: Any) -> Json:
    if not isinstance(text, str):
        return text
    try:
        return json.loads(text)
    except ValueError:
        return text


def _choice_case(
    spec: PublicDataset,
    index: int,
    *,
    state: Json,
    question_id: str,
    instructions: str,
    criteria: dict[str, Json | None],
    answer: str,
    meta: dict[str, Any] | None = None,
) -> Case:
    if answer not in criteria:
        raise ValueError(f"{spec.family} row {index}: label {answer!r} is not an option")
    return Case(
        id=f"{spec.family}-{index:05d}",
        family=spec.family,
        track="text",
        state=state,
        questions={question_id: ChoiceQuestion(instructions=instructions, criteria=criteria)},
        reference={
            question_id: Reference(kind=spec.reference_kind, choice=answer, source=spec.source)
        },
        meta={"source_index": index, **(meta or {})},
        approx_tokens=count_tokens(state_text(state)),
    )
