"""Live tests call real services and spend real money, so they run only when asked for twice:
the ``live`` marker (deselected by pyproject's addopts) and ``BAKEOFF_LIVE=1`` in the
environment, which an explicit ``-m`` on the command line cannot switch on by accident."""

from __future__ import annotations

import os

import pytest

ENV_VAR = "BAKEOFF_LIVE"


def require_live() -> None:
    if os.environ.get(ENV_VAR) != "1":
        pytest.skip(f"live tests run only with {ENV_VAR}=1")


def require_env(name: str) -> None:
    """A credential that must be set explicitly; file fallbacks such as the use-jev key do
    not count, so a live test never spends a key the operator did not hand it."""
    if not os.environ.get(name):
        pytest.skip(f"{name} is not set in the environment")
