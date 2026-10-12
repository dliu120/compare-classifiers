"""The smoke slice: a small Family of every kind under one data directory.

Public families need the network, the synthetic family needs the local aiproxy; a family that
cannot be built is logged and skipped so the others still land. Longstate families are
regenerated from their seed and the HF cache is downloads, so neither is git-tracked.
"""

from __future__ import annotations

import asyncio
import logging
import math
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

from bakeoff.config import Settings
from bakeoff.datasets import longstate, public, rendered, synthetic
from bakeoff.datasets.case import family_dir
from bakeoff.datasets.family import write_family
from bakeoff.http import make_client

log = logging.getLogger(__name__)

PUBLIC_COUNT = 100
SYNTHETIC_COUNT = 40
SYNTHETIC_MAX_BATCHES = 5
LONGSTATE_PER_FAMILY = 6
RENDERED_COUNT = 40
SEED = 0
GITIGNORE = "_cache/\nlongstate-*/\n"


def build_smoke(
    data_dir: Path,
    settings: Settings,
    *,
    limit: int | None = None,
    created: date | None = None,
    fetch: public.Fetch = public.fetch_table,
    generate: synthetic.Generator | None = None,
) -> list[str]:
    """Write every smoke Family under ``data_dir``; ``limit`` caps each Family's size.

    Returns the names of the Families written, in order.
    """
    created = created or datetime.now(tz=UTC).astimezone().date()  # the local calendar date
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    written: list[str] = []
    for family in public.LOADERS:
        if _build_public(data_dir, family, _scaled(PUBLIC_COUNT, limit), created, fetch):
            written.append(family)
    if _build_synthetic(data_dir, settings, _scaled(SYNTHETIC_COUNT, limit), created, generate):
        written.append(synthetic.FAMILY)
    for family, target in longstate.TARGETS.items():
        count = _scaled(LONGSTATE_PER_FAMILY, limit)
        per_position = math.ceil(count / len(longstate.POSITIONS))
        cases = longstate.build_longstate_cases(
            target, family=family, per_position=per_position, seed=SEED
        )[:count]
        _replace(data_dir, family)
        write_family(data_dir, longstate.manifest(family, created, seed=SEED), cases)
        written.append(family)
    _replace(data_dir, rendered.FAMILY)
    cases = rendered.build_rendered_cases(
        family_dir(data_dir, rendered.FAMILY), count=_scaled(RENDERED_COUNT, limit), seed=SEED
    )
    write_family(data_dir, rendered.manifest(created, seed=SEED), cases)
    written.append(rendered.FAMILY)
    return written


def _scaled(count: int, limit: int | None) -> int:
    return count if limit is None else max(1, min(count, limit))


def _replace(data_dir: Path, family: str) -> None:
    shutil.rmtree(family_dir(data_dir, family), ignore_errors=True)


def _build_public(
    data_dir: Path, family: str, count: int, created: date, fetch: public.Fetch
) -> bool:
    try:
        cases = public.LOADERS[family](data_dir, count, SEED, fetch=fetch)
    except Exception as exc:  # noqa: BLE001 - a dataset that will not load must not sink the rest
        log.warning("skipping %s: %s: %s", family, type(exc).__name__, exc)
        return False
    _replace(data_dir, family)
    write_family(data_dir, public.manifest(family, created), cases)
    return True


def _build_synthetic(
    data_dir: Path,
    settings: Settings,
    count: int,
    created: date,
    generate: synthetic.Generator | None,
) -> bool:
    result = asyncio.run(_generate(settings, count, generate))
    if not result.cases:
        log.warning("skipping %s: no agreed cases (%s)", synthetic.FAMILY, result)
        return False
    if len(result.cases) < count:
        log.warning("%s: %d of %d cases (%s)", synthetic.FAMILY, len(result.cases), count, result)
    notes = (
        f"batches {result.batches}, failures {result.failures}, authored {result.authored}, "
        f"disagreed {result.disagreed}, duplicates {result.duplicates}, "
        f"unjudged {result.unjudged}"
    )
    _replace(data_dir, synthetic.FAMILY)
    write_family(data_dir, synthetic.manifest(created, notes=notes), result.cases)
    return True


async def _generate(
    settings: Settings, count: int, generate: synthetic.Generator | None
) -> synthetic.SyntheticResult:
    if generate is not None:
        return await synthetic.generate_routing_cases(
            generate, target=count, max_batches=SYNTHETIC_MAX_BATCHES
        )
    async with make_client() as client:
        return await synthetic.generate_routing_cases(
            synthetic.aiproxy_generator(settings, client),
            target=count,
            max_batches=SYNTHETIC_MAX_BATCHES,
        )
