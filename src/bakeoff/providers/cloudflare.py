"""Cloudflare Workers AI Clef and Clef-flash: System One inside the Workers AI REST envelope.

Facts (developers.cloudflare.com, read 2026-10-06): images as a top-level list of data URLs
(max 4, PNG/JPEG/WebP, 4 MiB and 16 MP each, 8 MiB total decoded); 65,536-token context, and a
State past it is SILENTLY truncated (docs/adr/0003); the body is normally
``{"result": <System One response>, "success": true, "errors": [], "messages": []}``;
$0.24 (clef) and $0.09 (clef-flash) per M input, output free. Whether the result echoes a
top-level ``model`` is unverified; the Provider's model stands in when it is absent.
"""

from __future__ import annotations

from typing import Any

import httpx

from bakeoff.config import Settings
from bakeoff.providers.base import Provider
from bakeoff.providers.spec import require_credential, select_model
from bakeoff.providers.systemone_http import SystemOneProvider

URL_TEMPLATE = (
    "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/cloudflare/{model}"
)
ACCOUNT_ENV_VAR = "CLOUDFLARE_ACCOUNT_ID"
TOKEN_ENV_VAR = "CLOUDFLARE_AUTH_TOKEN"
MODELS = {"clef": "clef", "clef-flash": "clef-flash"}


class CloudflareProvider(SystemOneProvider):
    supports_images = True
    max_input_tokens = 65_536
    concurrency = 4

    def __init__(
        self,
        account_id: str,
        auth_token: str,
        model: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(auth_token, client=client)
        self.id = f"cloudflare/{model}"
        self.model = model
        self.price_key = model
        self.url = URL_TEMPLATE.format(account_id=account_id, model=model)

    def _unwrap(self, data: Any) -> Any:
        """Unwrap ``result`` when the envelope is present; otherwise the body is the response."""
        if isinstance(data, dict) and "success" in data:
            return data.get("result")
        return data


def build(spec: str, settings: Settings) -> Provider:
    model = select_model(spec, "cloudflare", MODELS)
    account_id = require_credential(settings.cloudflare_account_id, ACCOUNT_ENV_VAR, spec)
    auth_token = require_credential(settings.cloudflare_auth_token, TOKEN_ENV_VAR, spec)
    return CloudflareProvider(account_id, auth_token, model)


__all__ = [
    "ACCOUNT_ENV_VAR",
    "MODELS",
    "TOKEN_ENV_VAR",
    "URL_TEMPLATE",
    "CloudflareProvider",
    "build",
]
