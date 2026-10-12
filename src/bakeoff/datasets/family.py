"""Family manifest: ``family.json`` beside ``cases.jsonl``."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from bakeoff.datasets.case import Case, family_dir, write_cases

MANIFEST_NAME = "family.json"
CASES_NAME = "cases.jsonl"


class FamilyManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    track: Literal["text", "image"]
    source: str
    license: str
    reference_kind: Literal["gold", "silver"]
    generated_by: str | None = None
    created: date  # passed in by the caller; library code never reads the clock
    notes: str | None = None


def manifest_path(directory: Path) -> Path:
    return directory / MANIFEST_NAME


def write_manifest(manifest: FamilyManifest, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = manifest_path(directory)
    text = json.dumps(manifest.model_dump(mode="json"), indent=2, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")
    return path


def read_manifest(directory: Path) -> FamilyManifest:
    return FamilyManifest.model_validate_json(manifest_path(directory).read_text(encoding="utf-8"))


def write_family(data_dir: Path, manifest: FamilyManifest, cases: Iterable[Case]) -> Path:
    """Write ``cases.jsonl`` and ``family.json`` under ``<data_dir>/<name>``; returns that
    directory."""
    cases = list(cases)
    foreign = sorted({case.family for case in cases if case.family != manifest.name})
    if foreign:
        raise ValueError(f"family {manifest.name!r} got cases of {foreign}")
    directory = family_dir(data_dir, manifest.name)
    write_cases(cases, directory / CASES_NAME)
    write_manifest(manifest, directory)
    return directory
