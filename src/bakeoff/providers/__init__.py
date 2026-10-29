"""Provider registry.

A spec is ``<family>[/<path>...][?key=value&...]``:

    jev                         TypeSafe Jev (jev-1.13.0), text only
    cloudflare/clef|clef-flash  Cloudflare Workers AI Clef
    liquid/d1|d1.1|d1:free      Liquid d1 and d1.1
    openai-decisions            OpenAI Decisions API (gpt-6-luna)
    ownbuild/<route>/<model>    Own build; route is ``openai`` (direct) or ``copilot`` (aiproxy)
        ?effort=none|low|medium|high|xhigh|max&cap=512&max_in=64000
        &mode=probabilities|discrete|logprobs&samples=1&via=<http base of a running server>

Each module exposes ``build(spec: str, settings: Settings) -> Provider``.
"""

from __future__ import annotations

import importlib
from urllib.parse import parse_qsl

from bakeoff.config import Settings
from bakeoff.providers.base import Provider, ProviderResult

MODULES: dict[str, str] = {
    "jev": "bakeoff.providers.jev",
    "cloudflare": "bakeoff.providers.cloudflare",
    "liquid": "bakeoff.providers.liquid",
    "openai-decisions": "bakeoff.providers.openai_decisions",
    "foundry": "bakeoff.providers.foundry",
    "ownbuild": "bakeoff.providers.ownbuild",
}


def parse_spec(spec: str) -> tuple[str, list[str], dict[str, str]]:
    """Split ``family/a/b?k=v`` into (family, [a, b], {k: v})."""
    path, _, query = spec.partition("?")
    parts = [part for part in path.split("/") if part]
    if not parts:
        raise ValueError(f"empty provider spec: {spec!r}")
    return parts[0], parts[1:], dict(parse_qsl(query, keep_blank_values=True))


def make_provider(spec: str, settings: Settings) -> Provider:
    family, _, _ = parse_spec(spec)
    if family not in MODULES:
        raise ValueError(f"unknown provider family {family!r}; known: {sorted(MODULES)}")
    module = importlib.import_module(MODULES[family])
    return module.build(spec, settings)


__all__ = ["MODULES", "Provider", "ProviderResult", "make_provider", "parse_spec"]
