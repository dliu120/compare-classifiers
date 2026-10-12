"""TypeSafe Jev: the System One contract at its source, text only.

Jev facts (docs.typesafe.ai, read 2026-10-06): text only; 64k-token context, 32k of it for the
State plus the longest Question; 80 requests/s; $0.042 per M input tokens, output free.
"""

from __future__ import annotations

from bakeoff.config import Settings
from bakeoff.providers import parse_spec
from bakeoff.providers.base import Provider
from bakeoff.providers.spec import require_credential
from bakeoff.providers.systemone_http import SystemOneProvider

URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.13.0"
ENV_VAR = "TYPESAFE_API_KEY"


class JevProvider(SystemOneProvider):
    id = "jev"
    model = MODEL
    supports_images = False
    max_input_tokens = 32_000  # the State's share of the 64k context; a ~32k State gets HTTP 400
    concurrency = 8
    price_key = MODEL
    url = URL


def build(spec: str, settings: Settings) -> Provider:
    family, path, query = parse_spec(spec)
    if family != "jev" or path or query:
        raise ValueError(f"jev has one model and takes no path or query: {spec!r}")
    return JevProvider(require_credential(settings.typesafe_api_key, ENV_VAR, spec))


__all__ = ["ENV_VAR", "MODEL", "URL", "JevProvider", "build"]
