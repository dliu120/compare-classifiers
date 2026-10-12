"""Case: one State, its Questions, and their reference Answers (Gold or Silver)."""

from __future__ import annotations

import base64
import json
import mimetypes
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bakeoff.systemone import Json, Question, SystemOneRequest


class Reference(BaseModel):
    """The reference Answer for one Question. Exactly one of noul/choice/score is set."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["gold", "silver"]
    noul: bool | None = None
    choice: str | None = None
    score: int | None = None  # level index
    source: str | None = None  # who or what produced it

    @model_validator(mode="after")
    def _exactly_one(self) -> Reference:
        if sum(value is not None for value in (self.noul, self.choice, self.score)) != 1:
            raise ValueError("a Reference sets exactly one of noul, choice, score")
        return self


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    family: str
    track: Literal["text", "image"]
    state: Json
    image_path: str | None = None  # relative to the family directory; canonical PNG/JPEG
    image_sha256: str | None = None
    questions: dict[str, Question]
    reference: dict[str, Reference]
    meta: dict[str, Any] = Field(default_factory=dict)
    approx_tokens: int | None = (
        None  # o200k_base count of the state as text; the harness's proxy tokenizer
    )

    @model_validator(mode="after")
    def _references_match_questions(self) -> Case:
        missing = set(self.questions) - set(self.reference)
        if missing:
            raise ValueError(f"case {self.id}: no reference for questions {sorted(missing)}")
        if self.track == "image" and not self.image_path:
            raise ValueError(f"case {self.id}: image track needs image_path")
        return self

    def image_data_url(self, family_dir: Path) -> str | None:
        if not self.image_path:
            return None
        path = family_dir / self.image_path
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"

    def to_request(self, model: str, family_dir: Path | None = None) -> SystemOneRequest:
        image = self.image_data_url(family_dir) if family_dir is not None else None
        return SystemOneRequest(
            model=model,
            state=self.state,
            questions=self.questions,
            images=[image] if image else None,
        )


def write_cases(cases: Iterable[Case], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for case in cases:
            handle.write(json.dumps(case.model_dump(mode="json"), ensure_ascii=False) + "\n")
            count += 1
    return count


def read_cases(path: Path) -> Iterator[Case]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield Case.model_validate_json(line)


def family_dir(data_dir: Path, family: str) -> Path:
    return data_dir / family


def load_family(data_dir: Path, family: str) -> list[Case]:
    """Cases of one Family live at ``<data_dir>/<family>/cases.jsonl`` with images beside it."""
    return list(read_cases(family_dir(data_dir, family) / "cases.jsonl"))
