"""Spec and credential checks shared by the vendor adapters' ``build`` functions."""

from __future__ import annotations

from bakeoff.providers import parse_spec


def select_model(spec: str, family: str, models: dict[str, str], default: str | None = None) -> str:
    """The model a spec names: the family alone means ``default``, one path segment picks from
    ``models`` (segment -> model id). Anything else is a ValueError."""
    found, path, query = parse_spec(spec)
    if found != family or query or len(path) > 1:
        raise ValueError(f"a {family} spec is {family}[/<model>] without a query: {spec!r}")
    if not path:
        if default is None:
            raise ValueError(f"{family} needs a model segment, one of {sorted(models)}: {spec!r}")
        return default
    if path[0] not in models:
        raise ValueError(f"unknown {family} model {path[0]!r}; known: {sorted(models)}")
    return models[path[0]]


def require_credential(value: str | None, env_var: str, spec: str) -> str:
    """The credential, or a ValueError naming the environment variable that must be set."""
    if not value:
        raise ValueError(f"{env_var} is not set; provider {spec!r} needs it")
    return value
