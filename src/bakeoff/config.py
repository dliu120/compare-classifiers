"""Settings from the environment and ``.env``. Keys never leave this process."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

USE_JEV_KEY_FILE = (
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    / "agent-skills"
    / "use-jev"
    / "api-key"
)


class Settings(BaseModel):
    typesafe_api_key: str | None = None
    openai_api_key: str | None = None
    cloudflare_account_id: str | None = None
    cloudflare_auth_token: str | None = None
    liquid_api_key: str | None = None
    foundry_endpoint: str | None = None
    foundry_access_token: str | None = None
    foundry_deployment_name: str = "decision-1"
    foundry_requests_per_minute: int = Field(default=30, ge=1)
    aiproxy_base_url: str = "http://127.0.0.1:17688/v1"
    openai_base_url: str = "https://api.openai.com/v1"
    budget_usd: float = 50.0
    data_dir: Path = Path("data")
    runs_dir: Path = Path("runs")

    def has(self, provider_family: str) -> bool:
        """True when the credentials for a provider family are present (not validated)."""
        return {
            "jev": self.typesafe_api_key is not None,
            "openai-decisions": self.openai_api_key is not None,
            "cloudflare": self.cloudflare_account_id is not None
            and self.cloudflare_auth_token is not None,
            "liquid": self.liquid_api_key is not None,
            "foundry": bool(self.foundry_endpoint and self.foundry_access_token),
            "ownbuild": True,  # Copilot needs no key; the OpenAI route checks its own key
        }.get(provider_family, False)


def _read_use_jev_key() -> str | None:
    try:
        text = USE_JEV_KEY_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def load_settings(env_file: str | os.PathLike[str] | None = ".env") -> Settings:
    if env_file is not None:
        load_dotenv(env_file, override=False)
    env = os.environ
    return Settings(
        typesafe_api_key=env.get("TYPESAFE_API_KEY") or _read_use_jev_key(),
        openai_api_key=env.get("OPENAI_API_KEY") or None,
        cloudflare_account_id=env.get("CLOUDFLARE_ACCOUNT_ID") or None,
        cloudflare_auth_token=env.get("CLOUDFLARE_AUTH_TOKEN") or None,
        liquid_api_key=env.get("LIQUID_API_KEY") or None,
        foundry_endpoint=(env.get("FOUNDRY_ENDPOINT") or "").rstrip("/") or None,
        foundry_access_token=env.get("FOUNDRY_ACCESS_TOKEN") or None,
        foundry_deployment_name=env.get("FOUNDRY_DEPLOYMENT_NAME", "decision-1"),
        foundry_requests_per_minute=int(env.get("FOUNDRY_REQUESTS_PER_MINUTE", "30")),
        aiproxy_base_url=env.get("AIPROXY_BASE_URL", "http://127.0.0.1:17688/v1").rstrip("/"),
        openai_base_url=env.get("OPENAI_BASE_URL_DIRECT", "https://api.openai.com/v1").rstrip("/"),
        budget_usd=float(env.get("BAKEOFF_BUDGET_USD", "50")),
        data_dir=Path(env.get("BAKEOFF_DATA_DIR", "data")),
        runs_dir=Path(env.get("BAKEOFF_RUNS_DIR", "runs")),
    )
